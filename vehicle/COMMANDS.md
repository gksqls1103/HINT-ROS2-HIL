# 4륜 Vehicle 명령 실행표

전진 → 후진 → 좌회전 → 우회전 → 파킹을 한 번에 보고 싶다면 [DRIVING_DEMO.md](DRIVING_DEMO.md)의 주행 예시 스크립트를 실행하세요. 이 문서는 개별 명령을 설명합니다.

앞왼쪽·뒤왼쪽·앞오른쪽·뒤오른쪽 바퀴를 모두 구동합니다. 같은 쪽 앞뒤 바퀴를 함께 회전시키는 4륜 차동구동(skid-steer)입니다. 자동차 앞바퀴를 꺾는 Ackermann 조향은 아닙니다. 기존 `/cmd_vel` 계약을 사용합니다.

## 수동 명령

[README](README.md)대로 launch를 실행하고 별도 컨테이너 터미널에서 환경을 로드합니다.

```bash
source /opt/ros/humble/setup.bash
source /ros2_ws/install_vehicle/setup.bash
```

아래 명령을 하나씩 실행합니다. 다음 명령으로 바꾸기 전에 기존 발행자를 Ctrl+C로 종료합니다. 실제 Decision과 테스트 발행자를 함께 실행하지 않습니다.

| 동작 | linear.x (m/s) | angular.z (rad/s) |
|---|---:|---:|
| 전진 | 0.5 | 0 |
| 후진 | -0.4 | 0 |
| 감속 | 0.2 | 0 |
| 정지 | 0 | 0 |
| 전진 좌회전 | 0.3 | 0.2 |
| 전진 우회전 | 0.3 | -0.2 |
| 제자리 좌회전 | 0 | 0.4 |
| 제자리 우회전 | 0 | -0.4 |

```bash
# 전진
ros2 topic pub -r 20 /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.5}, angular: {z: 0.0}}'
# 후진
ros2 topic pub -r 20 /cmd_vel geometry_msgs/msg/Twist '{linear: {x: -0.4}, angular: {z: 0.0}}'
# 감속
ros2 topic pub -r 20 /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.2}, angular: {z: 0.0}}'
# 정지
ros2 topic pub -r 20 /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.0}, angular: {z: 0.0}}'
# 전진 좌회전
ros2 topic pub -r 20 /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.3}, angular: {z: 0.2}}'
# 전진 우회전
ros2 topic pub -r 20 /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.3}, angular: {z: -0.2}}'
# 제자리 좌회전
ros2 topic pub -r 20 /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.0}, angular: {z: 0.4}}'
# 제자리 우회전
ros2 topic pub -r 20 /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.0}, angular: {z: -0.4}}'
```

후진에서도 angular.z 양수는 차체 방향이 왼쪽으로 회전한다는 뜻입니다. 핸들 각도로 해석하지 않습니다.

## 제한·오류·단절

| 입력 | 기대 결과 |
|---|---|
| linear.x = 5 / -5 | 전달 속도 2 / -2 m/s로 제한 |
| angular.z = 5 / -5 | 전달 회전속도 1.5 / -1.5 rad/s로 제한 |
| NaN / 무한대 | 전체 명령 거부 후 정지 |
| linear.y/z 또는 angular.x/y가 0이 아님 | 지원하지 않는 축이므로 전체 명령 거부 후 정지 |
| 명령 발행 중단 | 0.5초 timeout 이후 정지 명령 전달 |
| Gazebo 일시정지로 피드백 단절 | 명령이 계속 와도 0.5초 후 정지 명령 전달 |
| 유효한 명령·피드백 재수신 | 주행 재개 |

횡이동 혼합 명령은 정지해야 합니다.

```bash
ros2 topic pub -r 20 /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.3, y: 0.2}, angular: {z: 0.0}}'
```

## C++ 자동 명령 검증

독립 월드와 launch를 실행한 상태에서:

```bash
ros2 run vehicle_node vehicle_smoke_test
```

실제 `/cmd_vel`에 명령을 보냅니다. `COMMAND`는 입력, `APPLIED`는 Vehicle이 Gazebo에 보낸 명령, `ODOM`은 바퀴 피드백, `WORLD`는 물리 월드 차체 속도입니다. 지원하지 않는 축과 NaN/무한대도 C++ 메시지로 전송합니다. 월드를 잠시 멈췄다가 재개하여 피드백 timeout을 검사합니다. 마지막에 0속도 명령을 보내며 실패 시 종료 코드 1을 반환합니다.

```bash
# 바퀴 피드백과 실제 차체 움직임을 비교합니다.
ros2 topic echo /vehicle/state
ros2 topic echo /vehicle/internal/ground_truth
ros2 topic echo /vehicle/internal/cmd_vel
```

`/vehicle/state`는 기존 계약의 바퀴 odometry이고 `/vehicle/internal/ground_truth`는 검증용 월드 좌표입니다. 장애물에 막히거나 미끄러지면 둘이 다를 수 있습니다. 외부 `/vehicle/state`, `/vehicle/pose`의 타입과 의미를 변경하지 않았습니다.
