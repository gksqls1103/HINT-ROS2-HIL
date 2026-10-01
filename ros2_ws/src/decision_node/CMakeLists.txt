cmake_minimum_required(VERSION 3.8)
project(decision_node)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(hil_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)

add_executable(decision_node src/decision_node.cpp)
ament_target_dependencies(decision_node rclcpp hil_msgs std_msgs geometry_msgs)

install(TARGETS decision_node DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY launch DESTINATION share/${PROJECT_NAME})

ament_package()
