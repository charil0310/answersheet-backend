import os
import logging
from typing import Dict, Optional, Any
from .image_processor import ImagePreprocessor
from .contour_detector import ContourDetector
from .region_divider import RegionDivider
from .threshold_processor import ThresholdProcessor
from .grid_generator import GridGenerator
from .answer_detector import AnswerDetector
from .answer_grader import AnswerGrader


# 设置环境变量解决内存泄漏警告
os.environ['OMP_NUM_THREADS'] = '1'

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class AnswerSheetGrader:
    """答题卡评分器外观类（支持多选题）"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.default_config = {
            'total_questions': 120,
            'score_per_question': 4,
            'multi_select_score': 4,
            'options_per_question': 4,
            'min_pixels_threshold': 290,
            'show_intermediate_results': False,
            'save_intermediate_results': False,
            'output_dir': 'output',
            'partial_score': True,
            'debug_mode': False,
            'enable_rotation_correction': True
        }
        self.default_config.update(self.config)
        self.config = self.default_config

        if self.config['save_intermediate_results'] and not os.path.exists(self.config['output_dir']):
            os.makedirs(self.config['output_dir'])

        # 初始化各个组件
        self.image_preprocessor = ImagePreprocessor(self.config['enable_rotation_correction'])
        self.contour_detector = ContourDetector(self.config['debug_mode'])
        self.region_divider = RegionDivider(self.config['debug_mode'])
        self.threshold_processor = ThresholdProcessor()
        self.grid_generator = GridGenerator()
        self.answer_detector = AnswerDetector(self.config['min_pixels_threshold'])
        self.answer_grader = AnswerGrader(
            self.config['score_per_question'],
            self.config['multi_select_score'],
            self.config['partial_score']
        )

    def process_image(self, image_path: str, answer_key: Optional[Dict] = None,
                      is_answer_key: bool = False) -> Dict[str, Any]:
        """处理答题卡图像的主函数（支持多选题）"""
        try:
            # 1. 图像预处理
            image, gray, enhanced, blurred, edged = self.image_preprocessor.preprocess(image_path)

            # 2. 查找文档轮廓
            doc_pts = self.contour_detector.find_document_contour(edged, image)

            # 3. 透视变换
            warped, M, (width, height) = self.contour_detector.four_point_transform(enhanced, doc_pts)
            if self.config['debug_mode']:
                self.contour_detector.cv_show('Warped Image', warped)

            # 4. 阈值处理
            thresh = self.threshold_processor.bitwise_and_thresholding(warped)

            # 5. 检测垂直线并划分区域
            regions, vertical_lines = self.region_divider.detect_vertical_lines(warped)
            if regions is None:
                raise ValueError("未检测到足够的垂直线")

            # 6. 处理每个区域
            all_answers = {}
            all_answer_map = {}
            current_question = 1
            total_questions = self.config['total_questions']

            for i, region in enumerate(regions):
                region_img = self.region_divider.extract_region(thresh, region)
                if region_img is None or region_img.size == 0:
                    logger.warning(f"区域 {i + 1} 为空，跳过")
                    continue

                region_img_options = self.threshold_processor.region_img_option_thresh(
                    region_img, self.config['debug_mode'])

                horizontal_proj = self.grid_generator.calculate_projection(region_img, axis=1)
                questions_per_region = total_questions // len(regions)
                expected_rows = min(questions_per_region, total_questions - current_question + 1)

                row_bounds = self.grid_generator.find_boundaries(horizontal_proj, expected_rows, mode='valley')
                if len(row_bounds) > expected_rows:
                    row_bounds = row_bounds[:expected_rows]

                vertical_proj = self.grid_generator.calculate_projection(region_img, axis=0)
                col_bounds = self.grid_generator.find_boundaries(vertical_proj, 4, mode='peak')

                if len(row_bounds) == 0 or len(col_bounds) < 4:
                    logger.warning(f"区域 {i + 1} 没有检测到有效的行或列边界，跳过")
                    continue

                region_offset_x = int(region['x1'])
                region_offset_y = int(region['y1'])

                grids, answer_map, answer_map_offset = self.grid_generator.generate_grids_and_map(
                    row_bounds, col_bounds, region_offset_x, region_offset_y,
                    start_question=current_question, start_option='A'
                )

                if self.config['debug_mode']:
                    grid_vis = self.grid_generator.draw_grids(region_img, grids)
                    self.contour_detector.cv_show(f'Region {i + 1} Grids', grid_vis)

                answers = self.answer_detector.detect_answers(region_img_options, answer_map)
                logger.info(f"区域 {i + 1} 识别了 {len(answers)} 个答案: {answers}")

                all_answers.update(answers)
                all_answer_map.update(answer_map_offset)
                current_question += len(row_bounds)

            if len(all_answers) > total_questions:
                logger.warning(f"识别了 {len(all_answers)} 个答案，但总题数只有 {total_questions}")
                sorted_keys = sorted(all_answers.keys())
                all_answers = {k: all_answers[k] for k in sorted_keys[:total_questions]}

            if is_answer_key:
                return {
                    'success': True,
                    'answers': all_answers,
                    'warped_image': warped,
                    'threshold_image': thresh
                }

            if answer_key is None:
                raise ValueError("评分时需要提供标准答案")

            result_vis, score, detailed_scores = self.answer_grader.compare_answers(
                warped, all_answer_map, all_answers, answer_key
            )

            if self.config['debug_mode']:
                self.contour_detector.cv_show('Graded Results', result_vis)

            actual_questions = min(len(all_answers), len(answer_key))
            max_score = actual_questions * self.config['score_per_question']

            return {
                'success': True,
                'score': score,
                'max_score': max_score,
                'correct_count': int(score // self.config['score_per_question']),
                'total_questions': actual_questions,
                'answers': all_answers,
                'detailed_scores': detailed_scores,
                'result_image': result_vis,
                'warped_image': warped,
                'threshold_image': thresh
            }

        except Exception as e:
            logger.error(f"处理图像失败: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def extract_answer_key(self, image_path: str) -> Dict[str, Any]:
        """从标准答案卡图像中提取答案（支持多选题）"""
        return self.process_image(image_path, is_answer_key=True)

    def grade_answer_sheet(self, image_path: str, answer_key: Dict) -> Dict[str, Any]:
        """对学生答题卡进行评分（支持多选题）"""
        return self.process_image(image_path, answer_key, is_answer_key=False)


# 保留原有函数接口以便向后兼容
def extract_answer_key(image_path: str, total_questions: int = 120, debug_mode: bool = False) -> Dict[str, Any]:
    """从标准答案卡图像中提取答案（兼容旧接口）"""
    grader = AnswerSheetGrader({
        'total_questions': total_questions,
        'debug_mode': debug_mode
    })
    return grader.extract_answer_key(image_path)


def grade_answer_sheet(image_path: str, answer_key: Dict, total_questions: int = 120,
                       score_per_question: int = 4, multi_select_score: int = 4,
                       partial_score: bool = True, debug_mode: bool = False) -> Dict[str, Any]:
    """对学生答题卡进行评分（兼容旧接口）"""
    grader = AnswerSheetGrader({
        'total_questions': total_questions,
        'score_per_question': score_per_question,
        'multi_select_score': multi_select_score,
        'partial_score': partial_score,
        'debug_mode': debug_mode
    })
    return grader.grade_answer_sheet(image_path, answer_key)


# 使用示例
if __name__ == "__main__":
    # 包含单选题和多选题的答案键
    ANSWER_KEY = {
        # 单选题
        1: 'A', 2: 'B', 3: 'C', 4: 'D', 5: 'A',
        # 多选题
        6: ['A', 'C'],  # 必须选A和C
        7: ['B', 'D'],  # 必须选B和D
        8: 'C', 9: 'A', 10: 'B',
        11: ['A', 'B', 'C'],  # 必须选A、B、C
        12: 'D', 13: 'A', 14: 'B', 15: 'C',
    }

    image_path1  ="../answer/1.jpg"
    image_path = "../answer/1.jpg"



    # 使用类的方式
    grader = AnswerSheetGrader({
        'total_questions': 120,
        'score_per_question': 4,
        'multi_select_score': 4,
        'partial_score': True,
        'debug_mode': True,  # 设置为False可关闭调试显示
        'enable_rotation_correction': True  # 启用旋转校正
    })

    # 提取标准答案
    answer_key_result = grader.extract_answer_key(image_path1)
    if answer_key_result['success']:
        ANSWER_KEY = answer_key_result['answers']
        print(f"提取的标准答案: {ANSWER_KEY}")

    # 评分
    result = grader.grade_answer_sheet(image_path, ANSWER_KEY)
    if result['success']:
        print(
            f"总分: {result['score']:.1f}/{result['max_score']} ({result['correct_count']}/{result['total_questions']})")
        print(f"识别的答案: {result['answers']}")

        # 保存结果图像
        #if result['result_image'] is not None:
            #cv2.imwrite("graded_result.jpg", result['result_image'])
            #print("评分结果已保存为 graded_result.jpg")
    else:
        print(f"处理失败: {result['error']}")