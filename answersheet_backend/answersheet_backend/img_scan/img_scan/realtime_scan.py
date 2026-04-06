# realtime_scan.py
import os
import cv2
import time
import queue
import threading
import numpy as np
import torch
import segmentation_models_pytorch as smp
from albumentations import Compose, Resize, Lambda
from albumentations.pytorch import ToTensorV2
from train import LitModel  # 你已有的Lightning模型定义

# ---------------------------
# 预处理（与训练保持一致）
# ---------------------------
def get_preprocessing_fn():
    return smp.encoders.get_preprocessing_fn("resnet34", pretrained="imagenet")

def build_transform(input_size=(256, 256)):
    return Compose([
        Resize(*input_size),
        Lambda(image=get_preprocessing_fn()),
        ToTensorV2()
    ])

# ---------------------------
# 角点与几何工具
# ---------------------------
def order_points(pts):
    pts = np.asarray(pts, dtype=np.float32)
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1)
    rect[0] = pts[np.argmin(s)]   # tl
    rect[2] = pts[np.argmax(s)]   # br
    rect[1] = pts[np.argmin(diff)]# tr
    rect[3] = pts[np.argmax(diff)]# bl
    return rect

def largest_contour(bin_mask):
    contours, _ = cv2.findContours(bin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours: 
        return None
    return max(contours, key=cv2.contourArea)

def detect_missing_corner(pts):
    # 基于包围盒分象限判断缺角
    min_x, min_y = np.min(pts[:,0]), np.min(pts[:,1])
    max_x, max_y = np.max(pts[:,0]), np.max(pts[:,1])
    w, h = max_x - min_x, max_y - min_y

    tl = pts[(pts[:,0] < min_x + 0.3*w) & (pts[:,1] < min_y + 0.3*h)]
    tr = pts[(pts[:,0] > max_x - 0.3*w) & (pts[:,1] < min_y + 0.3*h)]
    br = pts[(pts[:,0] > max_x - 0.3*w) & (pts[:,1] > max_y - 0.3*h)]
    bl = pts[(pts[:,0] < min_x + 0.3*w) & (pts[:,1] > max_y - 0.3*h)]

    if len(tl) < 1: return "top_left", (min_x, min_y)
    if len(tr) < 1: return "top_right", (max_x, min_y)
    if len(br) < 1: return "bottom_right", (max_x, max_y)
    if len(bl) < 1: return "bottom_left", (min_x, max_y)
    return "unknown", (0, 0)

def fix_corners_from_contour(cnt):
    # 优先近似多边形
    peri = cv2.arcLength(cnt, True)
    approx = cv2.approxPolyDP(cnt, 0.01 * peri, True).reshape(-1, 2)

    if len(approx) == 4:
        return order_points(approx)

    if len(approx) == 5:
        # 缺角→外接矩形→微调补点
        miss, suggest = detect_missing_corner(approx)
        rect = cv2.minAreaRect(approx.astype(np.float32))
        box = cv2.boxPoints(rect).astype(np.int32)
        box = order_points(box)
        if miss != "unknown":
            box[0] = 0.7 * box[0] + 0.3 * np.array(suggest, dtype=np.float32)  # 微调左上（或其它）角
        return box

    # 其它数量：凸包→近似，不行再最小外接矩形
    hull = cv2.convexHull(cnt)
    peri_h = cv2.arcLength(hull, True)
    approx_h = cv2.approxPolyDP(hull, 0.02 * peri_h, True).reshape(-1, 2)
    if len(approx_h) == 4:
        return order_points(approx_h)

    rect = cv2.minAreaRect(cnt.astype(np.float32))
    box = cv2.boxPoints(rect).astype(np.int32)
    return order_points(box)

def warp_perspective(img, quad, output_size=None):
    quad = order_points(quad)
    if output_size is None:
        (tl, tr, br, bl) = quad
        wA = np.linalg.norm(br - bl)
        wB = np.linalg.norm(tr - tl)
        hA = np.linalg.norm(tr - br)
        hB = np.linalg.norm(tl - bl)
        W = int(max(wA, wB))
        H = int(max(hA, hB))
        output_size = (max(W, 10), max(H, 10))
    dst = np.array(
        [[0, 0], [output_size[0]-1, 0], [output_size[0]-1, output_size[1]-1], [0, output_size[1]-1]], 
        dtype=np.float32
    )
    M = cv2.getPerspectiveTransform(quad.astype(np.float32), dst)
    return cv2.warpPerspective(img, M, output_size)

# ---------------------------
# 简单时序稳定：顶点EMA
# ---------------------------
class CornerEMA:
    def __init__(self, alpha=0.7):
        self.alpha = alpha
        self.prev = None  # (4,2)

    def update(self, corners):
        corners = np.asarray(corners, dtype=np.float32)
        corners = order_points(corners)
        if self.prev is None:
            self.prev = corners
        else:
            self.prev = self.alpha * self.prev + (1 - self.alpha) * corners
        return self.prev.copy()

# ---------------------------
# 模型加载 / 推理
# ---------------------------
def load_model(ckpt_path):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = LitModel.load_from_checkpoint(ckpt_path)
    model.eval().to(device)
    # 半精度可选：
    use_half = (device == "cuda")
    if use_half:
        model.half()
    return model, device, use_half

def infer_mask(model, device, use_half, frame_bgr, tf, thresh=0.5, input_size=(256,256)):
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    h0, w0 = rgb.shape[:2]
    batch = tf(image=rgb)["image"].unsqueeze(0)  # [1,3,H,W] float32
    if use_half:
        batch = batch.half()
    with torch.no_grad():
        batch = batch.to(device).float() 
        logits = model(batch)              # [1,1,H,W]
        probs = torch.sigmoid(logits)
        mask = (probs[0,0].float().cpu().numpy() > thresh).astype(np.uint8) * 255
    mask = cv2.resize(mask, (w0, h0), interpolation=cv2.INTER_NEAREST)
    # 形态学清理（去噪 / 填洞）
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5,5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9,9), np.uint8))
    return mask

# ---------------------------
# 生产者-消费者：采集与推理分离
# ---------------------------
def camera_loop(cam_id, frame_q, stop_flag, width=1280, height=720):
    cap = cv2.VideoCapture(cam_id, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)  # 部分摄像头支持
    while not stop_flag.is_set():
        ok, frame = cap.read()
        if not ok: 
            time.sleep(0.01)
            continue
        if not frame_q.full():
            frame_q.put(frame)
    cap.release()

def main(
    ckpt_path="lightning_logs/version_6/checkpoints/epoch=49-step=250.ckpt",
    cam_id=0,
    input_size=(256,256),
    show_mask=True,
    show_contour=True,
    save_dir="live_results"
):
    os.makedirs(save_dir, exist_ok=True)
    model, device, use_half = load_model(ckpt_path)
    tf = build_transform(input_size)

    frame_q = queue.Queue(maxsize=2)
    stop_flag = threading.Event()
    th = threading.Thread(target=camera_loop, args=(cam_id, frame_q, stop_flag))
    th.start()

    ema = CornerEMA(alpha=0.7)
    frame_count = 0
    fps_hist = []
    last_time = time.time()

    print("[INFO] 按 q 退出，按 s 保存矫正图，按 m 切换掩码可视化，按 b 切换轮廓可视化。")
    try:
        while True:
            if frame_q.empty():
                time.sleep(0.005)
                continue
            frame = frame_q.get()
            # 如果是竖屏（高 > 宽），旋转成横屏
            if frame.shape[0] > frame.shape[1]:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            t0 = time.time()
            mask = infer_mask(model, device, use_half, frame, tf, thresh=0.5, input_size=input_size)
            cnt = largest_contour(mask)

            warped = None
            draw = frame.copy()

            if cnt is not None and cv2.contourArea(cnt) > 5000:  # 面积阈值避免噪声
                corners = fix_corners_from_contour(cnt)
                corners = ema.update(corners)
                # 画角点/轮廓
                if show_contour:
                    cv2.drawContours(draw, [cnt], -1, (0,255,0), 2)
                for (x,y) in corners.astype(int):
                    cv2.circle(draw, (x,y), 6, (0,0,255), -1)
                # 透视
                warped = warp_perspective(frame, corners)
            else:
                ema.prev = None  # 丢失目标，重置EMA

            # 拼接可视化
            vis_rows = []
            left = draw
            right = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR) if show_mask else np.zeros_like(left)
            vis = np.hstack([left, right])
            if warped is not None:
                # 把矫正图缩到同高后拼到下面
                h = vis.shape[0]//2
                scale = h / warped.shape[0]
                warped_small = cv2.resize(warped, (int(warped.shape[1]*scale), h))
                pad = np.zeros((h, vis.shape[1]-warped_small.shape[1], 3), dtype=np.uint8)
                vis = np.vstack([vis, np.hstack([warped_small, pad])])

            # FPS 统计
            t1 = time.time()
            fps = 1.0 / (t1 - t0 + 1e-6)
            fps_hist.append(fps)
            fps = int(np.mean(fps_hist[-20:]))
            cv2.putText(vis, f"FPS: {fps}", (20,40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0,255,255), 2)

            cv2.imshow("Doc Scanner (live)", vis)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s') and warped is not None:
                out_path = os.path.join(save_dir, f"scan_{int(time.time())}.png")
                cv2.imwrite(out_path, warped)
                print(f"[SAVE] {out_path}")
            elif key == ord('m'):
                show_mask = not show_mask
            elif key == ord('b'):
                show_contour = not show_contour

            frame_count += 1

    finally:
        stop_flag.set()
        th.join()
        cv2.destroyAllWindows()
        print("[INFO] 已退出实时扫描。")

if __name__ == "__main__":
    # 修改为你的 ckpt 路径
    main(
        ckpt_path="lightning_logs/version_6/checkpoints/epoch=49-step=250.ckpt",
        cam_id=0,
        input_size=(256,256),
        save_dir="live_results"
    )
