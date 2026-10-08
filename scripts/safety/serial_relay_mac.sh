#!/usr/bin/env bash
# Mac 개발용: STM32 USB 시리얼을 TCP로 중계한다.
# 컨테이너에서는 host.docker.internal:<PORT> 로 접속한다.
# 사용법: ./serial_relay_mac.sh [장치경로] [포트=9000] [baud=115200]
set -euo pipefail

DEVICE="${1:-$(ls /dev/cu.usbmodem* 2>/dev/null | head -n1 || true)}"
PORT="${2:-9000}"
BAUD="${3:-115200}"

if ! command -v socat >/dev/null 2>&1; then
  echo "socat이 없습니다: brew install socat" >&2; exit 1
fi
if [ -z "${DEVICE}" ]; then
  echo "STM32 장치를 찾지 못했습니다. 연결을 확인하거나 경로를 인자로 주세요." >&2; exit 1
fi

echo "중계 시작: ${DEVICE} (${BAUD}) -> TCP ${PORT}"
exec socat -d -d "TCP-LISTEN:${PORT},reuseaddr,fork" \
  "FILE:${DEVICE},raw,echo=0,cs8,parenb=0,cstopb=0,ispeed=${BAUD},ospeed=${BAUD}"