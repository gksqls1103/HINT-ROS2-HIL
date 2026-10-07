"""
Vision Node (담당 B) — Docker 컨테이너에서 실행

입력 (input_mode)
  "topic"  : camera_publisher가 발행하는 카메라 topic 구독 (기본값)
             image_compressed=false → sensor_msgs/Image, true → sensor_msgs/CompressedImage
  "device" : /dev/videoX 직접 읽기 (예비용)

발행
  /vision/sign   std_msgs/String  "STOP" | "GO" | "NONE"   (Reliable, publish_rate Hz로 계속 발행)
  /vision/fault  std_msgs/String  "OK" | "CAMERA_NO_PUBLISHER" | "CAMERA_OPEN_FAILED"
                                  | "CAMERA_TIMEOUT" | "IMAGE_DECODE_ERROR" | "LOW_FPS"
  /vision/debug/compressed  sensor_msgs/CompressedImage  (publish_debug_image=true일 때만, BestEffort)

동작
  입력에서 최신 프레임만 유지 → 타이머마다 새 프레임이면 YOLO(ONNX) + HSV 판단 → 디바운싱 → 발행
  Fault 상태에서는 /vision/sign 을 NONE 으로 보내고, 원인은 /vision/fault 로 알린다.
"""
import os
import threading
import time

import cv2
from ament_index_python.packages import get_package_share_directory
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage, Image
from std_msgs.msg import String

from vision_pkg.detector import HsvParams, SignDebouncer, VisionParams, YoloOnnx, decide_sign, draw
from vision_pkg.image_conv import compressed_to_bgr, imgmsg_to_bgr


class TopicReader:
    """카메라 topic 구독. 콜백에서는 메시지만 저장하고, 디코딩은 실제로 쓸 때 1번만 한다."""

    def __init__(self, node, topic, compressed):
        self.node, self.topic = node, topic
        self.compressed = compressed
        self.lock = threading.Lock()
        self.msg, self.stamp = None, 0.0
        self._cache_stamp, self._cache_frame = None, None
        self.decode_error = None
        self.rx_count = 0
        msg_type = CompressedImage if compressed else Image
        # 이미지는 BestEffort로 구독: 발행자가 Reliable이든 BestEffort든 연결된다
        node.create_subscription(msg_type, topic, self._cb, qos_profile_sensor_data)
        node.get_logger().info(f"카메라 topic 구독: {topic} ({msg_type.__name__})")

    def _cb(self, msg):
        with self.lock:
            self.msg, self.stamp = msg, time.monotonic()
            self.rx_count += 1

    @property
    def opened(self):
        """발행자가 존재하는지 (topic 모드에서 '카메라 열림'에 해당)."""
        return self.node.count_publishers(self.topic) > 0

    def latest(self):
        with self.lock:
            msg, stamp = self.msg, self.stamp
        if msg is None:
            return None, 0.0
        if stamp != self._cache_stamp:
            try:
                self._cache_frame = compressed_to_bgr(msg) if self.compressed else imgmsg_to_bgr(msg)
                self.decode_error = None
            except ValueError as e:
                self._cache_frame = None
                if self.decode_error != str(e):
                    self.node.get_logger().error(str(e))
                self.decode_error = str(e)
            self._cache_stamp = stamp
        return self._cache_frame, stamp

    def stop(self):
        pass


class CameraReader:
    """(예비용) /dev/videoX에서 최신 프레임만 계속 읽어 둔다. 끊기면 재연결."""

    def __init__(self, device, width, height, fourcc, logger):
        self.device, self.width, self.height, self.fourcc = device, width, height, fourcc
        self.log = logger
        self.lock = threading.Lock()
        self.frame, self.stamp = None, 0.0
        self.opened = False
        self.decode_error = None
        self.running = True
        self.th = threading.Thread(target=self._loop, daemon=True)
        self.th.start()

    def _open(self):
        dev = int(self.device) if str(self.device).isdigit() else self.device
        cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
        if self.fourcc:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*self.fourcc))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _loop(self):
        cap = None
        while self.running:
            if cap is None or not cap.isOpened():
                cap = self._open()
                self.opened = cap.isOpened()
                if not self.opened:
                    self.log.warn(f"카메라 열기 실패: {self.device}, 1초 후 재시도")
                    time.sleep(1.0)
                    continue
                self.log.info(f"카메라 연결됨: {self.device}")
            ok, img = cap.read()
            if not ok:
                self.log.warn("프레임 읽기 실패 → 재연결")
                cap.release()
                cap = None
                self.opened = False
                time.sleep(0.2)
                continue
            with self.lock:
                self.frame, self.stamp = img, time.monotonic()
        if cap is not None:
            cap.release()

    def latest(self):
        with self.lock:
            return self.frame, self.stamp

    def stop(self):
        self.running = False


class VisionNode(Node):
    def __init__(self):
        super().__init__("vision_node")
        P = self.declare_parameter
        P("input_mode", "topic")            # "topic" | "device"
        P("image_topic", "/camera/image_raw")
        P("image_compressed", False)        # true면 CompressedImage 구독
        P("camera_device", "/dev/video0")   # device 모드 전용
        P("camera_width", 640)
        P("camera_height", 480)
        P("camera_fourcc", "")
        P("model_path", "")       # 비우면 패키지에 설치된 models/yolov8n_320.onnx
        P("onnx_threads", 4)
        P("publish_rate", 10.0)
        P("conf_thres", 0.35)
        P("nms_thres", 0.45)
        P("min_area_ratio", 0.002)
        P("yellow_as", "STOP")
        P("debounce_window", 5)
        P("debounce_votes", 3)
        P("frame_timeout", 1.0)  # 이 시간 이상 새 프레임 없으면 CAMERA_TIMEOUT
        P("min_fps", 2.0)        # 처리 FPS가 이 값 미만이면 LOW_FPS
        P("hsv_red1", [0, 10])
        P("hsv_red2", [160, 179])
        P("hsv_yellow", [15, 35])
        P("hsv_green", [40, 95])
        P("hsv_s_min", 80)
        P("hsv_v_min", 120)
        P("hsv_min_ratio", 0.04)
        P("publish_debug_image", False)
        P("debug_image_rate", 2.0)

        g = lambda n: self.get_parameter(n).value  # noqa: E731
        self.vp = VisionParams(
            conf_thres=g("conf_thres"), nms_thres=g("nms_thres"),
            min_area_ratio=g("min_area_ratio"), yellow_as=g("yellow_as"),
            hsv=HsvParams(
                red1=tuple(g("hsv_red1")), red2=tuple(g("hsv_red2")),
                yellow=tuple(g("hsv_yellow")), green=tuple(g("hsv_green")),
                s_min=g("hsv_s_min"), v_min=g("hsv_v_min"), min_ratio=g("hsv_min_ratio")))
        self.frame_timeout = g("frame_timeout")
        self.min_fps = g("min_fps")
        self.debug_on = g("publish_debug_image")
        self.debug_period = 1.0 / max(0.1, g("debug_image_rate"))

        model_path = g("model_path") or os.path.join(
            get_package_share_directory("vision_pkg"), "models", "yolov8n_320.onnx")
        self.model = YoloOnnx(model_path, threads=g("onnx_threads"))
        self.get_logger().info(f"모델 로드: {model_path} (imgsz={self.model.imgsz})")
        self.debouncer = SignDebouncer(g("debounce_window"), g("debounce_votes"))

        self.input_mode = g("input_mode")
        if self.input_mode == "topic":
            self.cam = TopicReader(self, g("image_topic"), g("image_compressed"))
        elif self.input_mode == "device":
            self.cam = CameraReader(g("camera_device"), g("camera_width"), g("camera_height"),
                                    g("camera_fourcc"), self.get_logger())
        else:
            raise ValueError(f"input_mode는 topic 또는 device: {self.input_mode}")

        reliable = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                              history=HistoryPolicy.KEEP_LAST, depth=10)
        self.pub_sign = self.create_publisher(String, "/vision/sign", reliable)
        self.pub_fault = self.create_publisher(String, "/vision/fault", reliable)
        self.pub_dbg = self.create_publisher(CompressedImage, "/vision/debug/compressed",
                                             qos_profile_sensor_data) if self.debug_on else None

        self.last_stamp = 0.0
        self.proc_times = []
        self.infer_ms = 0.0
        self.last_dbg = 0.0
        self.last_stat = time.monotonic()
        self.last_sign, self.last_fault = None, None
        self.ok_since = time.monotonic()  # Fault에서 회복한 시각. 직후 FPS 창이 덜 찬 동안은 LOW_FPS 판정 안 함
        self.timer = self.create_timer(1.0 / g("publish_rate"), self.tick)

    def _fps(self):
        now = time.monotonic()
        self.proc_times = [t for t in self.proc_times if now - t <= 2.0]
        return len(self.proc_times) / 2.0

    def _check_fault(self, frame, stamp, now):
        if not self.cam.opened:  # 발행자가 사라지면(카메라 노드 종료) 이전에 받은 프레임이 있어도 NO_PUBLISHER
            return "CAMERA_NO_PUBLISHER" if self.input_mode == "topic" else "CAMERA_OPEN_FAILED"
        if stamp == 0.0 or now - stamp > self.frame_timeout:
            return "CAMERA_TIMEOUT"
        if frame is None and self.cam.decode_error:
            return "IMAGE_DECODE_ERROR"
        return "OK"

    def tick(self):
        now = time.monotonic()
        frame, stamp = self.cam.latest()
        fault = self._check_fault(frame, stamp, now)

        sign = "NONE"
        if fault == "OK":
            if stamp != self.last_stamp:  # 새 프레임일 때만 추론
                self.last_stamp = stamp
                t0 = time.monotonic()
                dets = self.model.detect(frame, self.vp.conf_thres, self.vp.nms_thres)
                raw = decide_sign(frame, dets, self.vp)
                self.infer_ms = (time.monotonic() - t0) * 1000
                self.debouncer.update(raw)
                self.proc_times.append(now)
                if self.pub_dbg and now - self.last_dbg >= self.debug_period:
                    self.last_dbg = now
                    self._publish_debug(draw(frame, dets, self.debouncer.state, self._fps()))
            sign = self.debouncer.state
            if now - self.ok_since > 3.0 and self._fps() < self.min_fps:
                fault = "LOW_FPS"
        else:
            self.debouncer.reset()
            self.ok_since = now

        self.pub_sign.publish(String(data=sign))
        self.pub_fault.publish(String(data=fault))

        if sign != self.last_sign:
            self.get_logger().info(f"/vision/sign: {self.last_sign} → {sign}")
            self.last_sign = sign
        if fault != self.last_fault:
            # rclpy는 같은 호출 위치에서 로그 레벨이 바뀌면 ValueError → 레벨별로 호출을 나눈다
            if fault == "OK":
                self.get_logger().info(f"/vision/fault: {fault}")
            else:
                self.get_logger().warn(f"/vision/fault: {fault}")
            self.last_fault = fault
        if now - self.last_stat >= 5.0:  # 5초마다 성능 로그
            self.last_stat = now
            self.get_logger().info(f"처리 {self._fps():.1f} FPS, 추론 {self.infer_ms:.0f} ms, sign={sign}")

    def _publish_debug(self, img):
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 60])
        if not ok:
            return
        msg = CompressedImage()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "camera"
        msg.format = "jpeg"
        msg.data = buf.tobytes()
        self.pub_dbg.publish(msg)

    def destroy_node(self):
        self.cam.stop()
        super().destroy_node()


def main():
    rclpy.init()
    node = VisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
