"""
decision_dev.launch.py
=======================
D가 A/B/C 없이 혼자 decision_node를 개발/테스트할 때 쓰는 launch 파일.
fake_vision_node + fake_safety_node + decision_node 3개를 한 번에 띄운다.

실행:
    ros2 launch decision_node decision_dev.launch.py

나중에 B/C의 실제 노드가 준비되면, fake_vision_node/fake_safety_node 부분만
vision_node / stm32_bridge_node 로 교체한 decision_prod.launch.py 를 새로 만들면 된다.
(decision_node 코드는 수정할 필요 없음 — 토픽 이름/타입이 동일하기 때문)
"""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='fake_nodes',
            executable='fake_vision_node',
            name='fake_vision_node',
            output='screen',
        ),
        Node(
            package='fake_nodes',
            executable='fake_safety_node',
            name='fake_safety_node',
            output='screen',
        ),
        Node(
            package='decision_node',
            executable='decision_node',
            name='decision_node',
            output='screen',
        ),
    ])
