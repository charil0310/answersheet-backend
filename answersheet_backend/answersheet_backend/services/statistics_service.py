from extensions import db
from models.answer_sheet import AnswerSheet
from models.answer import Answer
from models.student import Student
from sqlalchemy import func


class StatisticsService:

    @staticmethod
    def basic_stats(exam_id):

        query = AnswerSheet.query.filter(
            AnswerSheet.exam_id == exam_id,
            AnswerSheet.status == "processed",
            AnswerSheet.student_id != None
        )

        avg_score = db.session.query(func.avg(AnswerSheet.total_score))\
            .filter(
                AnswerSheet.exam_id == exam_id,
                AnswerSheet.status == "processed"
            ).scalar()

        max_score = db.session.query(func.max(AnswerSheet.total_score))\
            .filter(
                AnswerSheet.exam_id == exam_id,
                AnswerSheet.status == "processed"
            ).scalar()

        min_score = db.session.query(func.min(AnswerSheet.total_score))\
            .filter(
                AnswerSheet.exam_id == exam_id,
                AnswerSheet.status == "processed"
            ).scalar()

        return {
            "average": float(avg_score or 0),
            "max": float(max_score or 0),
            "min": float(min_score or 0)
        }

    @staticmethod
    def ranking(exam_id):

        sheets = AnswerSheet.query.filter(
            AnswerSheet.exam_id == exam_id,
            AnswerSheet.status == "processed",
            AnswerSheet.student_id != None
        ).order_by(AnswerSheet.total_score.desc()).all()

        result = []

        for index, s in enumerate(sheets, start=1):

            student = Student.query.get(s.student_id)

            result.append({
                "rank": index,
                "student_name": student.name if student else "",
                "student_no": student.student_no if student else "",
                "score": s.total_score
            })

        return result

    @staticmethod
    def question_accuracy(exam_id):

        results = db.session.query(
            Answer.question_no,
            func.avg(Answer.is_correct)
        ).join(AnswerSheet)\
         .filter(AnswerSheet.exam_id == exam_id)\
         .group_by(Answer.question_no).all()

        return [
            {
                "question_no": r[0],
                "accuracy": round(float(r[1] or 0), 4)
            }
            for r in results
        ]

    @staticmethod
    def score_distribution(exam_id):

        sheets = AnswerSheet.query.filter(
            AnswerSheet.exam_id == exam_id,
            AnswerSheet.status == "processed"
        ).all()

        dist = {
            "90-100": 0,
            "80-89": 0,
            "70-79": 0,
            "60-69": 0,
            "<60": 0
        }

        for s in sheets:
            score = s.total_score or 0

            if score >= 90:
                dist["90-100"] += 1
            elif score >= 80:
                dist["80-89"] += 1
            elif score >= 70:
                dist["70-79"] += 1
            elif score >= 60:
                dist["60-69"] += 1
            else:
                dist["<60"] += 1

        return dist