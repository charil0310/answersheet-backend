import os
import cv2
from flask import Flask, render_template, Response, send_from_directory, jsonify
from camera import CardScanner
import numpy as np
from flask import request
from flask_cors import CORS
app = Flask(__name__)
CORS(app)
# 确保模型路径正确
scanner = CardScanner("lightning_logs/version_6/checkpoints/epoch=49-step=250.ckpt")
SAVE_DIR = os.path.join("static", "scans")
os.makedirs(SAVE_DIR, exist_ok=True)

def gen_frames():
    # 优化：尝试多种摄像头API（解决不同系统/设备兼容性问题）
    # 顺序：DirectShow(Windows) → MSMF(Windows) → V4L2(Linux) → 默认
    api_list = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_V4L2, cv2.CAP_ANY]
    cap = None
    
    # 尝试打开摄像头（逐个测试API）
    for api in api_list:
        cap = cv2.VideoCapture(1, api)
        if cap.isOpened():
            print(f"使用API {api} 成功打开摄像头")
            break
    
    # 所有API都失败的情况
    if not cap or not cap.isOpened():
        print("所有API均无法打开摄像头")
        error_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(error_frame, "摄像头打开失败", (50, 240), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        cv2.putText(error_frame, "请检查设备权限", (50, 280), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        ret, buffer = cv2.imencode('.jpg', error_frame)
        error_buffer = buffer.tobytes()
        while True:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + error_buffer + b'\r\n')
    
    # 设置摄像头参数（平衡手机显示效果）
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)   # 适合手机屏幕的宽度
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)  # 适合手机屏幕的高度
    cap.set(cv2.CAP_PROP_FPS, 20)            # 降低帧率，减少延迟
    cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)       # 自动对焦（便于扫描答题卡）

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                # 帧读取失败处理
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(frame, "获取帧失败", (50, 240), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            
            # 处理帧（如果需要）
            vis, _ = scanner.process_frame(frame)
            
            # 优化JPEG编码（针对手机网络）
            # 降低质量到40%，加快传输（手机网络可能不稳定）
            ret, buffer = cv2.imencode('.jpg', vis, [cv2.IMWRITE_JPEG_QUALITY, 40])
            if not ret:
                continue
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
    finally:
        # 确保摄像头释放
        cap.release()
        print("摄像头已释放")
    
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/video_feed")
def video_feed():
    return Response(gen_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

if __name__ == "__main__":
    # 使用多线程和更高性能的服务器配置
    app.run(debug=True, threaded=True, host='0.0.0.0', port=5000)