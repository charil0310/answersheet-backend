import cv2
import numpy as np
from sklearn.cluster import KMeans
import logging
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)


class RegionDivider:
    """区域分割器"""

    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode

    def cv_show(self, name: str, img: np.ndarray):
        """显示图像并等待按键后关闭（仅在调试模式下）"""
        if self.debug_mode:
            cv2.imshow(name, img)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

    def merge_close_lines(self, lines: List[Dict], threshold: int = 10) -> List[Dict]:
        """合并靠近的线段"""
        if len(lines) == 0:
            return lines

        lines.sort(key=lambda line: line['center_x'])
        merged_lines = []
        current_line = lines[0]

        for i in range(1, len(lines)):
            if abs(lines[i]['center_x'] - current_line['center_x']) < threshold:
                x1 = min(current_line['x1'], current_line['x2'], lines[i]['x1'], lines[i]['x2'])
                x2 = max(current_line['x1'], current_line['x2'], lines[i]['x1'], lines[i]['x2'])
                y1 = min(current_line['y1'], current_line['y2'], lines[i]['y1'], lines[i]['y2'])
                y2 = max(current_line['y1'], current_line['y2'], lines[i]['y1'], lines[i]['y2'])
                center_x = (current_line['center_x'] + lines[i]['center_x']) / 2
                length = max(current_line['length'], lines[i]['length'])

                current_line = {
                    'x1': x1, 'y1': y1,
                    'x2': x2, 'y2': y2,
                    'center_x': center_x,
                    'length': length
                }
            else:
                merged_lines.append(current_line)
                current_line = lines[i]

        merged_lines.append(current_line)
        return merged_lines

    def detect_vertical_lines(self, warped: np.ndarray) -> Tuple[List[Dict], List[Dict]]:
        """检测答题卡上的垂直线并划分区域"""
        if len(warped.shape) == 3:
            height, width = warped.shape[:2]
        else:
            height, width = warped.shape

        _, binary = cv2.threshold(warped.copy(), 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        lsd = cv2.createLineSegmentDetector(0)
        lines = lsd.detect(binary)[0] if lsd.detect(binary)[0] is not None else []

        vertical_lines = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)

            if 85 <= angle <= 95:
                if np.abs(x1 - x2) < 5:
                    length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                    center_x = (x1 + x2) / 2

                    if length > height * 0.3 and width * 0.2 < center_x < width * 0.8:
                        vertical_lines.append({
                            'x1': x1, 'y1': y1,
                            'x2': x2, 'y2': y2,
                            'center_x': center_x,
                            'length': length
                        })

        if vertical_lines:
            vertical_lines = self.merge_close_lines(vertical_lines, threshold=width * 0.02)

        # 垂直线不足时的备选方案
        if len(vertical_lines) < 3:
            logger.warning(f"只检测到 {len(vertical_lines)} 条垂直线，使用备选方案（等分区域）")
            region_width = width // 4

            regions = []
            for i in range(4):
                x1 = i * region_width
                x2 = (i + 1) * region_width if i < 3 else width
                regions.append({
                    'x1': x1, 'y1': 0,
                    'x2': x2, 'y2': height,
                    'name': f'Region{i + 1}'
                })

            filtered_lines = []
            for i in range(1, 4):
                x = i * region_width
                filtered_lines.append({
                    'x1': x, 'y1': 0,
                    'x2': x, 'y2': height,
                    'center_x': x,
                    'length': height
                })

            return regions, filtered_lines

        vertical_lines.sort(key=lambda line: line['center_x'])
        centroids = np.array([[line['center_x']] for line in vertical_lines])
        kmeans = KMeans(n_clusters=min(3, len(vertical_lines)), random_state=0).fit(centroids)

        main_lines = []
        for i in range(kmeans.n_clusters):
            cluster_indices = np.where(kmeans.labels_ == i)[0]
            best_idx = None
            max_length = 0
            for idx in cluster_indices:
                if vertical_lines[idx]['length'] > max_length:
                    max_length = vertical_lines[idx]['length']
                    best_idx = idx
            if best_idx is not None:
                main_lines.append(vertical_lines[best_idx])

        main_lines.sort(key=lambda line: line['center_x'])
        min_line_distance = width * 0.15
        filtered_lines = []
        prev_x = -min_line_distance
        for line in main_lines:
            if abs(line['center_x'] - prev_x) >= min_line_distance:
                filtered_lines.append(line)
                prev_x = line['center_x']

        if len(filtered_lines) < 3:
            filtered_lines = main_lines

        regions = []
        regions.append({'x1': 0, 'y1': 0, 'x2': filtered_lines[0]['center_x'], 'y2': height, 'name': 'Region1'})
        regions.append({'x1': filtered_lines[0]['center_x'], 'y1': 0, 'x2': filtered_lines[1]['center_x'], 'y2': height,
                        'name': 'Region2'})
        regions.append({'x1': filtered_lines[1]['center_x'], 'y1': 0, 'x2': filtered_lines[2]['center_x'], 'y2': height,
                        'name': 'Region3'})
        regions.append({'x1': filtered_lines[2]['center_x'], 'y1': 0, 'x2': width, 'y2': height, 'name': 'Region4'})

        # 可视化区域划分（仅在调试模式下）
        if self.debug_mode:
            vis = warped.copy()
            if len(vis.shape) == 2:
                vis = cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR)

            for i, region in enumerate(regions):
                x1, y1, x2, y2 = int(region['x1']), int(region['y1']), int(region['x2']), int(region['y2'])
                cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(vis, f'Region {i + 1}', (x1 + 10, y1 + 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

            self.cv_show('Region Division', vis)

        return regions, filtered_lines

    def extract_region(self, image: np.ndarray, region: Dict) -> Optional[np.ndarray]:
        """从图像中提取指定区域"""
        x1 = max(0, int(region['x1']))
        y1 = max(0, int(region['y1']))
        x2 = min(image.shape[1], int(region['x2']))
        y2 = min(image.shape[0], int(region['y2']))

        if x2 <= x1 or y2 <= y1:
            return None

        region_img = image[y1:y2, x1:x2]
        return region_img