#include <atomic>
#include <cerrno>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <thread>

#include <fcntl.h>
#include <netdb.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/types.h>
#include <termios.h>
#include <unistd.h>

#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/string.hpp"

class SafetyBridge : public rclcpp::Node
{
public:
  SafetyBridge() : Node("safety_bridge")
  {
    const char * env = std::getenv("SAFETY_SERIAL_URL");
    declare_parameter<std::string>("serial_url", env ? env : "/dev/ttyUSB0");
    declare_parameter<int>("baudrate", 115200);

    pub_ = create_publisher<std_msgs::msg::String>("safety/rx", 10);
    sub_ = create_subscription<std_msgs::msg::String>(
      "safety/tx", 10,
      [this](const std_msgs::msg::String::SharedPtr msg) { on_tx(msg->data); });

    thread_ = std::thread(&SafetyBridge::read_loop, this);
  }

  ~SafetyBridge() override
  {
    running_ = false;
    if (thread_.joinable()) {
      thread_.join();
    }
    close_port();
  }

private:
  // socket://host:port 이면 TCP, 아니면 장치 경로로 연다
  bool open_port()
  {
    const std::string url = get_parameter("serial_url").as_string();
    const int baud = get_parameter("baudrate").as_int();
    const std::string prefix = "socket://";

    bool sock = false;
    int fd = -1;
    if (url.rfind(prefix, 0) == 0) {
      sock = true;
      fd = open_tcp(url.substr(prefix.size()));
    } else {
      fd = open_tty(url, baud);
    }
    if (fd < 0) {
      return false;
    }

    std::lock_guard<std::mutex> lk(mtx_);
    fd_ = fd;
    is_socket_ = sock;
    RCLCPP_INFO(get_logger(), "connected: %s", url.c_str());
    return true;
  }

  static int open_tcp(const std::string & hostport)
  {
    const auto pos = hostport.rfind(':');
    if (pos == std::string::npos) {
      return -1;
    }
    const std::string host = hostport.substr(0, pos);
    const std::string port = hostport.substr(pos + 1);

    addrinfo hints{};
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    addrinfo * res = nullptr;
    if (getaddrinfo(host.c_str(), port.c_str(), &hints, &res) != 0) {
      return -1;
    }

    int fd = -1;
    for (addrinfo * p = res; p != nullptr; p = p->ai_next) {
      fd = socket(p->ai_family, p->ai_socktype, p->ai_protocol);
      if (fd < 0) {
        continue;
      }
      if (connect(fd, p->ai_addr, p->ai_addrlen) == 0) {
        break;
      }
      ::close(fd);
      fd = -1;
    }
    freeaddrinfo(res);

    if (fd >= 0) {
      timeval tv{1, 0};  // 읽기 타임아웃 1초 (종료 시 스레드가 멈출 수 있게)
      setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    }
    return fd;
  }

  static speed_t to_speed(int baud)
  {
    switch (baud) {
      case 9600: return B9600;
      case 19200: return B19200;
      case 38400: return B38400;
      case 57600: return B57600;
      case 230400: return B230400;
      default: return B115200;
    }
  }

  static int open_tty(const std::string & path, int baud)
  {
    const int fd = open(path.c_str(), O_RDWR | O_NOCTTY);
    if (fd < 0) {
      return -1;
    }
    termios tio{};
    if (tcgetattr(fd, &tio) != 0) {
      ::close(fd);
      return -1;
    }
    cfmakeraw(&tio);  // 8N1, 에코/줄바꿈 변환 없음
    cfsetispeed(&tio, to_speed(baud));
    cfsetospeed(&tio, to_speed(baud));
    tio.c_cflag |= (CLOCAL | CREAD);
    tio.c_cflag &= ~CSTOPB;
    tio.c_cc[VMIN] = 0;
    tio.c_cc[VTIME] = 10;  // 읽기 타임아웃 1초
    if (tcsetattr(fd, TCSANOW, &tio) != 0) {
      ::close(fd);
      return -1;
    }
    return fd;
  }

  void close_port()
  {
    std::lock_guard<std::mutex> lk(mtx_);
    if (fd_ >= 0) {
      ::close(fd_);
      fd_ = -1;
    }
  }

  void read_loop()
  {
    std::string line;
    while (running_ && rclcpp::ok()) {
      int fd;
      bool sock;
      {
        std::lock_guard<std::mutex> lk(mtx_);
        fd = fd_;
        sock = is_socket_;
      }
      if (fd < 0) {
        if (!open_port()) {
          RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 5000, "connect failed; retrying");
          std::this_thread::sleep_for(std::chrono::seconds(1));
        }
        continue;
      }

      char buf[256];
      const ssize_t n = read(fd, buf, sizeof(buf));
      if (n > 0) {
        for (ssize_t i = 0; i < n; ++i) {
          if (buf[i] == '\n') {
            if (!line.empty() && line.back() == '\r') {
              line.pop_back();
            }
            if (!line.empty()) {
              std_msgs::msg::String m;
              m.data = line;
              pub_->publish(m);
            }
            line.clear();
          } else {
            line.push_back(buf[i]);
            if (line.size() > 1024) {
              line.clear();  // 줄바꿈 없이 비정상적으로 길어지면 버림
            }
          }
        }
      } else if (n == 0 && !sock) {
        continue;  // tty 읽기 타임아웃
      } else if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)) {
        continue;  // 소켓 읽기 타임아웃
      } else {
        RCLCPP_WARN(get_logger(), "connection closed or error; reconnecting");
        close_port();
        line.clear();
        std::this_thread::sleep_for(std::chrono::seconds(1));
      }
    }
  }

  void on_tx(const std::string & text)
  {
    const std::string data = text + "\n";
    std::lock_guard<std::mutex> lk(mtx_);
    if (fd_ < 0) {
      RCLCPP_WARN(get_logger(), "not connected; tx dropped");
      return;
    }
    size_t sent = 0;
    while (sent < data.size()) {
      const ssize_t n = is_socket_
        ? send(fd_, data.data() + sent, data.size() - sent, MSG_NOSIGNAL)
        : write(fd_, data.data() + sent, data.size() - sent);
      if (n < 0) {
        if (errno == EINTR) {
          continue;
        }
        RCLCPP_WARN(get_logger(), "tx failed: %s", std::strerror(errno));
        return;
      }
      sent += static_cast<size_t>(n);
    }
  }

  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr pub_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr sub_;
  std::thread thread_;
  std::mutex mtx_;
  int fd_{-1};
  bool is_socket_{false};
  std::atomic<bool> running_{true};
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<SafetyBridge>());
  rclcpp::shutdown();
  return 0;
}