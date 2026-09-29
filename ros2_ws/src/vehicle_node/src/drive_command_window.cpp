#include "vehicle_node/drive_command_window.hpp"

#include <QFont>
#include <QPushButton>
#include <QVBoxLayout>


// GUI 창, 버튼, ROS 2 발행자를 생성합니다.
DriveCommandWindow::DriveCommandWindow()
: status_label_(nullptr),
  publish_timer_(nullptr),
  front_enabled_(false)
{
  // /cmd_vel 명령을 보내기 위한 ROS 2 노드를 만듭니다.
  node_ = std::make_shared<rclcpp::Node>("drive_command_gui");
  publisher_ = node_->create_publisher<geometry_msgs::msg::Twist>("/cmd_vel", 10);

  // 창 제목과 크기를 지정합니다.
  setWindowTitle("Vehicle Drive Command");
  setFixedSize(420, 260);

  // 위에서 아래 방향으로 화면 요소를 배치합니다.
  QVBoxLayout * layout = new QVBoxLayout(this);

  // 화면의 제목을 만듭니다.
  QLabel * title_label = new QLabel("Gazebo 차량 주행 명령", this);
  QFont title_font = title_label->font();
  title_font.setPointSize(18);
  title_font.setBold(true);
  title_label->setFont(title_font);
  title_label->setAlignment(Qt::AlignCenter);
  layout->addWidget(title_label);

  // 현재 명령 상태를 보여주는 문구를 만듭니다.
  status_label_ = new QLabel("현재 명령: STOP", this);
  QFont status_font = status_label_->font();
  status_font.setPointSize(14);
  status_label_->setFont(status_font);
  status_label_->setAlignment(Qt::AlignCenter);
  layout->addWidget(status_label_);

  // 초록색 FRONT 버튼을 만듭니다.
  QPushButton * front_button = new QPushButton("FRONT", this);
  front_button->setMinimumHeight(55);
  front_button->setStyleSheet(
    "QPushButton { background-color: #2e8b57; color: white; font-size: 18px; font-weight: bold; }");
  layout->addWidget(front_button);

  // 빨간색 STOP 버튼을 만듭니다.
  QPushButton * stop_button = new QPushButton("STOP", this);
  stop_button->setMinimumHeight(55);
  stop_button->setStyleSheet(
    "QPushButton { background-color: #c0392b; color: white; font-size: 18px; font-weight: bold; }");
  layout->addWidget(stop_button);

  // 각 버튼을 실행할 함수와 연결합니다.
  connect(front_button, &QPushButton::clicked, this, &DriveCommandWindow::setFrontCommand);
  connect(stop_button, &QPushButton::clicked, this, &DriveCommandWindow::setStopCommand);

  // 100 ms마다 현재 주행 명령을 반복해서 발행합니다.
  publish_timer_ = new QTimer(this);
  connect(publish_timer_, &QTimer::timeout, this, &DriveCommandWindow::publishCommand);
  publish_timer_->start(100);
}


// FRONT 버튼을 누르면 3 km/h 전진 상태로 바꿉니다.
void DriveCommandWindow::setFrontCommand()
{
  front_enabled_ = true;
  status_label_->setText("현재 명령: FRONT (3 km/h)");
  RCLCPP_INFO(node_->get_logger(), "FRONT 버튼을 눌렀습니다.");
}


// STOP 버튼을 누르면 정지 상태로 바꿉니다.
void DriveCommandWindow::setStopCommand()
{
  front_enabled_ = false;
  status_label_->setText("현재 명령: STOP");
  RCLCPP_INFO(node_->get_logger(), "STOP 버튼을 눌렀습니다.");
}


// 현재 버튼 상태에 맞는 Twist 메시지를 만듭니다.
void DriveCommandWindow::publishCommand()
{
  // 터미널에서 Ctrl+C를 누르면 Qt 창도 함께 종료합니다.
  if (!rclcpp::ok())
  {
    publish_timer_->stop();
    close();
    return;
  }

  geometry_msgs::msg::Twist command;

  // FRONT 상태에서는 3 km/h를 m/s로 변환해서 발행합니다.
  if (front_enabled_)
  {
    command.linear.x = 3.0 / 3.6;
  }
  else
  {
    command.linear.x = 0.0;
  }

  // 이번 GUI는 직진과 정지만 사용하므로 회전값은 0입니다.
  command.angular.z = 0.0;
  publisher_->publish(command);

  // ROS 2 내부 작업을 처리합니다.
  rclcpp::spin_some(node_);
}


// 속도가 0인 메시지를 발행합니다.
void DriveCommandWindow::publishStopMessage()
{
  geometry_msgs::msg::Twist stop_message;
  stop_message.linear.x = 0.0;
  stop_message.angular.z = 0.0;
  publisher_->publish(stop_message);
}


// 사용자가 창을 닫을 때 차량 정지 명령부터 전송합니다.
void DriveCommandWindow::closeEvent(QCloseEvent * event)
{
  publish_timer_->stop();
  publishStopMessage();
  event->accept();
}
