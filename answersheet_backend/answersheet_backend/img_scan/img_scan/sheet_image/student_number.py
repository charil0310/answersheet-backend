# -*- coding: utf-8 -*-
import cv2
import numpy as np
import os
import pandas as pd
from .. import predict
os.environ['OMP_NUM_THREADS'] = '1'


# ========================== #
#    一、右上角学号区域裁剪
# ========================== #
class StudentIDCutter:
    def __init__(self):
        # 学号区域比例
        self.x_ratio_start = 0.525
        self.x_ratio_end = 0.92
        self.y_ratio_start = 0.07
        self.y_ratio_end = 0.27
        # 黑块区域比例
        self.black_ratio_start = 0.92
        self.black_ratio_end = 1

    def cut_id_region(self, image_path, show=False):
        """裁剪学号区域和黑块区域"""
        if isinstance(image_path, str):
            image = cv2.imread(image_path)
            if image is None:
                raise ValueError(f"无法加载图像: {image_path}")
        elif isinstance(image_path, np.ndarray):
            image = image_path.copy()  # 直接使用传入的图像数组
        else:
            raise TypeError("image_input必须是文件路径（str）或ndarray图像数组")

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]

        # 学号区域
        x1 = int(w * self.x_ratio_start)
        x2 = int(w * self.x_ratio_end)
        y1 = int(h * self.y_ratio_start)
        y2 = int(h * self.y_ratio_end)
        id_region = gray[y1:y2, x1:x2]

        # 黑块区域
        bx1 = int(w * self.black_ratio_start)
        bx2 = int(w * self.black_ratio_end)
        black_region = gray[y1:y2, bx1:bx2]

        if show:
            vis = image.copy()
            cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(vis, "ID Region", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            cv2.imshow("Detected ID Region", vis)
            cv2.imshow("Cropped ID Region", id_region)
            cv2.imshow("Black Strip Region", black_region)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

        return id_region, black_region


# ========================== #
#    二、学号识别模块
# ========================== #
class StudentIDRecognizer:
    def otsu_thresholding(self, img):
        """Otsu二值化"""
        _, thresh = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return thresh

    def get_black_rows(self, black_region, show=False):
        """自适应识别黑块行位置"""
        thresh = self.otsu_thresholding(black_region)
        h, w = thresh.shape
        row_sums = np.sum(thresh, axis=1)

        # 简单峰值检测
        threshold = np.max(row_sums) * 0.5
        black_rows = np.where(row_sums > threshold)[0]

        # 合并连续行
        boundaries = []
        if len(black_rows) == 0:
            # fallback: 均分10行
            cell_h = h // 10
            for i in range(10):
                boundaries.append((i * cell_h, (i + 1) * cell_h))
        else:
            start = black_rows[0]
            for i in range(1, len(black_rows)):
                if black_rows[i] != black_rows[i - 1] + 1:
                    boundaries.append((start, black_rows[i - 1]))
                    start = black_rows[i]
            boundaries.append((start, black_rows[-1]))

        if show:
            vis = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)
            for y1, y2 in boundaries:
                cv2.rectangle(vis, (0, y1), (w - 1, y2), (0, 0, 255), 1)
            cv2.imshow("Black Blocks Visualization", vis)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

        return boundaries

    def recognize_id(self, id_region, black_region, num_cols=10, show=False):
        """根据黑块行自适应识别学号"""
        h, w = id_region.shape
        col_w = w // num_cols

        row_boundaries = self.get_black_rows(black_region, show=show)
        thresh = self.otsu_thresholding(id_region)

        student_id_digits = []

        vis = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR) if show else None

        for col in range(num_cols):
            max_fill = -1
            selected_row = None
            x1 = col * col_w
            for i, (y1, y2) in enumerate(row_boundaries):
                roi = thresh[y1:y2, x1:x1 + col_w]
                fill = cv2.countNonZero(roi)
                if fill > max_fill:
                    max_fill = fill
                    selected_row = i
            digit = selected_row if selected_row is not None else 0
            student_id_digits.append(str(digit))

            if show:
                y1, y2 = row_boundaries[selected_row]
                cv2.rectangle(vis, (x1, y1), (x1 + col_w, y2), (0, 0, 255), 1)

        if show:
            cv2.imshow("ID Region with Rows", vis)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

        return "".join(student_id_digits)


# ========================== #
#    三、主流程
# ========================== #
class StudentIDPipeline:
    def __init__(self):
        self.cutter = StudentIDCutter()
        self.recognizer = StudentIDRecognizer()

    def process_single_image(self, image_path, show=False):

            id_region, black_region = self.cutter.cut_id_region(image_path, show=show)
            student_id = self.recognizer.recognize_id(id_region, black_region, show=show)
            return student_id



# ========================== #
#    四、单个图片识别函数
# ========================== #
def process_single_image(image_path, show=False):
    """
    识别单个图片的学号

    Args:
        image_path: 图片文件路径
        show: 是否显示中间处理结果

    Returns:
        student_id: 识别出的学号字符串
    """
    pipeline = StudentIDPipeline()
    student_id = pipeline.process_single_image(image_path, show=show)
    return student_id


# ========================== #
#    五、批量识别 + Excel保存（保留作为可选功能）
# ========================== #
def batch_process(folder_path, output_excel="student_ids.xlsx", show=False):
    """批量处理文件夹中的所有图片（可选功能）"""
    pipeline = StudentIDPipeline()
    valid_ext = {".jpg", ".jpeg", ".png", ".bmp"}
    results = []

    for fname in os.listdir(folder_path):
        fpath = os.path.join(folder_path, fname)
        if not os.path.isfile(fpath):
            continue
        ext = os.path.splitext(fname)[-1].lower()
        if ext not in valid_ext:
            continue
        sid = pipeline.process_single_image(fpath, show=show)
        results.append({"文件名": fname, "学号": sid})

    df = pd.DataFrame(results)
    output_path = os.path.join(folder_path, output_excel)
    df.to_excel(output_path, index=False)
    print(f"\n批量识别完成，结果保存到：{output_path}")


# ========================== #
#    六、运行示例
# ========================== #
if __name__ == "__main__":
    # 单个图片识别示例
    image_path = predict.correct_document(
        image_path="../answer/6.jpg",
        ckpt_path="../lightning_logs/version_6/checkpoints/epoch=49-step=250.ckpt",
        save_result=False )  # 替换为你的图片路径
    student_id = process_single_image(image_path, show=True)
    print(f"识别结果: {student_id}")

    # 如果需要批量处理，取消下面的注释
    # folder_path = "picture"
    # batch_process(folder_path, show=False)