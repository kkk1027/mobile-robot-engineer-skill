from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    use_sim_time = LaunchConfiguration("use_sim_time")
    return LaunchDescription(
        [
            DeclareLaunchArgument("use_sim_time", default_value="true"),
            Node(
                package="controller_manager",
                executable="ros2_control_node",
                parameters=["config/controllers.yaml", {"use_sim_time": use_sim_time}],
                output="screen",
            ),
            Node(
                package="mini_diff_robot",
                executable="base_monitor",
                parameters=[{"use_sim_time": use_sim_time}],
                output="screen",
            ),
        ]
    )
