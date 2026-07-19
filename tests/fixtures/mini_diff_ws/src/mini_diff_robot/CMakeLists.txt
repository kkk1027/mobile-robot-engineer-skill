cmake_minimum_required(VERSION 3.16)
project(mini_diff_robot)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(diagnostic_msgs REQUIRED)

add_executable(base_monitor src/base_monitor.cpp)
ament_target_dependencies(base_monitor rclcpp geometry_msgs nav_msgs diagnostic_msgs)

install(TARGETS base_monitor DESTINATION lib/mini_diff_robot)
install(DIRECTORY launch config description DESTINATION share/mini_diff_robot)
ament_package()
