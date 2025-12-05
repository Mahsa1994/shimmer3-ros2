import sys, struct, serial, os
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from scipy import signal
from scipy.signal import find_peaks
import numpy as np
import subprocess
from std_msgs.msg import Float32, Float32MultiArray, Int32

class ros2_shimmer3(Node):
    def __init__(self):
        super().__init__('shimmer3_node')
        # Enable parameters
        self.declare_parameter('Sensor_Enable', True) # Enable to publish sensor data (true)
        self.declare_parameter('Chunk_Enable', True) # Enable to publish chunk data (true)        
        self.declare_parameter('Chunk_Length', 128) # Define the length of the chunk data
        self.declare_parameter('Device_Name', "74:D5:C6:52:65:C2") # Should be changed into your device name
        self.declare_parameter('Channel_Number', "6")
        
        self.Parm_Sensor_Enable = self.get_parameter('Sensor_Enable').value 
        self.Parm_Chunk_Enable = self.get_parameter('Chunk_Enable').value 
        self.Parm_Chunk_Length = self.get_parameter('Chunk_Length').value 
        self.Parm_Device_Name = self.get_parameter('Device_Name').value 
        self.Parm_Channel_Number = self.get_parameter('Channel_Number').value

        # Ensure the Bluetooth radio is available by running the '''$ hciconfig''' command.
        # Scan for the Shimmer by running the '''$ hcitool scan''' command.

        # Connect to Device via Bluetooth
        bt_addr = self.Parm_Device_Name
        try:
            if not is_rfcomm_bound(bt_addr):    # Check that its not already connected
                os.system("sudo rfcomm release 0") # release rfcomm0
                os.system("sudo chmod a+rw /dev/rfcomm0")
                msg = f"sudo rfcomm bind 0 {self.Parm_Device_Name} {self.Parm_Channel_Number}"
                os.system(msg)
                self.get_logger().info(msg)
            else:
                self.get_logger().info(f"Device {bt_addr} already bound to an rfcomm device. Step skipped.")

            self.ser = serial.Serial("/dev/rfcomm0", 115200, timeout=1) # 1 second timeout for clean opening. ser is a serial.Serial instance
            self.ser.flushInput()
            self.get_logger().info("port opening, done.")

            # send the set sensors command
            self.ser.write(struct.pack('BBBB', 0x08 , 0x04, 0x01, 0x00))  #GSR and PPG
            self.wait_for_ack()
            self.get_logger().info("sensor setting, done.")

            # Enable the internal expansion board power
            self.ser.write(struct.pack('BB', 0x5E, 0x01))
            self.wait_for_ack()
            self.get_logger().info("enable internal expansion board power, done.")

            # send the set sampling rate command
            # self.sample_freq = 32768 / clock_wait = X Hz
            self.sample_freq = 50
            clock_wait = (2 << 14) / self.sample_freq
            self.ser.write(struct.pack('<BH', 0x05, int(clock_wait)))
            self.wait_for_ack()

            # send start streaming command
            self.ser.write(struct.pack('B', 0x07))
            self.wait_for_ack()
            self.get_logger().info("start command sending, done.")
        
        except serial.SerialException as e:
            self.get_logger().error(f"Could not open serial port {e}")
            self.ser = None
            return

        # Publishers
        self.get_logger().info(f"Parm_Sensor_Enable: {self.Parm_Sensor_Enable}")
        if self.Parm_Sensor_Enable:
            self.pub_shimmer3_gsr_data = self.create_publisher(Float32, "biosensors/shimmer3_gsr/gsr", 10)
            self.pub_shimmer3_ppg_data = self.create_publisher(Float32, "biosensors/shimmer3_gsr/ppg", 10)
            self.pub_shimmer3_ppg_filtered = self.create_publisher(Float32, "biosensors/shimmer3_gsr/ppg_filtered", 10)
            self.pub_shimmer3_hr = self.create_publisher(Int32, "biosensors/shimmer3_gsr/hr", 10)

        if self.Parm_Chunk_Enable:
            self.pub_shimmer3_gsr_chunk_data = self.create_publisher(Float32MultiArray, "biosensors/shimmer3_gsr/gsr_chunk", 10) 
            self.pub_shimmer3_ppg_chunk_data = self.create_publisher(Float32MultiArray, "biosensors/shimmer3_gsr/ppg_chunk", 10)
        #self.get_logger().info("Packet Type\tTimestamp\tGSR\tPPG")
        
        # Attribute Initializations
        # Data
        self.data_index = 0
        self.gsr_data_index = 0
        self.gsr_chunk_data = []
        self.ppg_data_index = 0
        self.ppg_chunk_data = []
        self.ppg_buffer = []
        self.buffer_size = 128
        self.sample_frequency = 50.0
        self.prominence = 100
        
        # Read Data
        while rclpy.ok() and self.Parm_Sensor_Enable:
            (shimmer_raw_GSR, Shimmer_raw_PPG) = self.reading_shimmer3_data()

            self.pub_shimmer3_gsr_data.publish(Float32(data = shimmer_raw_GSR))
            self.pub_shimmer3_ppg_data.publish(Float32(data = Shimmer_raw_PPG))

            # PPG Filter Rolling Buffer
            self.ppg_buffer.append(Shimmer_raw_PPG) # append raw data to this buffer
            if len(self.ppg_buffer) > self.buffer_size: self.ppg_buffer.pop(0) # and pop out data from beginning once length is exceeded (constant length ppg_buffer)
            if len(self.ppg_buffer) == self.buffer_size: # when the buffer is filled (128 points in)
                filtered_window = self.bandpass_filter(self.ppg_buffer) # apply bandpass filter
                filtered_sample = filtered_window[-1] # get the most recent data point
                self.filtered_plot_buffer = filtered_window # for our plot
                self.pub_shimmer3_ppg_filtered.publish(Float32(data=filtered_sample)) # publish the filtered data
                hr = self.get_heartrate(filtered_window)
                # self.get_logger().info(f"Heartrate: {hr}")
                self.pub_shimmer3_hr.publish(Int32(data=hr))

            # Collect samples into a chunk list
            if self.Parm_Chunk_Enable:
                self.gsr_chunk_data.append(shimmer_raw_GSR)
                self.ppg_chunk_data.append(Shimmer_raw_PPG)

                #print(self.bvp_data_index, stream_id.name, timestamp, sample) #For test
                if self.data_index  == self.Parm_Chunk_Length - 1:
                    ppg_filtered = self.bandpass_filter(data=self.ppg_chunk_data) # Filter the chunk

                    # Publish chunk and filtered point (from chunk)
                    self.pub_shimmer3_gsr_chunk_data.publish(Float32MultiArray(data = self.gsr_chunk_data))
                    self.pub_shimmer3_ppg_chunk_data.publish(Float32MultiArray(data = self.ppg_chunk_data))
                    # self.pub_shimmer3_ppg_filtered.publish(Float32(data = self.ppg_chunk_data[-1]))

                    # Reset index and ref_array
                    self.gsr_chunk_data = []
                    self.ppg_chunk_data = []
                    self.data_index = 0

                else: self.data_index += 1
            else: pass

    def reading_shimmer3_data(self):
        ddata = ""
        numbytes = 0
        framesize = 8 # 1byte packet type + 3byte timestamp + 2 byte GSR + 2 byte PPG(Int A13)

        while numbytes < framesize:
            ddata = self.ser.read(framesize)
            #ddata = ddata + test.decode('utf-8')
            numbytes = len(ddata)
        
        data = ddata[0:framesize]
        ddata = ddata[framesize:]
        numbytes = len(ddata)

        (packettype) = struct.unpack('B', data[0:1])
        #(timestamp0, timestamp1, timestamp2) = struct.unpack('BBB', data[1:4])

        # read packet payload
        (PPG_raw, GSR_raw) = struct.unpack('HH', data[4:framesize])

        # get current GSR range resistor value
        Range = ((GSR_raw >> 14) & 0xff)  # isolate the upper two bits
        if(Range == 0):
            Rf = 40.2   # kohm
        elif(Range == 1):
            Rf = 287.0  # kohm
        elif(Range == 2):
            Rf = 1000.0 # kohm
        elif(Range == 3):
            Rf = 3300.0 # kohm

        # convert GSR to kohm value (?? kohm or volts ??)
        gsr_to_volts = (GSR_raw & 0x3fff) * (3.0/4095.0)
        GSR_ohm = Rf/( (gsr_to_volts /0.5) - 1.0)

        # convert PPG to milliVolt value
        PPG_mv = PPG_raw * (3000.0/4095.0)
        #print(GSR_ohm, type(GSR_ohm), PPG_mv, type(PPG_mv))
        return (float(GSR_ohm), float(PPG_mv))

    def wait_for_ack(self):
        ddata = ""
        ack = struct.pack('B', 0xff)
        while ddata != ack:
            ddata = self.ser.read(1)
            #self.get_logger().info("0x%02x" % ord(ddata[0]))
            
        return

    def bandpass_filter(self, data, lowcut= 0.5, highcut=5):
        # lowcut: 0.5Hz (30bpm) # gow with the low pass
        # highcut: 5Hz (300bpm)

        fnyq = 0.5 * self.sample_frequency # Nyquist frequency typically equal to half the sampling frequency  
        low = lowcut / fnyq # normalized lowcut to fnyq (which is 1)
        high = highcut / fnyq 
        b, a = signal.butter(4, [low,high], btype='band') # returns the filter coefficients (num and denom) 4th order butterworth filter (for relatively smooth and steep cutoff slopes)
        filtered_data = signal.filtfilt(b, a, np.array(data)) # filtfilt applies filter forward and backward to cancel phase shift. Minimal lag
        return filtered_data.tolist()

    def get_heartrate(self, ppg_signal):
        distance = int(0.5 * self.sample_frequency) # this creates a time range to avoid double detection
        peaks, _ = find_peaks(ppg_signal, distance=distance, prominence=self.prominence) # uses scipy.signal.find_peaks to return peaks (ignore other info)
        rr_intervals = np.diff(peaks) / self.sample_frequency # rr interval is ECG lingo for distance between peaks
        if len(rr_intervals) == 0: return 0 # if the peaks matrix is empty, just zero it
        hr = int(60.0 / np. mean(rr_intervals)) # calculate the heartrate
        return hr

def is_rfcomm_bound(bt_addr):
    try:
        output = subprocess.check_output(['rfcomm'], text=True)
        return bt_addr in output
    except subprocess.CalledProcessError:
        return False

def cleanup(self):
    self.get_logger().info("Cleaning")
    try:
        if self.ser and self.ser.is_open:   # if it exists and is open 
            self.ser.close()                # then close it
        
        msg = f"sudo rfcomm release 0"      # and release rfcomm0
        os.system(msg)
        self.get_logger().info(msg)
    
    except Exception as e:
        self.get_logger().error(f"Cleanup error: {e}")

def main(args=None):
    rclpy.init(args=args)
    ros2_shimmer3_node = ros2_shimmer3()
    try:
        while rclpy.ok():
            pass
            rclpy.spin(ros2_shimmer3_node)
    except KeyboardInterrupt:
        self.get_logger().info('repeater stopped cleanly')
    except BaseException:
        self.get_logger().info('exception in repeater:', file=sys.stderr)
        raise
    finally:
        ros2_shimmer3_node.cleanup()
        ros2_shimmer3_node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
