import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32, Float32MultiArray
import collections
import heartpy as hp
import numpy as np

# Attributes
SAMPLERATE = 50.032613 # Hz. This is determined from this Shimmer3 beforehand using hp.get_samplerate_mstimer(mstimer_data)
BPM_PUB_RATE = 10 # Hz. Doesn't need to be the full SAMPLERATE as BPM is only computed every peak.
UPPERLIMIT = 180  # Maximum plausible heart rate

class BPMDetectorNode(Node):
    def __init__(self):
        super().__init__('bpm_detector_node')
        # Parameters
        self.declare_parameter('ppg_buffer_length', 500)
        self.declare_parameter('hrv_limit', 1)

        self.ppg_buffer_length = int(self.get_parameter('ppg_buffer_length').value)
        self.hrv_limit = int(self.get_parameter('hrv_limit').value)

        self.last_bpm = 0.0

        # Subscriptions``
        self.subscription = self.create_subscription(
            Float32,
            'biosensors/shimmer3_gsr/ppg',
            self.ppg_callback,
            10)

        # Publishers
        self.publisher_single = self.create_publisher(
            Float32,
            '/live_bpm',
            10)
        self.publisher_buffer = self.create_publisher(
            Float32MultiArray,
            '/bpm_buffer',
            10)

        # Buffers
        self.ppg_buffer = collections.deque(maxlen=500) # rolling buffer, deque is an optimized list with O(1) appending and popping
        self.bpm_buffer = collections.deque(maxlen=50) 

        # Timers
        timer_period = 1.0 / BPM_PUB_RATE
        self.timer = self.create_timer(timer_period, self.publish_bpm)

    def ppg_callback(self, msg):
        self.ppg_buffer.append(msg.data)
        if len(self.ppg_buffer) >= self.ppg_buffer_length: self.compute_bpm() # wait until enough samples are collected

    def compute_bpm(self):
        ppg_data = np.array(self.ppg_buffer, dtype=float)
        try:
            wd, m = hp.process(ppg_data, SAMPLERATE) # wd: working data, m: measures
            wd['peaklist_t'] = [idx / SAMPLERATE for idx in wd['peaklist']]
            bpm_list = self.get_hr(wd['peaklist_t'])
            bpm = bpm_list[-1] if bpm_list else 0.0
            self.bpm_buffer.append(bpm)
            return bpm

        except Exception as e:
            self.get_logger().warning(f'BPM computation failed: {e}')

    def publish_bpm(self):
        msg = Float32()
        msg.data = self.last_bpm
        self.publisher_single.publish(msg)

        if len(self.bpm_buffer) >= 10:
            buffer_msg = Float32MultiArray()
            buffer_msg.data = list(self.bpm_buffer)
            self.publisher_buffer.publish(buffer_msg)
            # self.get_logger().info(f"Published BPM buffer: {len(msg.data)} samples")

    def get_hr(self, peaklist):
        rr_dist = [peaklist[idx] - peaklist[idx-1] for idx in range(1, len(peaklist))] # in samples
        rr_time = [rd / SAMPLERATE for rd in rr_dist]  # in seconds
        bpm_list = []
        for rd in rr_time:
            candidate = (1.0 / rd)
            bpm_diff = candidate - self.last_bpm
            if self.last_bpm != 0 and abs(bpm_diff) > self.hrv_limit:
                # self.get_logger().info(f"bpm_diff: {bpm_diff}")
                candidate = self.last_bpm + self.sign(bpm_diff) * self.hrv_limit
            if candidate > UPPERLIMIT: 
                # self.get_logger().info(f"bpm value of '{candidate}' exceeds {UPPERLIMIT}")
                candidate = self.last_bpm
            
            self.last_bpm = candidate
            bpm_list.append(candidate)
        return bpm_list

    def sign(self, x):
        x = float(x)
        return (x > 0) - (x < 0)

def main(args=None):
    rclpy.init(args=args)
    node = BPMDetectorNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()