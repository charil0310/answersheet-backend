from extensions import db
from datetime import datetime


class AnswerSheet(db.Model):
    __tablename__ = "answer_sheet"

    id = db.Column(db.BigInteger, primary_key=True)

    exam_id = db.Column(
        db.BigInteger,
        db.ForeignKey("exam.id"),
        nullable=False
    )

    student_id = db.Column(
        db.BigInteger,
        db.ForeignKey("student.id")
    )

    class_id = db.Column(
        db.BigInteger,
        db.ForeignKey("school_class.id")
    )

    exam_room = db.Column(db.String(100))

    raw_image_url = db.Column(db.String(1000))

    scan_time = db.Column(db.DateTime)

    total_score = db.Column(db.Float)
    correct_count = db.Column(db.Integer)
    wrong_count = db.Column(db.Integer)

    status = db.Column(
        db.Enum(
            "uploaded",
            "processing",
            "processed",
            "needs_review",
            "confirmed",
            "failed",
            "student_not_found",
            "student_recognition_failed"
        ),
        default="uploaded"
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    answers = db.relationship("Answer", backref="sheet")