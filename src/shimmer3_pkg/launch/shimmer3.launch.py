import os
from ament_index_python.packages import get_package_share_directory , get_search_paths
from launch.actions import DeclareLaunchArgument, ExecuteProcess, LogInfo
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch import LaunchDescription, Action
import launch
from launch.conditions import IfCondition


def generate_launch_description():  
    # Subject Information
    Subject_Number = "P1"

    # Launch Parameters
    ppg_buffer_length_arg = DeclareLaunchArgument(
        'ppg_buffer_length',
        default_value = "500",
        description = 'PPG buffer length with which BPM is found. The smaller, the less filtering, and the more noise.')
    ppg_buffer_length = LaunchConfiguration('ppg_buffer_length')

    hrv_limit_arg = DeclareLaunchArgument(
        'hrv_limit',
        default_value = "1",
        description = 'Reasonable difference in HR between samples, filters HR.')
    hrv_limit = LaunchConfiguration('hrv_limit')

    liveplot_arg = DeclareLaunchArgument(
        'liveplot',
        default_value = 'true',
        description = 'Show live BPM matplot')
    liveplot = LaunchConfiguration('liveplot')

    # Nodes
    shimmer3_node = Node(
        package='shimmer3_pkg',
        #namespace='Subject_Number',
        executable='shimmer3_node',
        name='shimmer3_node',
        output='screen',
        parameters=[{
            'Sensor_Enable': True, 
            'Chunk_Enable': True,
            'Chunk_Length': 128,
            ### For sensor devices
            # Ensure the Bluetooth radio is available by running the '''$ hciconfig''' command.
            # Scan for the Shimmer by running the '''$ hcitool scan''' command.
            'MAC_Addr': '74:D5:C6:52:65:C2',
        }])

    bpm_detector_node = Node(
        package='shimmer3_pkg',
        executable='bpm_detector_node',
        name='bpm_detector_node',
        output='screen',
        parameters=[{
            'ppg_buffer_length': ppg_buffer_length,
            'hrv_limit': hrv_limit,
        }] 
    )

    matplotter_node = Node(
        package='shimmer3_pkg',
        executable='matplotter_node',
        name='matplotter_node',
        output='screen',
        condition=IfCondition(LaunchConfiguration("liveplot"))
        )
    raw_ppg_logger_node = Node(
        package='shimmer3_pkg',
        executable='raw_ppg_logger',   # the ROS2 executable name of your CSV logger
        name='raw_ppg_logger',
        output='screen',
        parameters=[{
            'chunk_length': 128  # same chunk length if needed
        }]
)


    return LaunchDescription([
        # Arguments
        ppg_buffer_length_arg,
        hrv_limit_arg,
        liveplot_arg,

        # Log Messages
        LogInfo(msg=['Launching with ppg_buffer_length: ', ppg_buffer_length]),
        LogInfo(msg=['Launching with hrv_limit: ', hrv_limit]),
        LogInfo(msg=['Matplot live heartrate plotter (liveplot): ', liveplot]),

        # Nodes
        shimmer3_node,
        bpm_detector_node,
        matplotter_node,
        raw_ppg_logger_node,
        ])
