"""
Web Viewer (담당 B) — vision_node 디버그 이미지를 브라우저로 보기

  ros2 launch vision_pkg vision.launch.py web:=true
  → 브라우저에서 http://<Pi IP>:8080  (VS Code Remote-SSH면 포트 전달 후 http://localhost:8080)

구독
  /vision/debug/compressed  sensor_msgs/CompressedImage (vision_node, publish_debug_image=true)

HTTP
  /             영상 페이지
  /stream       MJPEG 스트림 (multipart/x-mixed-replace)
  /snapshot.jpg 최신 프레임 1장

받은 JPEG를 다시 인코딩하지 않고 그대로 내보낸다.
"""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage

PAGE = b"""<!doctype html>
<html><head><meta charset="utf-8"><title>vision_node debug</title>
<style>body{margin:0;background:#111;color:#ddd;font-family:sans-serif;text-align:center}
img{max-width:100%;height:auto;margin-top:8px}</style></head>
<body><div>/vision/debug/compressed</div><img src="/stream"></body></html>"""


class FrameBuffer:
    """최신 JPEG 1장. 새 프레임이 오면 기다리던 스트림들을 깨운다."""

    def __init__(self):
        self.cond = threading.Condition()
        self.jpeg, self.seq = None, 0

    def put(self, jpeg):
        with self.cond:
            self.jpeg, self.seq = jpeg, self.seq + 1
            self.cond.notify_all()

    def wait_next(self, last_seq, timeout):
        with self.cond:
            self.cond.wait_for(lambda: self.seq != last_seq, timeout)
            return self.jpeg, self.seq


def make_handler(buf, stop_event):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # 요청마다 찍히는 접속 로그 끔
            pass

        def do_GET(self):
            if self.path == "/":
                self._send(200, "text/html; charset=utf-8", PAGE)
            elif self.path == "/snapshot.jpg":
                jpeg, _ = buf.wait_next(-1, 0)
                if jpeg is None:
                    self._send(503, "text/plain; charset=utf-8", "아직 디버그 이미지 없음".encode())
                else:
                    self._send(200, "image/jpeg", jpeg)
            elif self.path == "/stream":
                self._stream()
            else:
                self._send(404, "text/plain", b"not found")

        def _send(self, code, ctype, body):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _stream(self):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            seq = -1
            try:
                while not stop_event.is_set():
                    jpeg, new_seq = buf.wait_next(seq, 1.0)
                    if jpeg is None or new_seq == seq:
                        continue
                    seq = new_seq
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode())
                    self.wfile.write(jpeg + b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass  # 브라우저 탭 닫힘

    return Handler


class WebViewer(Node):
    def __init__(self):
        super().__init__("web_viewer")
        self.declare_parameter("image_topic", "/vision/debug/compressed")
        self.declare_parameter("port", 8080)
        topic = self.get_parameter("image_topic").value
        port = self.get_parameter("port").value

        self.buf = FrameBuffer()
        self.stop_event = threading.Event()
        self.create_subscription(CompressedImage, topic, lambda m: self.buf.put(bytes(m.data)),
                                 qos_profile_sensor_data)

        ThreadingHTTPServer.daemon_threads = True
        self.server = ThreadingHTTPServer(("0.0.0.0", port), make_handler(self.buf, self.stop_event))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.get_logger().info(f"{topic} → http://0.0.0.0:{port}  (브라우저에서 열기)")

    def destroy_node(self):
        self.stop_event.set()
        self.server.shutdown()
        self.server.server_close()
        super().destroy_node()


def main():
    rclpy.init()
    node = WebViewer()
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
