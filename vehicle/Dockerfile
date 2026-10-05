FROM osrf/ros:humble-desktop
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-colcon-common-extensions ros-humble-ros-gz \
    ros-humble-rmw-cyclonedds-cpp ros-humble-tf2-ros \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /ros2_ws
RUN echo 'source /opt/ros/humble/setup.bash' >> /root/.bashrc
