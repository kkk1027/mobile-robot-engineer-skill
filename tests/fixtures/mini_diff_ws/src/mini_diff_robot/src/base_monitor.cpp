#include <chrono>
#include <memory>

#include "diagnostic_msgs/msg/diagnostic_array.hpp"
#include "geometry_msgs/msg/twist_stamped.hpp"
#include "nav_msgs/msg/odometry.hpp"
#include "rclcpp/rclcpp.hpp"

class BaseMonitor : public rclcpp::Node {
 public:
  BaseMonitor() : Node("base_monitor") {
    cmd_sub_ = create_subscription<geometry_msgs::msg::TwistStamped>(
        "/cmd_vel", 10, [this](geometry_msgs::msg::TwistStamped::SharedPtr) {
          last_command_ = now();
        });
    odom_pub_ = create_publisher<nav_msgs::msg::Odometry>("/odom", 10);
    diagnostics_pub_ =
        create_publisher<diagnostic_msgs::msg::DiagnosticArray>("/diagnostics", 10);
    watchdog_timer_ = create_wall_timer(std::chrono::milliseconds(50), [this]() {
      const bool command_timeout = (now() - last_command_).seconds() > 0.25;
      const bool emergency_stop = e_stop_active_;
      (void)command_timeout;
      (void)emergency_stop;
    });
  }

 private:
  bool e_stop_active_{false};
  rclcpp::Time last_command_{0, 0, RCL_ROS_TIME};
  rclcpp::Subscription<geometry_msgs::msg::TwistStamped>::SharedPtr cmd_sub_;
  rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr odom_pub_;
  rclcpp::Publisher<diagnostic_msgs::msg::DiagnosticArray>::SharedPtr diagnostics_pub_;
  rclcpp::TimerBase::SharedPtr watchdog_timer_;
};

int main(int argc, char **argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<BaseMonitor>());
  rclcpp::shutdown();
  return 0;
}
