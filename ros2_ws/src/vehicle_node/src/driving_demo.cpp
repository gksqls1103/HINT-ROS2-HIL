// 시각적인 제어 시연용입니다. 실제 Decision 대신 /cmd_vel을 발행합니다.
// 전진 -> 후진 -> 좌회전 -> 우회전 -> 후진 주차 -> 정지를 한 번 실행합니다.
#include <chrono>
#include <cmath>
#include <functional>
#include <iostream>
#include <memory>
#include "rclcpp/rclcpp.hpp"
#include "geometry_msgs/msg/twist.hpp"
#include "nav_msgs/msg/odometry.hpp"

class DemoNode : public rclcpp::Node
{
public:
  DemoNode() : Node("vehicle_driving_demo")
  {
    // 기존 Decision -> Vehicle 계약과 같은 Reliable / Volatile / 10입니다.
    command_pub = create_publisher<geometry_msgs::msg::Twist>("/cmd_vel", 10);
    state_sub = create_subscription<nav_msgs::msg::Odometry>("/vehicle/state", 10,
      std::bind(&DemoNode::onState, this, std::placeholders::_1));
    truth_sub = create_subscription<nav_msgs::msg::Odometry>("/vehicle/internal/ground_truth", 10,
      std::bind(&DemoNode::onTruth, this, std::placeholders::_1));
  }

  void onState(const nav_msgs::msg::Odometry::SharedPtr msg)
  {
    state = *msg;
    have_state = true;
    received = std::chrono::steady_clock::now();
  }

  void onTruth(const nav_msgs::msg::Odometry::SharedPtr msg)
  {
    truth = *msg;
    have_truth = true;
  }

  // 매 순간 같은 속도 명령을 보내 watchdog timeout을 방지합니다.
  void send(double speed, double rotation)
  {
    geometry_msgs::msg::Twist command;
    command.linear.x = speed;
    command.angular.z = rotation;
    command_pub->publish(command);
  }

  // Gazebo의 메시지 시간으로 구간 길이를 계산합니다.
  double simulationTime()
  {
    return state.header.stamp.sec + state.header.stamp.nanosec / 1000000000.0;
  }

  rclcpp::Publisher<geometry_msgs::msg::Twist>::SharedPtr command_pub;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr state_sub, truth_sub;
  nav_msgs::msg::Odometry state, truth;
  std::chrono::steady_clock::time_point received;
  bool have_state = false;
  bool have_truth = false;
};

// 구간 이름, 시뮬레이션 시간, 전진속도, 회전속도를 함께 보관합니다.
struct Stage
{
  const char * name;
  double seconds;
  double speed;
  double rotation;
};

// 한 구간을 실행합니다. 피드백 단절이나 다른 명령 발행자가 생기면 중단합니다.
bool runStage(std::shared_ptr<DemoNode> node, const Stage & stage)
{
  std::cout << "[시연] " << stage.name << " : " << stage.seconds << "초, v="
            << stage.speed << ", w=" << stage.rotation << std::endl;
  const double start_sim = node->simulationTime();
  const std::chrono::steady_clock::time_point start_wall = std::chrono::steady_clock::now();
  rclcpp::WallRate rate(20);
  while (rclcpp::ok() && node->simulationTime() - start_sim < stage.seconds) {
    rclcpp::spin_some(node);
    const std::chrono::steady_clock::time_point now = std::chrono::steady_clock::now();
    const double age = std::chrono::duration<double>(now - node->received).count();
    const double elapsed = std::chrono::duration<double>(now - start_wall).count();
    if (age > 0.5 || elapsed > stage.seconds * 4.0 + 3.0 ||
        node->count_publishers("/cmd_vel") > 1) {
      node->send(0.0, 0.0);
      std::cerr << "[시연 중단] 피드백 단절 또는 다른 /cmd_vel 발행자를 확인하세요." << std::endl;
      return false;
    }
    node->send(stage.speed, stage.rotation);
    rate.sleep();
  }
  // 구간 사이에 정지 명령을 보내고 다음 구간으로 이동합니다.
  node->send(0.0, 0.0);
  std::cout << "[위치] x=" << node->truth.pose.pose.position.x
            << ", y=" << node->truth.pose.pose.position.y << std::endl;
  return rclcpp::ok();
}

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  std::shared_ptr<DemoNode> node = std::make_shared<DemoNode>();
  rclcpp::WallRate rate(20);
  // DDS 연결과 피드백을 최대 5초 기다립니다. 시작 중에는 0속도를 보냅니다.
  for (int count = 0; count < 100 && rclcpp::ok(); ++count) {
    rclcpp::spin_some(node);
    if (node->count_publishers("/cmd_vel") > 1) {
      std::cerr << "Decision 또는 다른 테스트 발행자를 먼저 종료하세요." << std::endl;
      rclcpp::shutdown();
      return 1;
    }
    node->send(0.0, 0.0);
    if (count > 20 && node->have_state && node->have_truth) { break; }
    rate.sleep();
  }
  if (!node->have_state || !node->have_truth) {
    std::cerr << "Gazebo와 Vehicle launch를 먼저 실행하세요." << std::endl;
    rclcpp::shutdown();
    return 1;
  }
  // 새 월드 원점에서 시작해야 주차선 안에 도착하는 예시입니다.
  if (std::abs(node->truth.pose.pose.position.x) > 0.15 ||
      std::abs(node->truth.pose.pose.position.y) > 0.15 ||
      std::abs(node->truth.pose.pose.orientation.z) > 0.05) {
    std::cerr << "차량이 시작점에 없습니다. launch를 종료 후 다시 실행하세요." << std::endl;
    node->send(0.0, 0.0);
    rclcpp::shutdown();
    return 1;
  }

  const Stage stages[] = {
    {"준비: 정지", 1.0, 0.0, 0.0},
    {"전진", 3.0, 0.5, 0.0},
    {"정지", 1.0, 0.0, 0.0},
    {"후진: 시작점으로 복귀", 3.0, -0.5, 0.0},
    {"정지", 1.0, 0.0, 0.0},
    {"좌회전", 5.0, 0.3, 0.3},
    {"정지", 1.0, 0.0, 0.0},
    {"우회전: 차체 방향 복귀", 5.0, 0.3, -0.3},
    {"정지", 1.0, 0.0, 0.0},
    {"파킹: 주차선 안으로 저속 후진", 2.5, -0.3, 0.0},
    {"파킹 완료: 정지 유지", 3.0, 0.0, 0.0}
  };
  bool success = true;
  const int stage_count = sizeof(stages) / sizeof(stages[0]);
  for (int index = 0; index < stage_count && success; ++index) {
    success = runStage(node, stages[index]);
  }
  if (rclcpp::ok()) { node->send(0.0, 0.0); }
  // 실제 월드 위치가 주차선 안인지, 실제 차체가 정지했는지 확인합니다.
  if (success) {
    const double x = node->truth.pose.pose.position.x;
    const double y = node->truth.pose.pose.position.y;
    success = x > 0.9 && x < 1.7 && y > 1.55 && y < 2.05 &&
      std::abs(node->truth.twist.twist.linear.x) < 0.02 &&
      std::abs(node->truth.twist.twist.angular.z) < 0.02;
    std::cout << (success ? "[완료] 주차 구역 안에 정지했습니다." :
                            "[확인 필요] 주차 위치 또는 정지 상태가 기준 밖입니다.") << std::endl;
  }
  rclcpp::shutdown();
  return success ? 0 : 1;
}
