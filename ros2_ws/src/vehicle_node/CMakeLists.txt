cmake_minimum_required(VERSION 3.8)
project(vehicle_node)

# 모든 C++ 파일을 C++17 문법으로 컴파일합니다.
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ROS 2와 Qt GUI를 빌드할 때 필요한 패키지를 찾습니다.
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(Qt5 REQUIRED COMPONENTS Widgets)

# /cmd_vel을 구독하고 내용을 출력하는 실행 파일을 만듭니다.
add_executable(vehicle_node
  src/vehicle_node.cpp
  src/vehicle_node_main.cpp
)
target_include_directories(vehicle_node PRIVATE include)
ament_target_dependencies(vehicle_node rclcpp geometry_msgs)

# FRONT와 STOP 버튼을 제공하는 Qt GUI 실행 파일을 만듭니다.
add_executable(drive_command_gui
  src/drive_command_window.cpp
  src/drive_command_main.cpp
)
target_include_directories(drive_command_gui PRIVATE include)
ament_target_dependencies(drive_command_gui rclcpp geometry_msgs)
target_link_libraries(drive_command_gui Qt5::Widgets)

# ros2 run 명령으로 두 실행 파일을 찾을 수 있도록 설치합니다.
install(
  TARGETS vehicle_node drive_command_gui
  DESTINATION lib/${PROJECT_NAME}
)

# ros2 launch와 Gazebo가 launch 및 world 파일을 찾도록 설치합니다.
install(
  DIRECTORY launch worlds
  DESTINATION share/${PROJECT_NAME}
)

# 현재 폴더를 ROS 2 패키지로 완성합니다.
ament_package()
