import json
from flask import Blueprint, request, jsonify
from extensions import db
from models.exam import Exam
from models.question import Question
from models.exam_structure import ExamStructure
from models.answer_sheet import AnswerSheet
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

exam_bp = Blueprint("exam", __name__)


@exam_bp.route("/", methods=["POST"])
@jwt_required()
def create_exam():
    """
    创建考试
    ---
    tags:
      - Exam
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - exam_name
            - class_id
            - course_name
          properties:
            exam_name:
              type: string
              example: 期中考试
            class_id:
              type: integer
              example: 1
            course_name:
              type: string
              example: 数学
            exam_date:
              type: string
              example: 'Sun, 01 Jun 2025 09:00:00 GMT'
    responses:
      200:
        description: 创建成功
        schema:
          type: object
          properties:
            exam_id:
              type: integer
              example: 1
      401:
        description: 未授权
    """
    from datetime import datetime
    teacher_id = int(get_jwt_identity())
    data = request.json

    # 兼容 GMT 格式 & ISO 格式
    exam_date = None
    if "exam_date" in data and data["exam_date"]:
        try:
            # 优先尝试解析 GMT 格式：Sun, 01 Jun 2025 09:00:00 GMT
            exam_date = datetime.strptime(data["exam_date"], "%a, %d %b %Y %H:%M:%S %Z")
        except ValueError:
            try:
                # 备用：ISO 格式
                exam_date = datetime.fromisoformat(data["exam_date"].replace("Z", "+00:00"))
            except ValueError:
                exam_date = None

    exam = Exam(
        exam_name=data["exam_name"],
        class_id=data["class_id"],
        teacher_id=teacher_id,
        course_name=data.get("course_name", ""),
        exam_date=exam_date,
        status="CREATED"
    )

    db.session.add(exam)
    db.session.commit()

    # 初始化考试结构
    structure = ExamStructure(
        exam_id=exam.id,
        start_question_no=1,
        end_question_no=0,
        default_option_count=4
    )
    db.session.add(structure)
    db.session.commit()

    return jsonify({"exam_id": exam.id})


@exam_bp.route("/<int:exam_id>/structure", methods=["PUT"])
@jwt_required()
def update_exam_structure(exam_id):
    """
    更新考试结构（题号范围、默认选项数）
    ---
    tags:
      - Exam
    parameters:
      - name: exam_id
        in: path
        required: true
        type: integer
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            start_question_no:
              type: integer
              example: 1
            end_question_no:
              type: integer
              example: 50
            default_option_count:
              type: integer
              example: 4
    responses:
      200:
        description: 更新成功
      404:
        description: 考试或结构不存在
    """
    teacher_id = int(get_jwt_identity())
    exam = Exam.query.filter_by(id=exam_id, teacher_id=teacher_id).first()
    if not exam:
        return jsonify({"error": "考试不存在或无权限"}), 404

    structure = ExamStructure.query.filter_by(exam_id=exam_id).first()
    if not structure:
        return jsonify({"error": "考试结构未初始化"}), 404

    data = request.json
    structure.start_question_no = data.get("start_question_no", structure.start_question_no)
    structure.end_question_no = data.get("end_question_no", structure.end_question_no)
    structure.default_option_count = data.get("default_option_count", structure.default_option_count)
    
    db.session.commit()
    return jsonify({"msg": "考试结构更新成功"})


@exam_bp.route("/<int:exam_id>/questions", methods=["POST"])
@jwt_required()
def add_questions(exam_id):
    """
    添加考试题目（完善题型、评分规则等）
    ---
    tags:
      - Exam
    parameters:
      - name: exam_id
        in: path
        required: true
        type: integer
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - questions
          properties:
            questions:
              type: array
              items:
                type: object
                properties:
                  question_no:
                    type: integer
                    example: 1
                  question_type:
                    type: string
                    enum: [single, multi, judge]
                    example: single
                  correct_answer:
                    type: array
                    items:
                      type: string
                    example: ["A"]
                  max_score:
                    type: number
                    example: 5
                  option_count:
                    type: integer
                    example: 4
                  multi_scoring_mode:
                    type: string
                    enum: [all_or_nothing, partial]
                    example: all_or_nothing
                  partial_ratio:
                    type: float
                    example: 1.0
    responses:
      200:
        description: 添加成功
      401:
        description: 未授权
      404:
        description: 考试不存在
    """
    teacher_id = int(get_jwt_identity())
    exam = Exam.query.filter_by(id=exam_id, teacher_id=teacher_id).first()
    if not exam:
        return jsonify({"error": "考试不存在或无权限"}), 404

    data = request.json
    for q in data["questions"]:
        # 检查题号是否已存在
        existing = Question.query.filter_by(
            exam_id=exam_id,
            question_no=q["question_no"]
        ).first()
        if existing:
            return jsonify({"error": f"题号 {q['question_no']} 已存在"}), 400

        question = Question(
            exam_id=exam_id,
            question_no=q["question_no"],
            question_type=q.get("question_type", "single"),
            correct_answer_json=json.dumps(q["correct_answer"]),
            max_score=q.get("max_score", 1.0),
            option_count=q.get("option_count", 4),
            multi_scoring_mode=q.get("multi_scoring_mode", "all_or_nothing"),
            partial_ratio=q.get("partial_ratio", 1.0)
        )
        db.session.add(question)

    db.session.commit()

    # 检查是否需要更新考试状态（如果是首次添加题目，保持CREATED）
    return jsonify({"msg": "题目添加成功"})


@exam_bp.route("/<int:exam_id>/questions/<int:question_no>", methods=["PUT"])
@jwt_required()
def update_question(exam_id, question_no):
    """
    编辑考试题目
    ---
    tags:
      - Exam
    parameters:
      - name: exam_id
        in: path
        required: true
        type: integer
      - name: question_no
        in: path
        required: true
        type: integer
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            question_type:
              type: string
              enum: [single, multi, judge]
              example: single
            correct_answer:
              type: array
              items:
                type: string
              example: ["A"]
            max_score:
              type: number
              example: 5
            option_count:
              type: integer
              example: 4
            multi_scoring_mode:
              type: string
              enum: [all_or_nothing, partial]
              example: all_or_nothing
            partial_ratio:
              type: float
              example: 1.0
    responses:
      200:
        description: 更新成功
      404:
        description: 考试或题目不存在
    """
    teacher_id = int(get_jwt_identity())
    exam = Exam.query.filter_by(id=exam_id, teacher_id=teacher_id).first()
    if not exam:
        return jsonify({"error": "考试不存在或无权限"}), 404

    question = Question.query.filter_by(
        exam_id=exam_id,
        question_no=question_no
    ).first()
    if not question:
        return jsonify({"error": "题目不存在"}), 404

    data = request.json
    if "question_type" in data:
        question.question_type = data["question_type"]
    if "correct_answer" in data:
        question.correct_answer_json = json.dumps(data["correct_answer"])
    if "max_score" in data:
        question.max_score = data["max_score"]
    if "option_count" in data:
        question.option_count = data["option_count"]
    if "multi_scoring_mode" in data:
        question.multi_scoring_mode = data["multi_scoring_mode"]
    if "partial_ratio" in data:
        question.partial_ratio = data["partial_ratio"]

    db.session.commit()
    return jsonify({"msg": "题目更新成功"})


@exam_bp.route("/<int:exam_id>/questions", methods=["GET"])
@jwt_required()
def get_questions(exam_id):
    """
    获取考试题目列表
    ---
    tags:
      - Exam
    parameters:
      - name: exam_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: 返回题目列表
      404:
        description: 考试不存在
    """
    teacher_id = int(get_jwt_identity())
    exam = Exam.query.filter_by(id=exam_id, teacher_id=teacher_id).first()
    if not exam:
        return jsonify({"error": "考试不存在或无权限"}), 404

    questions = Question.query.filter_by(exam_id=exam_id).order_by(Question.question_no).all()
    return jsonify([
        {
            "question_no": q.question_no,
            "question_type": q.question_type,
            "correct_answer": json.loads(q.correct_answer_json),
            "max_score": q.max_score,
            "option_count": q.option_count,
            "multi_scoring_mode": q.multi_scoring_mode,
            "partial_ratio": q.partial_ratio
        }
        for q in questions
    ])


@exam_bp.route("/", methods=["GET"])
@jwt_required()
def list_exams():
    """
    获取考试列表
    ---
    tags:
      - Exam
    responses:
      200:
        description: 返回考试列表
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
                example: 1
              exam_name:
                type: string
                example: 期中考试
              course_name:
                type: string
                example: 数学
              class_id:
                type: integer
                example: 1
              exam_date:
                type: string
                format: date-time
                example: 2025-06-01T09:00:00
              status:
                type: string
                example: CREATED
              total_score:
                type: number
                example: 100
      401:
        description: 未授权
    """
    teacher_id = int(get_jwt_identity())
    exams = Exam.query.filter_by(teacher_id=teacher_id).all()

    return jsonify([
        {
            "id": e.id,
            "exam_name": e.exam_name,
            "course_name": e.course_name,
            "class_id": e.class_id,
            "exam_date": e.exam_date.isoformat() if e.exam_date else None,
            "status": e.status,
            "total_score": sum(q.max_score for q in e.questions) if e.questions else 0
        }
        for e in exams
    ])


@exam_bp.route("/<int:exam_id>", methods=["GET"])
@jwt_required()
def get_exam_detail(exam_id):
    """
    获取考试详情
    ---
    tags:
      - Exam
    parameters:
      - name: exam_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: 返回考试详情
      404:
        description: 考试不存在
    """
    teacher_id = int(get_jwt_identity())
    exam = Exam.query.filter_by(id=exam_id, teacher_id=teacher_id).first()
    if not exam:
        return jsonify({"error": "考试不存在或无权限"}), 404

    # 获取考试结构
    structure = ExamStructure.query.filter_by(exam_id=exam_id).first()
    # 统计答题卡状态
    sheet_stats = db.session.query(
        AnswerSheet.status,
        func.count(AnswerSheet.id)
    ).filter_by(exam_id=exam_id).group_by(AnswerSheet.status).all()

    return jsonify({
        "id": exam.id,
        "exam_name": exam.exam_name,
        "course_name": exam.course_name,
        "class_id": exam.class_id,
        "exam_date": exam.exam_date.isoformat() if exam.exam_date else None,
        "status": exam.status,
        "total_score": sum(q.max_score for q in exam.questions) if exam.questions else 0,
        "structure": {
            "start_question_no": structure.start_question_no if structure else 1,
            "end_question_no": structure.end_question_no if structure else 0,
            "default_option_count": structure.default_option_count if structure else 4
        },
        "sheet_stats": {status: count for status, count in sheet_stats},
        "question_count": len(exam.questions)
    })


@exam_bp.route("/<int:exam_id>/status", methods=["PUT"])
@jwt_required()
def update_exam_status(exam_id):
    """
    更新考试状态（自动聚合答题卡状态）
    ---
    tags:
      - Exam
    parameters:
      - name: exam_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: 更新成功
      404:
        description: 考试不存在
    """
    teacher_id = int(get_jwt_identity())
    exam = Exam.query.filter_by(id=exam_id, teacher_id=teacher_id).first()
    if not exam:
        return jsonify({"error": "考试不存在或无权限"}), 404

    # 获取该考试下的所有答题卡
    sheets = AnswerSheet.query.filter_by(exam_id=exam_id).all()
    if not sheets:
        exam.status = "CREATED"
    else:
        # 检查是否有答题卡上传，更新为IN_PROGRESS
        if any(s.status in ["uploaded", "processing", "processed", "needs_review"] for s in sheets):
            exam.status = "IN_PROGRESS"
        # 检查是否所有答题卡都已确认
        elif all(s.status == "confirmed" for s in sheets):
            exam.status = "COMPLETED"
        # 检查是否所有答题卡都失败
        elif all(s.status == "failed" for s in sheets):
            exam.status = "CREATED"

    db.session.commit()
    return jsonify({"msg": f"考试状态已更新为 {exam.status}", "status": exam.status})


@exam_bp.route("/<int:exam_id>", methods=["DELETE"])
@jwt_required()
def delete_exam(exam_id):
    """
    删除考试
    ---
    tags:
      - Exam
    parameters:
      - name: exam_id
        in: path
        required: true
        type: integer
        description: 考试ID
    responses:
      200:
        description: 删除成功
        schema:
          type: object
          properties:
            msg:
              type: string
              example: 删除成功
      404:
        description: 考试不存在
      401:
        description: 未授权
    """
    teacher_id = int(get_jwt_identity())
    exam = Exam.query.filter_by(id=exam_id, teacher_id=teacher_id).first()
    if not exam:
        return jsonify({"error": "考试不存在或无权限"}), 404

    # 级联删除相关数据
    Question.query.filter_by(exam_id=exam_id).delete()
    ExamStructure.query.filter_by(exam_id=exam_id).delete()
    AnswerSheet.query.filter_by(exam_id=exam_id).delete()
    
    db.session.delete(exam)
    db.session.commit()

    return jsonify({"msg": "删除成功"})