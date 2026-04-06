from extensions import db
from datetime import datetime


class ExamStructure(db.Model):
    __tablename__ = "exam_structure"

    id = db.Column(db.BigInteger, primary_key=True)

    exam_id = db.Column(
        db.BigInteger,
        db.ForeignKey("exam.id"),
        unique=True,
        nullable=False
    )

    start_question_no = db.Column(db.Integer, nullable=False)
    end_question_no = db.Column(db.Integer, nullable=False)

    default_option_count = db.Column(db.Integer, default=4)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )