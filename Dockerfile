FROM ubuntu:20.04

# Set noninteractive installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    bzip2 \
    ca-certificates \
    curl \
    git \
    build-essential \
    cmake \
    autoconf \
    libtool \
    pkg-config \
    libgoogle-glog-dev \
    python3.8 \
    python3.8-dev \
    python3-pip \
    software-properties-common && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install GCC 9.4 to match the version in requirements
RUN apt-get update && \
    apt-get install -y gcc-9 g++-9 && \
    update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-9 90 && \
    update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-9 90 && \
    update-alternatives --install /usr/bin/cc cc /usr/bin/gcc-9 90 && \
    update-alternatives --install /usr/bin/c++ c++ /usr/bin/g++-9 90 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set up Python 3.8 as the default
RUN ln -sf /usr/bin/python3.8 /usr/bin/python && \
    ln -sf /usr/bin/pip3 /usr/bin/pip && \
    python -m pip install --upgrade pip setuptools wheel

# Install pybind11 and other required packages
RUN apt-get update && \
    apt-get install -y python3-dev pybind11-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Build protobuf 3.19.1 from source (exact version required)
RUN apt-get update && apt-get install -y git autoconf automake libtool curl unzip && \
    git clone https://github.com/protocolbuffers/protobuf.git /tmp/protobuf && \
    cd /tmp/protobuf && \
    git checkout v3.19.1 && \
    ./autogen.sh && \
    ./configure && \
    make -j2 && \
    make install && \
    ldconfig && \
    cd / && \
    rm -rf /tmp/protobuf && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Python protobuf package with matching version
RUN pip install protobuf==3.19.1

# Set working directory
WORKDIR /app

# Copy the entire repository
COPY . /app/

# Compile protobuf files
RUN make protos_basic

# Install Python dependencies
RUN pip install pybind11 numpy==1.20.3 torch==1.10.0 cython==0.29.24

# Fix directory structure for dipcc (nested directories)
RUN mkdir -p /app/dipcc/cc /app/dipcc/pybind && \
    cp -r /app/dipcc/dipcc/cc/* /app/dipcc/cc/ && \
    cp -r /app/dipcc/dipcc/pybind/* /app/dipcc/pybind/ && \
    cp -r /app/dipcc/dipcc/profiling /app/dipcc/

# Build dipcc with 2 jobs to avoid memory issues
RUN cd /app/dipcc && \
    pybind11_DIR=$(python3 -c "import pybind11; print(pybind11.get_cmake_dir())") && \
    mkdir -p build && cd build && \
    cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=$pybind11_DIR .. && \
    make -j2 pydipcc && \
    cp dipcc/python/pydipcc*.so /app/fairdiplomacy/ && \
    echo "Built pydipcc module successfully"

# Configure fairdiplomacy to import pydipcc
RUN echo '#!/usr/bin/env python' > /app/fairdiplomacy/__init__.py && \
    echo 'import sys, os' >> /app/fairdiplomacy/__init__.py && \
    echo 'import importlib.util' >> /app/fairdiplomacy/__init__.py && \
    echo '' >> /app/fairdiplomacy/__init__.py && \
    echo '# Make the pydipcc module in this directory available' >> /app/fairdiplomacy/__init__.py && \
    echo 'spec = importlib.util.spec_from_file_location("pydipcc", os.path.join(os.path.dirname(__file__), "pydipcc.cpython-38-aarch64-linux-gnu.so"))' >> /app/fairdiplomacy/__init__.py && \
    echo 'if spec:' >> /app/fairdiplomacy/__init__.py && \
    echo '    pydipcc = importlib.util.module_from_spec(spec)' >> /app/fairdiplomacy/__init__.py && \
    echo '    spec.loader.exec_module(pydipcc)' >> /app/fairdiplomacy/__init__.py && \
    echo '    sys.modules["fairdiplomacy.pydipcc"] = pydipcc' >> /app/fairdiplomacy/__init__.py && \
    echo 'else:' >> /app/fairdiplomacy/__init__.py && \
    echo '    print("Could not find pydipcc module")' >> /app/fairdiplomacy/__init__.py

# Add the test script
RUN echo '#!/usr/bin/env python' > /app/test_pydipcc.py && \
    echo 'import sys; sys.path.insert(0, "/app")' >> /app/test_pydipcc.py && \
    echo 'try:' >> /app/test_pydipcc.py && \
    echo '    from fairdiplomacy import pydipcc' >> /app/test_pydipcc.py && \
    echo '    print("pydipcc imported successfully")' >> /app/test_pydipcc.py && \
    echo '    game = pydipcc.Game()' >> /app/test_pydipcc.py && \
    echo '    print("Game created successfully")' >> /app/test_pydipcc.py && \
    echo '    print("Current phase:", game.get_current_phase())' >> /app/test_pydipcc.py && \
    echo '    print("Available methods:", [m for m in dir(game) if not m.startswith("_")])' >> /app/test_pydipcc.py && \
    echo 'except Exception as e:' >> /app/test_pydipcc.py && \
    echo '    print(f"Error: {e}")' >> /app/test_pydipcc.py && \
    chmod +x /app/test_pydipcc.py

# Default command
CMD ["/bin/bash"]