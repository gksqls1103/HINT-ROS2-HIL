# ROS2 기반 HIL 자율주행 차량 검증 시스템

## 🌿 브랜치 전략 (Branch Strategy)
본 프로젝트는 역할(Role) 기반의 독립적인 브랜치 모델을 사용합니다.

* `master`: 배포 및 최종 통합 브랜치
* `<역할>_prod`: 각 역할별 안정화(Production) 브랜치
* `dev/<역할>`: 각 역할별 메인 개발(Development) 브랜치 (※ 표기 주의: `dev/역할명`)
* `<역할>/feat/#이슈번호`: 새로운 기능 개발을 위한 브랜치
* `<역할>/fix/#이슈번호`: 버그 수정을 위한 브랜치

**[역할(Role) 키워드]**
* `vehicle` : 이종찬
* `vision` : 김민지
* `safety` : 김환희
* `decision` : 이한빈

## 🚀 환경 실행 가이드 (공통)
1. `git clone https://github.com/gksqls1103/HINT-ROS2-HIL.git`
2. `cd HINT-ROS2-HIL`
3. `docker-compose up -d`
4. `docker exec -it ros2_hil_env bash`
5. `colcon build`