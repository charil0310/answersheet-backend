from flask import Blueprint, request, jsonify
from extensions import db
from models.teacher import Teacher
from flask_jwt_extended import create_access_token
from datetime import datetime

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["POST"])
def login():
    """
    微信 OpenID 登录（自动注册）
    ---
    tags:
      - Auth
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            openid:
              type: string
              example: wx_123456789
            name:
              type: string
              example: 张老师
            avatar_url:
              type: string
              example: https://example.com/avatar.jpg
    responses:
      200:
        description: 登录成功
    """

    data = request.json
    openid = data.get("openid")

    if not openid:
        return jsonify({"error": "缺少 openid"}), 400

    teacher = Teacher.query.filter_by(openid=openid).first()

    # 不存在就自动注册
    if not teacher:
        teacher = Teacher(
            openid=openid,
            name=data.get("name"),
            avatar_url=data.get("avatar_url"),
            created_at=datetime.utcnow()
        )
        db.session.add(teacher)
        db.session.commit()

    token = create_access_token(identity=str(teacher.id))

    return jsonify({
        "access_token": token,
        "teacher_id": teacher.id,
        "name": teacher.name,
        "avatar_url": teacher.avatar_url
    })