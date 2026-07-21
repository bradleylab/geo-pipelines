#!/bin/bash
# ortho-pipeline — Compute2 (enroot+pyxis). One site of drone images -> ortho.
#
# Required env vars:
#   IMAGES       — directory of drone images (on RIS storage3)
#   OUTPUT_DIR   — directory for collected products (ortho/dsm/dtm/point cloud)
#   IMG_SQSH     — path to the .sqsh cache of the ortho-pipeline image
# Optional:
#   GCP          — ODM gcp_list.txt (image-pixel-marked); default: GPS EXIF only
#   RESOLUTION   — orthophoto cm/px (default: ODM auto from GSD)
#   PC_QUALITY   — ultra|high|medium|low|lowest (default medium)
#   FEATURE_QUALITY — default high
#   EXTRA        — extra flags passed through to ODM run.py
#
# Submit with:
#   sbatch --export=ALL,IMAGES=...,OUTPUT_DIR=...,IMG_SQSH=... \
#          scripts/slurm/ortho.sbatch

#SBATCH --job-name=ortho
#SBATCH --account=compute2-alexander.s.bradley
#SBATCH --partition=general-cpu
#SBATCH --cpus-per-task=32
#SBATCH --mem=128G
#SBATCH --time=12:00:00
#SBATCH --output=logs/ortho_%j.out

set -euo pipefail

: "${IMAGES:?required}"
: "${OUTPUT_DIR:?required}"
: "${IMG_SQSH:?required}"
: "${GCP:=}"
: "${RESOLUTION:=}"
: "${PC_QUALITY:=medium}"
: "${FEATURE_QUALITY:=high}"
: "${EXTRA:=}"

mkdir -p "${OUTPUT_DIR}" logs

# Mount input and output parents so paths resolve inside the container.
IMAGES_PARENT=$(dirname "${IMAGES}")
OUTPUT_PARENT=$(dirname "${OUTPUT_DIR}")
MOUNTS="${IMAGES_PARENT}:${IMAGES_PARENT},${OUTPUT_PARENT}:${OUTPUT_PARENT}"

# Build the wrapper args.
ARGS=(run --images "${IMAGES}" --output "${OUTPUT_DIR}"
      --pc-quality "${PC_QUALITY}" --feature-quality "${FEATURE_QUALITY}"
      --max-concurrency "${SLURM_CPUS_PER_TASK}")
[[ -n "${RESOLUTION}" ]] && ARGS+=(--resolution "${RESOLUTION}")
if [[ -n "${GCP}" ]]; then
    GCP_PARENT=$(dirname "${GCP}")
    MOUNTS="${MOUNTS},${GCP_PARENT}:${GCP_PARENT}"
    ARGS+=(--gcp "${GCP}")
fi
[[ -n "${EXTRA}" ]] && ARGS+=(--extra "${EXTRA}")

srun \
    --container-image="${IMG_SQSH}" \
    --container-mounts="${MOUNTS}" \
    --container-workdir=/work \
    ortho-pipeline "${ARGS[@]}"
