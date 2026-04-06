from extensions import db
from datetime import datetime


class Answer(db.Model):
    __tablename__ = "answer"

    id = db.Column(db.BigInteger, primary_key=True)

    sheet_id = db.Column(
        db.BigInteger,
        db.ForeignKey("answer_sheet.id"),
        nullable=False
    )

    question_no = db.Column(db.Integer, nullable=False)

    recognized_option_json = db.Column(db.JSON)

    is_correct = db.Column(db.Boolean)

    score_awarded = db.Column(db.Float)

    confidence = db.Column(db.Float)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    __table_args__ = (
        db.UniqueConstraint(
            "sheet_id",
            "question_no",
            name="uq_sheet_question"
        ),
    )