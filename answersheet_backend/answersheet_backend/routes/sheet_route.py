import os
import json
from datetime import datetime
import cv2
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models.answer_sheet import AnswerSheet
from models.answer import Answer
from models.exam import Exam
from models.student import Student
from models.question import Question
from models.audit_log import AuditLog
from services.grading_service import GradingService
from img_scan.img_scan.sheet_image.answer_sheet_grader import AnswerSheetGrader

sheet_bp = Blueprint("sheet", __name__)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ===========================
# 上传答题卡（单张）
# ===========================
@sheet_bp.route("/upload/<int:exam_id>", methods=["POST"])
@jwt_required()
def upload_sheet(exam_id):
    """
    上传答题卡（单张）
    ---
    tags:
      - AnswerSheet
    parameters:
      - name: exam_id
        in: path
        required: true
        type: integer
      - name: file
        in: formData
        required: true
        type: file
      - name: class_id
        in: formData
        required: false
        type: integer
        example: 1
    responses:
      200:
        description: 上传成功
      400:
        description: 未上传文件
      403:
        description: 无权限
      404:
        description: 考试不存在
    """
    teacher_id = int(get_jwt_identity())

    exam = Exam.query.get(exam_id)
    if not exam:
        return jsonify({"error": "考试不存在"}), 404

    if exam.teacher_id != teacher_id:
        return jsonify({"error": "无权限"}), 403

    file = request.files.get("file")
    if not file:
        return jsonify({"error": "未上传文件"}), 400

    # 生成唯一文件名
    filename = f"{exam_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    print("========== 上传图片信息 ==========")
    print("文件路径:", filepath)
    print("文件大小:", os.path.getsize(filepath))

    img = cv2.imread(filepath)

    if img is None:
        print("OpenCV 读取失败")
    else:
        print("图片尺寸:", img.shape)

    print("=================================")
    # 获取班级ID
    class_id = request.form.get("class_id", exam.class_id)

    sheet = AnswerSheet(
        exam_id=exam_id,
        class_id=class_id,
        raw_image_url=filepath,
        status="uploaded"
    )

    db.session.add(sheet)
    db.session.commit()

    # 触发自动评分
    success, msg = GradingService.grade_sheet(sheet.id)

    # 更新考试状态
    exam.status = "IN_PROGRESS" if exam.status == "CREATED" else exam.status
    db.session.commit()

    return jsonify({
        "success": success,
        "message": msg,
        "sheet_id": sheet.id
    })


# # ===========================
# # 批量上传答题卡
# # ===========================
# @sheet_bp.route("/upload/batch/<int:exam_id>", methods=["POST"])
# @jwt_required()
# def batch_upload_sheets(exam_id):
#     """
#     批量上传答题卡
#     ---
#     tags:
#       - AnswerSheet
#     parameters:
#       - name: exam_id
#         in: path
#         required: true
#         type: integer
#       - name: files
#         in: formData
#         required: true
#         type: array
#         items:
#           type: file
#       - name: class_id
#         in: formData
#         required: false
#         type: integer
#         example: 1
#     responses:
#       200:
#         description: 上传成功
#       400:
#         description: 未上传文件
#       403:
#         description: 无权限
#       404:
#         description: 考试不存在
#     """
#     teacher_id = int(get_jwt_identity())

#     exam = Exam.query.get(exam_id)
#     if not exam:
#         return jsonify({"error": "考试不存在"}), 404

#     if exam.teacher_id != teacher_id:
#         return jsonify({"error": "无权限"}), 403

#     files = request.files.getlist("files")
#     if not files:
#         return jsonify({"error": "未上传文件"}), 400

#     class_id = request.form.get("class_id", exam.class_id)
#     results = []

#     for file in files:
#         if file.filename == "":
#             continue

#         # 生成唯一文件名
#         filename = f"{exam_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
#         filepath = os.path.join(UPLOAD_FOLDER, filename)
#         file.save(filepath)

#         # 创建答题卡记录
#         sheet = AnswerSheet(
#             exam_id=exam_id,
#             class_id=class_id,
#             raw_image_url=filepath,
#             status="uploaded"
#         )
#         db.session.add(sheet)
#         db.session.commit()

#         # 触发自动评分
#         success, msg = GradingService.grade_sheet(sheet.id)
#         results.append({
#             "filename": file.filename,
#             "sheet_id": sheet.id,
#             "success": success,
#             "message": msg
#         })

#     # 更新考试状态
#     exam.status = "IN_PROGRESS" if exam.status == "CREATED" else exam.status
#     db.session.commit()

#     return jsonify({
#         "total": len(results),
#         "success_count": sum(1 for r in results if r["success"]),
#         "failed_count": sum(1 for r in results if not r["success"]),
#         "details": results
#     })


# ===========================
# 查看考试所有答题卡
# ===========================
@sheet_bp.route("/exam/<int:exam_id>", methods=["GET"])
@jwt_required()
def list_sheets(exam_id):
    """
    查看考试所有答题卡
    ---
    tags:
      - AnswerSheet
    parameters:
      - name: exam_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: 返回答题卡列表
      404:
        description: 考试不存在
    """
    teacher_id = int(get_jwt_identity())
    exam = Exam.query.filter_by(id=exam_id, teacher_id=teacher_id).first()
    if not exam:
        return jsonify({"error": "考试不存在或无权限"}), 404

    sheets = AnswerSheet.query.filter_by(exam_id=exam_id).all()

    result = []
    for s in sheets:
        student = Student.query.get(s.student_id) if s.student_id else None
        result.append({
            "sheet_id": s.id,
            "student_name": student.name if student else "",
            "student_no": student.student_no if student else "",
            "score": s.total_score,
            "correct_count": s.correct_count,
            "wrong_count": s.wrong_count,
            "status": s.status,
            "scan_time": s.scan_time.isoformat() if s.scan_time else None,
            "created_at": s.created_at.isoformat()
        })

    return jsonify(result)


# ===========================
# 查看单张答题卡详情
# ===========================
@sheet_bp.route("/<int:sheet_id>", methods=["GET"])
@jwt_required()
def sheet_detail(sheet_id):
    """
    查看单张答题卡详情
    ---
    tags:
      - AnswerSheet
    parameters:
      - name: sheet_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: 返回答题卡详情
      404:
        description: 答题卡不存在
    """
    sheet = AnswerSheet.query.get(sheet_id)
    if not sheet:
        return jsonify({"error": "答题卡不存在"}), 404

    # 验证权限
    exam = Exam.query.get(sheet.exam_id)
    if exam.teacher_id != int(get_jwt_identity()):
        return jsonify({"error": "无权限"}), 403

    answers = Answer.query.filter_by(sheet_id=sheet_id).all()
    answer_details = []

    for a in answers:
        question = Question.query.filter_by(
            exam_id=sheet.exam_id,
            question_no=a.question_no
        ).first()
        
        answer_details.append({
            "answer_id": a.id,
            "question_no": a.question_no,
            "question_type": question.question_type if question else "",
            "correct_answer": json.loads(question.correct_answer_json) if question else [],
            "recognized_option": a.recognized_option_json,
            "is_correct": a.is_correct,
            "score_awarded": a.score_awarded,
            "confidence": a.confidence
        })

    student = Student.query.get(sheet.student_id) if sheet.student_id else None
    return jsonify({
        "sheet_id": sheet.id,
        "exam_id": sheet.exam_id,
        "class_id": sheet.class_id,
        "student_info": {
            "id": student.id if student else None,
            "name": student.name if student else "",
            "student_no": student.student_no if student else ""
        },
        "total_score": sheet.total_score,
        "correct_count": sheet.correct_count,
        "wrong_count": sheet.wrong_count,
        "status": sheet.status,
        "scan_time": sheet.scan_time.isoformat() if sheet.scan_time else None,
        "raw_image_url": sheet.raw_image_url,
        "corrected_image_url": sheet.corrected_image_url,
        "result_image_url": sheet.result_image_url,
        "answers": answer_details,
        "created_at": sheet.created_at.isoformat(),
        "updated_at": sheet.updated_at.isoformat()
    })


# ===========================
# 编辑答题卡答案
# ===========================
@sheet_bp.route("/answer/<int:answer_id>", methods=["PUT"])
@jwt_required()
def edit_answer(answer_id):
    """
    编辑答题卡答案（复核）
    ---
    tags:
      - AnswerSheet
    parameters:
      - name: answer_id
        in: path
        required: true
        type: integer
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            recognized_option:
              type: array
              items:
                type: string
              example: ["B"]
            score_awarded:
              type: number
              example: 5
    responses:
      200:
        description: 编辑成功
      404:
        description: 答案不存在
    """
    answer = Answer.query.get(answer_id)
    if not answer:
        return jsonify({"error": "答案记录不存在"}), 404

    # 验证权限
    sheet = AnswerSheet.query.get(answer.sheet_id)
    exam = Exam.query.get(sheet.exam_id)
    if exam.teacher_id != int(get_jwt_identity()):
        return jsonify({"error": "无权限"}), 403

    data = request.json
    # 记录旧值
    old_value = {
        "recognized_option": answer.recognized_option_json,
        "is_correct": answer.is_correct,
        "score_awarded": answer.score_awarded
    }

    # 更新答案
    answer.recognized_option_json = data.get("recognized_option", answer.recognized_option_json)
    
    # 重新计算是否正确和得分
    question = Question.query.filter_by(
        exam_id=sheet.exam_id,
        question_no=answer.question_no
    ).first()
    
    if question:
        correct_answer = set(json.loads(question.correct_answer_json))
        recognized_answer = set(answer.recognized_option_json)
        is_correct = correct_answer == recognized_answer
        
        # 优先使用手动指定的得分，否则自动计算
        if "score_awarded" in data:
            score_awarded = data["score_awarded"]
        else:
            score_awarded = question.max_score if is_correct else 0
            
        answer.is_correct = is_correct
        answer.score_awarded = score_awarded

    # 记录新值
    new_value = {
        "recognized_option": answer.recognized_option_json,
        "is_correct": answer.is_correct,
        "score_awarded": answer.score_awarded
    }

    # 记录审计日志
    GradingService._log(
        sheet.id,
        answer.id,
        "EDIT_ANSWER",
        old_value,
        new_value
    )

    # 更新答题卡总分
    sheet = AnswerSheet.query.get(answer.sheet_id)
    answers = Answer.query.filter_by(sheet_id=sheet.id).all()
    sheet.total_score = sum(a.score_awarded or 0 for a in answers)
    sheet.correct_count = sum(1 for a in answers if a.is_correct)
    sheet.wrong_count = len(answers) - sheet.correct_count
    sheet.status = "needs_review"  # 标记为需要复核
    sheet.updated_at = datetime.utcnow()

    db.session.commit()
    return jsonify({
        "msg": "答案已更新",
        "old_value": old_value,
        "new_value": new_value
    })


# ===========================
# 查看答题卡修改记录
# ===========================
@sheet_bp.route("/<int:sheet_id>/logs", methods=["GET"])
@jwt_required()
def get_sheet_logs(sheet_id):
    """
    查看答题卡修改记录
    ---
    tags:
      - AnswerSheet
    parameters:
      - name: sheet_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: 返回修改记录
      404:
        description: 答题卡不存在
    """
    sheet = AnswerSheet.query.get(sheet_id)
    if not sheet:
        return jsonify({"error": "答题卡不存在"}), 404

    # 验证权限
    exam = Exam.query.get(sheet.exam_id)
    if exam.teacher_id != int(get_jwt_identity()):
        return jsonify({"error": "无权限"}), 403

    logs = AuditLog.query.filter_by(sheet_id=sheet_id).order_by(AuditLog.created_at.desc()).all()
    return jsonify([
        {
            "log_id": log.id,
            "answer_id": log.answer_id,
            "action": log.action,
            "old_value": json.loads(log.old_value) if log.old_value else None,
            "new_value": json.loads(log.new_value) if log.new_value else None,
            "created_at": log.created_at.isoformat()
        }
        for log in logs
    ])


# ===========================
# 确认答题卡
# ===========================
@sheet_bp.route("/confirm/<int:sheet_id>", methods=["POST"])
@jwt_required()
def confirm_sheet(sheet_id):
    """
    确认答题卡
    ---
    tags:
      - AnswerSheet
    parameters:
      - name: sheet_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: 确认成功
      404:
        description: 答题卡不存在
    """
    sheet = AnswerSheet.query.get(sheet_id)
    if not sheet:
        return jsonify({"error": "答题卡不存在"}), 404

    # 验证权限
    exam = Exam.query.get(sheet.exam_id)
    if exam.teacher_id != int(get_jwt_identity()):
        return jsonify({"error": "无权限"}), 403

    # 记录审计日志
    GradingService._log(
        sheet.id,
        None,
        "CONFIRM_SHEET",
        {"status": sheet.status},
        {"status": "confirmed"}
    )

    # 更新状态
    sheet.status = "confirmed"
    sheet.updated_at = datetime.utcnow()
    db.session.commit()

    # 自动更新考试状态
    from routes.exam_route import update_exam_status
    update_exam_status(exam.id)

    return jsonify({
        "success": True,
        "message": "答题卡已确认",
        "sheet_id": sheet.id
    })


# ===========================
# 标记答题卡需要复核
# ===========================
@sheet_bp.route("/review/<int:sheet_id>", methods=["POST"])
@jwt_required()
def mark_for_review(sheet_id):
    """
    标记答题卡需要复核
    ---
    tags:
      - AnswerSheet
    parameters:
      - name: sheet_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: 标记成功
      404:
        description: 答题卡不存在
    """
    sheet = AnswerSheet.query.get(sheet_id)
    if not sheet:
        return jsonify({"error": "答题卡不存在"}), 404

    # 验证权限
    exam = Exam.query.get(sheet.exam_id)
    if exam.teacher_id != int(get_jwt_identity()):
        return jsonify({"error": "无权限"}), 403

    # 记录审计日志
    GradingService._log(
        sheet.id,
        None,
        "MARK_FOR_REVIEW",
        {"status": sheet.status},
        {"status": "needs_review"}
    )

    # 更新状态
    sheet.status = "needs_review"
    sheet.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "答题卡已标记为需要复核",
        "sheet_id": sheet.id
    })


# ===========================
# 删除答题卡
# ===========================
@sheet_bp.route("/<int:sheet_id>", methods=["DELETE"])
@jwt_required()
def delete_sheet(sheet_id):
    """
    删除答题卡
    ---
    tags:
      - AnswerSheet
    parameters:
      - name: sheet_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: 删除成功
      404:
        description: 答题卡不存在
    """
    sheet = AnswerSheet.query.get(sheet_id)
    if not sheet:
        return jsonify({"error": "答题卡不存在"}), 404

    # 验证权限
    exam = Exam.query.get(sheet.exam_id)
    if exam.teacher_id != int(get_jwt_identity()):
        return jsonify({"error": "无权限"}), 403

    # 删除相关答案和日志
    Answer.query.filter_by(sheet_id=sheet_id).delete()
    AuditLog.query.filter_by(sheet_id=sheet_id).delete()

    # 删除图片文件（可选）
    try:
        if sheet.raw_image_url and os.path.exists(sheet.raw_image_url):
            os.remove(sheet.raw_image_url)
        if sheet.corrected_image_url and os.path.exists(sheet.corrected_image_url):
            os.remove(sheet.corrected_image_url)
        if sheet.result_image_url and os.path.exists(sheet.result_image_url):
            os.remove(sheet.result_image_url)
    except Exception as e:
        print(f"删除图片失败: {e}")

    # 删除答题卡
    db.session.delete(sheet)
    db.session.commit()

    # 自动更新考试状态
    from routes.exam_route import update_exam_status
    update_exam_status(exam.id)

    return jsonify({"msg": "删除成功"})

