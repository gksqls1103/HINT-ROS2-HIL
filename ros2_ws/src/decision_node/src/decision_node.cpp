// Decision Node (C++)
// =====================
// D 담당. Vision(/vision/sign), Safety(/safety/state), Vehicle(/vehicle/state)
// 이벤트를 모아 하나의 상태머신(FSM)으로 최종 주행 판단을 내리고 /cmd_vel 을
// 발행한다.
//
// 상태:
//   IDLE            대기
//   DRIVING         주행 중
//   STOPPING        STOP 표지 인식 → 정지 대기
//   EMERGENCY_STOP  근접 장애물 감지 → 즉시 정지 (최우선)
//   RECOVERY        장애물 해소 → 잠깐 대기 후 주행 재개
//   FAIL_SAFE       통신 두절/FAULT → 안전 정지, 자동 복귀 없음(수동 개입 필요)
//
// 우선순위: EMERGENCY_STOP / FAIL_SAFE 가 Vision 판단보다 항상 우선한다.

#include <chrono>
#include <memory>
#include <optional>
#include <string>

#include "rclcpp/rclcpp.hpp"
#include "geometry_msgs/msg/twist.hpp"
#include "std_msgs/msg/string.hpp"
#include "hil_msgs/msg/vision_sign.hpp"
#include "hil_msgs/msg/safety_state.hpp"

using namespace std::chrono_literals;

namespace
{
constexpr double kSafetyTimeoutSec = 2.0;   // 이 시간 동안 /safety/state 미수신 시 통신 두절
constexpr double kRecoveryHoldSec = 1.5;    // EMERGENCY 해제 후 RECOVERY 유지 시간
constexpr double kDriveSpeed = 0.3;
constexpr double kStopSpeed = 0.0;
}  // namespace

enum class State
{
  IDLE,
  DRIVING,
  STOPPING,
  EMERGENCY_STOP,
  RECOVERY,
  FAIL_SAFE,
};

std::string to_string(State s)
{
  switch (s) {
    case State::IDLE: return "IDLE";
    case State::DRIVING: return "DRIVING";
    case State::STOPPING: return "STOPPING";
    case State::EMERGENCY_STOP: return "EMERGENCY_STOP";
    case State::RECOVERY: return "RECOVERY";
    case State::FAIL_SAFE: return "FAIL_SAFE";
  }
  return "UNKNOWN";
}

class DecisionNode : public rclcpp::Node
{
public:
  DecisionNode()
  : Node("decision_node"),
    state_(State::IDLE),
    started_(false)
  {
    last_safety_msg_time_ = this->now();

    // ---- Subscriptions ----
    vision_sub_ = this->create_subscription<hil_msgs::msg::VisionSign>(
      "/vision/sign", 10, std::bind(&DecisionNode::on_vision, this, std::placeholders::_1));

    safety_sub_ = this->create_subscription<hil_msgs::msg::SafetyState>(
      "/safety/state", 10, std::bind(&DecisionNode::on_safety, this, std::placeholders::_1));

    // /vehicle/state는 지금 단계에서는 로직에 반영하지 않음 (A 노드 완성 후 필요 시 추가)

    // ---- Publishers ----
    cmd_pub_ = this->create_publisher<geometry_msgs::msg::Twist>("/cmd_vel", 10);
    fault_pub_ = this->create_publisher<std_msgs::msg::String>("/system/fault", 10);

    // ---- Timers ----
    control_timer_ = this->create_wall_timer(
      200ms, std::bind(&DecisionNode::control_loop, this));

    safety_timeout_timer_ = this->create_wall_timer(
      500ms, std::bind(&DecisionNode::check_safety_timeout, this));

    // 데모 편의를 위해 5초 뒤 자동으로 DRIVING 시작 (1회성)
    auto_start_timer_ = this->create_wall_timer(
      5s, std::bind(&DecisionNode::auto_start_once, this));

    RCLCPP_INFO(this->get_logger(), "Decision Node 시작 — 초기 상태: IDLE");
  }

private:
  // ------------------------------------------------------------------
  // 상태 전이 유틸
  // ------------------------------------------------------------------
  void set_state(State new_state, const std::string & reason)
  {
    if (new_state == state_) {return;}
    RCLCPP_INFO(
      this->get_logger(), "[FSM] %s → %s  (%s)",
      to_string(state_).c_str(), to_string(new_state).c_str(), reason.c_str());
    state_ = new_state;
    if (new_state == State::RECOVERY) {
      recovery_started_at_ = this->now();
    }
  }

  void auto_start_once()
  {
    if (!started_ && state_ == State::IDLE) {
      started_ = true;
      set_state(State::DRIVING, "미션 시작(데모용 자동 트리거)");
    }
    auto_start_timer_->cancel();  // 1회만 실행
  }

  // ------------------------------------------------------------------
  // Vision 콜백 — STOP/GO 판단
  // ------------------------------------------------------------------
  void on_vision(const hil_msgs::msg::VisionSign::SharedPtr msg)
  {
    // 최우선 상태(EMERGENCY_STOP, FAIL_SAFE)에서는 Vision 신호를 무시한다.
    if (state_ == State::EMERGENCY_STOP || state_ == State::FAIL_SAFE) {
      return;
    }

    // 최소 3프레임 연속 인식돼야 신뢰 (B와 합의한 stable_count 규칙)
    if (msg->stable_count < 3) {
      return;
    }

    if (msg->sign == "STOP" && state_ == State::DRIVING) {
      set_state(
        State::STOPPING,
        "STOP 표지 인식(conf=" + std::to_string(msg->confidence) + ")");
    } else if (msg->sign == "GO" && state_ == State::STOPPING) {
      set_state(
        State::DRIVING,
        "GO 표지 인식(conf=" + std::to_string(msg->confidence) + ")");
    }
  }

  // ------------------------------------------------------------------
  // Safety 콜백 — EMERGENCY / RECOVERY / FAIL_SAFE 판단 (최우선)
  // ------------------------------------------------------------------
  void on_safety(const hil_msgs::msg::SafetyState::SharedPtr msg)
  {
    last_safety_msg_time_ = this->now();

    if (msg->level == "FAULT") {
      set_state(State::FAIL_SAFE, "Safety 노드 FAULT 보고");
      publish_fault("SAFETY_FAULT");
      return;
    }

    if (msg->level == "EMERGENCY") {
      set_state(
        State::EMERGENCY_STOP,
        "장애물 감지(distance=" + std::to_string(msg->distance_cm) + "cm)");
      return;
    }

    // EMERGENCY_STOP 상태였는데 CLEAR로 돌아오면 RECOVERY 거쳐 주행 재개
    if (msg->level == "CLEAR" && state_ == State::EMERGENCY_STOP) {
      set_state(State::RECOVERY, "장애물 해소");
    }
  }

  // ------------------------------------------------------------------
  // 통신 두절 감시 (Fail-Safe)
  // ------------------------------------------------------------------
  void check_safety_timeout()
  {
    const double elapsed = (this->now() - last_safety_msg_time_).seconds();
    if (elapsed > kSafetyTimeoutSec && state_ != State::FAIL_SAFE) {
      set_state(
        State::FAIL_SAFE,
        "/safety/state " + std::to_string(elapsed) + "초간 미수신");
      publish_fault("SAFETY_COMM_TIMEOUT");
    }
  }

  // ------------------------------------------------------------------
  // RECOVERY → DRIVING 자동 전이 (일정 시간 대기 후)
  // ------------------------------------------------------------------
  void maybe_finish_recovery()
  {
    if (state_ == State::RECOVERY && recovery_started_at_.has_value()) {
      const double elapsed = (this->now() - recovery_started_at_.value()).seconds();
      if (elapsed > kRecoveryHoldSec) {
        set_state(State::DRIVING, "Recovery 완료");
      }
    }
  }

  // ------------------------------------------------------------------
  // 제어 루프 — 현재 상태에 맞는 /cmd_vel 발행
  // ------------------------------------------------------------------
  void control_loop()
  {
    maybe_finish_recovery();

    geometry_msgs::msg::Twist twist;
    if (state_ == State::DRIVING) {
      twist.linear.x = kDriveSpeed;
    } else {
      // IDLE / STOPPING / EMERGENCY_STOP / RECOVERY / FAIL_SAFE 는 전부 정지
      twist.linear.x = kStopSpeed;
    }

    cmd_pub_->publish(twist);
  }

  void publish_fault(const std::string & code)
  {
    std_msgs::msg::String msg;
    msg.data = code;
    fault_pub_->publish(msg);
  }

  // ---- 상태 ----
  State state_;
  bool started_;
  rclcpp::Time last_safety_msg_time_;
  std::optional<rclcpp::Time> recovery_started_at_;

  // ---- ROS2 인터페이스 ----
  rclcpp::Subscription<hil_msgs::msg::VisionSign>::SharedPtr vision_sub_;
  rclcpp::Subscription<hil_msgs::msg::SafetyState>::SharedPtr safety_sub_;
  rclcpp::Publisher<geometry_msgs::msg::Twist>::SharedPtr cmd_pub_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr fault_pub_;
  rclcpp::TimerBase::SharedPtr control_timer_;
  rclcpp::TimerBase::SharedPtr safety_timeout_timer_;
  rclcpp::TimerBase::SharedPtr auto_start_timer_;
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<DecisionNode>());
  rclcpp::shutdown();
  return 0;
}
