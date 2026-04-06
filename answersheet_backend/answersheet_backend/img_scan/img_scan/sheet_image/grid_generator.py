import cv2
import numpy as np
import logging
from typing import List, Tuple, Dict

logger = logging.getLogger(__name__)


class GridGenerator:
    """网格生成器"""

    def calculate_projection(self, image: np.ndarray, axis: int) -> np.ndarray:
        """计算水平或垂直投影"""
        return np.sum(image, axis=axis)

    def preprocess_projection_exclude_top(self, projection: np.ndarray, exclude_ratio: float = 0.005) -> Tuple[
        np.ndarray, int]:
        """预处理投影，只排除图像上方的区域"""
        if len(projection) == 0:
            return projection, 0

        exclude_pixels = int(len(projection) * exclude_ratio)
        if exclude_pixels >= len(projection):
            exclude_pixels = len(projection) // 10

        valid_start = exclude_pixels
        processed_projection = projection.copy()
        max_val = np.max(projection)
        processed_projection[:valid_start] = max_val

        return processed_projection, valid_start

    def calculate_dynamic_min_gap(self, projection: np.ndarray, mode: str, max_number: int,
                                  min_pixels: int = 13, max_pixels: int = 150) -> int:
        """根据图像尺寸、题目数量和预期结构计算动态 min_gap"""
        total_length = len(projection)

        if total_length == 0 or max_number <= 0:
            return min_pixels

        if mode == 'valley':
            min_gap_factor = 0.03
            expected_boundaries = max_number + 2
            avg_gap = total_length / expected_boundaries
        else:
            min_gap_factor = 0.18
            expected_boundaries = max_number + 2
            avg_gap = total_length / expected_boundaries

        dynamic_min_gap = int(avg_gap * min_gap_factor)
        dynamic_min_gap = max(min_pixels, min(max_pixels, dynamic_min_gap))

        return dynamic_min_gap

    def find_boundaries(self, projection: np.ndarray, max_number: int, mode: str = 'valley') -> List[Tuple[int, int]]:
        """根据投影曲线找到边界，确保边界位于选项之间"""
        if len(projection) == 0:
            return []

        processed_projection, valid_start = self.preprocess_projection_exclude_top(projection)
        min_gap = self.calculate_dynamic_min_gap(processed_projection, mode, max_number)

        kernel_size = min(11, len(processed_projection) // 10)
        if kernel_size % 2 == 0:
            kernel_size += 1
        if kernel_size > 1:
            smoothed = np.convolve(processed_projection, np.ones(kernel_size) / kernel_size, mode='same')
        else:
            smoothed = processed_projection

        mean_val = np.mean(smoothed)
        std_val = np.std(smoothed)
        threshold = mean_val - 0.7 * std_val
        indices = np.where(smoothed < threshold)[0]

        if len(indices) == 0:
            return [(valid_start, len(projection))]

        groups = []
        current_group = [indices[0]]

        for i in range(1, len(indices)):
            if indices[i] - indices[i - 1] <= min_gap:
                current_group.append(indices[i])
            else:
                groups.append(current_group)
                current_group = [indices[i]]
        groups.append(current_group)

        boundaries = []
        for group in groups:
            if group:
                start = min(group)
                end = max(group)
                center = (start + end) // 2
                boundaries.append(center)

        if len(boundaries) < 2:
            return [(valid_start, len(projection))]

        full_boundaries = [valid_start]
        full_boundaries.extend(boundaries)
        full_boundaries.append(len(projection))

        boundary_pairs = []
        for i in range(len(full_boundaries) - 1):
            boundary_pairs.append((full_boundaries[i], full_boundaries[i + 1]))

        return boundary_pairs

    def generate_grids_and_map(self, row_bounds: List[Tuple[int, int]], col_bounds: List[Tuple[int, int]],
                               region_offset_x: int, region_offset_y: int, start_question: int = 1,
                               start_option: str = 'A', max_options: int = 4) -> Tuple[
        List[List[Tuple[int, int, int, int]]], Dict[Tuple[int, str], Tuple[int, int, int, int]], Dict[
            Tuple[int, str], Tuple[int, int, int, int]]]:
        """生成网格坐标和答案映射表，包含区域偏移量，限制选项数量"""
        grids = []
        answer_map_offset = {}
        answer_map = {}

        for row_idx, (y1, y2) in enumerate(row_bounds):
            row = []
            valid_col_bounds = col_bounds[2: 2 + max_options]

            for col_idx, (x1, x2) in enumerate(valid_col_bounds):
                grid_coords = (x1, y1, x2, y2)
                grid_coords_offset = (
                    region_offset_x + x1, region_offset_y + y1, region_offset_x + x2, region_offset_y + y2)
                row.append(grid_coords)
                question_id = row_idx + start_question
                option = chr(ord(start_option) + col_idx)
                answer_map_offset[(question_id, option)] = grid_coords_offset
                answer_map[(question_id, option)] = grid_coords
            grids.append(row)

        return grids, answer_map, answer_map_offset

    def draw_grids(self, image: np.ndarray, grids: List[List[Tuple[int, int, int, int]]]) -> np.ndarray:
        """在图像上绘制网格"""
        if len(image.shape) == 2:
            vis = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        else:
            vis = image.copy()

        for row in grids:
            for (x1, y1, x2, y2) in row:
                cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 1)
        return vis