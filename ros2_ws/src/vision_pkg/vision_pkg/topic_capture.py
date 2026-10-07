"""
카메라 topic 점검 + 테스트 사진 저장 도구 (컨테이너에서 실행)

  ros2 run vision_pkg topic_capture --topic /camera/image_raw --out /root/vision_ws/test_imgs
  ros2 run vision_pkg topic_capture --topic /camera/image_raw/compressed --compressed --out ...

- 2초마다 수신 FPS, 해상도, encoding, 지연(header.stamp 기준)을 출력한다.
- 터미널에 라벨을 입력하고 Enter → 최신 프레임을 <라벨>_<번호>.png 로 저장
  (예: red ↵, green ↵, none ↵, stop ↵). 라벨 없이 Enter → frame_<번호>.png
- --every 2 를 주면 2초마다 자동 저장
- q ↵ 로 종료
"""
import argparse
import os
import sys
import threading
import time

import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.utilities import remove_ros_args
from sensor_msgs.msg import CompressedImage, Image

from vision_pkg.image_conv import compressed_to_bgr, imgmsg_to_bgr


class Capture(Node):
    def __init__(self, args):
        super().__init__("topic_capture")
        self.args = args
        self.msg, self.times, self.lat = None, [], []
        self.counts = {}
        os.makedirs(args.out, exist_ok=True)
        T = CompressedImage if args.compressed else Image
        self.create_subscription(T, args.topic, self.cb, qos_profile_sensor_data)
        self.create_timer(2.0, self.stat)
        if args.every > 0:
            self.create_timer(args.every, lambda: self.save("auto"))
        self.get_logger().info(f"구독: {args.topic} ({T.__name__}), 저장 폴더: {args.out}")
        self.get_logger().info("라벨 입력 후 Enter로 저장 (예: red / green / yellow / none / stop), q로 종료")

    def cb(self, msg):
        now = time.time()
        self.msg = msg
        self.times.append(now)
        st = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        if st > 0:
            self.lat.append((now - st) * 1000)

    def stat(self):
        now = time.time()
        self.times = [t for t in self.times if now - t <= 2.0]
        if self.msg is None:
            n = self.count_publishers(self.args.topic)
            self.get_logger().warn(f"아직 수신 없음 (발행자 {n}개). topic 이름/QoS/ROS_DOMAIN_ID/ipc 설정 확인")
            return
        m = self.msg
        desc = f"{m.width}x{m.height} {m.encoding}" if not self.args.compressed else f"{m.format}, {len(m.data)//1024} KB"
        lat = f", 지연 {sum(self.lat)/len(self.lat):.0f} ms" if self.lat else ", 지연 측정불가(header.stamp 비어 있음)"
        self.lat = []
        self.get_logger().info(f"수신 {len(self.times)/2.0:.1f} FPS, {desc}{lat}")

    def save(self, label):
        if self.msg is None:
            self.get_logger().warn("저장할 프레임 없음")
            return
        try:
            img = compressed_to_bgr(self.msg) if self.args.compressed else imgmsg_to_bgr(self.msg)
        except ValueError as e:
            self.get_logger().error(str(e))
            return
        label = label or "frame"
        self.counts[label] = self.counts.get(label, 0) + 1
        path = os.path.join(self.args.out, f"{label}_{self.counts[label]:03d}.png")
        cv2.imwrite(path, img)
        self.get_logger().info(f"저장: {path}")


def main():
    rclpy.init()
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", default="/camera/image_raw")
    ap.add_argument("--compressed", action="store_true")
    ap.add_argument("--out", default="test_imgs")
    ap.add_argument("--every", type=float, default=0.0, help="N초마다 자동 저장 (0=끔)")
    args = ap.parse_args(remove_ros_args(sys.argv)[1:])
    node = Capture(args)

    stop = threading.Event()

    def stdin_loop():
        for line in sys.stdin:
            s = line.strip()
            if s == "q":
                break
            node.save(s)
        stop.set()

    threading.Thread(target=stdin_loop, daemon=True).start()
    try:
        while rclpy.ok() and not stop.is_set():
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == "__main__":
    main()
