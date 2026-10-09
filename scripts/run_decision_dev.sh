#!/usr/bin/env bash
set -euo pipefail

container_name="${ROS2_CONTAINER_NAME:-ros2_hil_env}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker CLI를 찾을 수 없습니다. Docker가 설치되어 있는지 확인하세요." >&2
  exit 1
fi

if ! docker container inspect "$container_name" >/dev/null 2>&1; then
  echo "컨테이너 '$container_name'가 없습니다. 먼저 Gazebo 실행 스크립트를 실행하세요." >&2
  exit 1
fi

if [ "$(docker container inspect -f '{{.State.Running}}' "$container_name")" != "true" ]; then
  echo "컨테이너 '$container_name'가 실행 중이 아닙니다. 먼저 Gazebo 실행 스크립트를 실행하세요." >&2
  exit 1
fi

exec docker exec -it "$container_name" bash -lc '
  set -euo pipefail
  source /opt/ros/humble/setup.bash
  cd /ros2_ws
  colcon build \
    --packages-up-to decision_node fake_nodes \
    --build-base build_hil \
    --install-base install_hil
  source /ros2_ws/install_hil/setup.bash
  exec ros2 launch decision_node decision_dev.launch.py
'
