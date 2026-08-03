# syntax=docker/dockerfile:1

#######
# Stage 1: Build
#######

FROM ros:jazzy-ros-core AS builder

# Install system-wide tools
RUN apt update && apt install -y --no-install-recommends \
    bluez \
    python3-colcon-common-extensions \
    python3-venv \
    python3-vcstool \
    python3-rosdep \
    git \
    python3-matplotlib \
    python3-numpy \
    && rm -rf /var/lib/apt/lists/*

# Set ROS middleware implementation persistently
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

# Initialize rosdep
RUN rosdep init || true && rosdep update && rosdep fix-permissions && rosdep update

# Create venv, activate, then install heartpy
RUN python3 -m venv /opt/venv
RUN /bin/bash -c "source /opt/venv/bin/activate && \
    python3 -m pip install --no-cache-dir \
    pyqt5 \
    'setuptools<81' \
    heartpy \
    pyserial \
    pyyaml"

# Create ROS2 workspace and copy src
WORKDIR /shimmer3
COPY src/ src/

# Install pkg dependencies
RUN rosdep install --from-paths src --ignore-src -r -y

# Build ws
RUN /bin/bash -c "source /opt/venv/bin/activate && \
    source /opt/ros/jazzy/setup.sh && colcon build --merge-install"

#######
# Stage 2: Runtime
#######

FROM ros:jazzy-ros-core

USER root
RUN apt update && apt install -y  --no-install-recommends \
    bluez \    
    python3-colcon-common-extensions \
    python3-pip \
    python3-pyqt5 \
    xvfb \
    && rm -rf /var/lib/apt/lists/*
RUN apt update && apt install -y sudo

# Create non-root user with no-password sudo rights 
RUN useradd -m ros && \
    echo "ros ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers
USER ros
WORKDIR /shimmer3

# Copy built artifacts from Stage 1
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /shimmer3/install/ /shimmer3/install/
COPY --from=builder /shimmer3/src /shimmer3/src/

# WORKDIR /home/ros
# RUN echo '\
# source /opt/venv/bin/activate\n\
# source /opt/ros/jazzy/setup.bash # source ROS2\n\
# sudo chown -R ros:ros /shimmer3/install /shimmer3/build /shimmer3/log\n\
# source install/setup.bash\n\
# export PS1="\[\e[38;2;13;183;237m\][CONTAINER \u@\h \w]\$ \[\e[0m\]"\n\
# ' >> /home/ros/.bashrc

CMD ["bash"]