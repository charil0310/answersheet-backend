from flask import Blueprint, request, jsonify
import pandas as pd
from extensions import db
from models.school_class import SchoolClass
from models.student import Student
from flask_jwt_extended import jwt_required, get_jwt_identity

student_bp = Blueprint("student", __name__)


@student_bp.route("/", methods=["POST"])
@jwt_required()
def add_student():
    """
    添加学生
    ---
    tags:
      - Student
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - name
            - student_no
            - class_id
          properties:
            name:
              type: string
              example: 张三
            student_no:
              type: string
              example: 2025001
            class_id:
              type: integer
              example: 1
    responses:
      200:
        description: 添加成功
        schema:
          type: object
          properties:
            student_id:
              type: integer
              example: 1
      400:
        description: 学号已存在
      403:
        description: 无权限
      401:
        description: 未授权
    """
    teacher_id = int(get_jwt_identity())
    data = request.json

    school_class = SchoolClass.query.get(data["class_id"])
    if not school_class or school_class.teacher_id != teacher_id:
        return jsonify({"error": "无权限"}), 403

    if Student.query.filter_by(
        student_no=data["student_no"],
        class_id=data["class_id"]
    ).first():
        return jsonify({"error": "学号已存在"}), 400

    student = Student(
        name=data["name"],
        student_no=data["student_no"],
        class_id=data["class_id"],
        teacher_id=teacher_id
    )

    db.session.add(student)
    db.session.commit()

    return jsonify({"student_id": student.id})


@student_bp.route("/class/<int:class_id>", methods=["GET"])
@jwt_required()
def list_students(class_id):
    """
    获取班级学生列表
    ---
    tags:
      - Student
    parameters:
      - name: class_id
        in: path
        required: true
        type: integer
        description: 班级ID
    responses:
      200:
        description: 返回学生列表
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
                example: 1
              name:
                type: string
                example: 张三
              student_no:
                type: string
                example: 2025001
      401:
        description: 未授权
    """

    students = Student.query.filter_by(class_id=class_id).all()

    return jsonify([
        {
            "id": s.id,
            "name": s.name,
            "student_no": s.student_no
        }
        for s in students
    ])


@student_bp.route("/<int:student_id>", methods=["DELETE"])
@jwt_required()
def delete_student(student_id):
    """
    删除学生
    ---
    tags:
      - Student
    parameters:
      - name: student_id
        in: path
        required: true
        type: integer
        description: 学生ID
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
        description: 学生不存在
      401:
        description: 未授权
    """

    student = Student.query.get(student_id)
    if not student:
        return jsonify({"error": "不存在"}), 404

    db.session.delete(student)
    db.session.commit()

    return jsonify({"msg": "删除成功"})


@student_bp.route("/import", methods=["POST"])
@jwt_required()
def import_students():
    """
    Excel批量导入学生
    ---
    tags:
      - Student
    summary: Excel导入学生
    consumes:
      - multipart/form-data
    parameters:
      - name: file
        in: formData
        type: file
        required: true
        description: Excel文件
      - name: class_id
        in: formData
        type: integer
        required: true
        example: 1
    responses:
      200:
        description: 导入结果
    """

    teacher_id = int(get_jwt_identity())

    if "file" not in request.files:
        return jsonify({"error": "请上传Excel文件"}), 400

    file = request.files["file"]

    class_id = request.form.get("class_id")
    if not class_id:
        return jsonify({"error": "缺少class_id"}), 400

    class_id = int(class_id)

    school_class = SchoolClass.query.get(class_id)

    if not school_class or school_class.teacher_id != teacher_id:
        return jsonify({"error": "无权限"}), 403

    # ======================
    # 读取Excel
    # ======================
    df = pd.read_excel(file)

    required = {"name", "student_no"}
    if not required.issubset(df.columns):
        return jsonify({"error": "Excel必须包含 name 和 student_no"}), 400

    # 删除空行
    df = df.dropna(subset=["student_no"])

    # ======================
    # 学号转字符串
    # ======================
    df["student_no"] = df["student_no"].apply(lambda x: str(int(x)) if pd.notna(x) else "")

    # ======================
    # Excel内部去重
    # ======================
    df = df.drop_duplicates(subset=["student_no"])

    # ======================
    # 查询数据库已有学号
    # ======================
    existing_students = Student.query.filter_by(class_id=class_id).all()
    existing_nos = {s.student_no for s in existing_students}

    added = 0
    skipped = 0

    for _, row in df.iterrows():

        student_no = row["student_no"].strip()

        if student_no in existing_nos:
            skipped += 1
            continue

        student = Student(
            name=str(row["name"]).strip(),
            student_no=student_no,
            class_id=class_id,
            teacher_id=teacher_id
        )

        db.session.add(student)

        existing_nos.add(student_no)
        added += 1

    db.session.commit()

    return jsonify({
        "added": added,
        "skipped": skipped
    })