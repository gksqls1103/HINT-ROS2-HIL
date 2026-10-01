// Fake Safety Node (C++)
// ========================
// C(STM32+FreeRTOS Safety Controller) 담당의 실제 stm32_bridge_node가 아직
// 없을 때, decision_node를 독립적으로 개발/테스트하기 위해 D가 만든 가짜 노드.
//
// 동작:
//   - 12초 주기로 CLEAR -> WARNING -> EMERGENCY -> CLEAR를 순환 발행
//   - 아주 가끔(약 30초에 1번꼴) FAULT(통신 두절 상황)를 흉내내서
//     decision_node의 Fail-Safe 로직도 테스트 가능하게 함

#include <chrono>
#include <map>
#include <memory>
#include <random>
#include <string>
#include <vector>

#include "rclcpp/rclcpp.hpp"
#include "hil_msgs/msg/safety_state.hpp"

using namespace std::chrono_literals;

namespace
{
constexpr double kStepSeconds = 12.0;
constexpr double kFaultChancePerTick = 1.0 / 150.0;  // 0.2초 tick 기준 대략 30초에 1번
}

class FakeSafetyNode : public rclcpp::Node
{
public:
  FakeSafetyNode()
  : Node("fake_safety_node"),
    cycle_({"CLEAR", "CLEAR", "CLEAR", "WARNING", "EMERGENCY", "EMERGENCY", "CLEAR"}),
    cycle_index_(0),
    rng_(std::random_device{}()),
    chance_dist_(0.0, 1.0)
  {
    publisher_ = this->create_publisher<hil_msgs::msg::SafetyState>("/safety/state", 10);

    tick_timer_ = this->create_wall_timer(
      200ms, std::bind(&FakeSafetyNode::publish_tick, this));

    cycle_timer_ = this->create_wall_timer(
      std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::duration<double>(kStepSeconds)),
      std::bind(&FakeSafetyNode::advance_cycle, this));

    RCLCPP_INFO(
      this->get_logger(),
      "Fake Safety Node 시작 — %.0f초마다 CLEAR→WARNING→EMERGENCY 순환 발행, "
      "가끔 FAULT(통신 두절) 흉내냄", kStepSeconds);
  }

private:
  void advance_cycle()
  {
    cycle_index_ = (cycle_index_ + 1) % cycle_.size();
  }

  float distance_for(const std::string & level)
  {
    std::uniform_real_distribution<float> clear(60.0f, 100.0f);
    std::uniform_real_distribution<float> warning(25.0f, 40.0f);
    std::uniform_real_distribution<float> emergency(5.0f, 15.0f);

    if (level == "CLEAR") {return clear(rng_);}
    if (level == "WARNING") {return warning(rng_);}
    if (level == "EMERGENCY") {return emergency(rng_);}
    return -1.0f;
  }

  void publish_tick()
  {
    std::string level;
    float distance;

    if (chance_dist_(rng_) < kFaultChancePerTick) {
      level = "FAULT";
      distance = -1.0f;
    } else {
      level = cycle_[cycle_index_];
      distance = distance_for(level);
    }

    auto msg = hil_msgs::msg::SafetyState();
    msg.header.stamp = this->now();
    msg.header.frame_id = "ultrasonic_link";
    msg.level = level;
    msg.distance_cm = distance;

    publisher_->publish(msg);

    RCLCPP_DEBUG(
      this->get_logger(), "publish level=%s distance_cm=%.1f",
      msg.level.c_str(), msg.distance_cm);
  }

  rclcpp::Publisher<hil_msgs::msg::SafetyState>::SharedPtr publisher_;
  rclcpp::TimerBase::SharedPtr tick_timer_;
  rclcpp::TimerBase::SharedPtr cycle_timer_;

  std::vector<std::string> cycle_;
  size_t cycle_index_;

  std::mt19937 rng_;
  std::uniform_real_distribution<double> chance_dist_;
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<FakeSafetyNode>());
  rclcpp::shutdown();
  return 0;
}
