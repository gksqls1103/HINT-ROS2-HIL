# Vehicle 수동 개발·통합 안내

담당 Vehicle은 인지 → 판단 → 제어 프로젝트의 **제어 및 가상 차량 시뮬레이션**을 구현합니다. Decision의 `/cmd_vel`을 받아 정지·감속·주행하고 `/vehicle/state`, `/vehicle/pose`를 제공합니다. 메시지 상세는 [INTERFACES.md](INTERFACES.md)를 참고하세요.

실제 컨테이너 빌드, 제어 시나리오 및 Gazebo/RViz GUI 확인 결과는 [VALIDATION.md](VALIDATION.md)에 기록했습니다. 4륜 모델의 전체 명령 예시는 [COMMANDS.md](COMMANDS.md)에 있습니다.

## 문서 선택

| 하고 싶은 일 | 읽을 문서 |
|---|---|
| 처음 빌드하고 실행하기 | 이 README의 1~2번 |
| 전진·후진·좌우 회전·파킹을 화면에서 보기 | [DRIVING_DEMO.md](DRIVING_DEMO.md) |
| 개별 명령 직접 보내기 | [COMMANDS.md](COMMANDS.md) |
| 움직인 차량을 시작 위치로 옮기기 | 이 문서의 4번 |
| Decision과 메시지 맞추기 | [INTERFACES.md](INTERFACES.md) |
| 검증 결과와 측정값 확인하기 | [VALIDATION.md](VALIDATION.md) |

## 내 폴더

| 경로 | 내용 |
|---|---|
| `ros2_ws/src/vehicle_node/` | Vehicle 전용 Dockerfile, 실행 및 인터페이스 문서 |
| `ros2_ws/src/vehicle_node/` | 담당 Vehicle의 독립 ROS 패키지 |
| `ros2_ws/src/vehicle_node/src/vehicle_node.cpp` | 한국어 주석이 있는 C++ 구독·발행 코드 |
| `ros2_ws/src/vehicle_node/launch/vehicle.launch.xml` | Gazebo, bridge, Vehicle, RViz 통합 실행 |
| `ros2_ws/src/vehicle_node/worlds/vehicle.sdf` | 차량, 직선/곡선 도로, 교차로, 정지선, 장애물 |
| `ros2_ws/src/vehicle_node/config/vehicle.rviz` | RViz 위치·상태·TF 화면 |

`docker-compose.vehicle.yml`은 루트의 공용 `Dockerfile`을 사용하며 차량 GUI 설정만 추가합니다. Humble의 공식 대응 Gazebo는 Fortress이며 `ros-humble-ros-gz`를 설치합니다. Fortress 명령 이름은 `ign gazebo`입니다. Gazebo Classic의 `gazebo` 명령과 `gazebo_ros` 플러그인을 사용하지 않습니다.

## 1. 호스트에서 컨테이너 준비

Linux Docker 호스트의 프로젝트 폴더에서 실행합니다.

```bash
cd /home/lee/hint/HINT-ROS2-HIL
cp -n .env.example .env
# X11 GUI 연결: root로 실행되는 로컬 컨테이너만 허용합니다.
xhost +si:localuser:root
docker compose -f docker-compose.yml -f docker-compose.vehicle.yml up -d --build
docker exec -it ros2_hil_env bash
```

`xhost`가 없으면 호스트에 X11 유틸리티가 필요합니다. Wayland에서는 XWayland DISPLAY를 사용합니다. DISPLAY가 설정되어 있는지 `echo "$DISPLAY"`로 확인하세요. Fedora/SELinux 호스트에서 마운트 접근이 거부되면 호스트 정책에 맞게 volume labeling 설정이 필요합니다. 기본 소프트웨어 렌더링은 GPU 없이 실행하기 위한 설정이며 느릴 수 있습니다.

## 2. 컨테이너 안에서 빌드·실행

```bash
source /opt/ros/humble/setup.bash
cd /ros2_ws
colcon build --packages-select vehicle_node --build-base build_vehicle --install-base install_vehicle
source install_vehicle/setup.bash
ros2 launch vehicle_node vehicle.launch.xml
```

GUI 없이 제어만 검증할 때:

```bash
ros2 launch vehicle_node vehicle.launch.xml gui:=false rviz:=false
```

월드는 자동으로 재생됩니다. 초기에는 차량이 정지합니다. 실행은 C++ 노드와 XML launch로 구성했습니다. ROS/colcon 자체의 Python 기반 도구는 환경 의존성입니다.

## 3. 독립 제어 검증

다른 호스트 터미널에서 컨테이너에 접속하고 환경을 로드합니다. 실제 Decision을 함께 실행할 때는 아래 테스트 발행자를 종료해야 합니다. 동시에 여러 `/cmd_vel` 발행자를 사용하면 명령이 섞입니다.

```bash
docker exec -it ros2_hil_env bash
source /opt/ros/humble/setup.bash
source /ros2_ws/install_vehicle/setup.bash
ros2 node list
ros2 topic info /cmd_vel -v
ros2 topic info /vehicle/state -v
ros2 topic echo /vehicle/state
```

각 명령을 종료하려면 Ctrl+C를 누릅니다. GO(전진):

```bash
ros2 topic pub -r 20 /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.5}, angular: {z: 0.0}}'
```

발행을 종료하면 약 0.5초 뒤 정지 명령이 전달됩니다. 감속 검증은 전진 발행자를 종료한 후 속도 0.2로 실행합니다.

```bash
ros2 topic pub -r 20 /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.2}, angular: {z: 0.0}}'
```

STOP(모든 속도 0):

```bash
ros2 topic pub -r 20 /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.0}, angular: {z: 0.0}}'
```

회전 및 위치 발행 검증:

```bash
ros2 topic pub -r 20 /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.3}, angular: {z: 0.2}}'
```

별도 터미널에서:

```bash
ros2 topic echo /vehicle/pose
ros2 topic hz /vehicle/state
ros2 topic hz /vehicle/pose
ros2 run tf2_ros tf2_echo odom base_link
```

정상 재생 시 약 20 Hz이며, 실제 시간당 관찰 주기는 시뮬레이션 real-time factor에 따라 달라집니다. 상태 속도와 위치 변화가 명령과 일치하는지 확인합니다. RViz는 `odom` 기준 위치 화살표, Odometry, TF를 표시합니다. 도로/차량 외형은 Gazebo 화면에서 확인합니다.

자동 검증은 다른 `/cmd_vel` 발행자가 없는 독립 월드에서 실행합니다. `colcon build --packages-select vehicle_node --build-base build_vehicle --install-base install_vehicle --cmake-args -DBUILD_TESTING=ON`으로 빌드한 후, launch가 실행 중인 별도 컨테이너 터미널에서:

```bash
source /opt/ros/humble/setup.bash
source /ros2_ws/install_vehicle/setup.bash
ros2 run vehicle_node vehicle_smoke_test
```

피드백, 물리 월드 위치, 전진/후진, 감속, STOP, 좌우 회전, 제자리 회전, 속도 제한, 오류 명령, 명령/피드백 timeout 및 복구를 검사합니다. 실패하면 종료 코드 1을 반환합니다.

## 4. 차량을 초기 위치로 옮기기

Gazebo 월드가 실행 중인 컨테이너 터미널에서 아래 스크립트를 실행하면 차량 모델을 시작 위치 `(x=0, y=0, z=0.21 m, yaw=0)`로 옮깁니다. 차량이 움직이는 중이라면 먼저 다른 터미널에서 `/cmd_vel`을 0으로 발행하고, 다른 `/cmd_vel` 발행자는 종료하세요.

```bash
cat > /tmp/reset_vehicle_pose.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

ign service -s /world/vehicle_world/set_pose \\
  --reqtype ignition.msgs.Pose \\
  --reptype ignition.msgs.Boolean \\
  --timeout 3000 \\
  --req 'name: "vehicle", position: {x: 0, y: 0, z: 0.21}, orientation: {w: 1}'
EOF
chmod +x /tmp/reset_vehicle_pose.sh
/tmp/reset_vehicle_pose.sh
```

서비스 호출 결과가 `data: true`이면 성공입니다. 위치는 `/vehicle/internal/ground_truth` 또는 Gazebo 화면에서 확인할 수 있습니다. 이 호출은 차량의 위치와 방향을 바꾸며, 차량을 정지시키는 명령은 아니므로 재설정 전에 속도 명령을 0으로 보내야 합니다.

## 5. Decision 연결

Decision은 현재 Twist를 Reliable / Volatile / Keep Last 10으로 5 Hz 발행합니다. 현재 Decision 코드에는 `/vehicle/state` 구독이 구현되지 않았으므로 차량 피드백을 이용한 정지 완료 판단은 아직 연결되지 않았습니다. 인지 이벤트와 FSM은 Decision이 처리하고, Vehicle은 내려온 명령을 실행합니다. 모든 컴퓨터의 `.env`에서 ROS_DOMAIN_ID, ROS_LOCALHOST_ONLY, RMW_IMPLEMENTATION을 맞춥니다. 상세 필드와 단위는 [INTERFACES.md](INTERFACES.md)를 따릅니다.

## 6. 종료·재빌드

launch 터미널에서 Ctrl+C로 종료하고 호스트에서:

```bash
docker compose -f docker-compose.yml -f docker-compose.vehicle.yml down
xhost -si:localuser:root
```

기존 빌드물을 삭제하지 않는 clean build 검증:

```bash
source /opt/ros/humble/setup.bash
cd /ros2_ws
colcon --log-base /tmp/vehicle-clean-log build --packages-select vehicle_node --build-base /tmp/vehicle-clean-build --install-base /tmp/vehicle-clean-install
source /tmp/vehicle-clean-install/setup.bash
ros2 launch vehicle_node vehicle.launch.xml gui:=false rviz:=false
```

## 코드 읽는 순서

`VehicleNode()`에서 파라미터/QoS와 통신을 만듭니다. `onCommand()`에서 Decision 명령을 검사합니다. `sendCommand()`에서 통신 단절 여부를 확인하고 Gazebo로 명령을 보냅니다. `onOdometry()`에서 Gazebo 피드백을 상태·위치·TF로 발행합니다. `main()`은 ROS 초기화와 콜백 실행을 담당합니다. ROS의 메시지 템플릿과 SharedPtr, 콜백 연결에 필요한 std::bind 외에 복잡한 문법을 사용하지 않았습니다.

## 범위와 한계

차량은 앞뒤 좌우 바퀴 4개를 모두 구동하는 차동구동 모델입니다. 실제 자동차 Ackermann 조향, 자동 경로 추종, 장애물 인지 센서는 구현 범위에 포함하지 않았습니다. 도로·교차로·곡선·정지선은 시나리오 환경이며 자동으로 길을 따라가거나 정지선을 인식하지 않습니다. 장애물은 물리 충돌체입니다. 외부 DiffDrive odometry는 월드 절대위치 센서가 아니며, 검증용 내부 ground_truth로 실제 차체 움직임을 별도로 검사합니다. 비상 정지는 Decision의 0속도 명령 전달을 검증하며 하드웨어 안전 인증을 의미하지 않습니다.

## 참고한 공식 문서

- [ROS 2 Humble와 Gazebo Fortress 대응](https://github.com/gazebosim/ros_gz/tree/humble)
- [Fortress ROS 2 연동](https://gazebosim.org/docs/fortress/ros2_integration/)
- [Fortress DiffDrive 예제](https://github.com/gazebosim/gz-sim/blob/ign-gazebo6/examples/worlds/diff_drive.sdf)
