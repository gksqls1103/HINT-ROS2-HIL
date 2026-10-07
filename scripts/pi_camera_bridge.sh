#!/usr/bin/env bash
# Raspberry Pi CSI 카메라 영상을 v4l2loopback 가상 카메라(/dev/video10)로 전달합니다.
# 컨테이너는 .env 의 VISION_CAMERA_DEVICE=/dev/video10 으로 이 장치를 사용합니다.
set -euo pipefail

DEVICE="${CAMERA_BRIDGE_DEVICE:-/dev/video10}"
WIDTH="${CAMERA_BRIDGE_WIDTH:-640}"
HEIGHT="${CAMERA_BRIDGE_HEIGHT:-480}"
FPS="${CAMERA_BRIDGE_FPS:-30}"

rpicam-vid -t 0 -n --width "$WIDTH" --height "$HEIGHT" --framerate "$FPS" --codec yuv420 -o - \
  | ffmpeg -hide_banner -loglevel error \
      -f rawvideo -pix_fmt yuv420p -s "${WIDTH}x${HEIGHT}" -r "$FPS" -i - \
      -f v4l2 -pix_fmt yuyv422 "$DEVICE"
