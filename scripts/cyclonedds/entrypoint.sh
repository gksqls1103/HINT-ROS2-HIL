#!/bin/bash
# 컨테이너 시작 시 .env 값으로 CycloneDDS 설정 파일을 만든 뒤 ROS 기본 엔트리포인트를 실행합니다.
#   CYCLONEDDS_PEERS     : 통신할 상대 장비 IP 목록 (쉼표 구분). 비어 있으면 기존처럼 멀티캐스트로 탐색
#   CYCLONEDDS_INTERFACE : 사용할 네트워크 인터페이스 (자기 IP 또는 이름, 예: 10.70.101.94, wlan0). 비어 있으면 자동 선택
set -e

xml_path="${CYCLONEDDS_URI#file://}"

general=""
if [ -n "${CYCLONEDDS_INTERFACE:-}" ]; then
  if [[ "$CYCLONEDDS_INTERFACE" =~ ^[0-9.]+$ ]]; then
    attr="address"
  else
    attr="name"
  fi
  general="<General><Interfaces><NetworkInterface ${attr}=\"${CYCLONEDDS_INTERFACE}\"/></Interfaces></General>"
fi

discovery=""
peers=""
for peer in ${CYCLONEDDS_PEERS//,/ }; do
  peers+="<Peer address=\"${peer}\"/>"
done
if [ -n "$peers" ]; then
  # 유니캐스트 탐색은 참가자별 포트를 알아야 하므로 ParticipantIndex를 자동 할당합니다.
  discovery="<Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>50</MaxAutoParticipantIndex><Peers>${peers}</Peers></Discovery>"
fi

echo "<CycloneDDS><Domain>${general}${discovery}</Domain></CycloneDDS>" > "$xml_path"

exec /ros_entrypoint.sh "$@"
