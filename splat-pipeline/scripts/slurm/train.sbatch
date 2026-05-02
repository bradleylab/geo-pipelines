#!/bin/bash
# splat-pipeline training stage — Compute2 (enroot+pyxis), H100 GPU
#
# Required env vars:
#   DATA_DIR     — processed dataset dir (output of sfm.sbatch)
#   OUTPUT_DIR   — training output root (will hold experiment/ subdir)
#   IMG_SQSH     — path to .sqsh cache of splat-pipeline image
# Optional:
#   METHOD       — nerfstudio method (default: splatfacto-big)
#   MAX_ITERS    — training iterations (default: 30000)
#   EXPERIMENT   — experiment name (defaults to nerfstudio-generated)
#
# Submit with:
#   sbatch --export=ALL,DATA_DIR=...,OUTPUT_DIR=...,IMG_SQSH=... \
#          scripts/slurm/train.sbatch
#
# Chain on SfM completion:
#   SFM_JOB=$(sbatch --parsable ...sfm.sbatch)
#   sbatch --dependency=afterok:${SFM_JOB} ...train.sbatch

#SBATCH --job-name=splat-train
#SBATCH --account=compute2-alexander.s.bradley
#SBATCH --partition=general-gpu
#SBATCH --gpus=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --output=logs/train_%j.out

set -euo pipefail

: "${DATA_DIR:?required}"
: "${OUTPUT_DIR:?required}"
: "${IMG_SQSH:?required}"
: "${METHOD:=splatfacto-big}"
: "${MAX_ITERS:=30000}"
: "${EXPERIMENT:=}"

mkdir -p "${OUTPUT_DIR}" logs

DATA_PARENT=$(dirname "${DATA_DIR}")
OUTPUT_PARENT=$(dirname "${OUTPUT_DIR}")

EXP_FLAG=""
if [[ -n "${EXPERIMENT}" ]]; then
    EXP_FLAG="--experiment-name '${EXPERIMENT}'"
fi

srun \
    --container-image="${IMG_SQSH}" \
    --container-mounts="${DATA_PARENT}:${DATA_PARENT},${OUTPUT_PARENT}:${OUTPUT_PARENT}" \
    --container-workdir=/work \
    bash -lc "
        export PYTHONNOUSERSITE=1
        splat-pipeline train \
            --data '${DATA_DIR}' \
            --output '${OUTPUT_DIR}' \
            --method '${METHOD}' \
            --max-num-iterations ${MAX_ITERS} \
            ${EXP_FLAG}
    "
