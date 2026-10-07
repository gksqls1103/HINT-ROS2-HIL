from glob import glob
from setuptools import setup

package_name = "vision_pkg"
setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
        ("share/" + package_name + "/launch", glob("launch/*.py")),
        ("share/" + package_name + "/models", glob("models/*.onnx")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    entry_points={"console_scripts": [
        "camera_publisher = vision_pkg.camera_publisher:main",
        "vision_node = vision_pkg.vision_node:main",
        "topic_capture = vision_pkg.topic_capture:main",
    ]},
)
