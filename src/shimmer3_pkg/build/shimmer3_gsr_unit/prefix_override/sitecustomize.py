import sys
if sys.prefix == '/usr':
    sys.real_prefix = sys.prefix
    sys.prefix = sys.exec_prefix = '/home/lairlab-squirtle/ros2_ws/src/shimmer3_pkg/install/shimmer3_pkg'
