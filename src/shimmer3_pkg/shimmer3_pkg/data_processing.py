# from rclpy.node import Node
# from scipy.signal import find_peaks

# class data_processing(Node):
#     def __init__(self):
#         super().__init__('data_processing_node')\

#         # Attributes
#         self.sample_frequency = 50 # later get this from the earlier node

#         # Subscribers
#         self.ppg_data = Subscriber(self, Node, <variable>)

    


# def main(args=None):
#     rclpy.init(args=args)
#     ros2_shimmer3_node = ros2_shimmer3()
#     try:
#         while rclpy.ok():
#             pass
#             rclpy.spin(ros2_shimmer3_node)
#     except KeyboardInterrupt:
#         self.get_logger().info('repeater stopped cleanly')
#     except BaseException:
#         self.get_logger().info('exception in repeater:', file=sys.stderr)
#         raise
#     finally:
#         data_processing.destroy_node()
#         rclpy.shutdown()