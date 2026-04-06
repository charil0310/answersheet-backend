from extensions import db
from datetime import datetime


class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id = db.Column(db.BigInteger, primary_key=True)

    sheet_id = db.Column(
        db.BigInteger,
        db.ForeignKey("answer_sheet.id")
    )

    answer_id = db.Column(
        db.BigInteger,
        db.ForeignKey("answer.id")
    )

    operator_openid = db.Column(db.String(128))

    action = db.Column(db.String(100))

    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )