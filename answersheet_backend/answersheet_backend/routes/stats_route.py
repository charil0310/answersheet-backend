from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.statistics_service import StatisticsService
from models.exam import Exam
from models.answer_sheet import AnswerSheet
from models.question import Question
from sqlalchemy import func

stats_bp = Blueprint("stats", __name__)


# ===========================
# 基本统计
# ===========================
@stats_bp.route("/<int:exam_id>/basic", methods=["GET"])
@jwt_required()
def basic_stats(exam_id):
    """
    获取考试基础统计（平均分、最高分、最低分）
    ---
    tags:
      - Statistics
    parameters:
      - name: exam_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: 返回基础统计数据
      404:
        description: 考试不存在
    """
    # 验证权限
    exam = Exam.query.filter_by(id=exam_id, teacher_id = int(get_jwt_identity())).first()
    if not exam:
        return jsonify({"error": "考试不存在或无权限"}), 404

    data = StatisticsService.basic_stats(exam_id)
    # 补充参考人数
    data["participant_count"] = AnswerSheet.query.filter_by(exam_id=exam_id).count()
    return jsonify(data)


# ===========================
# 排名
# ===========================
@stats_bp.route("/<int:exam_id>/ranking", methods=["GET"])
@jwt_required()
def ranking(exam_id):
    """
    获取学生成绩排名
    ---
    tags:
      - Statistics
    parameters:
      - name: exam_id
        in: path
        required: true
        type: integer
      - name: top
        in: query
        required: false
        type: integer
        example: 10
    responses:
      200:
        description: 返回排名数据
      404:
        description: 考试不存在
    """
    # 验证权限
    exam = Exam.query.filter_by(id=exam_id, teacher_id = int(get_jwt_identity())).first()
    if not exam:
        return jsonify({"error": "考试不存在或无权限"}), 404

    # 获取top参数，默认返回全部
    top = request.args.get("top", 0, type=int)
    data = StatisticsService.ranking(exam_id)
    
    if top > 0:
        data = data[:top]
    
    return jsonify({
        "total": len(data),
        "ranking": data
    })


# ===========================
# 每题正确率
# ===========================
@stats_bp.route("/<int:exam_id>/accuracy", methods=["GET"])
@jwt_required()
def question_accuracy(exam_id):
    """
    获取每题正确率
    ---
    tags:
      - Statistics
    parameters:
      - name: exam_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: 返回每题正确率
      404:
        description: 考试不存在
    """
    # 验证权限
    exam = Exam.query.filter_by(id=exam_id, teacher_id = int(get_jwt_identity())).first()
    if not exam:
        return jsonify({"error": "考试不存在或无权限"}), 404

    data = StatisticsService.question_accuracy(exam_id)
    
    # 补充题目类型和分值信息
    for item in data:
        question = Question.query.filter_by(
            exam_id=exam_id,
            question_no=item["question_no"]
        ).first()
        if question:
            item["question_type"] = question.question_type
            item["max_score"] = question.max_score
            item["correct_count"] = int(item["accuracy"] * AnswerSheet.query.filter_by(exam_id=exam_id).count())
            item["wrong_count"] = int((1 - item["accuracy"]) * AnswerSheet.query.filter_by(exam_id=exam_id).count())

    return jsonify(data)


# ===========================
# 分数分布
# ===========================
@stats_bp.route("/<int:exam_id>/distribution", methods=["GET"])
@jwt_required()
def score_distribution(exam_id):
    """
    获取分数分布统计
    ---
    tags:
      - Statistics
    parameters:
      - name: exam_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: 返回分数分布
      404:
        description: 考试不存在
    """
    # 验证权限
    exam = Exam.query.filter_by(id=exam_id, teacher_id = int(get_jwt_identity())).first()
    if not exam:
        return jsonify({"error": "考试不存在或无权限"}), 404

    data = StatisticsService.score_distribution(exam_id)
    
    # 补充百分比
    total = sum(data.values())
    distribution_with_percent = {}
    for range_name, count in data.items():
        percent = (count / total * 100) if total > 0 else 0
        distribution_with_percent[range_name] = {
            "count": count,
            "percent": round(percent, 2)
        }

    return jsonify({
        "total_students": total,
        "distribution": distribution_with_percent
    })


# ===========================
# 多次考试成绩对比
# ===========================
@stats_bp.route("/comparison", methods=["POST"])
@jwt_required()
def exam_comparison():
    """
    多次考试成绩对比
    ---
    tags:
      - Statistics
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            exam_ids:
              type: array
              items:
                type: integer
              example: [1,2,3]
    responses:
      200:
        description: 返回对比数据
      400:
        description: 参数错误
    """
    teacher_id = int(get_jwt_identity())
    data = request.json
    exam_ids = data.get("exam_ids", [])
    
    if not exam_ids:
        return jsonify({"error": "请选择要对比的考试"}), 400

    # 验证考试权限并获取数据
    comparison_data = []
    for exam_id in exam_ids:
        exam = Exam.query.filter_by(id=exam_id, teacher_id=teacher_id).first()
        if not exam:
            continue
        
        basic = StatisticsService.basic_stats(exam_id)
        distribution = StatisticsService.score_distribution(exam_id)
        accuracy = StatisticsService.question_accuracy(exam_id)
        
        # 计算及格率（60分及格）
        sheets = AnswerSheet.query.filter_by(exam_id=exam_id).all()
        total_sheets = len(sheets)
        pass_count = sum(1 for s in sheets if (s.total_score or 0) >= 60)
        pass_rate = (pass_count / total_sheets * 100) if total_sheets > 0 else 0

        comparison_data.append({
            "exam_id": exam.id,
            "exam_name": exam.exam_name,
            "course_name": exam.course_name or "",
            "exam_date": exam.exam_date.isoformat() if exam.exam_date else "",
            "basic_stats": basic,
            "pass_rate": round(pass_rate, 2),
            "participant_count": total_sheets,
            "score_distribution": distribution,
            "average_accuracy": round(sum(item["accuracy"] for item in accuracy) / len(accuracy) * 100, 2) if accuracy else 0
        })

    return jsonify({
        "total_exams": len(comparison_data),
        "data": comparison_data
    })


# ===========================
# 综合统计接口（前端仪表盘用）
# ===========================
@stats_bp.route("/<int:exam_id>/overview", methods=["GET"])
@jwt_required()
def overview(exam_id):
    """
    获取考试综合统计（仪表盘）
    ---
    tags:
      - Statistics
    parameters:
      - name: exam_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: 返回综合统计数据
      404:
        description: 考试不存在
    """
    # 验证权限
    exam = Exam.query.filter_by(id=exam_id, teacher_id = int(get_jwt_identity())).first()
    if not exam:
        return jsonify({"error": "考试不存在或无权限"}), 404

    # 获取各类统计数据
    basic = StatisticsService.basic_stats(exam_id)
    distribution = StatisticsService.score_distribution(exam_id)
    accuracy = StatisticsService.question_accuracy(exam_id)
    ranking = StatisticsService.ranking(exam_id)
    
    # 补充额外统计
    sheets = AnswerSheet.query.filter_by(exam_id=exam_id).all()
    total_sheets = len(sheets)
    pass_count = sum(1 for s in sheets if (s.total_score or 0) >= 60)
    pass_rate = (pass_count / total_sheets * 100) if total_sheets > 0 else 0

    # 找出正确率最低的5道题
    accuracy_sorted = sorted(accuracy, key=lambda x: x["accuracy"])[:5]

    return jsonify({
        "exam_info": {
            "id": exam.id,
            "name": exam.exam_name,
            "course": exam.course_name or "",
            "status": exam.status
        },
        "basic": basic,
        "distribution": distribution,
        "accuracy": accuracy,
        "ranking": ranking[:10],  # 只返回前10名
        "pass_rate": round(pass_rate, 2),
        "participant_count": total_sheets,
        "low_accuracy_questions": accuracy_sorted
    })


# ===========================
# 学生个人成绩统计
# ===========================
@stats_bp.route("/student/<int:student_id>/history", methods=["GET"])
@jwt_required()
def student_score_history(student_id):
    """
    获取学生历次考试成绩
    ---
    tags:
      - Statistics
    parameters:
      - name: student_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: 返回学生成绩历史
      404:
        description: 学生不存在
    """
    teacher_id = int(get_jwt_identity())
    
    # 验证学生归属
    from models.student import Student
    student = Student.query.filter_by(id=student_id, teacher_id=teacher_id).first()
    if not student:
        return jsonify({"error": "学生不存在或无权限"}), 404

    # 获取学生所有答题卡
    sheets = AnswerSheet.query.filter_by(student_id=student_id).all()
    history = []
    
    for sheet in sheets:
        exam = Exam.query.get(sheet.exam_id)
        if not exam:
            continue
        
        history.append({
            "exam_id": exam.id,
            "exam_name": exam.exam_name,
            "course_name": exam.course_name or "",
            "exam_date": exam.exam_date.isoformat() if exam.exam_date else "",
            "score": sheet.total_score or 0,
            "rank": None,  # 可以补充该考试中的排名
            "correct_count": sheet.correct_count or 0,
            "wrong_count": sheet.wrong_count or 0,
            "exam_total_score": sum(q.max_score for q in exam.questions) if exam.questions else 0
        })

    # 补充排名
    for item in history:
        ranking = StatisticsService.ranking(item["exam_id"])
        for idx, rank_item in enumerate(ranking, 1):
            if rank_item["student_no"] == student.student_no:
                item["rank"] = idx
                break

    return jsonify({
        "student_info": {
            "id": student.id,
            "name": student.name,
            "student_no": student.student_no,
            "class_id": student.class_id
        },
        "score_history": history
    })