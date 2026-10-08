# 4륜 Vehicle 검증 결과

검증일: 2026-10-05. 실제 Gazebo Fortress의 독립 물리 월드에 C++ 도구로 `/cmd_vel` 명령을 발행했습니다. 최종 **39개 검사 PASS, 0개 FAIL, 종료 코드 0**입니다. 과거 검증 기록입니다.

## 환경과 모델

Ubuntu 22.04.5 LTS / ROS 2 Humble / Fortress 6.18.0에서 C++ 빌드가 경고 없이 통과했습니다. `ign sdf -k` 결과는 Valid입니다. 차량은 앞뒤 좌우 구동 바퀴 4개이며 캐스터가 없습니다. 외부 토픽 이름·메시지 타입·방향을 유지했습니다.

## 실제로 보낸 명령

| 종류 | 명령/동작 | 결과 |
|---|---|---|
| 전진/감속/정지 | v=0.5 → 0.2 → 0 | 통과 |
| 후진 | v=-0.4 | 통과 |
| 전진 좌우 회전 | v=0.3, w=±0.2 | 통과 |
| 후진 좌우 회전 | v=-0.3, w=±0.2 | 통과 |
| 저속 | v=0.05 | 통과 |
| 제자리 좌우 회전 | v=0, w=±0.4 | 통과 |
| 선속도 제한 | v=±5 → ±2 | 통과 |
| 각속도 제한 | w=±5 → ±1.5 | 통과 |
| 복합 제한 | v=5, w=5 → v=2, w=1.5 | 통과 |
| 비정상 숫자 | NaN 선속도, 무한대 각속도 | 정지 |
| 지원하지 않는 4개 축 | linear.y/z, angular.x/y 비영 값 | 전체 명령 거부·정지 |
| 오류 이후 복구 | 유효한 v=0.3 재전송 | 주행 재개 |
| 명령 timeout | 명령 발행 종료 | 실제 차체 정지 |
| 피드백 timeout | 명령 유지 중 Gazebo 일시정지 | 내부 구동 명령 0 |
| 피드백 복구 | Gazebo 재개, 명령 계속 발행 | 주행 재개 |
| 상태·위치 계약 | frame, timestamp, pose/state 일치 | 통과 |

v는 m/s, w는 rad/s입니다. 명령 입력, Vehicle의 전달 명령, 바퀴 odometry, 실제 물리 월드 차체 속도를 함께 기록했습니다.

## 확인하고 수정한 문제

기존 노드는 전진 명령에 횡이동 값이 섞여도 지원하지 않는 필드만 무시하고 전진했습니다. 실패 테스트로 확인했고, linear.y/z 또는 angular.x/y가 비영 값이면 전체 명령을 취소하고 정지하도록 고쳤습니다. 오류 로그의 반복 출력도 제한했습니다.

4륜 회전의 타이어 모서리 접촉 오차를 확인하여 외형 폭 8 cm와 접지부 충돌 폭 2 cm를 구분한 근사 모델을 적용했습니다. 진행 방향/횡방향 마찰 설정을 명시했습니다. w=0.2에서 실제 차체 회전속도가 약 0.175 → 0.193 rad/s로 개선됐습니다.

| 명령 | 바퀴 피드백 | 물리 월드 피드백 |
|---|---:|---:|
| v=0.5 | 0.5 | 0.5 |
| v=-0.4 | -0.4 | -0.4 |
| w=0.2 | 0.2 | 약 0.1931 |
| 제자리 w=0.4 | 0.4 | 약 0.3862 |
| 제자리 w=1.5 제한 | 1.5 | 약 1.4483 |

4륜 차동구동에는 회전 중 미끄러짐이 있으므로 바퀴 odometry와 월드 위치가 완전히 같지는 않습니다. 외부 상태는 기존 계약을 유지하고, 내부 ground_truth로 실제 움직임을 별도로 검사했습니다.

## 재현과 검증 범위

이후 주차선을 추가하고 C++ `driving_demo.sh` 시연도 완료했습니다. 전진·후진·좌회전·우회전·후진 주차를 GUI에서 실행했고 최종 위치 약 (1.365, 1.861 m)에서 주차 위치·정지 검사를 통과했습니다. [시연 안내와 화면](DRIVING_DEMO.md)을 참고하세요. 시연 프로그램과 최종 주차선 월드도 컴파일 경고 없이 빌드했고 SDF Valid를 확인했습니다.

[수동 개발 안내](DEVELOPMENT.md)대로 빌드·launch한 뒤 다른 컨테이너 터미널에서 `/opt/ros/humble/setup.bash`, `/ros2_ws/install_vehicle/setup.bash`를 source하고 `ros2 run vehicle_node vehicle_smoke_test`를 실행합니다. 다른 명령 발행자는 없어야 합니다. 수동 명령은 [COMMANDS.md](COMMANDS.md)에 있습니다.

패키지명을 `vehicle_node`로 변경한 뒤 실제 공용 Compose 컨테이너에서 `sh ros2_ws/src/vehicle_node/run_vehicle.sh --headless` 한 번으로 이미지 준비·C++ 빌드·launch·전진/후진/좌우 회전/파킹을 완료했습니다. 종료 코드 0이며 최종 위치 약 (1.379, 1.871 m)에서 주차 검사를 통과했습니다.

`sh ros2_ws/src/vehicle_node/run_vehicle.sh` 기본 GUI 실행도 최종 위치 약 (1.380, 1.886 m)에서 주차 검사를 통과했고 완료 후 화면을 유지했습니다. 실행 중 동일 컨테이너의 잠금이 두 번째 실행을 차단하는 것도 확인했습니다.

마지막으로 Ctrl+C 종료 시 이 스크립트의 launch/Vehicle/RViz가 종료되고 잠금이 해제되는 것을 확인했습니다. Docker 개발 컨테이너는 실행 상태로 유지됩니다.

실제 Decision/Vision/Safety와의 팀 통합 및 하드웨어 연결은 검증하지 않았습니다. 이번 결과는 명시한 39개 검사에 대한 기록입니다. 모든 수치 조합·충돌·프로세스 장애를 검증했다는 뜻은 아닙니다. 피드백 단절은 Gazebo 일시정지로 검사했습니다.

여러 바퀴의 구동 연결과 월드 피드백 검증은 [공식 DiffDrive 구현](https://github.com/gazebosim/gz-sim/blob/ign-gazebo6/src/systems/diff_drive/DiffDrive.cc), [공식 OdometryPublisher 구현](https://github.com/gazebosim/gz-sim/blob/ign-gazebo6/src/systems/odometry_publisher/OdometryPublisher.cc)을 참고했습니다.

## 2026-10-08 재검증

차량 전용 파일을 `ros2_ws/src/vehicle_node/`로 모은 뒤 `bash ros2_ws/src/vehicle_node/run_vehicle.sh --headless`를 실행했습니다. Docker 이미지 생성, vehicle_node C++ 빌드, Gazebo 기동, 전진·후진·좌우 회전·주차 시연이 모두 종료 코드 0으로 통과했습니다. 최종 위치는 약 (1.373, 1.878 m)이며 주차 구역 안에서 정지했습니다.

참고 역할 문서와 현재 Decision 소스를 대조한 결과 `/cmd_vel` 이름과 `geometry_msgs/msg/Twist` 타입은 일치합니다. `/vehicle/state`와 `/vehicle/pose`는 역할 문서대로 발행하지만, 현재 Decision에는 `/vehicle/state` 구독이 구현되지 않았습니다. 다른 담당 노드는 이번 작업에서 수정하지 않았습니다.

공용 루트 `Dockerfile`과 루트 `docker-compose.vehicle.yml`로 다시 빌드한 뒤 headless 주행 검증을 반복했습니다. Vehicle 빌드와 Gazebo 시연이 종료 코드 0으로 통과했고, 최종 위치는 약 (1.373, 1.878 m)입니다.

## Decision 명령 형식 모의 검증 (2026-10-08)

공용 Dockerfile 기반 컨테이너에서 `run_gazebo.sh --headless`로 Gazebo, bridge, Vehicle을 실행했습니다. 별도 터미널에서 `ros2 run vehicle_node vehicle_smoke_test`를 실행하여 Decision과 같은 `geometry_msgs/msg/Twist`를 `/cmd_vel`에 20 Hz로 발행했습니다. 종료 코드 0으로 통과했습니다. 전진 0.5 m/s 명령에 대해 적용 명령, 바퀴 odometry, 물리 월드 피드백이 모두 0.5 m/s였습니다. 0.2 m/s 감속, 0 m/s 정지, 좌우 회전, 명령 timeout 정지와 피드백 timeout 정지도 통과했습니다. 실제 Decision 프로세스를 연결한 검증은 아닙니다.
