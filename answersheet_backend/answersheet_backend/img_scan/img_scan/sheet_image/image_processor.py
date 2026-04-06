import cv2
import numpy as np
import math
import logging
from typing import Tuple
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class ImageProcessor(ABC):
    """图像处理抽象基类"""

    @abstractmethod
    def process(self, image: np.ndarray) -> np.ndarray:
        pass


class RotationCorrector(ImageProcessor):
    """旋转校正处理器"""

    def rotate_image(self, image: np.ndarray, angle: float) -> np.ndarray:
        """旋转图像并调整画布大小防止裁剪"""
        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)

        angle_rad = math.radians(angle)
        abs_cos = abs(math.cos(angle_rad))
        abs_sin = abs(math.sin(angle_rad))

        new_w = int(h * abs_sin + w * abs_cos)
        new_h = int(h * abs_cos + w * abs_sin)

        M = cv2.getRotationMatrix2D(center, -angle, 1.0)
        M[0, 2] += (new_w - w) / 2
        M[1, 2] += (new_h - h) / 2

        rotated = cv2.warpAffine(image, M, (new_w, new_h),
                                 flags=cv2.INTER_LINEAR,
                                 borderValue=(255, 255, 255))
        return rotated

    def detect_and_correct_rotation(self, image: np.ndarray, binary: np.ndarray) -> Tuple[np.ndarray, float]:
        """检测图像中的直线并校正旋转"""
        lines = cv2.HoughLines(binary, 1, np.pi / 180, 200)

        if lines is not None:
            rho, theta = lines[0][0]
            angle = theta * 180 / np.pi
            rotate_angle = angle - 90
            rotated = self.rotate_image(image, rotate_angle)
        else:
            rotated = image.copy()
            rotate_angle = 0

        return rotated, rotate_angle

    def process(self, image: np.ndarray) -> np.ndarray:
        """处理图像旋转校正"""
        gray_temp = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, binary_temp = cv2.threshold(gray_temp, 50, 255, cv2.THRESH_BINARY_INV)
        rotated, rotate_angle = self.detect_and_correct_rotation(image, binary_temp)
        logger.info(f"应用旋转校正: {rotate_angle:.2f}度")
        return rotated


class ImagePreprocessor:
    """图像预处理器"""

    def __init__(self, enable_rotation_correction: bool = True):
        self.enable_rotation_correction = enable_rotation_correction
        self.rotation_corrector = RotationCorrector()

    def preprocess(self, image_path: str) -> Tuple[np.ndarray, ...]:
        """图像预处理：读取图像、灰度化、增强对比度、高斯模糊、边缘检测"""
        try:
            image = cv2.imread(image_path)
            if image is None:
                raise ValueError(f"无法加载图像: {image_path}")

            # 旋转校正
            if self.enable_rotation_correction:
                image = self.rotation_corrector.process(image)

            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
            blurred = cv2.GaussianBlur(enhanced, (5, 5), 0)
            edged = cv2.Canny(blurred, 50, 80)

            return image, gray, enhanced, blurred, edged
        except Exception as e:
            logger.error(f"图像预处理失败: {str(e)}")
            raise