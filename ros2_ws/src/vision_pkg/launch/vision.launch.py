import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    default_cfg = os.path.join(get_package_share_directory("vision_pkg"), "config", "vision_params.yaml")
    params = LaunchConfiguration("params")
    return LaunchDescription([
        DeclareLaunchArgument("params", default_value=default_cfg),
        DeclareLaunchArgument("camera", default_value="true",
                              description="camera_publisher 함께 실행 (/dev/video0 → /camera/image_raw)"),
        DeclareLaunchArgument("debug_image", default_value="false"),
        Node(
            package="vision_pkg",
            executable="camera_publisher",
            name="camera_publisher",
            output="screen",
            parameters=[params],
            condition=IfCondition(LaunchConfiguration("camera")),
        ),
        Node(
            package="vision_pkg",
            executable="vision_node",
            name="vision_node",
            output="screen",
            parameters=[params,
                        {"publish_debug_image": LaunchConfiguration("debug_image")}],
        ),
    ])
