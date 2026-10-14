#!/usr/bin/env python3
"""
신호등 검출 평가 (ROS 없이, 컨테이너에서 실행)

  cd /ros2_ws/src/vision_pkg
  python3 tools/eval_detect.py                                    # models/*.onnx 전부, 세트 A
  python3 tools/eval_detect.py --models yolov8n_320.onnx yolo11n_416.onnx --set B
  python3 tools/eval_detect.py --models yolo11n_320.onnx --vis 20  # 결과 이미지 20장 저장
  python3 tools/eval_detect.py --min-height 32                    # 높이 32px 미만 신호등은 채점 제외

데이터: tools/coco_prepare.py 결과 (test_imgs/coco/source/<세트>/ 사진 + labels.json)
노드와 같은 YoloOnnx(전처리·추론·후처리)로 traffic light만 채점한다.

지표 (정답 박스와 IoU ≥ 0.5인 검출 박스를 점수 높은 순으로 1:1 매칭)
  검출률(recall) = 맞힌 정답 / 전체 정답,  정밀도(precision) = 맞힌 검출 / 전체 검출
  AP50  = 임계값과 무관한 종합 점수 (precision-recall 곡선 아래 면적, COCO 101점 방식)
  크기별 검출률: 정답 박스 면적 small < 32², medium < 96², large (원본 픽셀, COCO 기준)
--min-height: 그보다 작은 정답은 빼고, 그 정답과 맞거나 그보다 작은 검출도 오검출로 세지 않는다 (COCO 크기 구간 채점과 같은 방식)
추론은 사진마다 1번(conf 0.01)만 하고, 임계값별 결과는 그 결과로 다시 계산한다.
"""
import argparse
import glob
import json
import os
import sys
import time

import cv2
import numpy as np

PKG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, PKG_DIR)
from vision_pkg.detector import CLS_TRAFFIC_LIGHT, YoloOnnx  # noqa: E402

IOU_THRES = 0.5
SIZES = ("small", "medium", "large")
CONF_SWEEP = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5)


def size_of(w, h):
    a = w * h
    return "small" if a < 32 ** 2 else "medium" if a < 96 ** 2 else "large"


def iou(box, gts):
    """box [x1,y1,x2,y2] 와 gts (N,4) 의 IoU."""
    x1 = np.maximum(box[0], gts[:, 0])
    y1 = np.maximum(box[1], gts[:, 1])
    x2 = np.minimum(box[2], gts[:, 2])
    y2 = np.minimum(box[3], gts[:, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    a = (box[2] - box[0]) * (box[3] - box[1])
    b = (gts[:, 2] - gts[:, 0]) * (gts[:, 3] - gts[:, 1])
    return inter / np.maximum(a + b - inter, 1e-9)


def match(dets, gts):
    """점수 높은 검출부터 아직 안 맞은 정답과 매칭. (검출별 TP 여부, 정답별 맞힌 검출 점수 또는 None)"""
    order = sorted(range(len(dets)), key=lambda i: -dets[i][1])
    gt_hit = [None] * len(gts)
    tp = [False] * len(dets)
    g = np.array(gts, np.float32).reshape(-1, 4)
    for i in order:
        if not len(g):
            break
        ious = iou(dets[i][0], g)
        ious[[j for j, h in enumerate(gt_hit) if h is not None]] = 0
        j = int(ious.argmax())
        if ious[j] >= IOU_THRES:
            gt_hit[j] = dets[i][1]
            tp[i] = True
    return tp, gt_hit


def ap50(scores, tps, n_gt):
    if not n_gt or not scores:
        return 0.0
    order = np.argsort(-np.array(scores))
    tp = np.array(tps, np.float32)[order]
    ctp, cfp = np.cumsum(tp), np.cumsum(1 - tp)
    rec, prec = ctp / n_gt, ctp / np.maximum(ctp + cfp, 1e-9)
    prec = np.maximum.accumulate(prec[::-1])[::-1]  # 오른쪽 최대값으로 단조 감소
    pts = np.linspace(0, 1, 101)
    idx = np.searchsorted(rec, pts, side="left")
    return float(np.mean([prec[i] if i < len(prec) else 0.0 for i in idx]))


def evaluate(model_path, items, img_dir, threads, vis_dir=None, vis_n=0, vis_conf=0.35, min_h=0):
    model = YoloOnnx(model_path, threads=threads)
    run = model.sess.run
    infer_t = []

    def timed_run(*a, **k):  # 추론(sess.run)만 따로 측정
        t = time.perf_counter()
        out = run(*a, **k)
        infer_t.append(time.perf_counter() - t)
        return out

    model.sess.run = timed_run
    classes = {CLS_TRAFFIC_LIGHT: "traffic_light"}
    first = cv2.imread(os.path.join(img_dir, items[0]["file"]))
    for _ in range(5):  # 준비 실행 (측정 제외)
        model.detect(first, 0.01, 0.45, classes)
    infer_t.clear()

    total_t, scores, tps = [], [], []
    gt_sizes, gt_scores = [], []  # 정답별 크기, 맞힌 검출 점수(None=못 맞힘)
    for k, it in enumerate(items):
        img = cv2.imread(os.path.join(img_dir, it["file"]))
        t = time.perf_counter()
        dets = model.detect(img, 0.01, 0.45, classes)
        total_t.append(time.perf_counter() - t)
        d = [((float(x1), float(y1), float(x2), float(y2)), det.conf)
             for det in dets for x1, y1, x2, y2 in [det.box]]
        keep = [b for b in it["boxes"] if b[3] >= min_h]
        small = [(x, y, x + w, y + h) for x, y, w, h in it["boxes"] if h < min_h]
        gts = [(x, y, x + w, y + h) for x, y, w, h in keep]
        tp, hit = match(d, gts)
        for i, ((x1, y1, x2, y2), _) in enumerate(d):  # 제외한 작은 정답과 맞거나 작은 검출은 채점에서 뺀다
            if not tp[i] and (y2 - y1 < min_h or (small and iou((x1, y1, x2, y2), np.array(small)).max() >= IOU_THRES)):
                continue
            scores.append(d[i][1])
            tps.append(tp[i])
        gt_sizes += [size_of(w, h) for _, _, w, h in keep]
        gt_scores += hit
        if vis_dir and k < vis_n:
            v = img.copy()
            for x1, y1, x2, y2 in gts:
                cv2.rectangle(v, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 1)
            for (x1, y1, x2, y2), s in d:
                if s >= vis_conf:
                    cv2.rectangle(v, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 1)
                    cv2.putText(v, f"{s:.2f}", (int(x1), max(10, int(y1) - 2)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)
            cv2.imwrite(os.path.join(vis_dir, it["file"]), v)

    n_gt = len(gt_sizes)
    scores_a, tps_a = np.array(scores), np.array(tps, bool)
    sweep = []
    for c in CONF_SWEEP:
        m = scores_a >= c
        tp, n_det = int(tps_a[m].sum()), int(m.sum())
        hit = [s is not None and s >= c for s in gt_scores]
        by_size = {}
        for sz in SIZES:
            sel = [h for h, g in zip(hit, gt_sizes) if g == sz]
            by_size[sz] = [int(sum(sel)), len(sel)]
        sweep.append({"conf": c, "recall": tp / n_gt if n_gt else 0.0,
                      "precision": tp / n_det if n_det else 0.0,
                      "tp": tp, "fp": n_det - tp, "by_size": by_size})
    ms = lambda a: (round(float(np.median(a)) * 1000, 1), round(float(np.percentile(a, 95)) * 1000, 1))
    return {"model": os.path.basename(model_path), "imgsz": model.imgsz, "threads": threads,
            "images": len(items), "gt": n_gt, "min_height": min_h, "ap50": round(ap50(scores, tps, n_gt), 4),
            "total_ms": ms(total_t), "infer_ms": ms(infer_t), "sweep": sweep}


def pick(r, conf):
    return min(r["sweep"], key=lambda s: abs(s["conf"] - conf))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", help="models/ 안 파일 이름 또는 경로 (기본: models/*.onnx 전부)")
    ap.add_argument("--data", default=os.path.join(PKG_DIR, "test_imgs", "coco", "source"))
    ap.add_argument("--set", default="A", help="A(모델 비교용) / B(최종 확인용)")
    ap.add_argument("--threads", type=int, default=2, help="onnx_threads (노드 기본값 2)")
    ap.add_argument("--conf", type=float, default=0.35, help="표에 보여줄 임계값 (노드 conf_thres)")
    ap.add_argument("--min-height", type=float, default=0, help="이 높이(원본 px) 미만 신호등은 채점 제외")
    ap.add_argument("--limit", type=int, default=0, help="앞에서 N장만 (빠른 확인용)")
    ap.add_argument("--vis", type=int, default=0, help="결과 이미지 N장 저장 (정답 초록, 검출 빨강)")
    ap.add_argument("--out", default=os.path.join(PKG_DIR, "result", "eval_detect"))
    args = ap.parse_args()

    models = args.models or sorted(glob.glob(os.path.join(PKG_DIR, "models", "*.onnx")))
    models = [m if os.path.exists(m) else os.path.join(PKG_DIR, "models", m) for m in models]
    img_dir = os.path.join(args.data, args.set)
    with open(os.path.join(img_dir, "labels.json")) as f:
        items = json.load(f)["images"]
    if args.limit:
        items = items[:args.limit]
    os.makedirs(args.out, exist_ok=True)
    n_gt = sum(1 for i in items for b in i["boxes"] if b[3] >= args.min_height)
    print(f"세트 {args.set}: 사진 {len(items)}장, 정답 {n_gt}개 (높이 {args.min_height:g}px 이상), "
          f"threads={args.threads}, conf={args.conf}")

    results = []
    for m in models:
        name = os.path.splitext(os.path.basename(m))[0]
        vis_dir = None
        if args.vis:
            vis_dir = os.path.join(args.out, f"vis_{name}_{args.set}")
            os.makedirs(vis_dir, exist_ok=True)
        print(f"  평가 중: {name} ...", flush=True)
        r = evaluate(m, items, img_dir, args.threads, vis_dir, args.vis, args.conf, args.min_height)
        results.append(r)
        tag = f"_h{args.min_height:g}" if args.min_height else ""
        with open(os.path.join(args.out, f"{name}_{args.set}{tag}.json"), "w") as f:
            json.dump(r, f, indent=1)

    print(f"\n[conf={args.conf}] 검출률 = 맞힌 정답/전체, 크기별은 맞힌 수/정답 수")
    print(f"{'모델':<16}{'AP50':>6}{'검출률':>8}{'정밀도':>8}{'오검출':>7}"
          f"{'small':>10}{'medium':>9}{'large':>8}{'전체ms':>12}{'추론ms':>12}")
    for r in results:
        s = pick(r, args.conf)
        size_cells = ["%d/%d" % tuple(s["by_size"][z]) for z in SIZES]
        total, infer = "%.0f/%.0f" % tuple(r["total_ms"]), "%.0f/%.0f" % tuple(r["infer_ms"])
        print(f"{os.path.splitext(r['model'])[0]:<16}{r['ap50']:>6.3f}{s['recall']:>8.1%}{s['precision']:>8.1%}"
              f"{s['fp']:>7}{size_cells[0]:>10}{size_cells[1]:>9}{size_cells[2]:>8}{total:>12}{infer:>12}")
    print("  (ms = median/p95, 전체 = 전처리+추론+후처리)")

    print("\n[conf별 검출률 / 정밀도]")
    print(f"{'모델':<16}" + "".join(f"{c:>12}" for c in CONF_SWEEP))
    for r in results:
        cells = ["%.0f%%/%.0f%%" % (s["recall"] * 100, s["precision"] * 100) for s in r["sweep"]]
        print(f"{os.path.splitext(r['model'])[0]:<16}" + "".join(f"{c:>12}" for c in cells))
    print(f"\n결과 JSON: {args.out}")


if __name__ == "__main__":
    main()
