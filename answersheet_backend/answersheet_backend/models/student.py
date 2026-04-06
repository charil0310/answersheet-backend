from extensions import db
from datetime import datetime


class Student(db.Model):
    __tablename__ = "student"

    id = db.Column(db.BigInteger, primary_key=True)

    teacher_id = db.Column(
        db.BigInteger,
        db.ForeignKey("teacher.id"),
        nullable=False
    )

    class_id = db.Column(
        db.BigInteger,
        db.ForeignKey("school_class.id"),
        nullable=False
    )

    student_no = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(200), nullable=False)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    sheets = db.relationship("AnswerSheet", backref="student")

    __table_args__ = (
        db.UniqueConstraint(
            "class_id",
            "student_no",
            name="uq_class_student_no"
        ),
    )