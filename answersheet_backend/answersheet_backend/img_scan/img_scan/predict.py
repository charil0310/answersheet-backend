import os
import cv2
import numpy as np
import torch
import segmentation_models_pytorch as smp
from albumentations import Compose, Resize, Lambda
from albumentations.pytorch import ToTensorV2
from .train import LitModel  # 导入训练时定义的模型类


# -------------------
# 1. 模型加载与预处理配置
# -------------------
def load_model(ckpt_path):
    """加载训练好的模型"""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = LitModel.load_from_checkpoint(ckpt_path)
    model.eval()
    model.to(device)
    return model, device


def get_preprocessing_fn():
    """获取与训练时一致的预处理函数"""
    return smp.encoders.get_preprocessing_fn("resnet34", pretrained="imagenet")


# -------------------
# 2. 图像预处理与预测
# -------------------
def preprocess_image(image_path, preprocess_fn, input_size=(256, 256)):
    """预处理输入图像（与训练时保持一致）"""
    # 读取图像并转为RGB
    image = cv2.imread(image_path)
    if image is None:
        raise FileNotFoundError(f"无法读取图像: {image_path}")

    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    original_h, original_w = image.shape[:2]

    # 定义预处理管道
    transform = Compose([
        Resize(*input_size),
        Lambda(image=preprocess_fn),
        ToTensorV2()
    ])

    # 应用预处理
    transformed = transform(image=image_rgb)
    image_tensor = transformed["image"].unsqueeze(0).type(torch.float32)  # 增加批次维度

    return image, image_tensor, (original_h, original_w)


def predict_mask(model, image_tensor, device, threshold=0.5):
    """使用模型预测分割掩码"""
    with torch.no_grad():
        image_tensor = image_tensor.to(device)
        logits = model(image_tensor)
        preds = torch.sigmoid(logits).cpu().numpy()[0, 0]  # 移除批次和通道维度

    # 应用阈值并转换为uint8
    mask = (preds > threshold).astype(np.uint8) * 255
    return mask


# -------------------
# 3. 角点检测与处理（重点修改部分）
# -------------------
def get_document_corners(mask):
    """从掩码中提取文档角点（针对5顶点答题卡优化）"""
    # 寻找轮廓（使用RETR_TREE确保捕获内部轮廓）
    contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise ValueError("未检测到轮廓")

    # 选择面积最大的轮廓（答题卡主体）
    contour = max(contours, key=cv2.contourArea)

    # 多边形逼近（调整epsilon以更好识别5边形）
    epsilon = 0.01 * cv2.arcLength(contour, True)  # 减小epsilon值提高精度
    approx = cv2.approxPolyDP(contour, epsilon, True)

    # 重塑为点列表
    pts = approx.reshape(-1, 2)
    return pts


def detect_missing_corner(pts):
    """检测缺失的角点（针对左上角缺失的情况）"""
    # 计算各点坐标特征
    min_x = np.min(pts[:, 0])
    max_x = np.max(pts[:, 0])
    min_y = np.min(pts[:, 1])
    max_y = np.max(pts[:, 1])

    # 左上角特征：x较小且y较小
    top_left_candidates = pts[(pts[:, 0] < (min_x + 0.3 * (max_x - min_x))) &
                              (pts[:, 1] < (min_y + 0.3 * (max_y - min_y)))]

    # 其他三个角的候选点
    top_right_candidates = pts[(pts[:, 0] > (max_x - 0.3 * (max_x - min_x))) &
                               (pts[:, 1] < (min_y + 0.3 * (max_y - min_y)))]
    bottom_right_candidates = pts[(pts[:, 0] > (max_x - 0.3 * (max_x - min_x))) &
                                  (pts[:, 1] > (max_y - 0.3 * (max_y - min_y)))]
    bottom_left_candidates = pts[(pts[:, 0] < (min_x + 0.3 * (max_x - min_x))) &
                                 (pts[:, 1] > (max_y - 0.3 * (max_y - min_y)))]

    # 判断哪个角点缺失（少于2个候选点视为缺失）
    if len(top_left_candidates) < 2:
        return "top_left", (min_x, min_y)  # 缺失左上角，返回建议补点坐标
    if len(top_right_candidates) < 1:
        return "top_right", (max_x, min_y)
    if len(bottom_right_candidates) < 1:
        return "bottom_right", (max_x, max_y)
    if len(bottom_left_candidates) < 1:
        return "bottom_left", (min_x, max_y)

    return "unknown", (0, 0)


def fix_corners(pts):
    """处理角点数量，确保为4个点（针对5点情况优化）"""
    # 处理5个点的情况（重点）
    if len(pts) == 5:
        print("检测到5个顶点，开始补全为矩形...")
        # 检测缺失的角点
        missing_corner, suggested_point = detect_missing_corner(pts)

        # 计算外接矩形（获取理想矩形的四个顶点）
        rect = cv2.minAreaRect(pts.astype(np.float32))
        box = cv2.boxPoints(rect).astype(np.int32)

        # 如果确认是左上角缺失，微调外接矩形顶点
        if missing_corner == "top_left":
            # 确保左上角点更合理（取外接矩形中最符合左上角特征的点）
            box_sorted = order_points(box)  # 先排序
            # 用建议点微调左上角
            box_sorted[0] = 0.7 * box_sorted[0] + 0.3 * np.array(suggested_point)
            return box_sorted.astype(np.int32)
        else:
            return box

    # 原有逻辑：处理4个点的情况
    if len(pts) == 4:
        return pts

    # 其他数量的点：使用凸包和外接矩形
    hull = cv2.convexHull(pts)
    epsilon = 0.02 * cv2.arcLength(hull, True)
    approx = cv2.approxPolyDP(hull, epsilon, True)
    fixed_pts = approx.reshape(-1, 2)

    if len(fixed_pts) != 4:
        rect = cv2.minAreaRect(pts.astype(np.float32))
        fixed_pts = cv2.boxPoints(rect).astype(np.int32)

    return fixed_pts


# -------------------
# 4. 透视变换与文档矫正
# -------------------
def order_points(pts):
    """对四点进行排序（左上、右上、右下、左下）"""
    rect = np.zeros((4, 2), dtype="float32")

    # 左上角点总和最小，右下角点总和最大
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]

    # 右上角点差最小，左下角点差最大
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]

    return rect


def warp_document(img, corners, output_size=None):
    """透视变换矫正文档"""
    # 排序角点
    rect = order_points(corners)

    # 如果未指定输出尺寸，计算原始宽高比
    if output_size is None:
        (tl, tr, br, bl) = rect
        widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
        widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
        maxWidth = max(int(widthA), int(widthB))

        heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
        heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
        maxHeight = max(int(heightA), int(heightB))

        output_size = (maxWidth, maxHeight)

    # 目标点
    dst = np.array([
        [0, 0],
        [output_size[0] - 1, 0],
        [output_size[0] - 1, output_size[1] - 1],
        [0, output_size[1] - 1]
    ], dtype="float32")

    # 计算透视变换矩阵并应用
    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(img, M, output_size)

    return warped


# -------------------
# 5. 完整处理流程（修改后的主函数）
# -------------------
def correct_document(image_path, ckpt_path=None, model=None, device=None,
                     threshold=0.5, output_size=None, save_result=False,
                     save_dir="results", return_details=False):
    """
    文档校正主函数

    参数:
        image_path: 输入图像路径
        ckpt_path: 模型权重路径（如果未提供model和device）
        model: 预加载的模型（可选）
        device: 设备（可选）
        threshold: 分割阈值
        output_size: 输出图像尺寸 (宽, 高)
        save_result: 是否保存结果图像
        save_dir: 结果保存目录
        return_details: 是否返回详细信息（原始图像、掩码、角点等）

    返回:
        校正后的图像，如果return_details=True则返回详细信息字典
    """
    # 加载模型（如果未提供）
    if model is None or device is None:
        if ckpt_path is None:
            raise ValueError("必须提供模型权重路径或预加载的模型")
        model, device = load_model(ckpt_path)
        preprocess_fn = get_preprocessing_fn()
    else:
        preprocess_fn = get_preprocessing_fn()

    # 预处理图像
    original_img, img_tensor, original_size = preprocess_image(
        image_path, preprocess_fn
    )

    # 预测掩码
    pred_mask = predict_mask(model, img_tensor, device, threshold)

    # 调整掩码尺寸以匹配原始图像
    mask_resized = cv2.resize(pred_mask, (original_size[1], original_size[0]),
                              interpolation=cv2.INTER_NEAREST)

    # 检测角点
    corners = get_document_corners(mask_resized)
    print(f"原始检测到的角点数量: {len(corners)}")

    # 处理角点确保为4个
    fixed_corners = fix_corners(corners)

    # 透视变换矫正
    warped_img = warp_document(original_img, fixed_corners, output_size)

    # 保存结果（如果需要）
    if save_result:
        os.makedirs(save_dir, exist_ok=True)

        # 绘制角点
        img_with_corners = original_img.copy()
        for (x, y) in fixed_corners:
            cv2.circle(img_with_corners, (x, y), 5, (0, 255, 0), -1)

        # 生成输出文件名
        base_name = os.path.splitext(os.path.basename(image_path))[0]

        # 保存结果
        #cv2.imwrite(os.path.join(save_dir, f"{base_name}_original_with_corners.jpg"), img_with_corners)
        #cv2.imwrite(os.path.join(save_dir, f"{base_name}_mask.png"), mask_resized)
        #cv2.imwrite(os.path.join(save_dir, f"{base_name}_warped.jpg"), warped_img)

        print(f"结果已保存至 {save_dir}")
        print(f"最终矫正使用的4个角点: {fixed_corners}")

    # 返回结果
    if return_details:
        return {
            "warped": warped_img,
            "original": original_img,
            "mask": mask_resized,
            "corners": fixed_corners
        }
    else:
        return warped_img


# -------------------
# 使用示例
# -------------------
if __name__ == "__main__":
    # 配置路径
    ckpt_path = "lightning_logs/version_6/checkpoints/epoch=49-step=250.ckpt"
    image_path = "answer/1.jpg"  # 替换为你的图像路径

    try:
        # 方式1：直接校正并返回图像（不保存）
        corrected_img = correct_document(
            image_path=image_path,
            ckpt_path=ckpt_path,
            save_result=False  # 不保存结果
        )

        # 显示结果
        cv2.imshow("Corrected Document", corrected_img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

        # 方式2：校正并保存结果
        corrected_img = correct_document(
            image_path=image_path,
            ckpt_path=ckpt_path,
            save_result=True,  # 保存结果
            save_dir="results"
        )

        # 方式3：获取详细信息
        result_details = correct_document(
            image_path=image_path,
            ckpt_path=ckpt_path,
            save_result=True,
            return_details=True  # 返回详细信息
        )

        # 访问详细信息
        warped_img = result_details["warped"]
        original_img = result_details["original"]
        mask = result_details["mask"]
        corners = result_details["corners"]

        print("处理完成！")

    except Exception as e:
        print(f"处理图像时出错: {str(e)}")