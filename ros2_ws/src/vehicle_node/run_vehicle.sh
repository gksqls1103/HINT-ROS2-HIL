#!/usr/bin/env bash
# sh run_vehicle.sh로 실행해도 내부 처리는 Bash로 통일합니다.
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi
set -e -o pipefail

# 스크립트 위치를 기준으로 찾으므로 어느 폴더에서 실행해도 됩니다.
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$project_dir"
mode="gui"
if [ "${1:-}" = "--headless" ]; then
  mode="headless"
elif [ "$#" -ne 0 ]; then
  echo "사용법: sh run_vehicle.sh [--headless]" >&2
  exit 1
fi

if ! command -v docker >/dev/null || ! docker info >/dev/null 2>&1; then
  echo "Docker가 실행 중이고 현재 사용자가 Docker에 접근할 수 있는지 확인하세요." >&2
  exit 1
fi

# 우리가 추가한 X11 허용만 종료 시 되돌립니다. 기존 설정은 보존합니다.
x11_added="false"
cleanup_host() {
  if [ "$x11_added" = "true" ]; then
    xhost -si:localuser:root >/dev/null 2>&1 || true
  fi
}
trap cleanup_host EXIT

if [ "$mode" = "gui" ]; then
  if [ -z "${DISPLAY:-}" ] || ! command -v xhost >/dev/null; then
    echo "GUI를 사용하려면 DISPLAY와 xhost가 필요합니다. GUI 없이 검사: sh run_vehicle.sh --headless" >&2
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

echo "[1/4] Vehicle 컨테이너 준비"
docker compose -f docker-compose.yml -f docker-compose.vehicle.yml up -d --build ros2_env

# 터미널에서는 Ctrl+C가 컨테이너 실행 프로그램에도 전달되도록 TTY를 사용합니다.
exec_options=(-T)
if [ -t 0 ] && [ -t 1 ]; then
  exec_options=()
fi
docker compose -f docker-compose.yml -f docker-compose.vehicle.yml exec "${exec_options[@]}" ros2_env bash \
  /ros2_ws/src/vehicle_node/scripts/run_demo_in_container.sh "$mode"
