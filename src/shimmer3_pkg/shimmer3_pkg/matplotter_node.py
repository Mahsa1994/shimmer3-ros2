import matplotlib
matplotlib.use('Qt5Agg')
import matplotlib.pyplot as plt
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32
from collections import deque
import numpy as np

class MatPlotterNode(Node):
    def __init__(self):
        super().__init__('matplotter_node')

        # Subscriptions
        self.subscription = self.create_subscription(
            Float32,
            'live_bpm',
            self.plot_callback,
            10)

        # Publishers
        # None, just the plot

        # Attributes
        self.sample_rate = 10 # in Hz. From bpm_detector.py BPM_PUB_RATE
        self.upperlimit = 180.0  # upper limit for heart rate in BPM
        self.maxlen = 500
        self.buffer = deque(maxlen=200000) # > one hour
        self.window_size = 10.0 # in s

        # Setup
        plt.ion() # interactive mode
        self.fig, self.ax = plt.subplots() # create figure fig and the axes (a single plot)
        (self.line,) = self.ax.plot([], [], marker='o', label='Live BPM') # create and store empty line object (to be updated)
        self.ax.set_ylim(0, self.upperlimit)
        self.ax.set_xlabel('Time [s]')
        self.ax.set_ylabel('BPM')
        self.ax.legend()
        self.get_logger().info("Showing plot...")
        plt.show() # actually show the window

    def plot_callback(self, msg):
        self.buffer.append(msg.data)
        self.update_plot()
        
    def update_plot(self):
        ydata = list(self.buffer)
        xdata = np.arange(len(ydata)) / self.sample_rate # time calculated form samples and frequency
        self.line.set_xdata(xdata)
        self.line.set_ydata(ydata)
        current_time = xdata[-1] if len(xdata) > 0 else 0
        window_start = max(0, current_time - self.window_size)
        self.ax.set_xlim(window_start, current_time)
        self.ax.set_ylim(0, self.upperlimit)

        # self.ax.relim() # autoscale calculations
        # self.ax.autoscale_view(scalex=True, scaley=False)
        # self.ax.set_xlim(current_time - self.window_size, current_time) # Something like this could save computation time compared to relim and autoscaling
        self.ax.figure.canvas.draw()
        self.ax.figure.canvas.flush_events()
        plt.pause(0.001)

def main(args=None):
    rclpy.init(args=args)
    node = MatPlotterNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt: pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()