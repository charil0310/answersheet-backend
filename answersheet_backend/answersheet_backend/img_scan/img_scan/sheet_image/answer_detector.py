import cv2
import numpy as np
from typing import Dict, Optional, Any


class AnswerDetector:
    """答案检测器"""

    def __init__(self, min_pixels_threshold: int = 290):
        self.min_pixels_threshold = min_pixels_threshold

    def detect_answers(self, thresh: np.ndarray, answer_map: Dict, min_pixels: Optional[int] = None) -> Dict[int, Any]:
        """识别所有填涂的答案（支持多选题）"""
        if min_pixels is None:
            min_pixels = self.min_pixels_threshold

        answers = {}

        questions = {}
        for (q, option), coords in answer_map.items():
            if q not in questions:
                questions[q] = []
            questions[q].append((option, coords))

        for q, options in questions.items():
            filled_options = []

            for option, (x1, y1, x2, y2) in options:
                roi = thresh[y1:y2, x1:x2]
                filled_pixels = cv2.countNonZero(roi)

                if filled_pixels >= min_pixels:
                    filled_options.append(option)

            if filled_options:
                answers[q] = filled_options[0] if len(filled_options) == 1 else filled_options

        return answers