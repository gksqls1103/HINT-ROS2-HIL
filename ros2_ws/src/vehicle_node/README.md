# Vehicle 실행 안내

Vehicle은 인지 → 판단 → 제어 프로젝트의 제어부입니다. Decision의 `/cmd_vel`을 받아 Gazebo의 4륜 차량을 움직이고 `/vehicle/state`, `/vehicle/pose`를 발행합니다.

## 1. 한 줄 실행

호스트 터미널에서 아래 명령을 실행하세요.

```bash
sh /home/lee/hint/HINT-ROS2-HIL/ros2_ws/src/vehicle_node/run_vehicle.sh
```

프로젝트 폴더에 있다면:

```bash
sh ros2_ws/src/vehicle_node/run_vehicle.sh
```

컨테이너 준비 → C++ 빌드 → Gazebo/RViz 실행 → 전진·후진·좌회전·우회전·후진 주차 명령을 자동으로 진행합니다. 처음에는 이미지 다운로드와 빌드 시간이 필요하며, 이후에는 빌드 캐시를 사용합니다.

Gazebo 월드는 x, y 각각 -4000 m부터 +4000 m까지 총 8 km × 8 km입니다. 500 m 간격의 격자 도로(각 방향 17개), 2 km 간격의 넓은 간선도로가 있습니다. 넓은 간선도로에는 중앙선, 가장자리 실선, 차로 구분 점선이 있습니다. 차량은 남쪽 안쪽 차로의 중앙인 `(0, -2.25)`에서 출발합니다. 원점 주변에는 횡단보도, 보도, 건물 외관과 전봇대가 있습니다. 동적 강체 보행자 4명이 x=8~30 m에 배치되어 차량과 충돌하면 물리적으로 밀리거나 넘어집니다. 이들은 자율 보행 애니메이션 없이 제자리에 서 있습니다. 외부 지도가 아닌 절차적으로 생성한 도시 도로망입니다. 차량 시연은 원점 주변에서 실행됩니다.

도로망을 수정한 뒤 다시 만들려면 `python3 ros2_ws/src/vehicle_node/worlds/generate_city_roads.py`를 실행하세요. 생성 결과는 `worlds/vehicle.sdf`에 들어가고 다음 실행 시 패키지에 설치됩니다.

## 2. 종료와 다시 실행

시연이 끝나면 차량은 주차 위치에 정지하고 화면은 유지됩니다. 실행한 터미널에서 Ctrl+C를 누르면 이 스크립트가 시작한 Gazebo·RViz·Vehicle이 종료됩니다. Docker 개발 컨테이너는 유지됩니다.

같은 명령을 다시 실행하면 새 월드의 시작점에서 다시 시연합니다. 실행 중에 두 번째 시연을 시작하면 잠금으로 중복 실행을 막습니다.

GUI 없이 명령·주차만 검사하고 자동 종료하려면:

```bash
sh ros2_ws/src/vehicle_node/run_vehicle.sh --headless
```

## 3. 실행 조건

Linux 호스트에 Docker와 Docker Compose가 있어야 하고, 현재 사용자에게 Docker 접근 권한이 필요합니다. GUI 실행에는 DISPLAY와 xhost가 필요합니다. 스크립트는 자신이 추가한 X11 접근 허용만 종료 시 해제합니다.

실제 Decision 또는 다른 `/cmd_vel` 발행자는 시연 전에 종료하세요. 시연 도구는 명령 충돌을 검사합니다. 이것은 Vehicle 제어 시연이며 인지·판단 모듈의 실행 스크립트는 아닙니다.

## 4. 폴더와 이름

`vehicle_a`를 기능 중심의 `vehicle_node`로 변경했습니다. 올바른 철자는 `vehicle_node`이며 `vechicle_node`는 사용하지 않습니다. 폴더명·ROS 패키지명·launch·스크립트·문서의 참조를 함께 변경했습니다. 외부 토픽과 메시지 계약은 유지합니다.

| 경로 | 용도 |
|---|---|
| `run_vehicle.sh` | 호스트에서 한 줄로 실행하는 진입점 |
| `ros2_ws/src/vehicle_node/` | C++ ROS 패키지 |
| `src/vehicle_node.cpp` | 구독·발행·제어 보호 처리 |
| `src/driving_demo.cpp` | 주행·주차 시연 명령 |
| `scripts/run_demo_in_container.sh` | 컨테이너 빌드·launch·시연·종료 관리 |
| `launch/vehicle.launch.xml` | Gazebo, bridge, Vehicle, RViz |
| `worlds/vehicle.sdf` | 8 km × 8 km 도로 월드, 4륜 차량과 원점 주행 시설 |
| `worlds/generate_city_roads.py` | 격자 도로 SDF 생성기 |

표의 src/scripts/launch/worlds 경로는 `ros2_ws/src/vehicle_node/` 아래입니다. 자동 실행은 `/ros2_ws/build_vehicle`, `/ros2_ws/install_vehicle`를 사용해 이전 패키지 빌드와 섞이지 않도록 했습니다.

## 5. 문서 선택

| 원하는 작업 | 문서 |
|---|---|
| 시연 순서·주차 결과 보기 | [DRIVING_DEMO.md](DRIVING_DEMO.md) |
| 개별 명령 직접 보내기 | [COMMANDS.md](COMMANDS.md) |
| Decision과 메시지 계약 맞추기 | [INTERFACES.md](INTERFACES.md) |
| 수동 빌드·launch·디버깅 | [DEVELOPMENT.md](DEVELOPMENT.md) |
| 검사 결과·측정값 확인 | [VALIDATION.md](VALIDATION.md) |

4륜 차동구동 모델이며 앞바퀴 조향 방식은 아닙니다. 주차 시연은 고정 속도 명령 시퀀스입니다. 실제 인지·경로 판단은 Decision의 책임입니다.
