#!/bin/bash
# splat-pipeline SfM stage — Compute2 (enroot+pyxis)
#
# Required env vars:
#   INPUT_PATH       — video file OR directory of images
#   OUTPUT_DIR       — output dataset dir (will hold transforms.json + colmap/)
#   IMG_SQSH         — path to .sqsh cache of splat-pipeline image
# Optional:
#   FRAMES_TARGET    — frames extracted from video (default 300)
#   FEATURE_TYPE     — default: superpoint
#   MATCHER_TYPE     — default: superpoint+lightglue
#
# Submit with:
#   sbatch --export=ALL,INPUT_PATH=...,OUTPUT_DIR=...,IMG_SQSH=... \
#          scripts/slurm/sfm.sbatch

#SBATCH --job-name=splat-sfm
#SBATCH --account=compute2-alexander.s.bradley
#SBATCH --partition=general-cpu
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=06:00:00
#SBATCH --output=logs/sfm_%j.out

set -euo pipefail

: "${INPUT_PATH:?required}"
: "${OUTPUT_DIR:?required}"
: "${IMG_SQSH:?required}"
: "${FRAMES_TARGET:=300}"
: "${FEATURE_TYPE:=superpoint}"
: "${MATCHER_TYPE:=superpoint+lightglue}"

mkdir -p "${OUTPUT_DIR}" logs

# Mount the parent dirs of inputs and outputs into the container so paths
# resolve transparently. PYTHONNOUSERSITE=1 prevents host pip-user packages
# from leaking into the container env (see research-infrastructure.md).
INPUT_PARENT=$(dirname "${INPUT_PATH}")
OUTPUT_PARENT=$(dirname "${OUTPUT_DIR}")

srun \
    --container-image="${IMG_SQSH}" \
    --container-mounts="${INPUT_PARENT}:${INPUT_PARENT},${OUTPUT_PARENT}:${OUTPUT_PARENT}" \
    --container-workdir=/work \
    bash -lc "
        export PYTHONNOUSERSITE=1
        splat-pipeline process \
            --input '${INPUT_PATH}' \
            --output '${OUTPUT_DIR}' \
            --feature-type '${FEATURE_TYPE}' \
            --matcher-type '${MATCHER_TYPE}' \
            --num-frames-target ${FRAMES_TARGET}
    "
