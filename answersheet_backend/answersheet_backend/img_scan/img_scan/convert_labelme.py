import os
import glob
import json
import numpy as np
import cv2

def convert_labelme_json(input_dir, output_mask_dir):
    os.makedirs(output_mask_dir, exist_ok=True)

    json_files = glob.glob(os.path.join(input_dir, "*.json"))
    print(f"Found {len(json_files)} json files in {input_dir}")

    for json_file in json_files:
        name = os.path.splitext(os.path.basename(json_file))[0]

        # ✅ 直接读取 JSON 文件
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        h, w = data["imageHeight"], data["imageWidth"]

        # 初始化 mask
        mask = np.zeros((h, w), dtype=np.uint8)

        # 遍历所有多边形
        for shape in data["shapes"]:
            points = np.array(shape["points"], dtype=np.int32)
            cv2.fillPoly(mask, [points], color=255)

        # 保存二值 mask
        mask_save_path = os.path.join(output_mask_dir, f"{name}.png")
        cv2.imwrite(mask_save_path, mask)
        print(f"✅ Saved {mask_save_path}")

if __name__ == "__main__":
    input_json_dir = "dataset/json"
    output_mask_dir = "dataset/masks"
    convert_labelme_json(input_json_dir, output_mask_dir)
