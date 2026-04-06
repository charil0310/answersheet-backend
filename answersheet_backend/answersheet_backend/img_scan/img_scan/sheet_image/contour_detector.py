import cv2
import numpy as np
import logging
from typing import Tuple, List, Dict, Any

logger = logging.getLogger(__name__)


class ContourDetector:
    """轮廓检测器"""

    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode

    def cv_show(self, name: str, img: np.ndarray):
        """显示图像并等待按键后关闭（仅在调试模式下）"""
        if self.debug_mode:
            cv2.imshow(name, img)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

    def find_document_contour(self, edged: np.ndarray, image: np.ndarray) -> np.ndarray:
        """在边缘检测图中查找最大的矩形轮廓"""
        try:
            cnts, _ = cv2.findContours(edged.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cnts = sorted(cnts, key=cv2.contourArea, reverse=True)

            docCnt = None
            for c in cnts:
                peri = cv2.arcLength(c, True)
                approx = cv2.approxPolyDP(c, 0.02 * peri, True)
                if len(approx) == 4:
                    docCnt = approx
                    break

            if docCnt is None:
                raise ValueError("未找到有效的矩形轮廓")

            # 可视化轮廓（仅在调试模式下）
            if self.debug_mode:
                contours_img = image.copy()
                cv2.drawContours(contours_img, [docCnt], -1, (0, 0, 255), 3)
                self.cv_show('Document Contour', contours_img)

            return docCnt.reshape(4, 2)
        except Exception as e:
            logger.error(f"查找文档轮廓失败: {str(e)}")
            raise

    def order_points(self, pts: np.ndarray) -> np.ndarray:
        """将四个点排序为左上、右上、右下、左下的顺序"""
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]  # 左上
        rect[2] = pts[np.argmax(s)]  # 右下

        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]  # 右上
        rect[3] = pts[np.argmax(diff)]  # 左下
        return rect

    def four_point_transform(self, image: np.ndarray, pts: np.ndarray) -> Tuple[
        np.ndarray, np.ndarray, Tuple[int, int]]:
        """执行透视变换"""
        rect = self.order_points(pts)
        (tl, tr, br, bl) = rect

        widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
        widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
        maxWidth = max(int(widthA), int(widthB))

        heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
        heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
        maxHeight = max(int(heightA), int(heightB))

        dst = np.array([
            [0, 0],
            [maxWidth - 1, 0],
            [maxWidth - 1, maxHeight - 1],
            [0, maxHeight - 1]], dtype="float32")

        M = cv2.getPerspectiveTransform(rect, dst)
        warped = cv2.warpPerspective(image, M, (maxWidth, maxHeight))
        return warped, M, (maxWidth, maxHeight)