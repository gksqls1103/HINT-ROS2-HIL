"""
ROS2 이미지 메시지 → OpenCV BGR 변환 (cv_bridge 없이).
rclpy를 import하지 않으므로 메시지 객체의 속성(encoding, height, width, step, data)만 있으면 동작한다.
"""
import cv2
import numpy as np

SUPPORTED = ("bgr8", "rgb8", "bgra8", "rgba8", "mono8",
             "yuv422 (uyvy)", "yuv422_yuy2 (yuyv)", "nv12", "nv21", "i420")


def _rows(buf, h, step):
    return buf[: h * step].reshape(h, step)


def imgmsg_to_bgr(msg):
    """sensor_msgs/Image → BGR ndarray. 지원하지 않는 encoding이면 ValueError."""
    enc = msg.encoding.lower()
    h, w, step = msg.height, msg.width, msg.step
    buf = np.frombuffer(bytes(msg.data) if not isinstance(msg.data, (bytes, bytearray)) else msg.data,
                        dtype=np.uint8)

    if enc in ("bgr8", "rgb8"):
        img = _rows(buf, h, step)[:, : w * 3].reshape(h, w, 3)
        return img.copy() if enc == "bgr8" else cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    if enc in ("bgra8", "rgba8"):
        img = _rows(buf, h, step)[:, : w * 4].reshape(h, w, 4)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR if enc == "bgra8" else cv2.COLOR_RGBA2BGR)
    if enc in ("mono8", "8uc1"):
        return cv2.cvtColor(_rows(buf, h, step)[:, :w].copy(), cv2.COLOR_GRAY2BGR)
    if enc in ("yuv422", "uyvy"):  # ROS의 yuv422 = UYVY
        img = _rows(buf, h, step)[:, : w * 2].reshape(h, w, 2)
        return cv2.cvtColor(img, cv2.COLOR_YUV2BGR_UYVY)
    if enc in ("yuv422_yuy2", "yuyv", "yuy2"):
        img = _rows(buf, h, step)[:, : w * 2].reshape(h, w, 2)
        return cv2.cvtColor(img, cv2.COLOR_YUV2BGR_YUY2)
    if enc in ("nv12", "nv21", "i420"):
        stride = step if step else w
        img = buf[: stride * h * 3 // 2].reshape(h * 3 // 2, stride)[:, :w]
        code = {"nv12": cv2.COLOR_YUV2BGR_NV12, "nv21": cv2.COLOR_YUV2BGR_NV21,
                "i420": cv2.COLOR_YUV2BGR_I420}[enc]
        return cv2.cvtColor(np.ascontiguousarray(img), code)
    raise ValueError(f"지원하지 않는 encoding: {msg.encoding} (지원: {', '.join(SUPPORTED)})")


def compressed_to_bgr(msg):
    """sensor_msgs/CompressedImage(jpeg/png) → BGR ndarray. 실패 시 ValueError."""
    img = cv2.imdecode(np.frombuffer(bytes(msg.data), np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"CompressedImage 디코딩 실패 (format={msg.format})")
    return img
