# ROS2 Shimmer3 PPG HR 

# Future Improvements
- Move on from obsolete BlueZ rfcomm in `bluez-obsolete-utils` to `bluetoothctl`
- Better source the Docker environment, incorporating commands into the DockerFile instead of copy-pasting into each new terminal.
- Get `matplooter_node.py` up and running (currently incomplete and inactive). Launch parameter `liveplot` currently defaults to false and the window does not appear.
- Appears to be a non fatal error `[shimmer3_node-1] Can't open RFCOMM control socket: Address family not supported by protocol`
- `matplotter_node.py` reuses the same global variable as `bpm_detector` but is hardcoded, which is not clean, and prevents efficiently changing `live_bpm` publishing rate
- `live_bpm` takes between 10 and 30s seconds from startup to publish non-zero data.

# Troubleshooting
- The device node `/dev/rfcomm0` will not be detected if `shimmer3_node` is running. Attempting to run `start.py` in another terminal will end the ongoing process, but not stop the node from spinning.
- If `start.py` does not connect to Bluetooth device, try opening a second terminal and running.
    ```
    bluetoothctl
    scan on
    ```
- If launching returns this error, `[ERROR] [1759514528.907245939] [shimmer3_node]: Could not open serial port [Errno 6] could not open port /dev/rfcomm0: [Errno 6] No such device or address: '/dev/rfcomm0'`, double check
    ```
    ls -l /dev/rfcomm0*
    ```

# Basic Code Structure
`start.py`
- Tests Bluetooth connection (skips rebinding if `/dev/rfcomm0` already exists)
- Auto-detects the USB serial device (`/dev/ttyACM*`, falling back to `/dev/ttyUSB*`)
- Removes any existing `shimmer3` container, then builds and runs a fresh one with host networking (`--net=host`, `--ipc=host`, `--pid=host`) and the detected devices attached. You are now inside the container.

`shimmer3.launch.py`
- Configures launch parameters and other default constants 
- Defines and spins (and eventually destroys on shutdown) nodes:
  -  `shimmer3_node`
      - Connects to Bluetooth
      - Streams and publishes shimmer3 data as singles or chunks 
  -  `bpm_detector_node`
      - Subscribes to  `shimmer3_node`'s `biosensors/shimmer3_gsr/ppg` topic for live ppg data.
      - Uses `heartpy`'s machine learning models to clean data and determine peaks from a rolling buffer.
      - Calculates bpm from peaklist, providing some cleaning using reasonable upper limits and sample-to-sample heartrate variability (e.g, its unreasonable for two samples 1/50th of a second apart to register heartrates as wide apart as 20bpm) 
      - Publishes heartrate as a single `live_bpm` and rolling buffer `bpm_buffer` for plotting. 
  -  `matplotter_node`
      - Subscribes to `bpm_detector_node`'s `bpm_buffer` and outputs a window
      - Can be toggled via launch parameter, on by default. 

# Requirements
- Bluetooth capability (dongle?)
- Install python libraries:
  ```bash
  $ pip3 install open-e4-client pexpect websocket-client
  ```

# Installation
```bash
cd 
git clone --branch main https://github.com/SMARTlab-Purdue/ros2-foxy-wearable-biosensors.git shimmer3
```

# Usage

The first time connecting Shimmer3 device to your computer, you will need to enter the device's pairing code, which is, according to the Shimmer User Manual, by default, `1234`. <br>
This will cause the device to temporarily connect to your computer via Bluetooth then disconnect, signalling it is ready to run.

*Determine RFCOMM channel*

In our case, it is `6`
```
bluetoothctl
sdptool browse <MAC-ADDRESS>
```

*Establish Bluetooth Connection, and build and run Docker Container*

The Dcont is built including `-v $(pwd)/src:/shimmer3/src \`, mounting the `src` folder on the host's computer to the Dcont's running `src` folder, so any edits made to files in that folder (packages) will be reflected and updated.

Every run of `start.py` removes any existing `shimmer3` container and starts a fresh one, so only changes under `src/` persist between runs.
```
python3 start.py
```

*Virtual Environment, Build and Source etc.* 

Copy paste this into the bash after running `python3 start.py`. <br>
(There is probably a better and simple way to incorporate this into the Dockerfile, but I was not able to work it out successfully:'))
```
source /opt/venv/bin/activate # source virtual environment
source /opt/ros/jazzy/setup.bash # source ROS2
sudo chown -R ros:ros /shimmer3/install /shimmer3/build /shimmer3/log
colcon build --merge-install && source install/setup.bash
source /shimmer3/install/setup.bash # source workspace
export PS1="\[\e[38;2;13;183;237m\][CONTAINER \u@\h \w]\$ \[\e[0m\]" # recolor the container prompt to Docker blue for convenience and ✨aeshetic✨
```

*Launch Package*

The above commands do not launch the shimmer3 package. You can do this manually from within the container.

```
ros2 launch shimmer3_pkg shimmer3.launch.py # launch file
```
Launch Parameters:<br>
`ppg_buffer_length`: PPG buffer length with which BPM is found. The smaller, the less filtering, and the more noise.<br>
`hrv_limit`: Maximum plausible change in heart rate between successive beats<br>
`liveplot`: Toggles Matplot window.  Default on.

*To stop and remove ALL containers*
```
deactivate # venv
sudo docker stop $(sudo docker ps -q)
sudo docker rm $(sudo docker ps -a -q)
```
