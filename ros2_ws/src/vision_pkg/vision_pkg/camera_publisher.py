"""
Camera Publisher (담당 B) — Docker 컨테이너에서 실행

Pi 호스트의 가상 웹캠(/dev/video10, pi-camera-bridge)이 컨테이너에 /dev/video0 으로 연결된다.
이 장치를 OpenCV로 읽어 sensor_msgs/Image(bgr8) topic으로 발행한다.

발행
  /camera/image_raw  sensor_msgs/Image  bgr8, BestEffort(sensor data QoS), publish_rate Hz 이하

장치를 열 수 없거나 읽기가 끊기면 발행을 멈추고 1초 간격으로 재연결한다.
(vision_node 쪽에서는 CAMERA_TIMEOUT 으로 보인다)
"""
import array
import threading
import time

import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


class CameraPublisher(Node):
    def __init__(self):
        super().__init__("camera_publisher")
        P = self.declare_parameter
        P("camera_device", "/dev/video0")
        P("camera_width", 640)
        P("camera_height", 480)
        P("camera_fourcc", "")       # 비우면 장치 기본값 (가상 웹캠은 YUYV)
        P("image_topic", "/camera/image_raw")
        P("frame_id", "camera")
        P("publish_rate", 15.0)      # 이보다 빨리 들어오는 프레임은 버린다

        g = lambda n: self.get_parameter(n).value  # noqa: E731
        self.device = g("camera_device")
        self.width, self.height = g("camera_width"), g("camera_height")
        self.fourcc = g("camera_fourcc")
        self.frame_id = g("frame_id")
        self.min_period = 1.0 / max(0.1, g("publish_rate"))

        self.pub = self.create_publisher(Image, g("image_topic"), qos_profile_sensor_data)
        self.get_logger().info(f"{self.device} → {g('image_topic')} (최대 {g('publish_rate'):.0f} Hz)")

        self.count = 0
        self.last_stat = time.monotonic()
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
        last_pub = 0.0
        while self.running and rclpy.ok():
            if cap is None or not cap.isOpened():
                cap = self._open()
                if not cap.isOpened():
                    self.get_logger().warn(f"카메라 열기 실패: {self.device}, 1초 후 재시도")
                    cap = None
                    time.sleep(1.0)
                    continue
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                self.get_logger().info(f"카메라 연결됨: {self.device} ({w}x{h})")
            ok, img = cap.read()
            if not ok:
                self.get_logger().warn("프레임 읽기 실패 → 재연결")
                cap.release()
                cap = None
                time.sleep(0.2)
                continue
            now = time.monotonic()
            # 30FPS 입력에 15Hz면 프레임 간격(33.3ms) 2번이 주기(66.7ms)보다 살짝 짧아 3장에 1장만 나간다 → 10% 여유
            if now - last_pub < self.min_period * 0.9:
                continue
            last_pub = now
            self._publish(img)
            if now - self.last_stat >= 5.0:  # 5초마다 발행 FPS 로그
                self.get_logger().info(f"발행 {self.count / (now - self.last_stat):.1f} FPS, "
                                       f"{img.shape[1]}x{img.shape[0]}")
                self.count, self.last_stat = 0, now
        if cap is not None:
            cap.release()

    def _publish(self, img):
        msg = Image()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id
        msg.height, msg.width = img.shape[:2]
        msg.encoding = "bgr8"
        msg.is_bigendian = 0
        msg.step = msg.width * 3
        msg.data = array.array("B", img.tobytes())  # bytes를 그대로 넣으면 원소마다 검사해서 느림
        self.pub.publish(msg)
        self.count += 1

    def destroy_node(self):
        self.running = False
        self.th.join(timeout=2.0)
        super().destroy_node()


def main():
    rclpy.init()
    node = CameraPublisher()
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
