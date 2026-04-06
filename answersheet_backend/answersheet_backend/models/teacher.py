from extensions import db
from datetime import datetime


class Teacher(db.Model):
    __tablename__ = "teacher"

    id = db.Column(db.BigInteger, primary_key=True)

    openid = db.Column(db.String(128), unique=True, nullable=False)
    name = db.Column(db.String(100))
    avatar_url = db.Column(db.String(500))

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    # 关系
    classes = db.relationship("SchoolClass", backref="teacher")
    exams = db.relationship("Exam", backref="teacher")
    students = db.relationship("Student", backref="teacher")