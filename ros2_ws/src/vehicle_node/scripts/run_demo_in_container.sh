#!/usr/bin/env bash
# 호스트 run_vehicle.sh가 호출합니다. 빌드 -> launch -> 명령 시연을 자동으로 실행합니다.
set -e -o pipefail
mode="${1:-gui}"
if [ "$mode" != "gui" ] && [ "$mode" != "headless" ]; then
  echo "실행 모드는 gui 또는 headless여야 합니다." >&2
  exit 1
fi

# 동일 컨테이너 안에서 두 시연을 동시에 시작하지 않도록 잠급니다.
exec 9>/tmp/vehicle_node_demo.lock
if ! flock -n 9; then
  echo "Vehicle 시연이 이미 실행 중입니다. 기존 터미널에서 Ctrl+C로 종료하세요." >&2
  exit 1
fi

source /opt/ros/humble/setup.bash
cd /ros2_ws
echo "[2/4] vehicle_node C++ 패키지 빌드"
# 이전 vehicle_a 빌드 결과를 읽지 않도록 별도 빌드/설치 경로를 사용합니다.
colcon build --packages-select vehicle_node --build-base build_vehicle \
  --install-base install_vehicle --cmake-args -DBUILD_TESTING=ON
source /ros2_ws/install_vehicle/setup.bash

launch_pid=""
cleanup_launch() {
  # 이 스크립트가 시작한 launch 그룹만 종료합니다.
  if [ -n "$launch_pid" ]; then
    kill -INT -- "-$launch_pid" 2>/dev/null || true
    wait "$launch_pid" 2>/dev/null || true
  fi
}
trap cleanup_launch EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

echo "[3/4] 새 Gazebo 월드와 Vehicle 실행"
gui="true"
if [ "$mode" = "headless" ]; then gui="false"; fi
setsid ros2 launch vehicle_node vehicle.launch.xml gui:="$gui" rviz:="$gui" \
  >/tmp/vehicle_node_launch.log 2>&1 &
launch_pid=$!

echo "[4/4] 전진 -> 후진 -> 좌회전 -> 우회전 -> 파킹"
# C++ 시연 노드가 실제 피드백과 통신 연결을 기다린 뒤 명령을 발행합니다.
if ! ros2 run vehicle_node driving_demo; then
  echo "시연을 완료하지 못했습니다. Gazebo 실행 로그:" >&2
  tail -n 30 /tmp/vehicle_node_launch.log >&2
  exit 1
fi

if [ "$mode" = "gui" ]; then
  echo "시연 완료: 차량은 주차 위치에 정지합니다. 화면을 닫으려면 이 터미널에서 Ctrl+C를 누르세요."
  wait "$launch_pid"
else
  echo "GUI 없는 주행·파킹 검증 완료"
fi
