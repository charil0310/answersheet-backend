from extensions import db
from datetime import datetime


class Question(db.Model):
    __tablename__ = "question"

    id = db.Column(db.BigInteger, primary_key=True)

    exam_id = db.Column(
        db.BigInteger,
        db.ForeignKey("exam.id"),
        nullable=False
    )

    question_no = db.Column(db.Integer, nullable=False)

    question_type = db.Column(
        db.Enum("single", "multi", "judge"),
        nullable=False
    )

    option_count = db.Column(db.Integer, default=4)

    correct_answer_json = db.Column(db.JSON, nullable=False)

    max_score = db.Column(db.Float, default=1)

    multi_scoring_mode = db.Column(
        db.Enum("all_or_nothing", "partial"),
        default="all_or_nothing"
    )

    partial_ratio = db.Column(db.Float, default=1)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    __table_args__ = (
        db.UniqueConstraint(
            "exam_id",
            "question_no",
            name="uq_exam_question"
        ),
    )