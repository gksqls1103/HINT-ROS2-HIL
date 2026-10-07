#!/usr/bin/env bash
set -e -o pipefail

mode="${1:-gui}"
if [ "$mode" != "gui" ] && [ "$mode" != "headless" ]; then
  echo "실행 모드는 gui 또는 headless여야 합니다." >&2
  exit 1
fi

# 주행 시연 스크립트와 동시에 같은 월드를 시작하지 않습니다.
exec 9>/tmp/vehicle_node_demo.lock
if ! flock -n 9; then
  echo "Vehicle 월드가 이미 실행 중입니다. 기존 터미널에서 Ctrl+C로 종료하세요." >&2
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
