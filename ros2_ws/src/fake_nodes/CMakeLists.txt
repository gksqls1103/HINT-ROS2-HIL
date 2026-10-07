cmake_minimum_required(VERSION 3.8)
project(fake_nodes)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(hil_msgs REQUIRED)
find_package(std_msgs REQUIRED)

add_executable(fake_vision_node src/fake_vision_node.cpp)
ament_target_dependencies(fake_vision_node rclcpp hil_msgs std_msgs)

add_executable(fake_safety_node src/fake_safety_node.cpp)
ament_target_dependencies(fake_safety_node rclcpp hil_msgs std_msgs)

install(TARGETS
  fake_vision_node
  fake_safety_node
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
