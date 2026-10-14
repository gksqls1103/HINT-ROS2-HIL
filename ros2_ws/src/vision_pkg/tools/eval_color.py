#!/usr/bin/env python3
"""
신호등 색 판별 평가 (ROS 없이, 컨테이너에서 실행)

  cd /ros2_ws/src/vision_pkg
  python3 tools/eval_color.py                 # 세트 A, config/vision_params.yaml 의 hsv_* 값
  python3 tools/eval_color.py --set B
  python3 tools/eval_color.py --vis           # 판단이 틀린 crop 모음 이미지 저장

데이터
  사진·박스: tools/coco_prepare.py 결과 (test_imgs/coco/source/<세트>/ 사진 + labels.json)
  색 정답:   tools/coco_color_labels.csv (set, file, box, label) — 높이 32px 이상 신호등에 직접 단 라벨
             R 빨강 / Y 노랑 / G 초록 / O 꺼짐(불이 안 보임, 옆·뒷면 포함) / X 애매해서 채점 제외
정답 박스를 그대로 잘라 노드와 같은 classify_light로 판정한다 (검출 성능과 분리해 색만 채점).

지표
  색 정확도: R/Y/G/O 4종이 맞은 비율 (classify_light의 UNKNOWN = O)
  판단 정확도: GO(G) / STOP(R, Y) / NONE(O) 이 맞은 비율 (yellow_as=STOP 기준)
  꺼짐→STOP: 꺼진 신호등을 빨강·노랑으로 본 수 (불필요한 정지)
"""
import argparse
import csv
import json
import os
import sys
import time
from dataclasses import fields

import cv2
import numpy as np
import yaml

PKG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, PKG_DIR)
from vision_pkg.detector import HsvParams, classify_light  # noqa: E402

COLORS = ("R", "Y", "G", "O")
SHORT = {"RED": "R", "YELLOW": "Y", "GREEN": "G", "UNKNOWN": "O"}
SIGN = {"R": "STOP", "Y": "STOP", "G": "GO", "O": "NONE"}
DRAW = {"R": (0, 0, 255), "Y": (0, 220, 255), "G": (0, 200, 0), "O": (200, 200, 200)}


def load_hsv(path):
    """vision_params.yaml 의 vision_node hsv_<필드> 값 → HsvParams."""
    with open(path) as f:
        p = yaml.safe_load(f)["vision_node"]["ros__parameters"]
    kw = {}
    for fd in fields(HsvParams):
        v = p.get(f"hsv_{fd.name}")
        if v is not None:
            kw[fd.name] = tuple(v) if isinstance(v, list) else v
    return HsvParams(**kw)


def load_crops(src, labels_csv, set_name):
    """[(이름, crop BGR, 정답)] — 정답 X는 제외."""
    with open(os.path.join(src, set_name, "labels.json")) as f:
        boxes = {e["file"]: e["boxes"] for e in json.load(f)["images"]}
    out, images = [], {}
    with open(labels_csv) as f:
        rows = [r for r in csv.DictReader(f) if r["set"] == set_name and r["label"] != "X"]
    for r in rows:
        if r["file"] not in images:
            images[r["file"]] = cv2.imread(os.path.join(src, set_name, r["file"]))
        img = images[r["file"]]
        if img is None:
            sys.exit(f"사진 없음: {r['file']} (tools/coco_prepare.py 먼저 실행)")
        x, y, w, h = boxes[r["file"]][int(r["box"])]
        crop = img[int(y):int(round(y + h)), int(x):int(round(x + w))]
        out.append((f"{r['file'][:-4]}_{r['box']}", crop, r["label"]))
    return out


def sheet(items, path, cell=150, cols=8):
    """틀린 crop 모음: 칸 위에 '정답→추정'."""
    cells = []
    for name, crop, gt, pred in items:
        s = (cell - 26) / max(crop.shape[:2])
        t = cv2.resize(crop, (max(1, int(crop.shape[1] * s)), max(1, int(crop.shape[0] * s))),
                       interpolation=cv2.INTER_CUBIC)
        c = np.full((cell, cell, 3), 40, np.uint8)
        oy, ox = 24 + (cell - 26 - t.shape[0]) // 2, (cell - t.shape[1]) // 2
        c[oy:oy + t.shape[0], ox:ox + t.shape[1]] = t
        cv2.putText(c, f"{gt}->{pred}", (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, DRAW[pred], 2, cv2.LINE_AA)
        cv2.putText(c, name[-8:], (4, cell - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (160, 160, 160), 1, cv2.LINE_AA)
        cells.append(c)
    cells += [np.full((cell, cell, 3), 40, np.uint8)] * (-len(cells) % cols)
    cv2.imwrite(path, np.vstack([np.hstack(cells[i:i + cols]) for i in range(0, len(cells), cols)]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="A", choices=("A", "B"))
    ap.add_argument("--src", default=os.path.join(PKG_DIR, "test_imgs", "coco", "source"))
    ap.add_argument("--labels", default=os.path.join(PKG_DIR, "tools", "coco_color_labels.csv"))
    ap.add_argument("--params", default=os.path.join(PKG_DIR, "config", "vision_params.yaml"))
    ap.add_argument("--out", default=os.path.join(PKG_DIR, "result", "eval_color"))
    ap.add_argument("--vis", action="store_true", help="판단이 틀린 crop 모음 이미지 저장")
    args = ap.parse_args()

    hsv = load_hsv(args.params)
    crops = load_crops(args.src, args.labels, args.set)
    cm = {(g, p): 0 for g in COLORS for p in COLORS}
    wrong, ms = [], []
    for name, crop, gt in crops:
        t0 = time.perf_counter()
        pred = SHORT[classify_light(crop, hsv)[0]]
        ms.append((time.perf_counter() - t0) * 1000)
        cm[(gt, pred)] += 1
        if SIGN[pred] != SIGN[gt]:
            wrong.append((name, crop, gt, pred))

    n = len(crops)
    color_ok = sum(cm[(c, c)] for c in COLORS)
    sign_ok = n - len(wrong)
    off_stop = cm[("O", "R")] + cm[("O", "Y")]
    print(f"[세트 {args.set}] 신호등 {n}개, HSV {args.params}")
    print(f"  색 정확도 {color_ok / n:.1%} ({color_ok}/{n}), 판단 정확도 {sign_ok / n:.1%} ({sign_ok}/{n})")
    print(f"  꺼짐→STOP {off_stop}개, 판정 시간 median {np.median(ms):.2f} ms / p95 {np.percentile(ms, 95):.2f} ms")
    print("  정답\\추정    " + "".join(f"{p:>5}" for p in COLORS))
    for g in COLORS:
        tot = sum(cm[(g, p)] for p in COLORS)
        if tot:
            print(f"  {g} ({tot:3d}개)  " + "".join(f"{cm[(g, p)]:>5}" for p in COLORS) + f"   맞음 {cm[(g, g)] / tot:.0%}")

    if args.vis and wrong:
        os.makedirs(args.out, exist_ok=True)
        path = os.path.join(args.out, f"wrong_{args.set}.png")
        sheet(wrong, path)
        print(f"  틀린 {len(wrong)}개: {path}")


if __name__ == "__main__":
    main()
