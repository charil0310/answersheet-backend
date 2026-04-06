import cv2
import torch
import numpy as np
from albumentations import Compose, Resize, Normalize
from albumentations.pytorch import ToTensorV2
from train import LitModel  # 你的Lightning模型定义


def order_points(pts):
    pts = np.asarray(pts, dtype=np.float32)
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1)
    rect[0] = pts[np.argmin(s)]   # 左上角
    rect[2] = pts[np.argmax(s)]   # 右下角
    rect[1] = pts[np.argmin(d)]   # 右上角
    rect[3] = pts[np.argmax(d)]   # 左下角
    return rect


def fix_corners(pts):
    # 优化轮廓处理速度
    if len(pts) < 4:
        return None
    hull = cv2.convexHull(pts)
    eps = 0.03 * cv2.arcLength(hull, True)  # 调整逼近精度，加快计算
    approx = cv2.approxPolyDP(hull, eps, True).reshape(-1, 2).astype(np.float32)
    
    if len(approx) == 4:
        return order_points(approx)
    # 最小外接矩形计算优化
    rect = cv2.minAreaRect(pts)
    box = cv2.boxPoints(rect).astype(np.float32)
    return order_points(box)


def warp_document(img, corners):
    quad = order_points(corners)
    (tl, tr, br, bl) = quad
    # 简化宽高计算
    W = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    H = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    dst = np.array([[0, 0], [W-1, 0], [W-1, H-1], [0, H-1]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(quad, dst)
    return cv2.warpPerspective(img, M, (W, H))


class CornerEMA:
    def __init__(self, alpha=0.7):
        self.alpha = alpha
        self.prev = None

    def reset(self):
        self.prev = None

    def update(self, corners):
        if corners is None:
            self.reset()
            return None
        corners = order_points(corners.astype(np.float32))
        if self.prev is None:
            self.prev = corners
        else:
            self.prev = self.alpha * self.prev + (1 - self.alpha) * corners
        return self.prev.copy()


class CardScanner:
    def __init__(self, ckpt_path, input_size=(128, 128), infer_interval=2):  # 减小输入尺寸，提高推理速度
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = LitModel.load_from_checkpoint(ckpt_path).to(self.device).eval()
        self.tf = Compose([
            Resize(*input_size),
            Normalize(),
            ToTensorV2()
        ])
        self.ema = CornerEMA(alpha=0.7)
        self.last_warped = None
        self.last_corners = None
        self.frame_count = 0
        self.infer_interval = infer_interval  # 减少推理频率

    def _infer_mask(self, frame_bgr):
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        h0, w0 = rgb.shape[:2]
        # 图像预处理优化
        batch = self.tf(image=rgb)["image"].unsqueeze(0).to(self.device, dtype=torch.float32)
        with torch.no_grad():
            # 推理速度优化：使用半精度（如果支持）
            if self.device == "cuda":
                batch = batch.half()
                logits = self.model(batch).float()
            else:
                logits = self.model(batch)
            prob = torch.sigmoid(logits)[0, 0].cpu().numpy()
        mask = (prob > 0.5).astype(np.uint8) * 255
        return cv2.resize(mask, (w0, h0), interpolation=cv2.INTER_NEAREST)

    def process_frame(self, frame_bgr):
        # 若输入帧为空，重置状态
        if frame_bgr is None or np.mean(frame_bgr) < 5:  # 均值接近0的视为无效帧
            self.ema.reset()
            self.last_corners = None
            self.last_warped = None
            return frame_bgr, None  # 直接返回原帧，不处理

        vis = frame_bgr.copy()
        self.frame_count += 1
        corners = None

        if self.frame_count % self.infer_interval == 0:
            mask = self._infer_mask(frame_bgr)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                # 只处理最大轮廓，减少计算
                cnt = max(contours, key=cv2.contourArea)
                if cv2.contourArea(cnt) > 5000:  # 增大面积阈值，过滤小噪声
                    approx = cv2.approxPolyDP(cnt, 0.01 * cv2.arcLength(cnt, True), True).reshape(-1, 2)
                    corners = fix_corners(approx)
                    corners = self.ema.update(corners)
                    self.last_corners = corners
                else:
                    self.ema.reset()
                    self.last_corners = None
            else:
                self.ema.reset()
                self.last_corners = None
        else:
            corners = self.last_corners

        # 绘制矩形（仅当检测到有效角点）
        if corners is not None:
            poly = corners.astype(np.int32).reshape(-1, 1, 2)
            cv2.polylines(vis, [poly], True, (255, 200, 100), 2, cv2.LINE_AA)
            self.last_warped = warp_document(frame_bgr, corners)
        else:
            self.last_warped = None

        return vis, self.last_warped

    def reset(self):
        """重置所有状态（摄像头异常时调用）"""
        self.ema.reset()
        self.last_corners = None
        self.last_warped = None
        self.frame_count = 0