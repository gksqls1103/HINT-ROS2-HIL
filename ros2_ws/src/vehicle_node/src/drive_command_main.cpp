#include <QApplication>

#include <rclcpp/rclcpp.hpp>

#include "vehicle_node/drive_command_window.hpp"


// C++ 주행 명령 GUI 프로그램이 시작되는 함수입니다.
int main(int argc, char * argv[])
{
  // ROS 2 C++ 통신과 Qt 화면 시스템을 시작합니다.
  rclcpp::init(argc, argv);
  QApplication application(argc, argv);

  // FRONT와 STOP 버튼이 있는 창을 만들고 표시합니다.
  DriveCommandWindow window;
  window.show();

  // 사용자가 창을 닫을 때까지 Qt 이벤트를 처리합니다.
  int result = application.exec();

  // GUI가 끝나면 ROS 2 통신을 안전하게 종료합니다.
  rclcpp::shutdown();
  return result;
}
