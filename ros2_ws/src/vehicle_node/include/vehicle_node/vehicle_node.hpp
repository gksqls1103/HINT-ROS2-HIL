#ifndef VEHICLE_NODE__VEHICLE_NODE_HPP_
#define VEHICLE_NODE__VEHICLE_NODE_HPP_

#include <geometry_msgs/msg/twist.hpp>
#include <rclcpp/rclcpp.hpp>


// /cmd_vel 주행 명령을 구독하는 ROS 2 노드입니다.
class VehicleNode : public rclcpp::Node
{
public:
  // 노드 이름과 구독자를 생성합니다.
  VehicleNode();

private:
  // /cmd_vel 메시지가 도착할 때 호출되는 함수입니다.
  void cmdVelCallback(const geometry_msgs::msg::Twist::SharedPtr message);

  // /cmd_vel 구독 객체를 실행 중에 유지합니다.
  rclcpp::Subscription<geometry_msgs::msg::Twist>::SharedPtr cmd_vel_subscription_;

  // 검증한 명령을 Gazebo 차량에 전달하는 발행 객체입니다.
  rclcpp::Publisher<geometry_msgs::msg::Twist>::SharedPtr vehicle_control_publisher_;
};

#endif  // VEHICLE_NODE__VEHICLE_NODE_HPP_
