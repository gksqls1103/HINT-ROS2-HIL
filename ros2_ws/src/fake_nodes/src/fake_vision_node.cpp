// Fake Vision Node (C++)
// =======================
// B(Vision 담당)의 실제 vision_node가 아직 없을 때, decision_node를 독립적으로
// 개발/테스트하기 위해 D가 만든 가짜 노드.
//
// 동작:
//   - 8초 주기로 NONE -> STOP -> (정지 유지) -> GO -> NONE 을 순환 발행
//   - STOP/GO로 전환된 뒤에는 stable_count를 0부터 올려가며 발행
//   - confidence는 0.85~0.98 사이 랜덤값
//
// 실제 B의 vision_node가 완성되면 decision_node 코드는 수정할 필요 없이
// launch 파일에서 이 노드 대신 vision_node를 띄우기만 하면 된다.

#include <chrono>
#include <memory>
#include <random>
#include <string>
#include <vector>

#include "rclcpp/rclcpp.hpp"
#include "hil_msgs/msg/vision_sign.hpp"

using namespace std::chrono_literals;

namespace
{
constexpr double kStepSeconds = 8.0;
}

class FakeVisionNode : public rclcpp::Node
{
public:
  FakeVisionNode()
  : Node("fake_vision_node"),
    cycle_({"NONE", "STOP", "STOP", "GO", "NONE"}),
    cycle_index_(0),
    stable_count_(0),
    last_sign_(""),
    rng_(std::random_device{}()),
    confidence_dist_(0.85f, 0.98f)
  {
    publisher_ = this->create_publisher<hil_msgs::msg::VisionSign>("/vision/sign", 10);

    tick_timer_ = this->create_wall_timer(
      200ms, std::bind(&FakeVisionNode::publish_tick, this));

    cycle_timer_ = this->create_wall_timer(
      std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::duration<double>(kStepSeconds)),
      std::bind(&FakeVisionNode::advance_cycle, this));

    RCLCPP_INFO(
      this->get_logger(),
      "Fake Vision Node 시작 — %.0f초마다 NONE→STOP→GO 순환 발행", kStepSeconds);
  }

private:
  void advance_cycle()
  {
    cycle_index_ = (cycle_index_ + 1) % cycle_.size();
  }

  void publish_tick()
  {
    const std::string & sign = cycle_[cycle_index_];

    if (sign == last_sign_) {
      stable_count_++;
    } else {
      stable_count_ = 0;
    }
    last_sign_ = sign;

    auto msg = hil_msgs::msg::VisionSign();
    msg.header.stamp = this->now();
    msg.header.frame_id = "camera_link";
    msg.sign = sign;
    msg.confidence = confidence_dist_(rng_);
    msg.stable_count = stable_count_;

    publisher_->publish(msg);

    RCLCPP_DEBUG(
      this->get_logger(), "publish sign=%s confidence=%.2f stable_count=%d",
      msg.sign.c_str(), msg.confidence, msg.stable_count);
  }

  rclcpp::Publisher<hil_msgs::msg::VisionSign>::SharedPtr publisher_;
  rclcpp::TimerBase::SharedPtr tick_timer_;
  rclcpp::TimerBase::SharedPtr cycle_timer_;

  std::vector<std::string> cycle_;
  size_t cycle_index_;
  int stable_count_;
  std::string last_sign_;

  std::mt19937 rng_;
  std::uniform_real_distribution<float> confidence_dist_;
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<FakeVisionNode>());
  rclcpp::shutdown();
  return 0;
}
