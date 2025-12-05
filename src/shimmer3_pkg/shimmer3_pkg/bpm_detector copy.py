import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32, Float32MultiArray
import collections
import heartpy as hp
import numpy as np

# Attributes
SAMPLERATE = 50.032613 # This is determined from this Shimmer3 beforehand using hp.get_samplerate_mstimer(mstimer_data)
BUFFER_LENGTH = 150 # make alaunch parameter. shorter the better to avoid excessive filtering.
UPPERLIMIT = 180  # Maximum plausible heart rate
HRV_LIMIT = 10    # Maximum plausible change in heart rate between successive beats

class BPMDetectorNode(Node):
    def __init__(self):
        super().__init__('bpm_detector_node')
        # Subscriptions
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
        self.buffer = collections.deque(maxlen=500) # rolling buffer, deque is an optimized list with O(1) appending and popping
        self.bpm_buffer = collections.deque(maxlen=50) 

    def ppg_callback(self, msg):
        self.buffer.append(msg.data)
        if len(self.buffer) >= BUFFER_LENGTH: self.compute_and_publish_bpm() # wait until enough samples are collected

    def compute_and_publish_bpm(self):
        ppg_data = np.array(self.buffer, dtype=float)
        try:
            wd, m = hp.process(ppg_data, SAMPLERATE) # wd: working data, m: measures
            wd['peaklist_t'] = [int(idx) / SAMPLERATE for idx in wd['peaklist']]
            bpm_list = get_hr(wd['peaklist_t'])
            bpm = bpm_list[-1] if bpm_list else 0.0
            self.publisher.publish(Float32(data=float(bpm)))
            self.bpm_buffer.append(bpm)
            if len(self.bpm_buffer) >= 10:
                msg = Float32MultiArray()
                msg.data = list(self.bpm_buffer)
                self.publisher_buffer.publish(msg)
                self.get_logger().info(f"Published BPM buffer: {len(msg.data)} samples")
            # self.get_logger().info(f'Published BPM: {bpm:.1f}')
        except Exception as e:
            self.get_logger().warning(f'BPM computation failed: {e}')

def get_hr(peaklist, printout=True):
    bpm = []
    rr_dist = [peaklist[idx] - peaklist[idx-1] for idx in range(1, len(peaklist))] # in samples
    rr_time = [rd / SAMPLERATE for rd in rr_dist]  # in seconds
    for i, rd in enumerate(rr_time):
        bpm.append(1.0 / rd)
        if len(bpm) > 1: # no difference check for first element
            bpm_diff = bpm[-1] - bpm[-2] 
            if abs(bpm_diff) > HRV_LIMIT: # limit exceeded (indicates unrealistic spike)
                print(f"bpm_diff: {bpm_diff}")
                bpm.pop()
                bpm.append(bpm[-1] + sign(bpm_diff) * HRV_LIMIT) # limit the change to the limit value
        if bpm[-1] > UPPERLIMIT:
            bpm.pop()
            if len(bpm) == 0:
                print(f"bpm is empty, appending 0.0")
                bpm.append(0.0)
            else: bpm.append(bpm[-1]) # ignore the change and repeat the last value

    if printout:
        print(f"bpm: {bpm}")
    return bpm

def sign(x):
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