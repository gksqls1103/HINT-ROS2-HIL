#!/usr/bin/env bash

# 명령 하나가 실패하면 잘못된 상태로 다음 명령을 실행하지 않고 종료합니다.
set -e

# 이 파일이 있는 scripts 폴더의 절대경로를 구합니다.
SCRIPT_DIRECTORY="$(cd "$(dirname "$0")" && pwd)"

# scripts 폴더의 상위 폴더를 프로젝트 폴더로 사용합니다.
PROJECT_DIRECTORY="$(dirname "$SCRIPT_DIRECTORY")"

# 어느 위치에서 스크립트를 실행해도 프로젝트 폴더에서 동작하게 합니다.
cd "$PROJECT_DIRECTORY"

# X11 프로그램이 컨테이너에서 호스트 화면을 사용할 수 있게 허용합니다.
# xhost 명령이 없는 환경에서는 이 부분을 건너뜁니다.
if command -v xhost >/dev/null 2>&1
then
    # 이미 허용되어 있거나 현재 환경에서 허용할 수 없어도 다음 확인을 계속합니다.
    xhost +local:docker >/dev/null 2>&1 || true
fi

# 기본 Docker 설정과 차량용 X11 설정을 함께 적용해서 컨테이너를 시작합니다.
docker compose \
    -f docker-compose.yml \
    -f docker-compose.vehicle.yml \
    up -d

# 최신 C++ 파일, launch 파일, world 파일이 적용되도록 패키지를 빌드합니다.
docker compose \
    -f docker-compose.yml \
    -f docker-compose.vehicle.yml \
    exec ros2_env bash -lc '
        source /opt/ros/humble/setup.bash
        cd /ros2_ws
        colcon build --packages-select vehicle_node --symlink-install
        source /ros2_ws/install/setup.bash
        ros2 launch vehicle_node track_3km.launch.xml
    '
