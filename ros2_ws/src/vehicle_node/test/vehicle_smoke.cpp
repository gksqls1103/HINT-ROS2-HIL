// 실제 Gazebo를 실행한 상태에서 주행/감속/정지/회전/명령 timeout을 검증합니다.
// 실제 Decision 대신 테스트 명령을 보내므로 독립 검증 환경에서만 실행하세요.
#include <chrono>
#include <cmath>
#include <functional>
#include <memory>
#include <iostream>
#include <limits>
#include "rclcpp/rclcpp.hpp"
#include "geometry_msgs/msg/twist.hpp"
#include "geometry_msgs/msg/pose_stamped.hpp"
#include "nav_msgs/msg/odometry.hpp"
#include "ros_gz_interfaces/srv/control_world.hpp"

class SmokeTest : public rclcpp::Node
{
public:
  SmokeTest() : Node("vehicle_smoke_test")
  {
    pub = create_publisher<geometry_msgs::msg::Twist>("/cmd_vel", rclcpp::QoS(10));
    state_sub = create_subscription<nav_msgs::msg::Odometry>("/vehicle/state", 10,
      std::bind(&SmokeTest::onState, this, std::placeholders::_1));
    pose_sub = create_subscription<geometry_msgs::msg::PoseStamped>("/vehicle/pose", 10,
      std::bind(&SmokeTest::onPose, this, std::placeholders::_1));
    // 바퀴 odometry가 아니라 물리 월드의 이동도 따로 확인합니다.
    truth_sub = create_subscription<nav_msgs::msg::Odometry>("/vehicle/internal/ground_truth", 10,
      std::bind(&SmokeTest::onTruth, this, std::placeholders::_1));
    command_sub = create_subscription<geometry_msgs::msg::Twist>("/vehicle/internal/cmd_vel", 10,
      std::bind(&SmokeTest::onCommand, this, std::placeholders::_1));
    control = create_client<ros_gz_interfaces::srv::ControlWorld>("/world/vehicle_world/control");
  }
  void onState(const nav_msgs::msg::Odometry::SharedPtr msg)
  {
    state = *msg;
    ++state_count;
  }
  void onPose(const geometry_msgs::msg::PoseStamped::SharedPtr msg)
  {
    pose = *msg;
    ++pose_count;
  }
  void onTruth(const nav_msgs::msg::Odometry::SharedPtr msg)
  {
    truth = *msg;
    ++truth_count;
  }
  void onCommand(const geometry_msgs::msg::Twist::SharedPtr msg)
  {
    applied = *msg;
  }
  rclcpp::Publisher<geometry_msgs::msg::Twist>::SharedPtr pub;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr state_sub;
  rclcpp::Subscription<geometry_msgs::msg::PoseStamped>::SharedPtr pose_sub;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr truth_sub;
  rclcpp::Subscription<geometry_msgs::msg::Twist>::SharedPtr command_sub;
  rclcpp::Client<ros_gz_interfaces::srv::ControlWorld>::SharedPtr control;
  nav_msgs::msg::Odometry state;
  geometry_msgs::msg::PoseStamped pose;
  nav_msgs::msg::Odometry truth;
  geometry_msgs::msg::Twist applied;
  int state_count = 0;
  int pose_count = 0;
  int truth_count = 0;
};

// 지정 시간 동안 명령을 20 Hz 발행하고 실제 상태를 수신합니다.
void runStage(std::shared_ptr<SmokeTest> node, double seconds,
              double speed, double rotation, bool publish, double lateral = 0.0,
              double vertical = 0.0, double roll = 0.0, double pitch = 0.0)
{
  geometry_msgs::msg::Twist command;
  command.linear.x = speed;
  command.angular.z = rotation;
  command.linear.y = lateral;
  command.linear.z = vertical;
  command.angular.x = roll;
  command.angular.y = pitch;
  const std::chrono::steady_clock::time_point start = std::chrono::steady_clock::now();
  rclcpp::WallRate rate(20);
  while (rclcpp::ok() &&
         std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count() < seconds) {
    if (publish) { node->pub->publish(command); }
    rclcpp::spin_some(node);
    rate.sleep();
  }
  // 명령, 바퀴 피드백, 물리 월드 피드백을 함께 출력합니다.
  std::cout << "COMMAND v=" << speed << " w=" << rotation << " publish=" << publish
            << " | APPLIED v=" << node->applied.linear.x << " w=" << node->applied.angular.z
            << " | ODOM v=" << node->state.twist.twist.linear.x
            << " w=" << node->state.twist.twist.angular.z
            << " | WORLD v=" << node->truth.twist.twist.linear.x
            << " w=" << node->truth.twist.twist.angular.z << std::endl;
}

// 시뮬레이터 일시정지로 피드백 단절을 만들고 watchdog을 검사합니다.
bool pauseWorld(std::shared_ptr<SmokeTest> node, bool pause)
{
  if (!node->control->wait_for_service(std::chrono::seconds(3))) { return false; }
  std::shared_ptr<ros_gz_interfaces::srv::ControlWorld::Request> request =
    std::make_shared<ros_gz_interfaces::srv::ControlWorld::Request>();
  request->world_control.pause = pause;
  rclcpp::Client<ros_gz_interfaces::srv::ControlWorld>::SharedFuture future =
    node->control->async_send_request(request).future.share();
  if (rclcpp::spin_until_future_complete(node, future, std::chrono::seconds(3)) !=
      rclcpp::FutureReturnCode::SUCCESS) { return false; }
  return future.get()->success;
}

// 결과를 출력하며 실패 개수를 누적합니다.
void check(bool condition, const char * name, int & failures)
{
  std::cout << (condition ? "PASS " : "FAIL ") << name << std::endl;
  if (!condition) { ++failures; }
}

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  std::shared_ptr<SmokeTest> node = std::make_shared<SmokeTest>();
  int failures = 0;
  runStage(node, 3.0, 0.0, 0.0, true);
  check(node->state_count > 10 && node->pose_count > 10, "feedback received", failures);
  check(node->truth_count > 10, "physical world feedback received", failures);
  check(node->state.header.frame_id == "odom" && node->state.child_frame_id == "base_link" &&
        node->pose.header.frame_id == "odom", "coordinate frames", failures);
  double start_x = node->state.pose.pose.position.x;
  double world_start_x = node->truth.pose.pose.position.x;
  runStage(node, 2.0, 0.5, 0.0, true);
  check(node->state.twist.twist.linear.x > 0.35, "GO measured speed", failures);
  check(node->state.pose.pose.position.x > start_x + 0.3, "GO position changed", failures);
  check(node->truth.pose.pose.position.x > world_start_x + 0.3,
        "GO physical position changed", failures);
  runStage(node, 2.0, 0.2, 0.0, true);
  check(std::abs(node->state.twist.twist.linear.x - 0.2) < 0.08, "deceleration", failures);
  check(std::abs(node->truth.twist.twist.linear.x - 0.2) < 0.08,
        "physical deceleration", failures);
  runStage(node, 1.5, 0.0, 0.0, true);
  check(std::abs(node->state.twist.twist.linear.x) < 0.02, "STOP", failures);
  check(std::abs(node->truth.twist.twist.linear.x) < 0.02, "physical STOP", failures);
  world_start_x = node->truth.pose.pose.position.x;
  runStage(node, 2.0, -0.4, 0.0, true);
  check(node->state.twist.twist.linear.x < -0.3 &&
        node->truth.pose.pose.position.x < world_start_x - 0.3, "reverse", failures);
  runStage(node, 2.0, 0.3, 0.2, true);
  check(node->state.twist.twist.angular.z > 0.1, "turning", failures);
  check(std::abs(node->truth.twist.twist.angular.z - 0.2) < 0.03,
        "physical left turn", failures);
  runStage(node, 2.0, 0.3, -0.2, true);
  check(node->state.twist.twist.angular.z < -0.1 &&
        std::abs(node->truth.twist.twist.angular.z + 0.2) < 0.03,
        "right turn", failures);
  runStage(node, 1.5, -0.3, 0.2, true);
  check(node->truth.twist.twist.linear.x < -0.2 &&
        std::abs(node->truth.twist.twist.angular.z - 0.2) < 0.03,
        "reverse with positive yaw", failures);
  runStage(node, 1.5, -0.3, -0.2, true);
  check(node->truth.twist.twist.linear.x < -0.2 &&
        std::abs(node->truth.twist.twist.angular.z + 0.2) < 0.03,
        "reverse with negative yaw", failures);
  runStage(node, 1.5, 0.05, 0.0, true);
  check(std::abs(node->truth.twist.twist.linear.x - 0.05) < 0.02,
        "low speed driving", failures);
  runStage(node, 1.5, 0.0, 0.4, true);
  check(std::abs(node->truth.twist.twist.linear.x) < 0.05 &&
        node->truth.twist.twist.angular.z > 0.15, "rotate in place left", failures);
  runStage(node, 1.5, 0.0, -0.4, true);
  check(std::abs(node->truth.twist.twist.linear.x) < 0.05 &&
        node->truth.twist.twist.angular.z < -0.15, "rotate in place right", failures);
  runStage(node, 1.0, 5.0, 0.0, true);
  check(std::abs(node->applied.linear.x - 2.0) < 0.001 &&
        std::abs(node->state.twist.twist.linear.x) <= 2.05, "positive speed limit", failures);
  runStage(node, 1.0, -5.0, 0.0, true);
  check(std::abs(node->applied.linear.x + 2.0) < 0.001 &&
        std::abs(node->state.twist.twist.linear.x) <= 2.05, "negative speed limit", failures);
  runStage(node, 1.0, 0.0, 5.0, true);
  check(std::abs(node->applied.angular.z - 1.5) < 0.001, "positive angular limit", failures);
  runStage(node, 1.0, 0.0, -5.0, true);
  check(std::abs(node->applied.angular.z + 1.5) < 0.001, "negative angular limit", failures);
  runStage(node, 1.5, 5.0, 5.0, true);
  check(std::abs(node->applied.linear.x - 2.0) < 0.001 &&
        std::abs(node->applied.angular.z - 1.5) < 0.001 &&
        node->truth.twist.twist.linear.x > 1.7 && node->truth.twist.twist.angular.z > 1.2,
        "combined speed and angular limits", failures);
  runStage(node, 1.0, std::numeric_limits<double>::quiet_NaN(), 0.0, true);
  check(node->applied.linear.x == 0.0 && node->applied.angular.z == 0.0,
        "NaN stops", failures);
  runStage(node, 1.0, 0.3, std::numeric_limits<double>::infinity(), true);
  check(node->applied.linear.x == 0.0 && node->applied.angular.z == 0.0,
        "infinity stops", failures);
  runStage(node, 1.0, 0.3, 0.0, true, 0.2);
  check(node->applied.linear.x == 0.0 && node->applied.angular.z == 0.0,
        "unsupported lateral command stops", failures);
  runStage(node, 0.8, 0.3, 0.0, true, 0.0, 0.2);
  check(node->applied.linear.x == 0.0 && node->applied.angular.z == 0.0,
        "unsupported vertical command stops", failures);
  runStage(node, 0.8, 0.3, 0.0, true, 0.0, 0.0, 0.2);
  check(node->applied.linear.x == 0.0 && node->applied.angular.z == 0.0,
        "unsupported roll command stops", failures);
  runStage(node, 0.8, 0.3, 0.0, true, 0.0, 0.0, 0.0, 0.2);
  check(node->applied.linear.x == 0.0 && node->applied.angular.z == 0.0,
        "unsupported pitch command stops", failures);
  runStage(node, 1.0, 0.3, 0.0, true);
  check(node->truth.twist.twist.linear.x > 0.2, "recovery after invalid command", failures);
  runStage(node, 1.5, 0.0, 0.0, false);
  check(std::abs(node->state.twist.twist.linear.x) < 0.02 &&
        std::abs(node->state.twist.twist.angular.z) < 0.02, "command timeout stop", failures);
  check(std::abs(node->truth.twist.twist.linear.x) < 0.02 &&
        std::abs(node->truth.twist.twist.angular.z) < 0.02, "physical timeout stop", failures);
  check(pauseWorld(node, true), "pause world", failures);
  runStage(node, 1.2, 0.3, 0.0, true);
  check(node->applied.linear.x == 0.0 && node->applied.angular.z == 0.0,
        "feedback timeout stop while commands continue", failures);
  check(pauseWorld(node, false), "resume world", failures);
  runStage(node, 1.5, 0.3, 0.0, true);
  check(node->truth.twist.twist.linear.x > 0.2, "recovery after feedback resumes", failures);
  runStage(node, 1.0, 0.0, 0.0, true);
  check(node->state.header.stamp.sec > 0, "simulation timestamp", failures);
  check(std::abs(node->pose.pose.position.x - node->state.pose.pose.position.x) < 0.1,
        "pose agrees with state", failures);
  rclcpp::shutdown();
  return failures == 0 ? 0 : 1;
}
