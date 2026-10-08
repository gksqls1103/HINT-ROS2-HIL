#!/usr/bin/env bash
set -e -o pipefail

mode="${1:-gui}"
if [ "$mode" != "gui" ] && [ "$mode" != "headless" ]; then
  echo "실행 모드는 gui 또는 headless여야 합니다." >&2
  exit 1
fi

# 이전 Vehicle launch가 남아 있으면 그 프로세스에 종료 신호를 보냅니다.
# 다른 패키지의 Gazebo 월드와 launch는 종료하지 않습니다.
mapfile -t previous_launches < <(
  pgrep -f '^/usr/bin/python3 /opt/ros/humble/bin/ros2 launch vehicle_node vehicle.launch.xml( |$)' || true
)
for pid in "${previous_launches[@]}"; do
  echo "기존 Vehicle Gazebo launch 종료: PID $pid"
  kill -INT "$pid" 2>/dev/null || true
done
for attempt in {1..40}; do
  [ "${#previous_launches[@]}" -eq 0 ] && break
  still_running=false
  for pid in "${previous_launches[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then still_running=true; fi
  done
  [ "$still_running" = false ] && break
  sleep 0.25
done
for pid in "${previous_launches[@]}"; do
  if kill -0 "$pid" 2>/dev/null; then kill -TERM "$pid" 2>/dev/null || true; fi
done

# 이전 launch가 비정상 종료되어 Gazebo만 남은 경우에도 이 차량 월드만 정리합니다.
mapfile -t previous_gazebo < <(pgrep -f '^ign gazebo -r (-s )?.*/vehicle.sdf$' || true)
for pid in "${previous_gazebo[@]}"; do
  echo "기존 Vehicle Gazebo 종료: PID $pid"
  kill -INT "$pid" 2>/dev/null || true
done

# 주행 시연 스크립트와 동시에 같은 월드를 시작하지 않습니다.
exec 9>/tmp/vehicle_node_demo.lock
if ! flock -w 5 9; then
  echo "Vehicle 월드 잠금을 해제하지 못했습니다. 실행 중인 차량 시연을 확인하세요." >&2
  exit 1
fi

source /opt/ros/humble/setup.bash
cd /ros2_ws
colcon build --packages-select vehicle_node --build-base build_vehicle \
  --install-base install_vehicle --cmake-args -DBUILD_TESTING=OFF
source /ros2_ws/install_vehicle/setup.bash

gui="true"
if [ "$mode" = "headless" ]; then gui="false"; fi
exec ros2 launch vehicle_node vehicle.launch.xml gui:="$gui" rviz:=false
