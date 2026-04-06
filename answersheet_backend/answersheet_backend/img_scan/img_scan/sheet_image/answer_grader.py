import cv2
import numpy as np
from typing import Dict, Tuple, Any


class AnswerGrader:
    """答案评分器"""

    def __init__(self, score_per_question: int = 4, multi_select_score: int = 4, partial_score: bool = True):
        self.score_per_question = score_per_question
        self.multi_select_score = multi_select_score
        self.partial_score = partial_score

    def compare_answers(self, thresh: np.ndarray, answer_map: Dict, answers: Dict, answer_key: Dict) -> Tuple[
        np.ndarray, float, Dict[int, float]]:
        """评估答案并可视化结果（支持单选和多选）"""
        if len(thresh.shape) == 2:
            vis = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)
        else:
            vis = thresh.copy()

        correct_count = 0
        total_questions = len(answer_key)
        scores = {}

        if self.multi_select_score is None:
            multi_select_score = self.score_per_question
        else:
            multi_select_score = self.multi_select_score

        for q, correct_ans in answer_key.items():
            user_ans = answers.get(q)

            if isinstance(correct_ans, list):
                if isinstance(user_ans, list):
                    correct_set = set(correct_ans)
                    user_set = set(user_ans)

                    if correct_set == user_set:
                        scores[q] = multi_select_score
                        correct_count += 1
                        color = (0, 255, 0)
                    elif self.partial_score and user_set.issubset(correct_set) and len(user_set) > 0:
                        partial_ratio = len(user_set) / len(correct_set)
                        scores[q] = multi_select_score * partial_ratio
                        color = (0, 255, 255)
                    else:
                        scores[q] = 0
                        color = (0, 0, 255)
                else:
                    scores[q] = 0
                    color = (0, 0, 255)
            else:
                if isinstance(user_ans, list):
                    scores[q] = 0
                    color = (0, 0, 255)
                else:
                    if user_ans == correct_ans:
                        scores[q] = self.score_per_question
                        correct_count += 1
                        color = (0, 255, 0)
                    else:
                        scores[q] = 0
                        color = (0, 0, 255)

            user_ans_list = user_ans if isinstance(user_ans, list) else [user_ans] if user_ans else []
            for ans in user_ans_list:
                user_coords = answer_map.get((q, ans))
                if user_coords:
                    x1, y1, x2, y2 = user_coords
                    cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)

            correct_ans_list = correct_ans if isinstance(correct_ans, list) else [correct_ans]
            if user_ans_list != correct_ans_list:
                for ans in correct_ans_list:
                    correct_coords = answer_map.get((q, ans))
                    if correct_coords:
                        x1, y1, x2, y2 = correct_coords
                        cv2.rectangle(vis, (x1, y1), (x2, y2), (255, 0, 0), 1)

        total_score = sum(scores.values())
        max_score = total_questions * self.score_per_question

        score_text = f"Score: {total_score:.1f}/{max_score} ({correct_count}/{total_questions})"
        cv2.putText(vis, score_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        return vis, total_score, scores