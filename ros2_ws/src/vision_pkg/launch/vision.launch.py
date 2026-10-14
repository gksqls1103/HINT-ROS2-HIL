import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def vision_node(context, params, publish_debug):
    overrides = {"publish_debug_image": publish_debug}
    model = LaunchConfiguration("model").perform(context)
    if model:  # model:= 을 줬을 때만 yaml의 model_path를 덮어쓴다
        overrides["model_path"] = model
    return [Node(
        package="vision_pkg",
        executable="vision_node",
        name="vision_node",
        output="screen",
        parameters=[params, overrides],
    )]


def generate_launch_description():
    default_cfg = os.path.join(get_package_share_directory("vision_pkg"), "config", "vision_params.yaml")
    params = LaunchConfiguration("params")
    web = LaunchConfiguration("web")
    debug_image = LaunchConfiguration("debug_image")
    # web:=true 면 디버그 이미지도 자동으로 켠다
    publish_debug = PythonExpression(["'", debug_image, "' == 'true' or '", web, "' == 'true'"])
    return LaunchDescription([
        DeclareLaunchArgument("params", default_value=default_cfg),
        DeclareLaunchArgument("camera", default_value="true",
                              description="camera_publisher 함께 실행 (/dev/video0 → /camera/image_raw)"),
        DeclareLaunchArgument("debug_image", default_value="false"),
        DeclareLaunchArgument("model", default_value="",
                              description="모델 파일 이름(models/ 안) 또는 절대 경로. 비우면 yaml의 model_path"),
        DeclareLaunchArgument("web", default_value="false",
                              description="web_viewer 실행: 브라우저 http://<Pi IP>:8080 에서 바운딩박스 영상 보기"),
        Node(
            package="vision_pkg",
            executable="camera_publisher",
            name="camera_publisher",
            output="screen",
            parameters=[params],
            condition=IfCondition(LaunchConfiguration("camera")),
        ),
        OpaqueFunction(function=vision_node, args=[params, publish_debug]),
        Node(
            package="vision_pkg",
            executable="web_viewer",
            name="web_viewer",
            output="screen",
            parameters=[params],
            condition=IfCondition(web),
        ),
    ])
