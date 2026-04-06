from flask import Blueprint, request, jsonify
from extensions import db
from models.school_class import SchoolClass
from flask_jwt_extended import jwt_required, get_jwt_identity

class_bp = Blueprint("class", __name__)


@class_bp.route("/", methods=["POST"])
@jwt_required()
def create_class():
    """
    创建班级
    ---
    tags:
      - Class
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
              example: 高三一班
            semester:
              type: string
              example: 2025春季
    responses:
      200:
        description: 创建成功，返回班级ID
      401:
        description: 未授权
    """

    teacher_id = int(get_jwt_identity())
    data = request.json

    new_class = SchoolClass(
        class_name=data["name"],   # 改这里
        semester=data["semester"], # 必须加
        teacher_id=teacher_id
    )

    db.session.add(new_class)
    db.session.commit()

    return jsonify({"class_id": new_class.id})


@class_bp.route("/", methods=["GET"])
@jwt_required()
def list_classes():
    """
    获取当前教师的班级列表
    ---
    tags:
      - Class
    security:
      - Bearer: []
    parameters:
      - name: Authorization
        in: header
        type: string
        required: true
        description: Bearer JWT Token
    responses:
      200:
        description: 返回班级列表
      401:
        description: 未授权
    """

    teacher_id = int(get_jwt_identity())

    classes = SchoolClass.query.filter_by(teacher_id=teacher_id).all()

    return jsonify([
        {"id": c.id, "name": c.class_name}
        for c in classes
    ])


@class_bp.route("/<int:class_id>", methods=["DELETE"])
@jwt_required()
def delete_class(class_id):
    """
    删除班级
    ---
    tags:
      - Class
    security:
      - Bearer: []
    parameters:
      - name: Authorization
        in: header
        type: string
        required: true
        description: Bearer JWT Token
      - name: class_id
        in: path
        type: integer
        required: true
        description: 班级ID
    responses:
      200:
        description: 删除成功
      404:
        description: 班级不存在
      401:
        description: 未授权
    """

    school_class = SchoolClass.query.get(class_id)
    if not school_class:
        return jsonify({"error": "不存在"}), 404

    db.session.delete(school_class)
    db.session.commit()

    return jsonify({"msg": "删除成功"})