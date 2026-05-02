#!/bin/bash
# splat-pipeline export stage — Compute2 (enroot+pyxis), CPU
#
# Required env vars:
#   TRAIN_DIR    — training output dir (search for latest config.yml)
#   EXPORT_DIR   — where to write splat.ply
#   IMG_SQSH     — path to .sqsh cache of splat-pipeline image
#
# Optional:
#   CONFIG       — explicit path to config.yml (skips auto-detect)

#SBATCH --job-name=splat-export
#SBATCH --account=compute2-alexander.s.bradley
#SBATCH --partition=general-cpu
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=00:30:00
#SBATCH --output=logs/export_%j.out

set -euo pipefail

: "${TRAIN_DIR:?required}"
: "${EXPORT_DIR:?required}"
: "${IMG_SQSH:?required}"
: "${CONFIG:=}"

mkdir -p "${EXPORT_DIR}" logs

TRAIN_PARENT=$(dirname "${TRAIN_DIR}")
EXPORT_PARENT=$(dirname "${EXPORT_DIR}")

CONFIG_FLAG=""
if [[ -n "${CONFIG}" ]]; then
    CONFIG_FLAG="--config '${CONFIG}'"
else
    CONFIG_FLAG="--output-dir '${TRAIN_DIR}'"
fi

srun \
    --container-image="${IMG_SQSH}" \
    --container-mounts="${TRAIN_PARENT}:${TRAIN_PARENT},${EXPORT_PARENT}:${EXPORT_PARENT}" \
    --container-workdir=/work \
    bash -lc "
        export PYTHONNOUSERSITE=1
        splat-pipeline export \
            ${CONFIG_FLAG} \
            --export-dir '${EXPORT_DIR}'
    "
