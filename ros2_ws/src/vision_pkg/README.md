# vision_pkg — 신호등/STOP 표지판 인식 (담당 B)

## 구조

```
┌──────────────────────────── Raspberry Pi 5 ─────────────────────────────┐
│ [호스트]                          [Docker: ros2_hil_env]                 │
│ Pi Camera → rpicam-vid → ffmpeg   /dev/video0 → camera_publisher         │
│   → v4l2loopback /dev/video10 ──▶   → /camera/image_raw (bgr8, 15Hz)      │
│   (pi-camera-bridge 서비스)          → vision_node (YOLO ONNX + HSV)       │
└──────────────────────────────────────────│──────────────────────────────┘
                                           │ /vision/sign, /vision/fault (10Hz)
                                           ▼
                          [노트북] D: Decision FSM → Gazebo 차량
```

처리 흐름:
```
/camera/image_raw → BGR → YOLOv8n(COCO, ONNX 320) → traffic light / stop sign bbox
  → 신호등 bbox HSV 색 판별 (RED / YELLOW / GREEN)
  → 프레임 판단 (stop sign 또는 빨간불·노란불 → STOP, 초록불 → GO, 그 외 → NONE)
  → 디바운싱 (최근 5프레임 중 3프레임 이상 같으면 상태 변경)
  → /vision/sign 10Hz 발행
```

## 폴더 구성

| 경로 | 내용 |
|---|---|
| `vision_pkg/camera_publisher.py` | `/dev/video0` → `/camera/image_raw` 발행 (끊기면 1초마다 재연결) |
| `vision_pkg/vision_node.py` | 인식 노드. `input_mode=device`면 장치를 직접 읽음 (예비) |
| `vision_pkg/detector.py` | ROS2와 무관한 핵심 로직 (YOLO ONNX 추론, HSV 판별, 판단, 디바운싱) |
| `vision_pkg/image_conv.py` | ROS 이미지 메시지 → OpenCV 변환 (cv_bridge 불필요) |
| `vision_pkg/topic_capture.py` | 카메라 topic 점검(FPS/해상도/encoding/지연) + 테스트 사진 저장 |
| `config/vision_params.yaml` | 카메라, 임계값, HSV 파라미터 |
| `launch/vision.launch.py` | camera_publisher + vision_node 실행 |
| `models/yolov8n_320.onnx` | COCO 사전학습 YOLOv8n, 입력 320. 패키지 share에 설치됨 |
| `tools/vision_test.py` | ROS2 없이 사진/영상으로 검증, HSV 캘리브레이션 |
| `tools/export_model.py` | 노트북에서 YOLO → ONNX 변환 (ultralytics 필요) |

## 인터페이스

| Topic | 방향 | 타입 | 값 / QoS |
|---|---|---|---|
| `/camera/image_raw` | camera_publisher → vision_node | `sensor_msgs/Image` 또는 `CompressedImage` | BestEffort로 구독 (발행자가 Reliable이어도 연결됨) |
| `/vision/sign` | 발행 | `std_msgs/String` | `STOP` / `GO` / `NONE`, Reliable, **10Hz 계속 발행** |
| `/vision/fault` | 발행 | `std_msgs/String` | 아래 표, Reliable, 10Hz |
| `/vision/debug/compressed` | 발행 | `sensor_msgs/CompressedImage` | 박스 그린 JPEG, BestEffort, 기본 꺼짐 |

| Fault 코드 | 의미 |
|---|---|
| `OK` | 정상 |
| `CAMERA_NO_PUBLISHER` | 카메라 topic 발행자가 없음 (camera_publisher 꺼짐) |
| `CAMERA_TIMEOUT` | `frame_timeout`(1초) 이상 새 프레임 없음 |
| `IMAGE_DECODE_ERROR` | 지원하지 않는 encoding 등으로 변환 실패 |
| `LOW_FPS` | 처리 FPS가 `min_fps`(2) 미만 |
| `CAMERA_OPEN_FAILED` | (device 모드) 장치 열기 실패 |

- Fault 상태에서는 `/vision/sign`을 `NONE`으로 보낸다. 감속/정지 판단은 D의 FSM이 한다.
- 지원 encoding: `bgr8`, `rgb8`, `bgra8`, `rgba8`, `mono8`, `yuv422`(UYVY), `yuv422_yuy2`(YUYV), `nv12`, `nv21`, `i420`, CompressedImage(jpeg/png)


## 실행

호스트 가상 카메라(`pi-camera-bridge`)와 컨테이너 실행은 [루트 README](../../../README.md#담당-b-vision--raspberry-pi) 참고.

```bash
# 컨테이너 안
cd /ros2_ws
colcon build --packages-select vision_pkg && source install/setup.bash
ros2 launch vision_pkg vision.launch.py                     # camera_publisher + vision_node
ros2 launch vision_pkg vision.launch.py debug_image:=true   # 박스 그린 이미지도 발행
ros2 launch vision_pkg vision.launch.py camera:=false       # vision_node만
```

확인 (노트북에서도 같은 `ROS_DOMAIN_ID`면 보임):
```bash
ros2 topic hz /camera/image_raw      # ~15 Hz
ros2 topic echo /vision/sign
ros2 topic echo /vision/fault
ros2 topic hz /vision/sign           # ~10 Hz
ros2 run rqt_image_view rqt_image_view /vision/debug/compressed
```
노드 로그에 5초마다 `발행 x FPS`(camera_publisher), `처리 x FPS, 추론 y ms`(vision_node)가 찍힌다.

Pi 5 측정값 (640x480, `onnx_threads: 2`): 카메라 발행 ~15 Hz, 처리 10 FPS, 추론 60~70 ms.
`onnx_threads: 4`로 올리면 추론은 조금 빨라지지만 camera_publisher와 CPU를 다퉈 카메라가 ~10 Hz로 떨어진다.

Fault 확인: camera_publisher를 끄면 `CAMERA_NO_PUBLISHER`, 다시 켜면 `OK`.
호스트 브리지(`sudo systemctl stop pi-camera-bridge`)를 멈추면 `CAMERA_TIMEOUT`.

## 테스트 사진으로 정확도 확인

휴대폰에 **실제 신호등 사진**을 띄우고 라벨별로 저장 (라벨 입력 후 Enter, `q`로 종료):
```bash
ros2 run vision_pkg topic_capture --topic /camera/image_raw --out /ros2_ws/src/vision_pkg/test_imgs
#   red ↵ → test_imgs/red_001.png,  green ↵ / yellow ↵ / none ↵ / stop ↵
```
거리와 각도를 바꿔 라벨당 5장 이상. 그다음 ROS2 없이 판정:
```bash
cd /ros2_ws/src/vision_pkg
python3 tools/vision_test.py --model models/yolov8n_320.onnx --source test_imgs/ --nogui --out result/
#   red_001.png → STOP | 65.1 ms | traffic_light(0.61,RED,area=0.031)
```
- 검출이 안 되면: 더 크고 선명한 사진, 휴대폰 밝기 조정, `--conf 0.25`
- 색이 틀리면: GUI가 있는 노트북에서 `--calib`로 HSV 조정 → `config/vision_params.yaml`에 반영
- `test_imgs/`, `result/`는 git에 올리지 않는다 (`.gitignore`)

## 미정 (D와 합의)

- 메시지 타입: `std_msgs/String` 유지 vs `hil_msgs/VisionSign` (#9)
- 노란불: STOP vs NONE (현재 STOP, `yellow_as`)
- 휴대폰을 내렸을 때 NONE을 "신호 없음"으로 볼지
- 재정지 방지(쿨다운)를 Vision이 할지 D의 FSM이 할지
- D가 Vision 다운으로 판단할 topic timeout (제안 1초)
