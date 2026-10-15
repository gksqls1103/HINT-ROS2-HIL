#!/usr/bin/env bash
# ROS와 workspace 환경을 먼저 source한 뒤 실행합니다.
# C++ 시연 노드가 전진/후진/좌우 회전/후진 주차 명령을 순서대로 보냅니다.
set -euo pipefail
exec ros2 run vehicle_node driving_demo "$@"
