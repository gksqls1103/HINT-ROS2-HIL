#ifndef VEHICLE_NODE__DRIVE_COMMAND_WINDOW_HPP_
#define VEHICLE_NODE__DRIVE_COMMAND_WINDOW_HPP_

#include <QCloseEvent>
#include <QLabel>
#include <QTimer>
#include <QWidget>

#include <geometry_msgs/msg/twist.hpp>
#include <rclcpp/rclcpp.hpp>


// FRONT와 STOP 버튼을 표시하고 /cmd_vel을 발행하는 창입니다.
class DriveCommandWindow : public QWidget
{
public:
  // 화면과 ROS 2 발행자를 생성합니다.
  DriveCommandWindow();

protected:
  // 창을 닫을 때 차량을 먼저 정지시킵니다.
  void closeEvent(QCloseEvent * event) override;

private:
  // 버튼 처리와 메시지 발행을 담당하는 함수입니다.
  void setFrontCommand();
  void setStopCommand();
  void publishCommand();
  void publishStopMessage();

  // ROS 2 노드와 /cmd_vel 발행자를 저장합니다.
  rclcpp::Node::SharedPtr node_;
  rclcpp::Publisher<geometry_msgs::msg::Twist>::SharedPtr publisher_;

  // 화면 상태와 반복 발행에 사용하는 객체입니다.
  QLabel * status_label_;
  QTimer * publish_timer_;

  // true이면 전진하고 false이면 정지합니다.
  bool front_enabled_;
};

#endif  // VEHICLE_NODE__DRIVE_COMMAND_WINDOW_HPP_
