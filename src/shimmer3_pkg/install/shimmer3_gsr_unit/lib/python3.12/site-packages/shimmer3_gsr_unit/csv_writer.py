import os
import rclpy
from rclpy.node import Node
import rclpy.logging 
import csv
from std_msgs.msg import Float32
import time
import shutil

class RawPPGLogger(Node):
    def __init__(self):
        super().__init__('raw_ppg_logger')

        # Parameter Declaration
        self.declare_parameter('chunk_length', 128)
        self.chunk_length = self.get_parameter('chunk_length').value

        # Subscribers
        self.sub = self.create_subscription(Float32, "biosensors/shimmer3_gsr/ppg", self.callback, 10)

        # Path
        home_dir = os.path.expanduser("~")
        csv_path = os.path.join(home_dir, "ros2_ws", "src", "shimmer3_pkg", "ppg.csv")
        self.csv_file = open(csv_path, mode='w', newline='') # w: writemode, newline: create new rows
        self.csv_writer = csv.writer(self.csv_file)

        header = ["timestamp", "ppg"]
        self.csv_writer.writerow(header)
        self.get_logger().info("Raw PPG data logger node started. Waiting for messages.")

        self.first_timestamp_flag = False
        self.first_timestamp = 0.0

    def callback(self, msg):
        try:
            ppg_data = msg.data
            current_timestamp = time.time()
            if self.first_timestamp_flag == False: 
                self.first_timestamp = current_timestamp  # in milliseconds for hp.mstimer
                print(f"first_timestep: {self.first_timestamp}")
                self.first_timestamp_flag = True
            relative_timestamp = (current_timestamp - self.first_timestamp) * 1000  # in milliseconds for hp.mstimer
            self.csv_writer.writerow([relative_timestamp, ppg_data])
            self.get_logger().info(f"Recorded PPG data point.")

        except Exception as e:
            self.get_logger().error(f"Error writing PPG data: {e}")

    def destroy_node(self):
        self.csv_file.close()
        self.get_logger().info("CSV file closed. Node shutting down.")
        dst_file = os.path.join(os.path.expanduser("~"), "ros2_ws", "src", "heartrate_analysis_python", "heartpy", "data", "ppg.csv")
        shutil.copy(self.csv_file, dst_file)
        super().destroy_node()

def main(args=None):
    rclpy.init(args=args)
    node = RawPPGLogger()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
	main()