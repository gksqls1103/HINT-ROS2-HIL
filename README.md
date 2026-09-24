# ROS2 기반 HIL 자율주행 차량 검증 시스템

## 🌿 브랜치 전략 (Branch Strategy)
본 프로젝트는 역할(Role) 기반의 독립적인 브랜치 모델을 사용합니다.

* `main`: 배포 및 최종 통합 브랜치
* `<역할>_prod`: 각 역할별 안정화(Production) 브랜치
* `dev/<역할>`: 각 역할별 메인 개발(Development) 브랜치 (※ 표기 주의: `dev/역할명`)
* `<역할>/feat/#이슈번호`: 새로운 기능 개발을 위한 브랜치
* `<역할>/fix/#이슈번호`: 버그 수정을 위한 브랜치

**[역할(Role) 키워드]**
* `vehicle` : 이종찬
* `vision` : 김민지
* `safety` : 김환희
* `decision` : 이한빈

## 🚀 담당자별 Docker 환경 실행

### 최초 준비

1. `git clone https://github.com/gksqls1103/HINT-ROS2-HIL.git`
2. `cd HINT-ROS2-HIL`
3. 각 담당자는 자신의 컴퓨터에서 `.env.example`을 복사해 개인용 `.env`를 만듭니다.
	- Windows PowerShell: `Copy-Item .env.example .env`
	- Linux/WSL2: `cp .env.example .env`
4. 각 담당자는 자신의 `.env`에서 장치 경로를 수정합니다.
5. 모든 담당자는 `.env`의 `ROS_DOMAIN_ID`, `ROS_LOCALHOST_ONLY`, `RMW_IMPLEMENTATION` 값을 동일하게 사용합니다.
6. `.env`는 컴퓨터별 설정 파일이므로 Git에 커밋하지 않습니다. `.gitignore`에 등록되어 있습니다.

### 담당 A: Vehicle

실제 카메라와 STM32를 연결하지 않고 Gazebo GUI만 추가합니다.

```bash
docker compose -f docker-compose.yml -f docker-compose.vehicle.yml up -d --build
docker exec -it ros2_hil_env bash
```

Windows에서는 X11 GUI가 바로 표시되지 않을 수 있으므로 WSL2 또는 Ubuntu 환경을 권장합니다.

### 담당 B: Vision / Raspberry Pi

`.env`의 `VISION_CAMERA_DEVICE`를 실제 카메라 경로로 설정한 뒤 실행합니다.

```bash
docker compose -f docker-compose.yml -f docker-compose.vision.yml up -d --build
docker exec -it ros2_hil_env bash
```

카메라 경로는 `ls /dev/video*`로 확인합니다.

### 담당 C: Safety / STM32 Bridge

`.env`의 `SAFETY_SERIAL_DEVICE`를 실제 STM32 장치 경로로 설정한 뒤 실행합니다.

```bash
docker compose -f docker-compose.yml -f docker-compose.safety.yml up -d --build
docker exec -it ros2_hil_env bash
```

시리얼 경로는 `ls /dev/ttyUSB*` 및 `ls /dev/ttyACM*`으로 확인합니다.

### 담당 D: Decision / State Machine

실제 하드웨어 없이 Decision 노드만 실행합니다.

```bash
docker compose -f docker-compose.yml -f docker-compose.decision.yml up -d --build
docker exec -it ros2_hil_env bash
```

### ROS 2 패키지 빌드

컨테이너 내부에서 실행합니다.

```bash
colcon build
source install/setup.bash
```

### 통신 확인

모든 컴퓨터가 같은 Wi-Fi에 연결되어 있고 `.env`의 ROS 2 통신 설정이 동일해야 합니다.

```bash
ros2 node list
ros2 topic list
```

ROS 2 노드가 서로 보이지 않으면 방화벽, Wi-Fi의 장치 간 통신 차단, `ROS_DOMAIN_ID`, DDS 설정을 확인합니다.

### 컨테이너 종료 및 재생성

```bash
docker compose down
docker compose -f docker-compose.yml -f docker-compose.vehicle.yml down
```

각 담당자는 자신이 사용한 override 파일을 포함해 종료해야 합니다.