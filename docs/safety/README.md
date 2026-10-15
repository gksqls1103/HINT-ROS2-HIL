# Safety (STM32 ↔ ROS2 브릿지)

## 구조
STM32 ─UART(115200 8N1)─ [Pi: USB 직결 / Mac: 호스트 중계(TCP)] ─ `safety_node` ─ ROS2 토픽

`safety_node`(C++)는 환경변수 `SAFETY_SERIAL_URL`로 접속 방식을 정합니다.

| 환경 | 값 | 방식 |
|---|---|---|
| Pi | `/dev/ttyUSB0` (compose가 설정) | 시리얼 장치를 직접 열기 |
| Mac | `socket://host.docker.internal:9000` (기본값) | 호스트 중계(socat)에 TCP 접속 |

- Pi: `docker-compose.safety.yml`이 호스트 장치(`.env`의 `SAFETY_SERIAL_DEVICE`)를 컨테이너 `/dev/ttyUSB0`로 연결
- Mac: `docker-compose.safety.mac.yml`이 주소만 주입. 중계 포트를 바꾸려면 `.env`에 `SAFETY_SERIAL_URL=socket://host.docker.internal:<포트>`를 추가하고 중계 스크립트도 같은 포트로 실행

## 토픽 (임시, 프로토콜 확정 후 변경)
- `/safety/rx` (`std_msgs/String`): STM32 → ROS2, 한 줄씩 발행
- `/safety/tx` (`std_msgs/String`): ROS2 → STM32, 한 줄씩 전송

연결이 끊기면 1초 간격으로 자동 재접속합니다.

## 동작 확인
다른 컨테이너 터미널에서 `source /ros2_ws/install/setup.bash` 후 실행합니다.

```
ros2 topic echo /safety/rx
ros2 topic pub --once /safety/tx std_msgs/msg/String "{data: '5'}"
```
현재 펌웨어(통신 검증용)는 받은 값을 2배 해서 응답하므로 `data: RX: 5 (x2=10)`가 출력됩니다.

## 검증 현황
- Mac(TCP 경로): STM32 왕복 통신 확인
- Pi(USB 직결): 설정 조합 확인, 실장비 통신은 검증 전

## 펌웨어
`firmware/safety_stm32/`에 있는 통신 검증용 펌웨어입니다. 실제 Safety 로직은 프로토콜 확정 후 추가합니다.