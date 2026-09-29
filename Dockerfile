FROM osrf/ros:humble-desktop

# 필수 유틸리티 및 빌드 툴 설치
RUN apt-get update && apt-get install -y \
    nano \
    python3-pip \
    python3-colcon-common-extensions \
    ros-humble-gazebo-ros-pkgs \
    ros-humble-cv-bridge \
    ros-humble-rmw-cyclonedds-cpp \
    libopencv-dev \
    && rm -rf /var/lib/apt/lists/*

#(Safety) UART 연동을 위한 파이썬 시리얼 라이브러리
RUN pip3 install pyserial

# 워크스페이스 지정
WORKDIR /ros2_ws

# 컨테이너 진입 시 ROS2 환경변수 자동 소싱
RUN echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc