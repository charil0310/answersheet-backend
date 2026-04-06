from extensions import db
from models.answer_sheet import AnswerSheet
from models.answer import Answer
from models.question import Question
from models.exam_structure import ExamStructure
from models.student import Student
from models.audit_log import AuditLog

from datetime import datetime
import json
import os
import shutil

from img_scan.img_scan.sheet_image.answer_sheet_grader import AnswerSheetGrader
from img_scan.img_scan.sheet_image.student_number import process_single_image
from img_scan.img_scan import predict
import cv2

class GradingService:

    CONFIDENCE_DEFAULT = 0.95  # 你的算法没返回confidence，用默认值

    @staticmethod
    def grade_sheet(sheet_id):

        sheet = AnswerSheet.query.get(sheet_id)
        if not sheet:
            return False, "答题卡不存在"

        try:
            # ==============================
            # 1️⃣ 状态 -> processing
            # ==============================
            sheet.status = "processing"
            db.session.commit()

            GradingService._log(sheet.id, None, "START_PROCESSING")

            image_path = sheet.raw_image_url
            if not os.path.exists(image_path):
                raise Exception("图片不存在")

            # ==============================
            # 2️⃣ 读取 exam_structure
            # ==============================
            structure = ExamStructure.query.filter_by(
                exam_id=sheet.exam_id
            ).first()

            if not structure:
                raise Exception("未配置考试结构")

            start_no = structure.start_question_no
            end_no = structure.end_question_no
            total_questions = end_no - start_no + 1

            # ==============================
            # 3️⃣ 识别学号
            # ==============================

            # 1 读取原图
            img = cv2.imread(image_path)
            if img is None:
                raise Exception("图片读取失败")

            # 2 透视矫正（使用predict）
            corrected_image = predict.correct_document(
                image_path=image_path,
                ckpt_path="img_scan/img_scan/lightning_logs/version_6/checkpoints/epoch=49-step=250.ckpt",
                save_result=False
            )

            # 兼容返回类型
            if isinstance(corrected_image, str):
                corrected_img = cv2.imread(corrected_image)
            else:
                corrected_img = corrected_image

            if corrected_img is None:
                raise Exception("答题卡矫正失败")

            # 3 学号识别
            student_no = process_single_image(
                corrected_img,
                show=False
            )
            # ① 没识别到学号
            if not student_no:
                sheet.status = "student_recognition_failed"
                db.session.commit()
                return False, "未识别到学号"

            # ② 识别到了但数据库没有
            student = Student.query.filter_by(
                student_no=student_no,
                class_id=sheet.class_id
            ).first()

            if not student:
                sheet.status = "student_not_found"
                db.session.commit()
                return False, f"学号未匹配: {student_no}"

            # ③ 正常
            # 检查是否已有答题卡
            existing = AnswerSheet.query.filter(
                AnswerSheet.exam_id == sheet.exam_id,
                AnswerSheet.student_id == student.id,
                AnswerSheet.id != sheet.id
            ).first()

            if existing:
                sheet.status = "needs_review"
                db.session.commit()
                return False, f"该学生已有答题卡 {student_no}"

            sheet.student_id = student.id
            db.session.commit()

            # ==============================
            # 4️⃣ 构造标准答案 answer_key（从 question 表读取）
            # ==============================
            questions = Question.query.filter(
                Question.exam_id == sheet.exam_id,
                Question.question_no >= start_no,
                Question.question_no <= end_no
            ).order_by(Question.question_no).all()

            if not questions:
                raise Exception("未配置题目")

            answer_key = {}
            for q in questions:
                # 核心修复：解析JSON字符串为算法期望的纯字符格式（如 ["A"] → "A"）
                try:
                    correct_answers = json.loads(q.correct_answer_json)
                    answer_key[q.question_no] = correct_answers[0] if correct_answers else ""
                except json.JSONDecodeError as e:
                    raise Exception(f"题目 {q.question_no} 答案格式错误: {str(e)}")

            # ==============================
            # 5️⃣ 调用真实答题卡评分算法
            # ==============================
            print("========== 判分参数 ==========")
            print("total_questions:", total_questions)
            print("answer_key:", answer_key)
            print("answer_key数量:", len(answer_key))
            for k, v in answer_key.items():
                print(f"题号 {k} -> 正确答案 {v}")
            print("================================")
            grader = AnswerSheetGrader({
                "total_questions": 120,
                "score_per_question": 4,
                "multi_select_score": 4,
                "partial_score": True,
                "debug_mode": False,
                "enable_rotation_correction": True
            })

            result = grader.grade_answer_sheet(
                image_path=image_path,
                answer_key=answer_key
            )

            if not result["success"]:
                raise Exception(result.get("error", "评分失败"))

            recognized_answers = result["answers"]
            print("识别题目数量:", len(recognized_answers))
            if len(recognized_answers) < total_questions * 0.5:
                raise Exception("识别题目数量异常，可能模板配置错误")
            
            Answer.query.filter_by(sheet_id=sheet.id).delete()
            db.session.commit()
            # ==============================
            # 6️⃣ 写入 Answer 表
            # ==============================
            total_score = 0
            correct_count = 0
            wrong_count = 0

            for q in questions:

                recognized = recognized_answers.get(q.question_no)

                if recognized is None:
                    wrong_count += 1
                    continue

                if isinstance(recognized, str):
                    try:
                        recognized = json.loads(recognized)
                    except:
                        recognized = [recognized]

                correct_answers = q.correct_answer_json

                if isinstance(correct_answers, str):
                    correct_answers = json.loads(correct_answers)

                correct_set = set(correct_answers)
                recognized_set = set(recognized)

                is_correct = correct_set == recognized_set

                if is_correct:
                    correct_count += 1
                    score_awarded = q.max_score
                else:
                    wrong_count += 1
                    score_awarded = 0

                total_score += score_awarded

                answer = Answer(
                    sheet_id=sheet.id,
                    question_no=q.question_no,
                    recognized_option_json=json.dumps(recognized),
                    is_correct=is_correct,
                    score_awarded=score_awarded,
                    confidence=GradingService.CONFIDENCE_DEFAULT
                )

                db.session.add(answer)

            # ==============================
            # 7️⃣ 更新答题卡
            # ==============================
            sheet.total_score = total_score
            sheet.correct_count = correct_count
            sheet.wrong_count = wrong_count
            sheet.scan_time = datetime.utcnow()
            sheet.status = "processed"

            db.session.commit()

            GradingService._log(
                sheet.id,
                None,
                "PROCESS_COMPLETED",
                None,
                f"score={total_score}"
            )

            return True, "阅卷完成"

        except Exception as e:

            sheet.status = "failed"
            db.session.commit()

            GradingService._log(
                sheet.id,
                None,
                "PROCESS_FAILED",
                None,
                str(e)
            )

            return False, str(e)

    # ==============================
    # 审计日志
    # ==============================
    @staticmethod
    def _log(sheet_id, answer_id, action, old=None, new=None):

        try:
            operator = None

            try:
                from flask_jwt_extended import get_jwt_identity
                operator = get_jwt_identity()
            except:
                pass

            log = AuditLog(
                sheet_id=sheet_id,
                answer_id=answer_id,
                operator_openid=str(operator) if operator else None,
                action=action,
                old_value=json.dumps(old, ensure_ascii=False) if old else None,
                new_value=json.dumps(new, ensure_ascii=False) if new else None
            )

            db.session.add(log)
            db.session.commit()

        except Exception as e:
            # 防止日志失败影响主业务
            db.session.rollback()