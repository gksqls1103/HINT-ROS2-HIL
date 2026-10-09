# Decision 개발 서버 실행

이 절차는 Gazebo 차량 환경과 Decision 개발 노드를 함께 실행합니다. Decision 개발 launch는 실제 Vision/Safety 노드 대신 `fake_vision_node`, `fake_safety_node`를 실행합니다.

## 준비

- Docker가 실행 중이어야 합니다.
- ROS 2 통신을 확인할 때는 양쪽 PC에서 `ROS_DOMAIN_ID`, `ROS_LOCALHOST_ONLY`, `RMW_IMPLEMENTATION`을 동일하게 설정합니다.
- WSL2에서 Cyclone DDS를 사용하는 경우, 프로젝트의 Compose 설정이 LAN 인터페이스 `eth0`를 지정하는지 확인합니다.

### WSL2 네트워크 설정 (Windows 11 22H2 이상)

WSL2에서 다른 PC와 ROS 2 통신을 하려면 mirrored networking을 사용합니다. Windows 사용자 프로필의 `%UserProfile%\.wslconfig` 파일에 다음 설정을 추가합니다. 파일이 이미 있으면 기존 내용을 지우지 말고 `[wsl2]` 항목에 `networkingMode=mirrored`를 추가합니다.

```ini
[wsl2]
networkingMode=mirrored
```

관리자 권한 PowerShell에서 Hyper-V 방화벽의 WSL 기본 인바운드 동작을 허용합니다.

```powershell
Set-NetFirewallHyperVVMSetting -Name '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -DefaultInboundAction Allow
```

설정을 적용하려면 PowerShell에서 WSL을 종료한 뒤 다시 시작합니다.

```powershell
wsl --shutdown
```

Microsoft는 mirrored networking이 LAN 연결과 멀티캐스트를 지원한다고 안내하며, `.wslconfig` 적용을 위해 WSL을 재시작하도록 설명합니다. 자세한 내용은 [WSL 네트워킹](https://learn.microsoft.com/windows/wsl/networking) 및 [WSL 고급 설정](https://learn.microsoft.com/windows/wsl/wsl-config)을 참고하세요.

## 원인과 해결

WSL2에서 HTTP 서버는 다른 PC에서 접속됐고 ROS 2 설정도 양쪽이 같았으며, `ros2 multicast` 검사도 통과했지만 DDS 노드와 토픽은 서로 발견되지 않는 문제가 있었습니다. `ros2 doctor --report`에서 WSL 네트워크 인터페이스로 `eth0` (`192.168.75.58`) 외에 `docker0`와 `lo`도 표시됐습니다. Cyclone DDS의 인터페이스 자동 선택 경로가 원인으로 확인됐습니다. 자동 선택 시 실제로 어느 인터페이스를 골랐는지는 별도로 추적하지 않았지만, `eth0`를 명시하자 통신이 성공했습니다.

WSL 컨테이너에서 Cyclone DDS 인터페이스를 `eth0`로 고정하자 talker/listener 통신이 성공했습니다. 이 저장소의 기본 Compose 설정은 동일한 인터페이스를 `CYCLONEDDS_URI`로 지정합니다.

```xml
<CycloneDDS>
  <Domain>
    <General>
      <Interfaces>
        <NetworkInterface name="eth0" multicast="true"/>
      </Interfaces>
    </General>
  </Domain>
</CycloneDDS>
```

다른 네트워크 인터페이스를 사용하는 PC에서는 `ros2 doctor --report`로 LAN 인터페이스 이름을 확인한 뒤 `.env`의 `CYCLONEDDS_URI`에서 `name="eth0"`을 해당 이름으로 바꿉니다. 환경변수를 바꾼 뒤에는 ROS 프로세스와 컨테이너를 재시작해야 적용됩니다. 이 문서의 Gazebo 실행 스크립트를 다시 실행하면 Compose가 변경된 설정으로 컨테이너를 준비합니다.

멀티캐스트 검사나 HTTP 접속 성공만으로 DDS 통신이 확인되지는 않습니다. 두 PC의 ROS 2 설정이 같고 네트워크 경로가 열려 있어도 Cyclone DDS가 잘못된 인터페이스를 사용하면 노드 발견과 토픽 통신이 실패할 수 있습니다.

## 실행

저장소 루트에서 터미널 두 개를 엽니다.

### 터미널 1: Gazebo 실행

```bash
bash ros2_ws/src/vehicle_node/run_gazebo.sh
```

화면 없이 실행하려면 다음처럼 실행합니다.

```bash
bash ros2_ws/src/vehicle_node/run_gazebo.sh --headless
```

이 단계에서 `ros2_hil_env` 컨테이너가 준비되고 Gazebo, ROS-Gazebo bridge, Vehicle 노드가 실행됩니다. 터미널 1은 실행 중인 상태로 둡니다.

### 터미널 2: Decision 개발 노드 실행

```bash
bash scripts/run_decision_dev.sh
```

이 스크립트는 컨테이너 안에서 ROS 2 Humble 환경을 불러오고, `decision_node`와 `fake_nodes` 및 의존 패키지를 빌드한 다음 `decision_dev.launch.py`를 실행합니다. launch 로그가 표시되는 동안 터미널 2도 실행 상태로 둡니다.

## 확인

세 노드가 실행됐는지 다른 컨테이너 셸에서 확인할 수 있습니다.

```bash
docker exec -it ros2_hil_env bash -lc '
  source /opt/ros/humble/setup.bash &&
  source /ros2_ws/install_hil/setup.bash &&
  ros2 node list
'
```

다음 노드 이름이 목록에 나타나야 합니다.

- `/decision_node`
- `/fake_vision_node`
- `/fake_safety_node`

## 종료

각 터미널에서 `Ctrl+C`를 눌러 해당 launch를 종료합니다. Decision 노드만 종료하면 터미널 2에서 `Ctrl+C`를 누릅니다. Gazebo까지 종료하려면 터미널 1에서도 `Ctrl+C`를 누릅니다.

## 재실행

`run_decision_dev.sh`는 실행할 때마다 colcon 빌드를 수행합니다. 변경 사항이 없으면 빌드는 빠르게 끝나며, 빌드 결과는 `build_hil`과 `install_hil`에 저장됩니다. Vehicle 패키지의 `build_vehicle`/`install_vehicle` 결과와 분리되어 있습니다.

컨테이너가 없거나 중지된 경우 먼저 터미널 1에서 Gazebo 실행 명령을 다시 실행합니다. 컨테이너 이름을 다르게 지정했다면 `ROS2_CONTAINER_NAME` 환경변수로 설정할 수 있습니다.

```bash
ROS2_CONTAINER_NAME=my_ros2_container bash scripts/run_decision_dev.sh
```
