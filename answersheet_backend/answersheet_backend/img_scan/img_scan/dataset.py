import os
import cv2
import numpy as np
from torch.utils.data import Dataset
from PIL import Image  # 补充缺失的import
import torch  # 补充缺失的import

class SegmentationDataset(Dataset):
    def __init__(self, img_dir, mask_dir, id_list, transform=None):  # 添加transform参数
        self.img_dir = img_dir
        self.mask_dir = mask_dir
        self.ids = id_list
        self.transform = transform  # 保存transform

    def __len__(self):
        return len(self.ids)

    def __getitem__(self, idx):
        img_id = self.ids[idx]
        img_path = os.path.join(self.img_dir, img_id + ".jpg")
        mask_path = os.path.join(self.mask_dir, img_id + ".png")

        # 读图
        image = Image.open(img_path).convert("RGB")
        mask = Image.open(mask_path).convert("L")  # 灰度图（单通道）

        # 转为numpy数组（供transform使用）
        image = np.array(image)
        mask = np.array(mask)

        # 应用数据增强
        # 在dataset.py中修改transform应用部分
        if self.transform is not None:
            transformed = self.transform(image=image, mask=mask)
            image = transformed["image"].type(torch.float32)  # 强制转为float32
            mask = transformed["mask"].type(torch.float32)    # 强制转为float32
            mask = mask.unsqueeze(0) / 255.0
        else:
            # 若无transform，同样显式指定float32
            image = image.astype(np.float32) / 255.0
            mask = mask.astype(np.float32)
            image = torch.from_numpy(image).permute(2, 0, 1).type(torch.float32)
            mask = torch.from_numpy(mask).unsqueeze(0) / 255.0 .type(torch.float32)

        return image, mask