#!/bin/bash
# Script to detect the platform and recommend appropriate Docker build settings

# Get system information
ARCH=$(uname -m)
OS=$(uname -s)
MEM_TOTAL=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print int($2/1024/1024)}' || echo "unknown")

if [[ "$OS" == "Darwin" ]]; then
    # MacOS - use sysctl for memory
    MEM_TOTAL=$(sysctl -n hw.memsize 2>/dev/null | awk '{print int($1/1024/1024/1024)}' || echo "unknown")
fi

# Number of CPU cores
if [[ "$OS" == "Darwin" ]]; then
    CPU_CORES=$(sysctl -n hw.ncpu)
else
    CPU_CORES=$(nproc --all 2>/dev/null || echo 2)
fi

# Cap jobs at a reasonable level
MAX_JOBS=$(( CPU_CORES > 8 ? 8 : CPU_CORES ))
RECOMMENDED_JOBS=$(( CPU_CORES > 4 ? 4 : CPU_CORES ))

echo "Platform Detection Results"
echo "=========================="
echo "Architecture: $ARCH"
echo "Operating System: $OS"
echo "CPU Cores: $CPU_CORES"
echo "RAM: ${MEM_TOTAL}GB"
echo

echo "Recommended Docker Build Settings"
echo "================================="

# Recommend settings based on architecture and memory
if [[ "$ARCH" == "arm64" || "$ARCH" == "aarch64" ]]; then
    echo "Platform: ARM64"
    echo "Dockerfile: Dockerfile.unified"
    
    if [[ "$MEM_TOTAL" == "unknown" ]]; then
        echo "Build Jobs: ${RECOMMENDED_JOBS} (estimated based on CPU cores)"
        echo "Memory Limit: Not specified (use system default)"
    elif [[ $MEM_TOTAL -lt 8 ]]; then
        echo "Build Jobs: 1 (low memory system)"
        echo "Memory Limit: ${MEM_TOTAL}g (all available)"
    elif [[ $MEM_TOTAL -lt 16 ]]; then
        echo "Build Jobs: 2"
        echo "Memory Limit: 6g"
    else
        echo "Build Jobs: ${RECOMMENDED_JOBS}"
        echo "Memory Limit: 8g"
    fi
    
    echo
    echo "Recommended command:"
    if [[ "$MEM_TOTAL" == "unknown" || $MEM_TOTAL -lt 8 ]]; then
        echo "./scripts/docker_build.sh --jobs 1"
    elif [[ $MEM_TOTAL -lt 16 ]]; then
        echo "./scripts/docker_build.sh --jobs 2 --memory 6g"
    else
        echo "./scripts/docker_build.sh --jobs ${RECOMMENDED_JOBS} --memory 8g"
    fi
    
elif [[ "$ARCH" == "x86_64" ]]; then
    echo "Platform: x86_64"
    echo "Dockerfile: Dockerfile.unified"
    
    if [[ "$MEM_TOTAL" == "unknown" ]]; then
        echo "Build Jobs: ${RECOMMENDED_JOBS} (estimated based on CPU cores)"
        echo "Memory Limit: Not specified (use system default)"
    elif [[ $MEM_TOTAL -lt 8 ]]; then
        echo "Build Jobs: 1 (low memory system)"
        echo "Memory Limit: ${MEM_TOTAL}g (all available)"
    elif [[ $MEM_TOTAL -lt 16 ]]; then
        echo "Build Jobs: 2"
        echo "Memory Limit: 6g"
    else
        echo "Build Jobs: ${RECOMMENDED_JOBS}"
        echo "Memory Limit: 8g"
    fi
    
    echo
    echo "Recommended command:"
    if [[ "$MEM_TOTAL" == "unknown" || $MEM_TOTAL -lt 8 ]]; then
        echo "./scripts/docker_build.sh --jobs 1"
    elif [[ $MEM_TOTAL -lt 16 ]]; then
        echo "./scripts/docker_build.sh --jobs 2 --memory 6g"
    else
        echo "./scripts/docker_build.sh --jobs ${RECOMMENDED_JOBS} --memory 8g"
    fi
    
else
    echo "Platform: $ARCH (unusual architecture)"
    echo "Dockerfile: Dockerfile.unified"
    echo "Build Jobs: 1 (conservative for unusual architecture)"
    echo "Memory Limit: Not specified (use system default)"
    
    echo
    echo "Recommended command:"
    echo "./scripts/docker_build.sh --jobs 1"
fi

echo
echo "Notes:"
echo "- Adjust --jobs based on your system's CPU and memory"
echo "- Higher --jobs may speed up builds but requires more memory"
echo "- If builds fail with memory errors, reduce --jobs or increase --memory"
echo "- Memory limits only apply during the build process"