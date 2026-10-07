#!/usr/bin/env python3
"""노트북에서 1회 실행: COCO 사전학습 YOLO를 ONNX(320)로 변환 → models/ 에 저장 후 Pi로 복사.
   pip install ultralytics onnx onnxslim
   python3 tools/export_model.py            # yolov8n
   python3 tools/export_model.py yolo11n    # 다른 모델
"""
import os, shutil, sys
from ultralytics import YOLO

name = sys.argv[1] if len(sys.argv) > 1 else "yolov8n"
imgsz = int(sys.argv[2]) if len(sys.argv) > 2 else 320
out = YOLO(f"{name}.pt").export(format="onnx", imgsz=imgsz, opset=12)
os.makedirs("models", exist_ok=True)
dst = os.path.join("models", f"{name}_{imgsz}.onnx")
shutil.move(out, dst)
print("saved:", dst)
