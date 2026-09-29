# 담당 A Gazebo 가상 차량 개발 과정

## 1 문서 목적

이 문서는 `ref/ROS2_HIL_담당자별_역할실행계획서.docx`에 정의된 **담당 A Gazebo Virtual Vehicle** 역할을 실제로 개발하기 위한 절차서다. 현재 저장소에서 Vehicle 패키지를 생성하는 단계부터 Gazebo 시뮬레이션, Decision 노드 연동, Clean Build 검증까지를 다룬다.

담당 A의 최종 목표는 다음과 같다.

- Docker 환경에서 ROS 2와 Gazebo GUI를 실행한다.
- Road, Curve, Intersection, Stop Line, Obstacle을 구성한다.
- `/cmd_vel`을 구독해 주행, 감속, 정지 동작으로 변환한다.
- `/vehicle/state`와 `/vehicle/pose`를 Decision 노드와 RViz에 제공한다.
- Launch 파일로 Gazebo, 차량, Vehicle Node를 한 번에 실행한다.
- X11, ROS 2 Topic, 안정성, Clean Build를 검증한다.

## 2 담당 범위

### 포함되는 작업

1. Gazebo World와 가상 차량 Model 구성
2. Vehicle Node와 Gazebo 제어 플러그인 구현
3. ROS 2 Topic과 QoS 구현
4. Launch 파일 작성
5. Docker X11 GUI 검증
6. 독립 주행 및 Decision 통합 테스트
7. README, 실행 로그, 테스트 결과 정리

### 포함되지 않는 작업

- Vision 표지판 인식
- STM32, Ultrasonic, FreeRTOS 안전 로직
- Decision FSM 구현
- 팀 공통 Docker 기반 총괄

통합 테스트에서는 위 모듈이 생성한 이벤트와 명령이 Gazebo 차량에 올바르게 반영되는지 확인한다.

## 3 ROS 2 인터페이스 계약

| 구분 | Topic | 메시지 타입 | 상대 | 의미 |
|---|---|---|---|---|
| 구독 | `/cmd_vel` | `geometry_msgs/msg/Twist` | D → A | `linear.x`는 선속도, `angular.z`는 각속도 |
| 발행 | `/vehicle/state` | `std_msgs/msg/String` | A → D | `STOPPED`, `DRIVING` 차량 상태 |
| 발행 | `/vehicle/pose` | `geometry_msgs/msg/Pose2D` | A → D, RViz | `x`, `y`, `theta` 차량 위치 |
| 내부 | `/odom` | `nav_msgs/msg/Odometry` | Gazebo → Vehicle Node | Gazebo가 계산한 Pose와 Twist |

Topic 이름과 의미는 담당 D와 합의한 후 고정한다. 변경이 필요하면 공용 문서, 발행 노드, 구독 노드를 함께 수정한다.

### QoS 기준

- 제어 명령과 차량 상태는 우선 `Reliable`, `Keep Last`, Depth 10을 사용한다.
- Publisher와 Subscriber의 QoS 호환성을 `ros2 topic info -v`로 확인한다.
- 위치 발행 주기는 20 Hz로 시작하고 통합 테스트로 조정한다.

### Fail Safe 기준

- `/cmd_vel`이 1초 이상 수신되지 않으면 차량을 정지시킨다.
- NaN과 비정상적으로 큰 속도 명령을 검증한다.
- Node 종료 또는 Topic 단절 시 마지막 주행 명령을 계속 유지하지 않는다.

## 4 목표 디렉토리 구조

```text
ros2_ws/src/vehicle_node/
├── CMakeLists.txt
├── package.xml
├── config/
│   └── vehicle.yaml
├── include/vehicle_node/
│   └── vehicle_node.hpp
├── launch/
│   └── vehicle.launch.py
├── models/vehicle/
│   ├── model.config
│   └── model.sdf
├── src/
│   ├── vehicle_node.cpp
│   └── vehicle_gazebo_plugin.cpp
└── worlds/
    └── vehicle.world
```

Gazebo 표준 `diff_drive` 플러그인을 사용하면 자체 플러그인은 생략할 수 있다. 자체 플러그인을 사용하면 Command Timeout, 가속도, 최대 속도, Odometry 발행 역할을 분리한다.

## 5 개발 단계

### 5.1 공통 실행 환경 확인

1. `.env.example`을 `.env`로 복사한다.
2. `ROS_DOMAIN_ID`, `ROS_LOCALHOST_ONLY`, `RMW_IMPLEMENTATION`을 팀원과 맞춘다.
3. Vehicle Docker override를 포함해 컨테이너를 빌드한다.
4. 컨테이너에서 ROS 2와 Gazebo를 확인한다.

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.vehicle.yml up -d --build
docker exec -it ros2_hil_env bash
```

컨테이너 안에서 확인한다.

```bash
source /opt/ros/humble/setup.bash
ros2 --help
gazebo --version
```

Linux 호스트에서 X11을 확인한다.

```bash
echo "$DISPLAY"
ls -l /tmp/.X11-unix
xhost +SI:localuser:root
```

완료 조건:

- `ros2_hil_env` 컨테이너가 실행된다.
- Gazebo GUI가 호스트 화면에 표시된다.
- ROS 2 CLI가 정상 실행된다.

### 5.2 Vehicle 패키지 생성

```bash
cd /ros2_ws/src
ros2 pkg create vehicle_node \
  --build-type ament_cmake \
  --dependencies rclcpp geometry_msgs std_msgs nav_msgs gazebo_ros
```

`package.xml`에 의존성을 정리하고 `CMakeLists.txt`에 Vehicle Node, Gazebo 플러그인, Launch, Model, World 설치 규칙을 추가한다.

```bash
cd /ros2_ws
colcon build --packages-select vehicle_node
source install/setup.bash
ros2 pkg executables vehicle_node
```

### 5.3 Gazebo World 구성

다음 구성을 순서대로 추가한다.

1. Ground Plane과 Light
2. 직선 Road
3. Curve
4. Intersection
5. Stop Line과 차선
6. Collision이 있는 Obstacle
7. 차량 Spawn 지점과 기본 Camera 시점

검증 항목:

- Road Visual과 Collision 좌표가 일치한다.
- 차량이 도로 아래로 하락하지 않는다.
- 장애물을 통과하지 않는다.
- 정지선과 교차로가 명확하게 보인다.

### 5.4 가상 차량 Model 구성

필수 요소:

- `base_link`, 차체 Collision, Visual
- 왼쪽·오른쪽 Wheel Link과 Joint
- Mass, Inertia, Tire Friction
- ROS 2 제어 플러그인

주의사항:

- SI 단위를 사용한다. 길이는 m, 질량은 kg, 속도는 m/s다.
- Inertia가 비정상적으로 작으면 차량이 튀거나 전복된다.
- Collision은 Visual Mesh보다 단순한 Box, Cylinder 조합을 사용한다.
- Wheel Radius와 Wheel Separation은 속도 계산과 일치해야 한다.
- 마찰이 너무 크면 회전이 어렵고, 너무 작으면 미끄러진다.

완료 조건:

- 차량이 지면 위에 안정적으로 Spawn된다.
- 직진, 후진, 좌회전, 우회전이 가능하다.
- 충돌 후 시뮬레이션이 발산하지 않는다.

### 5.5 Vehicle Node 구현

Vehicle Node는 Gazebo와 Decision Node 사이의 상태 인터페이스를 담당한다.

1. `/cmd_vel` 구독과 마지막 명령 시간 기록
2. `/odom` 구독
3. Quaternion을 Yaw로 변환
4. `/vehicle/state` 발행
5. `/vehicle/pose` 발행
6. Timeout 시 `STOPPED` 처리

상태 판정 기준:

```text
abs(linear.x) < epsilon && abs(angular.z) < epsilon
  -> STOPPED

그 외
  -> DRIVING
```

검증 명령:

```bash
ros2 node list
ros2 topic list
ros2 topic info /cmd_vel -v
ros2 topic echo /vehicle/state
ros2 topic echo /vehicle/pose
```

### 5.6 Gazebo 차량 제어 구현

```text
/cmd_vel
  -> cmdVelCallback
  -> 목표 선속도와 각속도 저장
  -> Gazebo Update Tick
  -> 가속도와 감속도 적용
  -> Wheel Joint 또는 차체 속도 적용
  -> /odom 발행
```

구현 순서:

1. 정지
2. 저속 직선 주행
3. 후진
4. 좌·우 회전
5. 가속·감속
6. Command Timeout
7. `/odom` Pose와 Twist 발행

| 파라미터 | 의미 | 초기 값 예시 |
|---|---|---|
| `wheel_radius` | 바퀴 반지름 | `0.095 m` |
| `wheel_separation` | 좌·우 바퀴 간격 | `0.48 m` |
| `linear_acceleration` | 선가속도 | `2.0 m/s²` |
| `angular_acceleration` | 각가속도 | `2.0 rad/s²` |
| `command_timeout` | 명령 단절 후 정지 시간 | `1.0 s` |
| `publish_rate` | 상태 발행 주기 | `20 Hz` |

### 5.7 Launch 파일 구현

Launch 파일은 다음을 한 번에 실행해야 한다.

1. Gazebo Server와 Client
2. World
3. Vehicle Model Spawn
4. Vehicle Node
5. Parameter 파일

```bash
ros2 launch vehicle_node vehicle.launch.py
```

종료 후 남은 `gzserver`, `gzclient` 프로세스와 Gazebo Port 충돌이 없어야 한다.

### 5.8 독립 주행 테스트

직진:

```bash
ros2 topic pub -r 10 /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 1.0}, angular: {z: 0.0}}"
```

좌회전:

```bash
ros2 topic pub -r 10 /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.5}, angular: {z: 0.5}}"
```

우회전:

```bash
ros2 topic pub -r 10 /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.5}, angular: {z: -0.5}}"
```

후진:

```bash
ros2 topic pub -r 10 /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: -0.5}, angular: {z: 0.0}}"
```

정지:

```bash
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.0}, angular: {z: 0.0}}"
```

검증 항목:

- 직진·후진 시 위치가 서로 반대 방향으로 변한다.
- 회전 시 `theta`의 부호와 값이 변한다.
- 정지 명령 후 속도가 0으로 감속한다.
- 명령 중단 시 Timeout 후 자동 정지한다.
- 주행 중 `DRIVING`, 정지 후 `STOPPED`가 발행된다.

### 5.9 Decision Node와 1차 연동

연동 전 확인:

```bash
ros2 topic type /cmd_vel
ros2 topic type /vehicle/state
ros2 topic type /vehicle/pose
ros2 topic info /cmd_vel -v
ros2 topic hz /vehicle/state
ros2 topic hz /vehicle/pose
```

연동 시나리오:

1. Decision Node가 GO 상태에서 `/cmd_vel`을 발행한다.
2. Vehicle이 `DRIVING`으로 전환하고 Pose가 변한다.
3. Vision STOP Event를 Fake Topic으로 발행한다.
4. Decision이 정지 명령을 발행한다.
5. Vehicle이 감속 후 `STOPPED`를 발행한다.
6. Safety EMERGENCY Event 시 즉시 정지하는지 확인한다.

담당 A는 Topic Echo, State 전환, Pose 변화, Gazebo 화면, 통합 로그를 증적으로 남긴다.

### 5.10 안정화와 Clean Build

- 고속 명령에서 차량이 튀거나 전복되지 않는지 확인한다.
- 좌·우 회전 부호가 ROS 좌표계와 일치하는지 확인한다.
- 정지 후 밀림과 Pose Drift를 측정한다.
- Obstacle 충돌 후 Pose와 상태를 확인한다.
- Gazebo 종료 후 고아 프로세스가 없어야 한다.
- 재실행 시 같은 초기 위치에서 시작해야 한다.

```bash
docker compose -f docker-compose.yml -f docker-compose.vehicle.yml down
docker compose -f docker-compose.yml -f docker-compose.vehicle.yml up -d --build
docker exec -it ros2_hil_env bash

cd /ros2_ws
colcon build --packages-select vehicle_node
source install/setup.bash
ros2 launch vehicle_node vehicle.launch.py
```

## 6 테스트 체크리스트

### 독립 기능

- [ ] Docker Image Build와 Container 실행
- [ ] Gazebo GUI X11 출력
- [ ] Vehicle Model Spawn
- [ ] `/cmd_vel` Subscriber
- [ ] `/vehicle/state`, `/vehicle/pose` Publisher
- [ ] 직진, 후진, 좌회전, 우회전
- [ ] 감속 후 정지
- [ ] Command Timeout 자동 정지
- [ ] X, Y, Theta 변화

### 통합 기능

- [ ] D의 Decision Node 명령 수신
- [ ] GO 명령 시 DRIVING
- [ ] STOP Marker 시 STOPPED
- [ ] Emergency 시 즉시 정지
- [ ] Recovery 후 주행 재개
- [ ] ROS 2 통신 단절 시 Fail Safe 정지

### 안정성과 재현성

- [ ] 30분 이상 실행 중 Gazebo 종료 없음
- [ ] 차량이 지면 아래로 하락하지 않음
- [ ] 정지 중 Pose Drift가 허용 범위 이내임
- [ ] 재실행 시 Gazebo Port 충돌 없음
- [ ] Clean Build 성공
- [ ] 다른 팀원 PC에서 README만으로 재현 가능

## 7 문제 발생 시 진단 순서

문제는 **개별 Node → ROS 2 Topic → Gazebo → 통합** 순서로 범위를 줄인다.

### Gazebo GUI가 보이지 않음

```bash
echo "$DISPLAY"
ls -l /tmp/.X11-unix
xhost
docker exec ros2_hil_env printenv DISPLAY
```

`DISPLAY`, X11 Volume, X Server 권한, XWayland, Qt `xcb` 오류를 확인한다.

### 차량이 Spawn되지 않음

```bash
ros2 service list | grep spawn
ros2 topic list
```

Gazebo ROS Factory Plugin, SDF 경로, Mesh URI, Model 이름 중복, Spawn 타이밍을 확인한다.

### `/cmd_vel`을 보내도 움직이지 않음

```bash
ros2 topic info /cmd_vel -v
ros2 topic echo /cmd_vel
ros2 node list
```

Topic 이름, Namespace, QoS, Wheel Joint 이름, Wheel Radius, Timeout을 확인한다.

### 회전 방향이 반대임

- ROS 2에서 `angular.z > 0`은 반시계 방향이다.
- Wheel Joint Axis와 `/vehicle/pose.theta` 부호를 확인한다.

### 차량이 튀거나 전복됨

- Mass, Inertia, Spawn Z, Collision 겹침을 확인한다.
- Wheel Torque, Friction, Physics Time Step을 조정한다.
- 고속 명령에 속도 상한과 가속도 제한을 적용한다.

## 8 주차별 개발 일정

| 기간 | 작업 | 완료 조건 |
|---|---|---|
| 9/23 ~ 9/26 | Interface 확정, Docker Gazebo, X11 확인 | 공통 Container에서 Gazebo GUI 실행 |
| 9/26 ~ 10/2 | World, Vehicle, Vehicle Node, 이동·정지 MVP | `/cmd_vel`로 이동과 정지 |
| 10/3 ~ 10/6 | Decision과 ROS 2 1차 연결 | D의 명령으로 Gazebo 제어 |
| 10/7 ~ 10/10 | Gazebo 안정화, HIL End to End MVP | Emergency Stop 포함 전체 흐름 |
| 10/11 ~ 10/14 | 경로·환경 보완, 최종 시나리오 | STOP, GO, Emergency, Recovery, Fault |
| 10/15 ~ 10/17 | Bug Fix, Feature Freeze | 신규 기능 없이 결함 수정 |
| 10/18 ~ 10/19 | 전체 환경 재구축 | Clean Build 성공 |
| 10/20 | 코드, README, 영상 정리 | 최종 제출 |

## 9 마일스톤

| 날짜 | 체크포인트 | 증적 |
|---|---|---|
| 9/25 | Docker에서 Gazebo와 ROS 2 Workspace 실행 | Container, GUI, Build 로그 |
| 10/02 | 차량 이동·정지 MVP | Topic Echo, Gazebo 영상 |
| 10/06 | STOP Marker → Decision → Gazebo STOP | State와 Pose 변화 |
| 10/10 | Ultrasonic → STM32 → ROS 2 → Emergency Stop | 정지 응답 시간 |
| 10/14 | 전체 시나리오 동작 | 통합 테스트 기록 |
| 10/20 | Clean Build과 README 재현 | 새 환경 실행 기록 |

## 10 최종 산출물

- `vehicle_node` ROS 2 패키지
- Gazebo World, Vehicle SDF, Mesh
- 차량 제어 플러그인 또는 표준 Plugin 설정
- Vehicle Launch와 Parameter 파일
- Docker X11 실행 설정
- 독립 테스트와 Decision 통합 테스트 결과
- Clean Build 및 README 재현 절차

## 11 완료 정의

1. Clean Build 상태에서 Vehicle 패키지가 빌드된다.
2. Launch 명령 한 번으로 Gazebo, World, Vehicle, Vehicle Node가 실행된다.
3. `/cmd_vel`로 직진, 후진, 좌회전, 우회전, 정지가 동작한다.
4. 명령 단절 시 Timeout 후 정지한다.
5. `/vehicle/state`와 `/vehicle/pose`가 정의된 타입과 주기로 발행된다.
6. Decision의 GO, STOP, Emergency 명령이 차량에 반영된다.
7. Gazebo GUI가 Docker X11 패스스루로 표시된다.
8. 30분 이상 실행해도 Node 종료와 Gazebo 발산이 없다.
9. 다른 팀원이 README만 보고 결과를 재현할 수 있다.

## 12 개발 기록 템플릿

```markdown
## 작업명

### 목적
- 작업이 필요한 이유

### 변경 파일
- path/to/file

### 구현 내용
- 구현한 기능
- 주요 설계 결정

### 테스트
- 실행 명령
- 기대 결과
- 실제 결과

### 문제와 해결
- 발생한 문제
- 원인
- 해결 방법

### 남은 작업
- 후속 작업
```
