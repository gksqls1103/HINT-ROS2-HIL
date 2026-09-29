#include <memory>

#include <rclcpp/rclcpp.hpp>

#include "vehicle_node/vehicle_node.hpp"


// C++ Vehicle Node 프로그램이 시작되는 함수입니다.
int main(int argc, char * argv[])
{
  // ROS 2 C++ 통신을 시작합니다.
  rclcpp::init(argc, argv);

  // VehicleNode 객체를 만들고 종료될 때까지 메시지를 기다립니다.
  std::shared_ptr<VehicleNode> vehicle_node = std::make_shared<VehicleNode>();
  rclcpp::spin(vehicle_node);

  // 노드 실행이 끝나면 ROS 2 통신을 안전하게 종료합니다.
  rclcpp::shutdown();
  return 0;
}
