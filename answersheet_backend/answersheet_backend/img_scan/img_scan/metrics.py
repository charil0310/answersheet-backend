import torch

def iou_pytorch(outputs: torch.Tensor, labels: torch.Tensor, smooth=1e-6):
    outputs = (outputs > 0.5).float()
    labels = labels.float()
    intersection = (outputs * labels).sum((1,2,3))
    union = outputs.sum((1,2,3)) + labels.sum((1,2,3)) - intersection
    iou = (intersection + smooth) / (union + smooth)
    return iou.mean()

def dice_score(outputs: torch.Tensor, labels: torch.Tensor, smooth=1e-6):
    outputs = (outputs > 0.5).float()
    labels = labels.float()
    intersection = (outputs * labels).sum((1,2,3))
    dice = (2. * intersection + smooth) / (outputs.sum((1,2,3)) + labels.sum((1,2,3)) + smooth)
    return dice.mean()
