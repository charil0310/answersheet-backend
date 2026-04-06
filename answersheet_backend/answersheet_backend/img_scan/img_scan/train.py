import torch
import pytorch_lightning as pl
import segmentation_models_pytorch as smp
from torch.utils.data import DataLoader
from .dataset import SegmentationDataset
from .metrics import iou_pytorch, dice_score
import albumentations as A
from albumentations.pytorch import ToTensorV2

# 新增：加载ID列表的函数
def load_id_list(file_path):
    """从文本文件读取图像ID列表"""
    with open(file_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f.readlines() if line.strip()]

class LitModel(pl.LightningModule):
    def __init__(self):
        super().__init__()
        # 定义模型时指定预处理器（关键：确保与预训练权重匹配）
        self.model = smp.Unet(
            encoder_name="resnet34",
            encoder_weights="imagenet",
            in_channels=3,
            classes=1
        )
        self.loss_fn = smp.losses.DiceLoss(smp.losses.BINARY_MODE, from_logits=True)

    def forward(self, x):
        return self.model(x)

    def training_step(self, batch, batch_idx):
        imgs, masks = batch
        logits = self(imgs)
        loss = self.loss_fn(logits, masks)
        preds = torch.sigmoid(logits)
        iou = iou_pytorch(preds, masks)
        dice = dice_score(preds, masks)
        
        self.log("train_loss", loss, on_step=False, on_epoch=True)
        self.log("train_iou", iou, on_step=False, on_epoch=True)
        self.log("train_dice", dice, on_step=False, on_epoch=True)
        return loss

    def validation_step(self, batch, batch_idx):
        imgs, masks = batch
        logits = self(imgs)
        loss = self.loss_fn(logits, masks)
        preds = torch.sigmoid(logits)
        iou = iou_pytorch(preds, masks)
        dice = dice_score(preds, masks)
        
        self.log("val_loss", loss, prog_bar=True)
        self.log("val_iou", iou, prog_bar=True)
        self.log("val_dice", dice, prog_bar=True)
        return loss

    def configure_optimizers(self):
        return torch.optim.Adam(self.parameters(), lr=1e-3)

if __name__ == "__main__":
    # 关键修复：加载模型对应的预处理器（ImageNet标准化）
    preprocess_fn = smp.encoders.get_preprocessing_fn(
        encoder_name="resnet34", 
        pretrained="imagenet"
    )

    # 加载训练集和验证集ID列表
    train_ids = load_id_list("dataset/train.txt")
    val_ids = load_id_list("dataset/val.txt")

    # 数据增强配置（添加标准化步骤）
    train_tf = A.Compose([
        A.Resize(256, 256),
        A.HorizontalFlip(p=0.5),
        A.RandomBrightnessContrast(p=0.2),
        # 应用预处理器：将图像标准化为ImageNet分布（关键步骤）
        A.Lambda(image=preprocess_fn),
        ToTensorV2()  # 转为float32 tensor，通道顺序(C,H,W)
    ])
    val_tf = A.Compose([
        A.Resize(256, 256),
        A.Lambda(image=preprocess_fn),  # 验证集同样需要标准化
        ToTensorV2()
    ])

    # 实例化数据集
    train_dataset = SegmentationDataset(
        img_dir="dataset/images",
        mask_dir="dataset/masks",
        id_list=train_ids,
        transform=train_tf
    )
    val_dataset = SegmentationDataset(
        img_dir="dataset/images",
        mask_dir="dataset/masks",
        id_list=val_ids,
        transform=val_tf
    )

    # 数据加载器
    train_loader = DataLoader(
        train_dataset,
        batch_size=8,
        shuffle=True,
        num_workers=4,
        persistent_workers=True
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=8,
        shuffle=False,
        num_workers=4,
        persistent_workers=True
    )

    # 模型训练
    model = LitModel()
    trainer = pl.Trainer(
        max_epochs=50,
        accelerator="gpu" if torch.cuda.is_available() else "cpu",
        log_every_n_steps=10
    )
    trainer.fit(model, train_loader, val_loader)