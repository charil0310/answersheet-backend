from extensions import db
from datetime import datetime


class Exam(db.Model):
    __tablename__ = "exam"

    id = db.Column(db.BigInteger, primary_key=True)

    teacher_id = db.Column(
        db.BigInteger,
        db.ForeignKey("teacher.id"),
        nullable=False
    )

    exam_name = db.Column(db.String(255), nullable=False)
    course_name = db.Column(db.String(200))

    class_id = db.Column(
        db.BigInteger,
        db.ForeignKey("school_class.id")
    )

    exam_date = db.Column(db.DateTime)

    status = db.Column(
        db.Enum("CREATED", "IN_PROGRESS", "COMPLETED", "ARCHIVED"),
        default="CREATED"
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    questions = db.relationship("Question", backref="exam")
    sheets = db.relationship("AnswerSheet", backref="exam")
    structure = db.relationship("ExamStructure", uselist=False, backref="exam")