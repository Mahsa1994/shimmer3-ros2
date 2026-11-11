# syntax=docker/dockerfile:1

#######
# Stage 1: Build
#######

FROM ros:jazzy-ros-core AS builder

USER root

# Install system dependencies and ROS 2 Cyclone DDS
RUN apt-get update && apt-get install -y --no-install-recommends \
    bluez \
    ros-jazzy-rmw-cyclonedds-cpp \
    python3-colcon-common-extensions \
    python3-venv \
    python3-vcstool \
    python3-rosdep \
    git \
    python3-matplotlib \
    python3-numpy \
    && rm -rf /var/lib/apt/lists/*

# Use Cyclone DDS consistently
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

# Initialize rosdep
RUN rosdep init || true && \
    rosdep update && \
    rosdep fix-permissions && \
    rosdep update

# Create Python virtual environment
RUN python3 -m venv /opt/venv

RUN /bin/bash -c "source /opt/venv/bin/activate && \
    python3 -m pip install --no-cache-dir \
    pyqt5 \
    'setuptools<81' \
    heartpy \
    pyserial \
    pyyaml"

# Create ROS 2 workspace
WORKDIR /shimmer3

COPY src/ src/

# Install package dependencies
RUN rosdep install \
    --from-paths src \
    --ignore-src \
    -r -y

# Build workspace
RUN /bin/bash -c "source /opt/venv/bin/activate && \
    source /opt/ros/jazzy/setup.bash && \
    colcon build --merge-install"


#######
# Stage 2: Runtime
#######

FROM ros:jazzy-ros-core

USER root

# Install runtime dependencies, including Cyclone DDS
RUN apt-get update && apt-get install -y --no-install-recommends \
    bluez \
    sudo \
    xvfb \
    python3-pip \
    python3-pyqt5 \
    ros-jazzy-rmw-cyclonedds-cpp \
    && rm -rf /var/lib/apt/lists/*

# Set ROS middleware implementation persistently
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

# Create non-root user with passwordless sudo
RUN useradd -m ros && \
    echo "ros ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

# Set workspace
WORKDIR /shimmer3

# Copy Python environment
COPY --from=builder /opt/venv /opt/venv

# Copy built ROS 2 workspace
COPY --from=builder /shimmer3/install/ /shimmer3/install/
COPY --from=builder /shimmer3/src/ /shimmer3/src/

# Ensure runtime workspace is owned by ros
RUN chown -R ros:ros /shimmer3 /opt/venv

USER ros

CMD ["bash"]
