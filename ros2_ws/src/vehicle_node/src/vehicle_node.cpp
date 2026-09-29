#include "vehicle_node/vehicle_node.hpp"


// VehicleNode가 생성될 때 노드와 /cmd_vel 구독자를 준비합니다.
VehicleNode::VehicleNode()
: Node("vehicle_node")
{
  // 검증을 마친 명령을 Gazebo 전용 토픽으로 보내는 발행자를 만듭니다.
  vehicle_control_publisher_ = create_publisher<geometry_msgs::msg::Twist>(
    "/vehicle/control_cmd",
    10);

  // /cmd_vel 토픽에서 Twist 형식의 주행 명령을 받습니다.
  cmd_vel_subscription_ = create_subscription<geometry_msgs::msg::Twist>(
    "/cmd_vel",
    10,
    [this](const geometry_msgs::msg::Twist::SharedPtr message)
    {
      // 메시지를 받으면 별도의 처리 함수로 전달합니다.
      cmdVelCallback(message);
    });

  // 사용자가 노드 실행 상태를 알 수 있도록 로그를 출력합니다.
  RCLCPP_INFO(get_logger(), "Vehicle Node가 시작되었습니다.");
  RCLCPP_INFO(get_logger(), "/cmd_vel 명령을 기다립니다.");
}


// 수신한 속도값을 확인한 뒤 Gazebo 차량에 전달합니다.
void VehicleNode::cmdVelCallback(const geometry_msgs::msg::Twist::SharedPtr message)
{
  // linear.x는 양수일 때 전진하고 음수일 때 후진합니다.
  double forward_speed = message->linear.x;

  // angular.z는 양수일 때 좌회전하고 음수일 때 우회전합니다.
  double turn_speed = message->angular.z;

  // 전진과 회전 속도가 모두 0이면 정지 명령입니다.
  if (forward_speed == 0.0 && turn_speed == 0.0)
  {
    RCLCPP_INFO(get_logger(), "STOP 명령을 받았습니다.");

    // STOP 명령도 Vehicle Node를 거쳐 Gazebo 차량에 전달합니다.
    vehicle_control_publisher_->publish(*message);
    return;
  }

  // 하나 이상의 속도값이 있으면 주행 명령으로 출력합니다.
  RCLCPP_INFO(
    get_logger(),
    "FRONT 명령: 전진 속도=%.3f m/s, 회전 속도=%.3f rad/s",
    forward_speed,
    turn_speed);

  // 검증한 FRONT 명령을 Gazebo 차량 플러그인에 전달합니다.
  vehicle_control_publisher_->publish(*message);
}
