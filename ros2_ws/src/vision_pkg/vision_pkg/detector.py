"""
ROS2와 무관한 순수 Vision 로직.
- YoloOnnx      : COCO 사전학습 YOLO(ONNX)로 traffic light / stop sign 검출
- classify_light: 신호등 bbox 안에서 켜진 램프를 찾아 색 판별 (RED / YELLOW / GREEN / UNKNOWN)
- decide_sign   : 한 프레임의 검출 결과 → STOP / GO / NONE
- SignDebouncer : 최근 N프레임 중 M프레임 이상 같은 결과일 때만 상태 변경

노트북 테스트 스크립트(tools/vision_test.py)와 ROS2 Vision Node가 같은 코드를 사용한다.
"""
from collections import deque
from dataclasses import dataclass, field

import cv2
import numpy as np

# COCO class id
CLS_TRAFFIC_LIGHT = 9
CLS_STOP_SIGN = 11
TARGET_CLASSES = {CLS_TRAFFIC_LIGHT: "traffic_light", CLS_STOP_SIGN: "stop_sign"}


@dataclass
class Detection:
    cls_id: int
    name: str
    conf: float
    box: tuple  # (x1, y1, x2, y2) 원본 이미지 좌표
    color: str = ""  # traffic_light일 때만 RED/YELLOW/GREEN/UNKNOWN

    def area_ratio(self, img_w, img_h):
        x1, y1, x2, y2 = self.box
        return max(0, x2 - x1) * max(0, y2 - y1) / float(img_w * img_h)


@dataclass
class HsvParams:
    # OpenCV HSV: H 0~179, S/V 0~255. 빨강은 0 부근과 180 부근 두 구간.
    red1: tuple = (0, 10)
    red2: tuple = (160, 179)
    yellow: tuple = (15, 35)
    green: tuple = (40, 95)
    s_min: int = 80
    v_min: int = 120
    min_ratio: float = 0.02  # 램프 덩어리 면적 / bbox 면적 최소값 (작은 반사·잡음 무시)
    max_ratio: float = 0.5  # 이보다 큰 덩어리는 신호등 몸체(노란색 몸체 등)로 보고 무시
    # 켜진 램프 판정: 덩어리 밝기(V 상위 10%)가 이 값 이상 (RED, YELLOW, GREEN 순)
    # 노란 몸체·청록 배경은 어둡고, 켜진 노랑·초록 램프는 거의 포화된다. 빨강은 어둡게 찍혀 기준 없음
    lit_v: tuple = (0, 220, 220)


@dataclass
class VisionParams:
    conf_thres: float = 0.35
    nms_thres: float = 0.45
    min_area_ratio: float = 0.002  # 화면 대비 bbox 면적이 이보다 작으면(멀면) 무시
    yellow_as: str = "STOP"  # 노란불을 STOP / NONE 중 무엇으로 볼지 (D와 합의)
    hsv: HsvParams = field(default_factory=HsvParams)


class YoloOnnx:
    """Ultralytics YOLOv8/YOLO11 detect 모델을 ONNX로 export한 파일용 추론기."""

    def __init__(self, model_path, imgsz=320, threads=4):
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        self.sess = ort.InferenceSession(model_path, so, providers=["CPUExecutionProvider"])
        self.input_name = self.sess.get_inputs()[0].name
        shape = self.sess.get_inputs()[0].shape
        self.imgsz = shape[2] if isinstance(shape[2], int) else imgsz

    def _letterbox(self, img):
        h, w = img.shape[:2]
        r = self.imgsz / max(h, w)
        nw, nh = int(round(w * r)), int(round(h * r))
        resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((self.imgsz, self.imgsz, 3), 114, dtype=np.uint8)
        top, left = (self.imgsz - nh) // 2, (self.imgsz - nw) // 2
        canvas[top:top + nh, left:left + nw] = resized
        return canvas, r, left, top

    def detect(self, bgr, conf_thres=0.35, nms_thres=0.45, classes=TARGET_CLASSES):
        h, w = bgr.shape[:2]
        canvas, r, padx, pady = self._letterbox(bgr)
        x = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        x = np.transpose(x, (2, 0, 1))[None]
        out = self.sess.run(None, {self.input_name: x})[0][0]  # (4+80, N)
        out = out.T  # (N, 84)

        cls_ids = list(classes.keys())
        scores_all = out[:, 4:]
        scores = scores_all[:, cls_ids]
        best = scores.argmax(axis=1)
        conf = scores[np.arange(len(scores)), best]
        keep = conf >= conf_thres
        if not np.any(keep):
            return []

        boxes = out[keep, :4]
        conf = conf[keep]
        cls = np.array(cls_ids)[best[keep]]

        # cx,cy,w,h (letterbox 좌표) → x1,y1,x2,y2 (원본 좌표)
        cx, cy, bw, bh = boxes.T
        x1 = (cx - bw / 2 - padx) / r
        y1 = (cy - bh / 2 - pady) / r
        x2 = (cx + bw / 2 - padx) / r
        y2 = (cy + bh / 2 - pady) / r
        xyxy = np.stack([x1, y1, x2, y2], axis=1)
        xyxy[:, [0, 2]] = xyxy[:, [0, 2]].clip(0, w - 1)
        xyxy[:, [1, 3]] = xyxy[:, [1, 3]].clip(0, h - 1)

        xywh = [[float(a), float(b), float(c - a), float(d - b)] for a, b, c, d in xyxy]
        idx = cv2.dnn.NMSBoxes(xywh, conf.tolist(), conf_thres, nms_thres)
        idx = np.array(idx).flatten() if len(idx) else []

        dets = []
        for i in idx:
            c = int(cls[i])
            dets.append(Detection(c, classes[c], float(conf[i]),
                                  tuple(int(v) for v in xyxy[i])))
        return dets


def color_masks(crop_bgr, p: HsvParams):
    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    sv_lo = (p.s_min, p.v_min)

    def rng(hr):
        return cv2.inRange(hsv, (hr[0], *sv_lo), (hr[1], 255, 255))

    red = cv2.bitwise_or(rng(p.red1), rng(p.red2))
    return {"RED": red, "YELLOW": rng(p.yellow), "GREEN": rng(p.green)}


def classify_light(crop_bgr, p: HsvParams):
    """신호등 crop의 색 판별. (color, {color: 램프 덩어리 면적비}) 반환.
    색별 마스크에서 연결된 덩어리를 찾고, 크기(min_ratio~max_ratio)와 밝기(lit_v)를 만족하는
    가장 큰 덩어리의 색으로 정한다. 없으면 UNKNOWN (꺼짐·옆면·뒷면)."""
    if crop_bgr is None or crop_bgr.size == 0:
        return "UNKNOWN", {}
    v = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)[:, :, 2]
    total = crop_bgr.shape[0] * crop_bgr.shape[1]
    ratios = {}
    for (color, m), lit in zip(color_masks(crop_bgr, p).items(), p.lit_v):
        n, labels, stats, _ = cv2.connectedComponentsWithStats(m)
        best = 0.0
        for i in range(1, n):
            r = stats[i, cv2.CC_STAT_AREA] / total
            if p.min_ratio <= r <= p.max_ratio and r > best and np.percentile(v[labels == i], 90) >= lit:
                best = r
        ratios[color] = best
    color = max(ratios, key=ratios.get)
    if ratios[color] == 0:
        return "UNKNOWN", ratios
    return color, ratios


def decide_sign(bgr, dets, vp: VisionParams):
    """한 프레임 판단. STOP 표지판 > 신호등(가장 큰 것) 순으로 본다."""
    h, w = bgr.shape[:2]
    near = [d for d in dets if d.area_ratio(w, h) >= vp.min_area_ratio]

    for d in near:
        if d.cls_id == CLS_TRAFFIC_LIGHT:
            x1, y1, x2, y2 = d.box
            d.color, _ = classify_light(bgr[y1:y2, x1:x2], vp.hsv)

    if any(d.cls_id == CLS_STOP_SIGN for d in near):
        return "STOP"

    lights = [d for d in near if d.cls_id == CLS_TRAFFIC_LIGHT and d.color != "UNKNOWN"]
    if not lights:
        return "NONE"
    biggest = max(lights, key=lambda d: d.area_ratio(w, h))
    if biggest.color == "RED":
        return "STOP"
    if biggest.color == "GREEN":
        return "GO"
    return vp.yellow_as  # YELLOW


class SignDebouncer:
    """최근 window 프레임 중 min_votes 이상 같은 값이면 상태를 바꾼다."""

    def __init__(self, window=5, min_votes=3, initial="NONE"):
        self.hist = deque(maxlen=window)
        self.min_votes = min_votes
        self.state = initial

    def update(self, raw):
        self.hist.append(raw)
        if self.hist.count(raw) >= self.min_votes:
            self.state = raw
        return self.state

    def reset(self, state="NONE"):
        self.hist.clear()
        self.state = state


def draw(bgr, dets, sign, fps=None):
    img = bgr.copy()
    palette = {"RED": (0, 0, 255), "GREEN": (0, 200, 0), "YELLOW": (0, 220, 255)}
    for d in dets:
        col = palette.get(d.color, (255, 128, 0) if d.cls_id == CLS_STOP_SIGN else (200, 200, 200))
        x1, y1, x2, y2 = d.box
        cv2.rectangle(img, (x1, y1), (x2, y2), col, 2)
        label = f"{d.name} {d.conf:.2f} {d.color}".strip()
        cv2.putText(img, label, (x1, max(15, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 2)
    txt = f"SIGN: {sign}" + (f"  {fps:.1f} FPS" if fps else "")
    cv2.putText(img, txt, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 3)
    cv2.putText(img, txt, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 1)
    return img
