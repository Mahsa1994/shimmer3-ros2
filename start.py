#!/usr/bin/env python3

import os
import subprocess
import sys
import time
import serial
import glob

BT_ADDR = "74:D5:C6:52:65:C2"
DEVICE_NODE = "/dev/rfcomm0"
CHANNEL = 6
CONTAINER_NAME = "shimmer3"
WAIT_SEC = 2
syst = os.system

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def find_serial_device():
    """Automatically find the USB serial device (ttyACM* or ttyUSB*)"""
    # Look for ACM devices (common for Bluegiga/Shimmer)
    devices = glob.glob('/dev/ttyACM*')
    # If none, look for USB devices
    if not devices:
        devices = glob.glob('/dev/ttyUSB*')

    if devices:
        print(f"--> Found serial device: {devices[0]}")
        return devices[0]
    else:
        print("Error: No /dev/ttyACM* or /dev/ttyUSB* device found!")
        print("Please check if your USB dongle is plugged in.")
        sys.exit(1)

def bind_connect_shimmer3():
    # FIXED 2026-09-18 (three bugs found live-debugging a stuck connection):
    # 1. Used to skip straight to the Docker stage if /dev/rfcomm0 merely
    #    EXISTED, without verifying it was actually a live connection - a
    #    stale device node (e.g. left over from a previous failed attempt)
    #    looked identical to a working one and got trusted outright. Now
    #    always does a fresh release+bind+read-verify cycle, every call.
    # 2. Only caught subprocess.CalledProcessError, which `run()`'s plain
    #    subprocess.run() (no check=True) never actually raises anyway - a
    #    real serial.SerialException from a dead connection (the actual
    #    common failure mode) went uncaught and crashed the whole script.
    # 3. No bound on retries, and no cleanup of the serial handle between
    #    failed attempts - could leak a held-open port across retries,
    #    compounding "multiple access on port" style failures.
    MAX_ATTEMPTS = 5
    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"Connecting to {BT_ADDR} (attempt {attempt}/{MAX_ATTEMPTS})...")
        ser = None
        try:
            run("sudo rfcomm release 0")
            run(f"sudo rfcomm bind 0 {BT_ADDR} {str(CHANNEL)}")
            run(f"sudo chmod a+rw {DEVICE_NODE}")
            ser = serial.Serial(DEVICE_NODE, 115200, timeout=1)
            ser.write(b'\x07')
            time.sleep(WAIT_SEC)
            data = ser.read(100)
            if data:
                print(f"Bluetooth: {BT_ADDR} connection outside of '{CONTAINER_NAME}' container successful!")
                ser.close()
                return
        except (subprocess.CalledProcessError, serial.SerialException) as e:
            print(f"Connection attempt {attempt} failed: {e}")
        finally:
            if ser is not None and ser.is_open:
                ser.close()
        print("Connection unsuccessful, trying again")
        time.sleep(1)

    print(f"ERROR: could not establish a Bluetooth connection to {BT_ADDR} "
          f"after {MAX_ATTEMPTS} attempts. Check the sensor is powered on, "
          f"in range, and not already connected elsewhere "
          f"(try: bluetoothctl info {BT_ADDR}) before retrying.")
    sys.exit(1)

def build_run():
    # 1. Find the actual device name (e.g., /dev/ttyACM0 or /dev/ttyACM1)
    host_device = find_serial_device()

    syst("xhost +local:")
    run_output = subprocess.run('docker ps -a --format "{{.Names}}"', shell=True, capture_output=True, check=True, text=True)

    container_exists = False
    if run_output and run_output.stdout:
        container_names = run_output.stdout.splitlines()
        if CONTAINER_NAME in container_names:
            container_exists = True

    if container_exists:
        print(f"'{CONTAINER_NAME}' container already exists. Starting now...")
        syst(f"docker start {CONTAINER_NAME}")
        syst(f"docker exec -it -e DISPLAY=$DISPLAY {CONTAINER_NAME} bash")
    else:
        print(f"{CONTAINER_NAME} container does not exist yet. Building and running now...")
        syst(f"docker build -t {CONTAINER_NAME}:jazzy .")

        # 2. Construct command with AUTO-DETECTED device and HOST NETWORKING
        docker_cmd = f"""docker run -it \
            --name {CONTAINER_NAME} \
            --net=host \
            --ipc=host \
            --pid=host \
            --cap-add=NET_ADMIN \
            --device /dev/rfkill \
            --device {host_device}:/dev/ttyUSB0 \
            --device {DEVICE_NODE} \
            -v $(pwd)/src:/shimmer3/src \
            -v /tmp/.X11-unix:/tmp/.X11-unix \
            -e DISPLAY=$DISPLAY \
            {CONTAINER_NAME}:jazzy \
            bash -c "source /opt/venv/bin/activate && \
                    source /opt/ros/jazzy/setup.bash && \
                    source /shimmer3/install/setup.bash && \
                    export PS1='[\\[\\e[38;2;13;183;237m\\]][CONTAINER \\u@\\h \\w]\\$ [\\[\\e[0m\\]]' && \
                    exec bash -i"
            """

        syst(docker_cmd)

if __name__ == "__main__":
    # NOTE: previously did an unconditional `docker rm -f` here "to ensure
    # new settings (network + device) are applied" - but that made
    # build_run()'s own container_exists reuse logic dead code, forcing a
    # full rebuild+recreate every run. Removed so the container (and
    # anything built inside it, e.g. session state) persists across runs.
    # If you deliberately change docker_cmd's flags/devices in build_run()
    # and need them to actually take effect, manually run
    # `docker rm -f shimmer3` once yourself before the next start.py run -
    # reusing an existing container does NOT pick up new docker run flags.
    bind_connect_shimmer3()
    build_run()
