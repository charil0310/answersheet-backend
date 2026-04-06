# make_split.py
import os
import random

img_dir = "dataset/images"
out_train = "dataset/train.txt"
out_val = "dataset/val.txt"

all_files = [os.path.splitext(f)[0] for f in os.listdir(img_dir) if f.endswith(".jpg")]
all_files.sort()
random.seed(42)
random.shuffle(all_files)

# 8:2 划分
split_idx = int(len(all_files) * 0.8)
train_files = all_files[:split_idx]
val_files = all_files[split_idx:]

with open(out_train, "w") as f:
    f.write("\n".join(train_files))
with open(out_val, "w") as f:
    f.write("\n".join(val_files))

print(f"Train size: {len(train_files)}, Val size: {len(val_files)}")
