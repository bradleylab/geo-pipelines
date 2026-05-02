# splat-pipeline: video/photos -> 3D Gaussian Splat (.ply)
#
# COLMAP-cuda + nerfstudio + gsplat + hloc, targeted at H100 (sm_90).
# Single-arch build keeps image small and compile time manageable.
# To target other GPUs, override CUDA_ARCHITECTURES at build time.

FROM nvidia/cuda:11.8.0-devel-ubuntu22.04

ENV TZ=UTC \
    DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# H100 only by default. Override with --build-arg CUDA_ARCHITECTURES="86;89;90"
# for multi-arch builds.
ARG CUDA_ARCHITECTURES=90
ENV TORCH_CUDA_ARCH_LIST=9.0

# ----------------------------------------------------------------------
# System dependencies: COLMAP build deps, Python, ffmpeg
# ----------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake ninja-build git curl wget ca-certificates \
        ffmpeg \
        # COLMAP deps
        libatlas-base-dev libboost-filesystem-dev libboost-graph-dev \
        libboost-program-options-dev libboost-system-dev libboost-test-dev \
        libcgal-dev libeigen3-dev libflann-dev libfreeimage-dev \
        libgflags-dev libglew-dev libgoogle-glog-dev libmetis-dev \
        libqt5opengl5-dev libsqlite3-dev libsuitesparse-dev qtbase5-dev \
        libceres-dev \
        # Python
        python3.10 python3.10-dev python3-pip python-is-python3 \
    && rm -rf /var/lib/apt/lists/*

# ----------------------------------------------------------------------
# COLMAP from source with CUDA support
# ----------------------------------------------------------------------
ARG COLMAP_VERSION=3.9.1
RUN git clone https://github.com/colmap/colmap.git \
        --branch ${COLMAP_VERSION} --depth 1 /tmp/colmap \
    && mkdir /tmp/colmap/build \
    && cd /tmp/colmap/build \
    && cmake .. -GNinja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_CUDA_ARCHITECTURES="${CUDA_ARCHITECTURES}" \
    && ninja install -j "$(nproc)" \
    && rm -rf /tmp/colmap

# ----------------------------------------------------------------------
# Python: pip + PyTorch matching CUDA 11.8
# ----------------------------------------------------------------------
RUN python -m pip install --upgrade pip setuptools wheel
RUN pip install \
        torch==2.1.2 \
        torchvision==0.16.2 \
        --index-url https://download.pytorch.org/whl/cu118

# ----------------------------------------------------------------------
# tinycudann (needed by some nerfstudio methods, e.g. nerfacto)
# Compile-from-source against our CUDA + arch.
# ----------------------------------------------------------------------
RUN pip install ninja
RUN pip install \
        git+https://github.com/NVlabs/tiny-cuda-nn/#subdirectory=bindings/torch

# ----------------------------------------------------------------------
# nerfstudio (training framework + ns-process-data + ns-export)
# ----------------------------------------------------------------------
ARG NERFSTUDIO_VERSION=1.1.5
RUN pip install nerfstudio==${NERFSTUDIO_VERSION}

# ----------------------------------------------------------------------
# gsplat: force-rebuild from source so wheel matches our CUDA arch.
# nerfstudio installs a compatible pinned version; we recompile in place.
# ----------------------------------------------------------------------
RUN pip install --force-reinstall --no-binary=:all: \
        $(pip show gsplat | awk '/Name|Version/ {print $2}' | paste -sd '==' -)

# ----------------------------------------------------------------------
# hloc for SuperPoint+LightGlue front-end (forest scenes need this; SIFT
# fails on bark/leaf repetition).
# ----------------------------------------------------------------------
RUN pip install \
        git+https://github.com/cvg/Hierarchical-Localization.git@master

# ----------------------------------------------------------------------
# CLI wrapper
# ----------------------------------------------------------------------
COPY bin/splat-pipeline /usr/local/bin/splat-pipeline
RUN chmod +x /usr/local/bin/splat-pipeline

# ----------------------------------------------------------------------
# Runtime config
# ----------------------------------------------------------------------
WORKDIR /work
ENTRYPOINT ["splat-pipeline"]
CMD ["--help"]

# Image labels (OCI annotations)
LABEL org.opencontainers.image.source="https://github.com/bradleylab/geo-pipelines"
LABEL org.opencontainers.image.description="video/photos to 3D Gaussian Splat (.ply) — COLMAP + nerfstudio + gsplat, sm_90"
LABEL org.opencontainers.image.licenses="Apache-2.0"
