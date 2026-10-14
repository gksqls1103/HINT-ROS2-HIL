#!/usr/bin/env python3
"""
COCO val2017 신호등 테스트셋 준비 (ROS 없이, 표준 라이브러리만 사용)

  python3 tools/coco_prepare.py                     # 신호등 있는 사진 전부 → test_imgs/coco/source
  python3 tools/coco_prepare.py --limit 20          # 시험용 20장만
  python3 tools/coco_prepare.py --calib 200         # INT8 보정용 train2017 신호등 사진 200장 → test_imgs/coco/calib

1) COCO val2017 라벨(Ultralytics YOLO 형식 coco2017labels.zip, 약 48MB)을 받는다
   - 원본 COCO 라벨 zip(약 240MB)은 이어받기가 안 돼서 이쪽을 쓴다. 박스는 같고 crowd 박스만 빠져 있다
2) traffic light(클래스 9) 박스가 있는 사진만 골라 다운로드 (val2017은 모델 학습에 쓰이지 않은 검증셋)
3) 사진 단위로 A(모델 비교용) / B(최종 확인용) 분할
--calib: 평가셋(val)과 겹치지 않는 train2017에서 신호등 사진만 무작위로 받는다 (INT8 보정용, 라벨 없음)

출력 (커밋하지 않음)
  <out>/A/000000012345.jpg     원본 사진
  <out>/A/000000012345.txt     YOLO 라벨 "0 cx cy w h" (정규화, 신호등만)
  <out>/A/labels.json          원본 픽셀 좌표 박스 [x, y, w, h] (eval_detect가 사용)
다운로드가 끊겨도 다시 실행하면 이어서 받는다.
"""
import argparse
import json
import os
import random
import struct
import sys
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

LABELS_URL = "https://github.com/ultralytics/assets/releases/download/v0.0.0/coco2017labels.zip"
LABELS_DIR = "coco/labels/{}/"
IMAGE_URL = "http://images.cocodataset.org/{}/{}"
TRAFFIC_LIGHT = 9  # COCO 80클래스 기준 (모델 출력 번호와 같음)
PKG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def download(url, path, quiet=False, retries=5):
    """끊기면 Range로 이어받는다 (서버가 지원할 때). 완료되면 .part → 최종 이름."""
    tmp = path + ".part"
    for attempt in range(retries):
        have = os.path.getsize(tmp) if os.path.exists(tmp) else 0
        req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                if have and r.status != 206:  # 이어받기 미지원 → 처음부터
                    have = 0
                total = have + int(r.headers.get("Content-Length", 0))
                with open(tmp, "ab" if have else "wb") as f:
                    done = have
                    while True:
                        buf = r.read(1 << 16)
                        if not buf:
                            break
                        f.write(buf)
                        done += len(buf)
                        if not quiet and total:
                            print(f"\r  {done >> 20}/{total >> 20} MB", end="", flush=True)
            if not quiet:
                print()
            os.replace(tmp, path)
            return
        except OSError as e:
            if attempt == retries - 1:
                raise
            if not quiet:
                print(f"\n  끊김({e}), 이어받기 재시도 {attempt + 1}/{retries - 1}")
            time.sleep(3)


def jpeg_size(path):
    """JPEG 헤더에서 (width, height)만 읽는다 (외부 라이브러리 없이)."""
    with open(path, "rb") as f:
        if f.read(2) != b"\xff\xd8":
            raise ValueError("JPEG 아님")
        while True:
            m = f.read(2)
            if len(m) < 2 or m[0] != 0xFF:
                raise ValueError("JPEG 헤더 읽기 실패")
            if m[1] in (0xD8, 0x01) or 0xD0 <= m[1] <= 0xD7:
                continue
            seg = struct.unpack(">H", f.read(2))[0]
            if 0xC0 <= m[1] <= 0xCF and m[1] not in (0xC4, 0xC8, 0xCC):  # SOF
                h, w = struct.unpack(">xHH", f.read(5))
                return w, h
            f.seek(seg - 2, 1)


def load_labels(cache_dir, split="val2017"):
    """split 라벨 중 신호등 박스만 {파일명: [(cx, cy, w, h), ...]} (정규화)."""
    zp = os.path.join(cache_dir, "coco2017labels.zip")
    if not os.path.exists(zp):
        print(f"COCO 라벨 다운로드: {LABELS_URL}")
        download(LABELS_URL, zp)
    out, prefix = {}, LABELS_DIR.format(split)
    with zipfile.ZipFile(zp) as z:
        for name in z.namelist():
            if not (name.startswith(prefix) and name.endswith(".txt")):
                continue
            boxes = []
            for line in z.read(name).decode().split("\n"):
                p = line.split()
                if len(p) == 5 and int(p[0]) == TRAFFIC_LIGHT:
                    boxes.append(tuple(float(v) for v in p[1:]))
            if boxes:
                out[os.path.basename(name)[:-4] + ".jpg"] = boxes
    return out


def fetch_all(split, files, d, workers):
    """split 사진 files를 폴더 d로 받는다. 이미 있는 파일은 건너뛴다."""
    todo = [f for f in files if not os.path.exists(os.path.join(d, f))]
    failed = []

    def fetch(f):
        try:
            download(IMAGE_URL.format(split, f), os.path.join(d, f), quiet=True)
        except OSError as e:  # 모아서 보고, 다시 실행하면 이어서 받음
            failed.append(f"{f}: {e}")

    with ThreadPoolExecutor(workers) as pool:
        for i, _ in enumerate(pool.map(fetch, todo), 1):
            print(f"\r  {i}/{len(todo)}", end="", flush=True)
    if todo:
        print()
    for msg in failed:
        print("  실패:", msg, file=sys.stderr)
    return len(todo)


def prepare_calib(cache_dir, out_dir, n, seed, workers):
    files = sorted(load_labels(cache_dir, "train2017"))
    random.Random(seed).shuffle(files)
    os.makedirs(out_dir, exist_ok=True)
    print(f"[calib] train2017 신호등 사진 {len(files)}장 중 {n}장 → {out_dir}")
    fetch_all("train2017", files[:n], out_dir, workers)
    print(f"  완료: {len([f for f in os.listdir(out_dir) if f.endswith('.jpg')])}장")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(PKG_DIR, "test_imgs", "coco", "source"))
    ap.add_argument("--split", type=float, default=0.7, help="A 세트 비율 (나머지 B)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0, help="N장만 (0=전부, 시험용)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--calib", type=int, default=0, help="INT8 보정용 train2017 사진 N장만 받기 (평가셋 준비는 안 함)")
    args = ap.parse_args()

    cache_dir = os.path.join(os.path.dirname(os.path.normpath(args.out)), "cache")
    os.makedirs(cache_dir, exist_ok=True)
    if args.calib:
        prepare_calib(cache_dir, os.path.join(os.path.dirname(os.path.normpath(args.out)), "calib"),
                      args.calib, args.seed, args.workers)
        return
    labels = load_labels(cache_dir)
    files = sorted(labels)
    print(f"traffic light: 사진 {len(files)}장, 박스 {sum(len(b) for b in labels.values())}개")

    random.Random(args.seed).shuffle(files)  # 같은 seed면 항상 같은 분할
    if args.limit:
        files = files[:args.limit]
    n_a = round(len(files) * args.split)
    sets = {"A": sorted(files[:n_a]), "B": sorted(files[n_a:])}

    for name, fs in sets.items():
        d = os.path.join(args.out, name)
        os.makedirs(d, exist_ok=True)
        print(f"[{name}] {len(fs)}장")
        fetch_all("val2017", fs, d, args.workers)

        entries = []
        for f in fs:
            path = os.path.join(d, f)
            if not os.path.exists(path):
                continue
            W, H = jpeg_size(path)
            boxes = [[round((cx - w / 2) * W, 1), round((cy - h / 2) * H, 1), round(w * W, 1), round(h * H, 1)]
                     for cx, cy, w, h in labels[f]]
            with open(path[:-4] + ".txt", "w") as t:
                t.writelines(f"0 {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n" for cx, cy, w, h in labels[f])
            entries.append({"file": f, "width": W, "height": H, "boxes": boxes})
        with open(os.path.join(d, "labels.json"), "w") as t:
            json.dump({"category": "traffic light", "box_format": "xywh_pixel", "images": entries}, t, indent=1)
        print(f"  labels.json: 사진 {len(entries)}장, 박스 {sum(len(e['boxes']) for e in entries)}개")

    print(f"완료: {args.out}")


if __name__ == "__main__":
    main()
