// Vehicle: Decision 명령을 실행하고 Gazebo에서 측정한 상태를 전달합니다.
#include <chrono>
#include <cmath>
#include <functional>
#include <memory>
#include <stdexcept>
#include "rclcpp/rclcpp.hpp"
#include "geometry_msgs/msg/twist.hpp"
#include "geometry_msgs/msg/pose_stamped.hpp"
#include "geometry_msgs/msg/transform_stamped.hpp"
#include "nav_msgs/msg/odometry.hpp"
#include "tf2_ros/transform_broadcaster.h"

class VehicleNode : public rclcpp::Node
{
public:
  VehicleNode() : Node("vehicle_node")
  {
    // 기본 제한값: 속도 m/s, 회전속도 rad/s, 타임아웃 초.
    command_timeout_ = declare_parameter<double>("command_timeout", 0.5);
    feedback_timeout_ = declare_parameter<double>("feedback_timeout", 0.5);
    max_linear_speed_ = declare_parameter<double>("max_linear_speed", 2.0);
    max_angular_speed_ = declare_parameter<double>("max_angular_speed", 1.5);
    if (!positive(command_timeout_) || !positive(feedback_timeout_) ||
        !positive(max_linear_speed_) || !positive(max_angular_speed_)) {
      throw std::invalid_argument("Limits and timeouts must be finite and positive");
    }

    // 외부 계약: Reliable / Volatile / Keep Last 10.
    rclcpp::QoS qos(10);
    qos.reliable();
    qos.durability_volatile();
    command_pub_ = create_publisher<geometry_msgs::msg::Twist>(
      "/vehicle/internal/cmd_vel", qos);
    state_pub_ = create_publisher<nav_msgs::msg::Odometry>("/vehicle/state", qos);
    pose_pub_ = create_publisher<geometry_msgs::msg::PoseStamped>("/vehicle/pose", qos);

    // std::bind는 메시지가 도착했을 때 실행할 멤버 함수를 연결합니다.
    command_sub_ = create_subscription<geometry_msgs::msg::Twist>(
      "/cmd_vel", qos,
      std::bind(&VehicleNode::onCommand, this, std::placeholders::_1));
    // 내부 피드백 구독은 두 가지 신뢰도 발행자 모두와 연결되도록 Best Effort 사용.
    rclcpp::QoS feedback_qos(10);
    feedback_qos.best_effort();
    odometry_sub_ = create_subscription<nav_msgs::msg::Odometry>(
      "/vehicle/internal/odometry", feedback_qos,
      std::bind(&VehicleNode::onOdometry, this, std::placeholders::_1));
    tf_broadcaster_ = std::make_shared<tf2_ros::TransformBroadcaster>(*this);

    // 실제 시간 타이머: Gazebo가 일시정지해도 명령 단절 검사를 수행합니다.
    timer_ = create_wall_timer(std::chrono::milliseconds(50),
      std::bind(&VehicleNode::sendCommand, this));
    RCLCPP_INFO(get_logger(), "Vehicle control ready: /cmd_vel -> Gazebo");
  }

  // 정상 종료 때 마지막 정지 명령을 보냅니다.
  void stop()
  {
    geometry_msgs::msg::Twist zero;
    command_pub_->publish(zero);
  }

private:
  // 유효한 양수인지 검사합니다.
  bool positive(double value)
  {
    return std::isfinite(value) && value > 0.0;
  }

  // 복잡한 문법 없이 속도를 최대/최소 범위로 제한합니다.
  double limit(double value, double maximum)
  {
    if (value > maximum) { return maximum; }
    if (value < -maximum) { return -maximum; }
    return value;
  }

  // Decision -> Vehicle: 전진속도와 회전속도를 받습니다.
  void onCommand(const geometry_msgs::msg::Twist::SharedPtr msg)
  {
    command_ = geometry_msgs::msg::Twist();
    // NaN/무한대가 들어오면 기존 주행 명령을 취소합니다.
    if (!std::isfinite(msg->linear.x) || !std::isfinite(msg->linear.y) ||
        !std::isfinite(msg->linear.z) || !std::isfinite(msg->angular.x) ||
        !std::isfinite(msg->angular.y) || !std::isfinite(msg->angular.z)) {
      have_command_ = false;
      stop();
      RCLCPP_ERROR_THROTTLE(get_logger(), *get_clock(), 2000,
        "Invalid command: vehicle stopped");
      return;
    }
    // 이 차량은 평면 주행만 가능합니다. 지원하지 않는 명령을 조용히 무시하지 않습니다.
    // 예: 전진 + 횡이동 명령은 일부만 실행하면 의도와 다른 경로로 움직일 수 있습니다.
    if (msg->linear.y != 0.0 || msg->linear.z != 0.0 ||
        msg->angular.x != 0.0 || msg->angular.y != 0.0) {
      have_command_ = false;
      stop();
      RCLCPP_ERROR_THROTTLE(get_logger(), *get_clock(), 2000,
        "Unsupported axis: use only linear.x and angular.z; vehicle stopped");
      return;
    }
    // 평면 차동구동 모델이므로 linear.x, angular.z만 제어합니다.
    command_.linear.x = limit(msg->linear.x, max_linear_speed_);
    command_.angular.z = limit(msg->angular.z, max_angular_speed_);
    command_time_ = std::chrono::steady_clock::now();
    have_command_ = true;
    sendCommand();  // STOP은 다음 타이머까지 기다리지 않고 전달합니다.
  }

  // 명령/피드백이 신선할 때만 Gazebo로 주행 명령을 전달합니다.
  void sendCommand()
  {
    const std::chrono::steady_clock::time_point now = std::chrono::steady_clock::now();
    const double command_age = std::chrono::duration<double>(now - command_time_).count();
    const double feedback_age = std::chrono::duration<double>(now - feedback_time_).count();
    if (!have_command_ || !have_feedback_ || command_age > command_timeout_ ||
        feedback_age > feedback_timeout_) {
      stop();
      return;
    }
    command_pub_->publish(command_);
  }

  // Gazebo -> Vehicle -> Decision/RViz: 실제 피드백을 그대로 전달합니다.
  void onOdometry(const nav_msgs::msg::Odometry::SharedPtr msg)
  {
    feedback_time_ = std::chrono::steady_clock::now();
    have_feedback_ = true;
    nav_msgs::msg::Odometry state = *msg;
    state.header.frame_id = "odom";
    state.child_frame_id = "base_link";
    // 위치, quaternion 자세, 실제 선속도/각속도, 시간과 공분산을 보존합니다.
    state_pub_->publish(state);

    geometry_msgs::msg::PoseStamped pose;
    pose.header = state.header;
    pose.pose = state.pose.pose;
    pose_pub_->publish(pose);

    // RViz가 차체 위치를 찾을 수 있도록 odom -> base_link TF를 제공합니다.
    geometry_msgs::msg::TransformStamped transform;
    transform.header = state.header;
    transform.child_frame_id = "base_link";
    transform.transform.translation.x = pose.pose.position.x;
    transform.transform.translation.y = pose.pose.position.y;
    transform.transform.translation.z = pose.pose.position.z;
    transform.transform.rotation = pose.pose.orientation;
    tf_broadcaster_->sendTransform(transform);
  }

  // 통신 객체는 노드 실행 동안 유지해야 하므로 멤버로 보관합니다.
  rclcpp::Publisher<geometry_msgs::msg::Twist>::SharedPtr command_pub_;
  rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr state_pub_;
  rclcpp::Publisher<geometry_msgs::msg::PoseStamped>::SharedPtr pose_pub_;
  rclcpp::Subscription<geometry_msgs::msg::Twist>::SharedPtr command_sub_;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odometry_sub_;
  std::shared_ptr<tf2_ros::TransformBroadcaster> tf_broadcaster_;
  rclcpp::TimerBase::SharedPtr timer_;
  geometry_msgs::msg::Twist command_;
  std::chrono::steady_clock::time_point command_time_;
  std::chrono::steady_clock::time_point feedback_time_;
  bool have_command_ = false;
  bool have_feedback_ = false;
  double command_timeout_, feedback_timeout_, max_linear_speed_, max_angular_speed_;
};

// ROS 초기화 -> 노드 생성 -> 콜백 실행 -> 종료 순서입니다.
int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  std::shared_ptr<VehicleNode> node = std::make_shared<VehicleNode>();
  rclcpp::spin(node);
  if (rclcpp::ok()) { node->stop(); }
  rclcpp::shutdown();
  return 0;
}
