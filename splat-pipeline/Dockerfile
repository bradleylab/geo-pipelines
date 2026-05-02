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
#
# Three different env vars feed into the build because each subsystem reads
# its own:
#   - CMAKE_CUDA_ARCHITECTURES (cmake/COLMAP) — semicolon-separated SM nums (90)
#   - TORCH_CUDA_ARCH_LIST (PyTorch + gsplat) — semicolon-separated SM versions (9.0)
#   - TCNN_CUDA_ARCHITECTURES (tinycudann) — semicolon-separated SM nums (90)
# tcnn falls back to runtime CUDA introspection if unset, which fails on
# GHA runners with no GPU. Explicit setting is mandatory here.
ARG CUDA_ARCHITECTURES=90
ENV TORCH_CUDA_ARCH_LIST=9.0
ENV TCNN_CUDA_ARCHITECTURES=${CUDA_ARCHITECTURES}

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

# Pin numpy<2: torch 2.1.2 + nerfstudio 1.1.x stack predates numpy 2.x ABI.
# Without this, the torch wheel pulls numpy 2.2 transitively and downstream
# extensions (nerfstudio, hloc) compile against the old API. Lock to 1.x.
RUN pip install "numpy<2"

RUN pip install \
        torch==2.1.2 \
        torchvision==0.16.2 \
        --index-url https://download.pytorch.org/whl/cu118

# ----------------------------------------------------------------------
# tinycudann (needed by some nerfstudio methods, e.g. nerfacto)
# Compile-from-source against our CUDA + arch.
#
# --no-build-isolation: tcnn's setup.py imports pkg_resources but doesn't
# declare setuptools as a PEP 517 build-dep, so pip's isolated build env
# omits it and the install errors with "No module named 'pkg_resources'".
# Using the host env (which has setuptools) avoids this.
# ----------------------------------------------------------------------
RUN pip install ninja
RUN pip install --no-build-isolation \
        git+https://github.com/NVlabs/tiny-cuda-nn/#subdirectory=bindings/torch

# ----------------------------------------------------------------------
# nerfstudio (training framework + ns-process-data + ns-export)
# ----------------------------------------------------------------------
ARG NERFSTUDIO_VERSION=1.1.5
RUN pip install nerfstudio==${NERFSTUDIO_VERSION}

# Re-pin numpy<2 in case nerfstudio's deps bumped it.
RUN pip install "numpy<2"

# ----------------------------------------------------------------------
# gsplat: force-rebuild from source so wheel matches our CUDA arch.
# nerfstudio installs a compatible pinned version; we recompile in place.
# --no-deps: don't touch its dependencies (we already have the right torch).
# --no-binary gsplat: only force source build for gsplat itself.
# --no-build-isolation: same reason as tcnn — gsplat's setup.py imports
# torch, which isn't in the build-isolation env. Use the host env where
# torch is actually installed.
# ----------------------------------------------------------------------
RUN GSPLAT_VERSION=$(pip show gsplat | awk '/^Version:/ {print $2}') \
    && echo "rebuilding gsplat ${GSPLAT_VERSION} for sm_90" \
    && pip install --no-deps --force-reinstall --no-binary=gsplat \
        --no-build-isolation \
        "gsplat==${GSPLAT_VERSION}"

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
