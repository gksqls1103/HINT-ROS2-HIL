# Vehicle 구독·발행 인터페이스

## 프로젝트에서 Vehicle이 하는 일

인지(Vision / Safety) → 판단(Decision) → 제어(Vehicle / Gazebo).

Vehicle은 Decision의 속도 명령을 가상 차량의 바퀴 구동으로 변환하고, Gazebo에서 받은 차량 위치·자세·속도를 Decision과 RViz에 제공합니다. 표지 인식, 장애물 판단, STOP/GO 이벤트 판단과 FSM은 Decision의 책임입니다. Vehicle은 명령/피드백 단절 시 정지하는 실행부 보호 기능을 제공합니다.

원본 역할 문서의 토픽 이름·방향·의미를 유지했습니다. 원본에는 메시지 타입·QoS 수치가 없으므로 아래 항목은 이번 개발에서 정한 구체적인 계약입니다. `/vehcile/state`가 아닌 `/vehicle/state`입니다.

## 외부 계약

| 연결 | 토픽 | 메시지 타입 | 주기 | QoS |
|---|---|---|---|---|
| Decision → Vehicle | `/cmd_vel` | `geometry_msgs/msg/Twist` | 권장 20 Hz, 간격 0.5초 이하 | Reliable / Volatile / Keep Last 10 |
| Vehicle → Decision | `/vehicle/state` | `nav_msgs/msg/Odometry` | 시뮬레이션 시간 기준 20 Hz | Reliable / Volatile / Keep Last 10 |
| Vehicle → Decision / RViz | `/vehicle/pose` | `geometry_msgs/msg/PoseStamped` | 시뮬레이션 시간 기준 20 Hz | Reliable / Volatile / Keep Last 10 |

Reliable 구독자는 Reliable 발행자와 연결해야 합니다. Decision의 `/cmd_vel` 발행을 Best Effort로 설정하면 Vehicle의 구독과 연결되지 않습니다. Volatile이므로 새 노드에 과거 명령을 재전송하지 않습니다. 모든 컴퓨터에서 ROS_DOMAIN_ID와 DDS 설정을 맞춥니다.

### `/cmd_vel`: 차량을 어떻게 움직일지

| 필드 | 의미 | 단위/규칙 |
|---|---|---|
| `linear.x` | 전진/후진 목표 속도 | m/s, 양수 전진, 음수 후진, 범위 -2.0~2.0 |
| `angular.z` | 목표 회전속도 | rad/s, 양수 좌회전, 음수 우회전, 범위 -1.5~1.5 |
| 나머지 linear/angular 필드 | 평면 4륜 차동구동에서 지원하지 않음 | 반드시 0, 비영 값은 전체 명령 거부 후 정지 |

전진 예: `{linear: {x: 0.5}, angular: {z: 0.0}}`.
감속 예: 0.5 m/s 주행 중 `{linear: {x: 0.2}, angular: {z: 0.0}}`.
정지 예: `{linear: {x: 0.0}, angular: {z: 0.0}}`.
곡선 예: `{linear: {x: 0.3}, angular: {z: 0.2}}`.

Twist에는 timestamp가 없습니다. Vehicle은 수신 시점의 실제 단조 증가 시간을 사용해 timeout을 검사합니다. Decision은 명령을 주기적으로 발행해야 합니다. 범위 초과는 제한하고 NaN/무한대는 정지 처리합니다. 감속 목표는 즉시 전달하며 별도 가속도 램프는 없습니다. 실제 감속/정지 시간은 시뮬레이터 물리 상태에 따릅니다.

### `/vehicle/state`: 현재 차량이 실제로 어떻게 움직이는지

| 필드 | 제공 정보 | 사용 방법 |
|---|---|---|
| `header.stamp` | Gazebo 피드백 생성 시뮬레이션 시간 | 피드백 신선도 검사 |
| `header.frame_id` | `odom` | 위치/자세 기준 좌표계 |
| `child_frame_id` | `base_link` | 속도 기준 차체 좌표계 |
| `pose.pose.position.x/y/z` | 현재 위치 | m, odom 기준 |
| `pose.pose.orientation.x/y/z/w` | 현재 방향 | quaternion, 각도가 아님 |
| `twist.twist.linear.x/y/z` | 피드백 선속도 | m/s, base_link 기준 |
| `twist.twist.angular.x/y/z` | 피드백 각속도 | rad/s, base_link 기준 |
| `pose.covariance`, `twist.covariance` | Gazebo가 제공한 공분산 배열 | 원본 보존, 0을 완벽한 정확도로 해석하지 않음 |

주행 확인은 명령 속도가 아닌 `twist.twist.linear.x`와 `angular.z`로 합니다. 예를 들어 `abs(linear.x) < 0.02` 및 `abs(angular.z) < 0.02`를 정지 판정의 초기 기준으로 사용할 수 있지만, Decision에서 연속 유지 시간과 임계값을 결정해야 합니다.

Odometry는 `DRIVING`, `EMERGENCY`, `FAIL-SAFE` 같은 FSM 문자열을 담지 않습니다. 해당 판단은 Decision이 담당합니다. 배터리, 센서 장애물 거리, STOP 표지 인식 결과도 이 토픽에 임의로 추가하지 않습니다. 그런 정보가 필요하면 별도 합의가 필요합니다.

피드백은 DiffDrive의 바퀴 운동 기반 odometry입니다. 충돌/미끄러짐 시 월드의 절대 위치와 차이가 생길 수 있으며 ground-truth 센서는 아닙니다. 피드백이 없으면 상태/위치를 만들어 발행하지 않습니다. Decision도 상태 수신 단절을 검사해야 합니다.

### `/vehicle/pose`: 위치와 방향만 필요한 소비자

| 필드 | 값/의미 |
|---|---|
| `header.stamp` | `/vehicle/state`와 동일한 피드백 시간 |
| `header.frame_id` | `odom` |
| `pose.position` | `/vehicle/state.pose.pose.position`과 동일 |
| `pose.orientation` | `/vehicle/state.pose.pose.orientation`과 동일 |

RViz의 Fixed Frame은 `odom`입니다. TF `odom → base_link`도 함께 제공합니다. x 전방, y 좌측, z 위쪽입니다. odom은 차량 시작 지점을 원점으로 하는 로컬 좌표이며 지도 좌표 `map`이나 GPS가 아닙니다.

## 내부 연결: Decision에서 직접 사용하지 않는 토픽

| 연결 | ROS 토픽 | 메시지 | 설명 |
|---|---|---|---|
| Vehicle → bridge → Gazebo | `/vehicle/internal/cmd_vel` | Twist | 보호 처리된 구동 명령, 20 Hz 및 명령 수신 즉시 |
| Gazebo → bridge → Vehicle | `/vehicle/internal/odometry` | Odometry | 시뮬레이터 피드백, Vehicle 구독 QoS Best Effort / Volatile / 10 |
| Gazebo → bridge → 검증 도구 | `/vehicle/internal/ground_truth` | Odometry | 실제 물리 월드 차체 위치·속도, `world` 기준 |
| Gazebo → ROS | `/clock` | `rosgraph_msgs/msg/Clock` | 시뮬레이션 시간 |
| Vehicle → RViz | `/tf` | `tf2_msgs/msg/TFMessage` | odom → base_link, tf2 기본 QoS |

Gazebo Transport의 `/model/vehicle/cmd_vel`과 `/model/vehicle/odometry`는 bridge에서 위 내부 ROS 토픽으로 연결합니다. bridge를 외부 `/cmd_vel`에 직접 연결하면 Vehicle의 보호 처리를 우회하므로 그렇게 구성하지 않습니다.

검증용 `/world/vehicle_world/control` 서비스(`ros_gz_interfaces/srv/ControlWorld`)는 Gazebo 일시정지/재개에 사용합니다. 외부 Vehicle → Decision 토픽 계약에 포함하지 않습니다. 4륜 구동과 명령 예시는 [COMMANDS.md](COMMANDS.md)에 있습니다.

## 제어 보호 동작

시작 시 정지합니다. 최초 피드백과 유효한 명령이 모두 있어야 주행합니다. 명령 수신 간격 또는 피드백 수신 간격이 0.5초를 넘으면 50 ms 주기의 타이머가 정지 명령을 발행합니다. STOP 명령은 수신 콜백에서 즉시 전달합니다. 유효한 명령과 피드백이 다시 수신되면 주행 가능합니다.

Gazebo 일시정지 중에도 watchdog은 실제 시간으로 실행합니다. 시뮬레이터가 멈춰 있으면 물리 처리는 재개 시 진행됩니다. Vehicle 프로세스 자체가 강제 종료되면 watchdog도 멈추므로 이 기능을 하드웨어 안전 정지나 프로세스 장애 대응 장치로 간주하지 않습니다.

`/system/fault`의 타입과 값은 원본 문서에 정의되어 있지 않아 이번 구현에 임의 구독을 추가하지 않았습니다. 현재 Decision은 fault/emergency 상황에서 `/cmd_vel`에 0을 발행해야 합니다.
