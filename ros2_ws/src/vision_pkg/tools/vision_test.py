#!/usr/bin/env python3
"""
Vision 단독 테스트 (ROS2 없이 실행 가능)

예시
  # 1) Pi 카메라로 찍은 사진 폴더 검증 (노트북, GUI 없이 결과 저장)
  python3 tools/vision_test.py --model models/yolov8n_320.onnx --source test_imgs/ --nogui --out result/

  # 2) 컨테이너 안에서 가상 카메라 실시간 확인 (GUI 없으면 --nogui로 콘솔 출력)
  python3 tools/vision_test.py --model models/yolov8n_320.onnx --source /dev/video0 --nogui

  # 3) HSV 캘리브레이션 (GUI 필요, 트랙바로 값 조정 후 q → 값 출력)
  #    사진 폴더도 가능: n 키로 다음 사진. 컨테이너에 화면이 없으면 저장한 사진을 노트북에서 캘리브레이션
  python3 tools/vision_test.py --model models/yolov8n_320.onnx --source test_imgs/ --calib
"""
import argparse
import glob
import os
import sys
import time

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from vision_pkg.detector import (  # noqa: E402
    CLS_TRAFFIC_LIGHT, SignDebouncer, VisionParams, YoloOnnx, classify_light, color_masks,
    decide_sign, draw)

IMG_EXT = (".jpg", ".jpeg", ".png", ".bmp")


def open_source(src):
    if os.path.isdir(src):
        files = sorted(f for f in glob.glob(os.path.join(src, "*")) if f.lower().endswith(IMG_EXT))
        return "images", files
    if src.lower().endswith(IMG_EXT):
        return "images", [src]
    dev = int(src) if src.isdigit() else src
    cap = cv2.VideoCapture(dev, cv2.CAP_V4L2) if isinstance(dev, str) and dev.startswith("/dev/") \
        else cv2.VideoCapture(dev)
    if not cap.isOpened():
        sys.exit(f"[ERR] 입력을 열 수 없음: {src}")
    return "stream", cap


def run_images(files, model, vp, args):
    if args.out:
        os.makedirs(args.out, exist_ok=True)
    for f in files:
        img = cv2.imread(f)
        if img is None:
            print(f"[SKIP] {f}")
            continue
        t0 = time.time()
        dets = model.detect(img, vp.conf_thres, vp.nms_thres)
        sign = decide_sign(img, dets, vp)
        ms = (time.time() - t0) * 1000
        h, w = img.shape[:2]
        info = ", ".join(f"{d.name}({d.conf:.2f},{d.color or '-'},area={d.area_ratio(w, h):.3f})"
                         for d in dets) or "검출 없음"
        print(f"{os.path.basename(f):30s} → {sign:5s} | {ms:6.1f} ms | {info}")
        vis = draw(img, dets, sign)
        if args.out:
            cv2.imwrite(os.path.join(args.out, os.path.basename(f)), vis)
        if not args.nogui:
            cv2.imshow("vision_test", vis)
            if cv2.waitKey(0) & 0xFF == ord("q"):
                break


def run_stream(cap, model, vp, args):
    deb = SignDebouncer(args.window, args.votes)
    last_print, n, t_start = 0, 0, time.time()
    fps = 0.0
    while True:
        ok, img = cap.read()
        if not ok:
            print("[WARN] 프레임 읽기 실패")
            time.sleep(0.1)
            continue
        dets = model.detect(img, vp.conf_thres, vp.nms_thres)
        raw = decide_sign(img, dets, vp)
        sign = deb.update(raw)
        n += 1
        el = time.time() - t_start
        if el >= 1.0:
            fps, n, t_start = n / el, 0, time.time()
        if time.time() - last_print > 0.5:
            print(f"raw={raw:5s} debounced={sign:5s} fps={fps:4.1f} dets="
                  + ", ".join(f"{d.name}:{d.conf:.2f}:{d.color or '-'}" for d in dets))
            last_print = time.time()
        if not args.nogui:
            cv2.imshow("vision_test", draw(img, dets, sign, fps))
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break


def run_calib(get_frame, model, vp, on_next=None):
    """트랙바로 HSV / conf 조정. 신호등 crop과 각 색 마스크를 함께 보여준다.
    get_frame(): 현재 프레임 반환, on_next(): (사진 모드) n 키로 다음 사진"""
    win = "calib"
    cv2.namedWindow(win)
    p = vp.hsv
    bars = {
        "conf x100": (int(vp.conf_thres * 100), 100),
        "red1_hi": (p.red1[1], 30), "red2_lo": (p.red2[0], 179),
        "yel_lo": (p.yellow[0], 60), "yel_hi": (p.yellow[1], 60),
        "grn_lo": (p.green[0], 120), "grn_hi": (p.green[1], 120),
        "s_min": (p.s_min, 255), "v_min": (p.v_min, 255),
        "ratio x1000": (int(p.min_ratio * 1000), 300),
    }
    for k, (v, mx) in bars.items():
        cv2.createTrackbar(k, win, v, mx, lambda _: None)

    while True:
        img = get_frame()
        if img is None:
            continue
        g = lambda k: cv2.getTrackbarPos(k, win)  # noqa: E731
        vp.conf_thres = max(0.01, g("conf x100") / 100)
        p.red1 = (0, g("red1_hi"))
        p.red2 = (g("red2_lo"), 179)
        p.yellow = (g("yel_lo"), g("yel_hi"))
        p.green = (g("grn_lo"), g("grn_hi"))
        p.s_min, p.v_min = g("s_min"), g("v_min")
        p.min_ratio = g("ratio x1000") / 1000

        dets = model.detect(img, vp.conf_thres, vp.nms_thres)
        sign = decide_sign(img, dets, vp)
        cv2.imshow("vision_test", draw(img, dets, sign))

        lights = [d for d in dets if d.cls_id == CLS_TRAFFIC_LIGHT]
        if lights:
            d = max(lights, key=lambda d: (d.box[2] - d.box[0]) * (d.box[3] - d.box[1]))
            x1, y1, x2, y2 = d.box
            crop = img[y1:y2, x1:x2]
            if crop.size:
                crop = cv2.resize(crop, (120, int(120 * crop.shape[0] / max(1, crop.shape[1]))))
                m = color_masks(crop, p)
                color, ratios = classify_light(crop, p)
                row = [crop] + [cv2.cvtColor(m[k], cv2.COLOR_GRAY2BGR) for k in ("RED", "YELLOW", "GREEN")]
                cv2.imshow("crop | RED | YELLOW | GREEN", cv2.hconcat(row))
                cv2.setWindowTitle("calib", f"calib  {color}  " +
                                   " ".join(f"{k}={v:.3f}" for k, v in ratios.items()))

        key = cv2.waitKey(30) & 0xFF
        if key == ord("q"):
            break
        if key == ord("n") and on_next:
            on_next()

    print("\n# ---- config/vision_params.yaml 에 옮길 값 ----")
    print(f"conf_thres: {vp.conf_thres:.2f}")
    print(f"hsv_red1: [{p.red1[0]}, {p.red1[1]}]\nhsv_red2: [{p.red2[0]}, {p.red2[1]}]")
    print(f"hsv_yellow: [{p.yellow[0]}, {p.yellow[1]}]\nhsv_green: [{p.green[0]}, {p.green[1]}]")
    print(f"hsv_s_min: {p.s_min}\nhsv_v_min: {p.v_min}\nhsv_min_ratio: {p.min_ratio:.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="ONNX 모델 경로")
    ap.add_argument("--source", required=True, help="이미지 파일/폴더, /dev/videoX, 카메라 번호, 영상 파일")
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--min-area", type=float, default=0.002)
    ap.add_argument("--yellow-as", default="STOP", choices=["STOP", "NONE"])
    ap.add_argument("--window", type=int, default=5)
    ap.add_argument("--votes", type=int, default=3)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--nogui", action="store_true", help="화면 없이 콘솔 출력만")
    ap.add_argument("--out", help="(이미지 모드) 결과 이미지 저장 폴더")
    ap.add_argument("--calib", action="store_true", help="HSV 캘리브레이션 모드 (GUI 필요)")
    args = ap.parse_args()

    vp = VisionParams(conf_thres=args.conf, min_area_ratio=args.min_area, yellow_as=args.yellow_as)
    model = YoloOnnx(args.model)
    kind, src = open_source(args.source)

    if kind == "images" and args.calib:
        imgs = [cv2.imread(f) for f in src]
        imgs = [i for i in imgs if i is not None]
        if not imgs:
            sys.exit("[ERR] 읽을 수 있는 사진 없음")
        idx = [0]

        def nxt():
            idx[0] = (idx[0] + 1) % len(imgs)
            print(f"[{idx[0] + 1}/{len(imgs)}] {os.path.basename(src[idx[0]])}")
        run_calib(lambda: imgs[idx[0]], model, vp, nxt)
    elif kind == "images":
        run_images(src, model, vp, args)
    else:
        src.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        src.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
        if args.calib:
            run_calib(lambda: (lambda r: r[1] if r[0] else None)(src.read()), model, vp)
        else:
            run_stream(src, model, vp, args)
        src.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
