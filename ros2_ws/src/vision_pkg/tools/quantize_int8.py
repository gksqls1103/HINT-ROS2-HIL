#!/usr/bin/env python3
"""
YOLO ONNX → INT8 정적 양자화 (Pi 호스트에서 실행, onnx 패키지가 필요해 컨테이너가 아닌 venv 사용)

  ~/.venvs/yolo-export/bin/python tools/quantize_int8.py models/yolo11n_640.onnx
  nice taskset -c 1-3 ~/.venvs/yolo-export/bin/python ...   # 3코어만 사용 (전체 부하로 Pi가 꺼진 적 있음)
  → models/yolo11n_640_int8.onnx (이름은 --out으로 변경)

- 보정 데이터: tools/coco_prepare.py --calib 200 으로 받은 train2017 사진 (평가셋 val과 겹치지 않음)
- 전처리는 노드와 같은 YoloOnnx letterbox를 그대로 쓴다
- opset 12 모델은 13으로 올린다 (채널별 양자화의 DequantizeLinear axis는 opset 13부터)
- 보정은 MinMax만 쓴다. Percentile/Entropy는 모든 중간 출력을 메모리에 쌓아 640 입력에서 Pi가 멈췄다.
  MinMax도 16장마다 중간 출력을 비워 메모리 사용량을 제한한다
- Detect head의 디코딩(DFL, Concat, 박스 계산, 점수 Sigmoid)은 FP32로 둔다.
  출력 하나에 박스 좌표(0~640)와 점수(0~1)가 섞여 있어 INT8 눈금 하나로 묶으면 점수가 0으로 뭉개진다
"""
import argparse
import glob
import os
import re
import sys
import tempfile

import cv2
import numpy as np
import onnx
from onnx import version_converter
from onnxruntime.quantization import (CalibrationDataReader, CalibrationMethod, QuantFormat, QuantType,
                                      quantize_static)
from onnxruntime.quantization.shape_inference import quant_pre_process

PKG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, PKG_DIR)
from vision_pkg.detector import YoloOnnx  # noqa: E402



class Reader(CalibrationDataReader):
    def __init__(self, yolo, files):
        self.yolo, self.files, self.name = yolo, iter(files), yolo.input_name

    def get_next(self):
        f = next(self.files, None)
        if f is None:
            return None
        canvas = self.yolo._letterbox(cv2.imread(f))[0]
        x = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        return {self.name: np.transpose(x, (2, 0, 1))[None]}


def head_nodes(model, last_conv):
    """Detect head(마지막 /model.N/) 중 FP32로 남길 노드: 디코딩 전부 (+ 각 출력 가지의 마지막 Conv)."""
    names = [n.name for n in model.graph.node]
    head = max({int(m.group(1)) for n in names if (m := re.match(r"/model\.(\d+)/", n))})
    p = f"/model.{head}/"
    out = [n for n in names if n.startswith(p) and not re.match(rf"{re.escape(p)}cv[234]\.", n)]
    if last_conv:
        out += [n for n in names if re.match(rf"{re.escape(p)}cv[234]\.\d+/cv[234]\.\d+\.2/Conv", n)]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model", help="FP32 ONNX (models/ 안 파일 이름 또는 경로)")
    ap.add_argument("--out", help="출력 경로 (기본: <모델>_int8.onnx)")
    ap.add_argument("--calib", default=os.path.join(PKG_DIR, "test_imgs", "coco", "calib"))
    ap.add_argument("--num", type=int, default=200, help="보정에 쓸 사진 수")
    ap.add_argument("--act", choices=("s8", "u8"), default="s8", help="activation 타입 (Pi 5에서 s8이 더 빠름)")
    ap.add_argument("--exclude-last-conv", action="store_true", help="출력 가지의 마지막 Conv도 FP32로")
    args = ap.parse_args()

    src = args.model if os.path.exists(args.model) else os.path.join(PKG_DIR, "models", args.model)
    out = args.out or os.path.splitext(src)[0] + "_int8.onnx"
    files = sorted(glob.glob(os.path.join(args.calib, "*.jpg")))[:args.num]
    if not files:
        sys.exit(f"보정 사진 없음: {args.calib} (tools/coco_prepare.py --calib 200 먼저 실행)")

    with tempfile.TemporaryDirectory() as tmp:
        m = onnx.load(src)
        if m.opset_import[0].version < 13:
            m = version_converter.convert_version(m, 13)
        op13 = os.path.join(tmp, "op13.onnx")
        onnx.save(m, op13)
        pre = os.path.join(tmp, "pre.onnx")
        quant_pre_process(op13, pre)
        exclude = head_nodes(onnx.load(pre), args.exclude_last_conv)
        yolo = YoloOnnx(src, threads=4)
        print(f"{os.path.basename(src)} (imgsz {yolo.imgsz}) 보정 {len(files)}장, MinMax, act {args.act}, "
              f"FP32 유지 노드 {len(exclude)}개")
        quantize_static(pre, out, Reader(yolo, files), quant_format=QuantFormat.QDQ, per_channel=True,
                        activation_type=QuantType.QInt8 if args.act == "s8" else QuantType.QUInt8,
                        weight_type=QuantType.QInt8, calibrate_method=CalibrationMethod.MinMax,
                        nodes_to_exclude=exclude, extra_options={"CalibMaxIntermediateOutputs": 16})
    print(f"저장: {out} ({os.path.getsize(out) / 1e6:.1f} MB, 원본 {os.path.getsize(src) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
