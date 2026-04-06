from extensions import db
from datetime import datetime


class SchoolClass(db.Model):
    __tablename__ = "school_class"

    id = db.Column(db.BigInteger, primary_key=True)

    teacher_id = db.Column(
        db.BigInteger,
        db.ForeignKey("teacher.id"),
        nullable=False
    )

    class_name = db.Column(db.String(200), nullable=False)
    semester = db.Column(db.String(50), nullable=False)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    students = db.relationship("Student", backref="school_class")
    exams = db.relationship("Exam", backref="school_class")
    sheets = db.relationship("AnswerSheet", backref="school_class")