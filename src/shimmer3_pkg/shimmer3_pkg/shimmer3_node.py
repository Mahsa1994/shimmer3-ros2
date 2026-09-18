import sys, struct, serial, os
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from scipy import signal
from scipy.signal import find_peaks
import numpy as np
import subprocess
from std_msgs.msg import Float32, Float32MultiArray, Int32
import time
syst = os.system
sys.stdout.flush()

class ros2_shimmer3(Node):
    def __init__(self):
        super().__init__('shimmer3_node')
        # Enable parameters
        self.declare_parameter('Sensor_Enable', True) # Enable to publish sensor data (true)
        self.declare_parameter('Chunk_Enable', True) # Enable to publish chunk data (true)        
        self.declare_parameter('Chunk_Length', 128) # Define the length of the chunk data
        self.declare_parameter('MAC_Addr', "74:D5:C6:52:65:C2") # Should be changed into your device name
        self.declare_parameter('Channel_Number', "6")
        self.declare_parameter('Device_Name', "/dev/rfcomm0")
        
        self.Parm_Sensor_Enable = self.get_parameter('Sensor_Enable').value 
        self.Parm_Chunk_Enable = self.get_parameter('Chunk_Enable').value 
        self.Parm_Chunk_Length = self.get_parameter('Chunk_Length').value 
        self.Parm_MAC_Addr = self.get_parameter('MAC_Addr').value 
        self.Parm_Channel_Number = self.get_parameter('Channel_Number').value
        self.Parm_Device_Name = self.get_parameter('Device_Name').value

        # Ensure the Bluetooth radio is available by running the '''$ hciconfig''' command.
        # Scan for the Shimmer by running the '''$ hcitool scan''' command.

        # Connect to Device via Bluetooth
        bt_addr = self.Parm_MAC_Addr
        print(f"bt_addr: {bt_addr}")
        print(f"Device_Name: {self.Parm_Device_Name}")
        try:
            WAIT_SEC = 2
            attempt = 0
            # FIXED 2026-09-18: this loop only caught subprocess.CalledProcessError
            # (which the `syst()`/os.system() calls never actually raise), not
            # serial.SerialException - the real, common failure when the RFCOMM
            # link is dead or refused. That exception was escaping straight to
            # the outer `except serial.SerialException` below, ending the
            # connection attempt after a SINGLE try instead of actually
            # retrying like the loop structure implies. Also now closes the
            # serial handle before retrying, so a failed attempt doesn't leave
            # the port held open and compound "multiple access on port" style
            # failures on the next try.
            while True:
                attempt += 1
                try:
                    syst("sudo rfcomm release 0") # release rfcomm0
                    syst(f"sudo rfcomm bind 0 {bt_addr} {str(self.Parm_Channel_Number)}")
                    syst(f"sudo chmod a+rw {self.Parm_Device_Name}") # (ch)ange (mod)e and let (a)ll users (r)ead or (w)rite to device
                    self.ser = serial.Serial(self.Parm_Device_Name, 115200, timeout=1) # open port
                    self.ser.write(b'\x07') # trigger data stream
                    time.sleep(WAIT_SEC)
                    data = self.ser.read(100) # read arbitrary 100B of data
                    if data:
                        print(f"{bt_addr} connection successful on channel {self.Parm_Channel_Number} and rfcomm port device {self.Parm_MAC_Addr} in container <CONTAINER_NAME>!")
                        break # if the read data exists, success!
                except (subprocess.CalledProcessError, serial.SerialException) as e:
                    print(f"Connection attempt {attempt} failed: {e}")
                    if getattr(self, 'ser', None) is not None:
                        try:
                            self.ser.close()
                        except Exception:
                            pass
                        self.ser = None
                print(f"Connection unsuccessful (attempt {attempt}), trying again")
                time.sleep(1)

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
 
        if self.Parm_Chunk_Enable:
            self.pub_shimmer3_gsr_chunk_data = self.create_publisher(Float32MultiArray, "biosensors/shimmer3_gsr/gsr_chunk", 10) 
            self.pub_shimmer3_ppg_chunk_data = self.create_publisher(Float32MultiArray, "biosensors/shimmer3_gsr/ppg_chunk", 10)
      
        # Attribute Initializations
        # Data
        self.data_index = 0
        self.gsr_data_index = 0
        self.gsr_chunk_data = []
        self.ppg_data_index = 0
        self.ppg_chunk_data = []
        self.ppg_buffer = []
        self.buffer_size = 128
        self.sample_frequency = 50.032613
        self.prominence = 100
        
        # Read Data
        while rclpy.ok() and self.Parm_Sensor_Enable:
            (shimmer_raw_GSR, Shimmer_raw_PPG) = self.reading_shimmer3_data()

            self.pub_shimmer3_gsr_data.publish(Float32(data = shimmer_raw_GSR))
            self.pub_shimmer3_ppg_data.publish(Float32(data = Shimmer_raw_PPG))

            # PPG Filter Rolling Buffer
            self.ppg_buffer.append(Shimmer_raw_PPG) # append raw data to this buffer
            if len(self.ppg_buffer) > self.buffer_size: self.ppg_buffer.pop(0) # and pop out data from beginning once length is exceeded (constant length ppg_buffer)

            # Collect samples into a chunk list
            if self.Parm_Chunk_Enable:
                self.gsr_chunk_data.append(shimmer_raw_GSR)
                self.ppg_chunk_data.append(Shimmer_raw_PPG)

                #print(self.bvp_data_index, stream_id.name, timestamp, sample) #For test
                if self.data_index  == self.Parm_Chunk_Length - 1:
                    # ppg_filtered = self.bandpass_filter(data=self.ppg_chunk_data) # Filter the chunk

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

    def cleanup(self):
        self.get_logger().info("Cleaning...")
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
    node = ros2_shimmer3()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        print('repeater stopped cleanly')
    except BaseException:
        print('exception in repeater:', file=sys.stderr)
        raise
    finally:
        node.cleanup()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
