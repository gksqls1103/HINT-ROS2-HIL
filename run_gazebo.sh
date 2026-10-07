#!/usr/bin/env bash
# Gazebo, ROS bridge, Vehicle 노드만 실행합니다.
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi
set -e -o pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_dir"

mode="gui"
if [ "${1:-}" = "--headless" ] && [ "$#" -eq 1 ]; then
  mode="headless"
elif [ "$#" -ne 0 ]; then
  echo "사용법: sh run_gazebo.sh [--headless]" >&2
  exit 1
fi

if ! command -v docker >/dev/null || ! docker info >/dev/null 2>&1; then
  echo "Docker가 실행 중이고 현재 사용자가 Docker에 접근할 수 있는지 확인하세요." >&2
  exit 1
fi

x11_added="false"
cleanup_host() {
  if [ "$x11_added" = "true" ]; then
    xhost -si:localuser:root >/dev/null 2>&1 || true
  fi
}
trap cleanup_host EXIT

if [ "$mode" = "gui" ]; then
  if [ -z "${DISPLAY:-}" ] || ! command -v xhost >/dev/null; then
    echo "GUI를 사용하려면 DISPLAY와 xhost가 필요합니다. GUI 없이 실행: sh run_gazebo.sh --headless" >&2
    exit 1
  fi
  if ! xhost >/dev/null 2>&1; then
    echo "현재 DISPLAY의 X11 서버에 연결할 수 없습니다." >&2
    exit 1
  fi
  if ! xhost | grep -Fq 'SI:localuser:root'; then
    xhost +si:localuser:root >/dev/null
    x11_added="true"
  fi
fi

docker compose -f docker-compose.yml -f docker-compose.vehicle.yml up -d --build ros2_env

exec_options=(-i)
if [ -t 0 ] && [ -t 1 ]; then
  exec_options=(-it)
fi

echo "Gazebo, ROS bridge, Vehicle 노드를 실행합니다. 종료하려면 Ctrl+C를 누르세요."
docker exec "${exec_options[@]}" ros2_hil_env bash \
  /ros2_ws/src/vehicle_node/scripts/run_gazebo_in_container.sh "$mode"
