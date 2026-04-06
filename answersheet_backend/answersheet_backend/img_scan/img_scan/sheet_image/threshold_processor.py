import cv2
import numpy as np
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class ThresholdProcessor:
    """阈值处理器"""

    def bitwise_and_thresholding(self, warped: np.ndarray) -> np.ndarray:
        """结合两种阈值处理方法"""
        _, thresh1 = cv2.threshold(warped.copy(), 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        thresh2 = self.otsu_thresholding(warped, False)
        thresh = cv2.bitwise_and(thresh1, thresh2)
        return thresh

    def otsu_thresholding(self, warped: np.ndarray, debug: bool = False) -> np.ndarray:
        """优化的阈值处理方法"""
        if len(warped.shape) == 3:
            gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
        else:
            gray = warped.copy()

        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 35, 15)

        if debug:
            total_pixels = thresh.size
            filled_pixels = cv2.countNonZero(thresh)
            fill_ratio = filled_pixels / total_pixels
            logger.info(f"二值化结果 - 填涂比例: {fill_ratio:.4f}")

        return thresh

    def region_img_option_thresh(self, region_img: np.ndarray, debug_mode: bool = False) -> np.ndarray:
        """通过轮廓检测提取填涂选项"""
        height, width = region_img.shape[:2]
        cnts, _ = cv2.findContours(region_img.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        filled_options = []

        for contour in cnts:
            area = cv2.contourArea(contour)
            min_area = (width * height) / 1000
            max_area = (width * height) / 200
            if not (min_area <= area <= max_area):
                continue

            filled_options.append(contour)

        blank_image = np.zeros((height, width, 1), dtype=np.uint8)
        result = cv2.drawContours(blank_image, filled_options, -1, (255, 255, 255), -1)

        if debug_mode:
            cv2.imshow("region_options", result)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

        return result