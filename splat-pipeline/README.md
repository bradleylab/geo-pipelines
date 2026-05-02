# splat-pipeline

Containerized pipeline for producing 3D Gaussian Splat (`.ply`) scenes from
videos or image directories. SfM via COLMAP (CUDA, SuperPoint+LightGlue
front-end), training via nerfstudio's `splatfacto-big`, export to standard
3DGS `.ply`.

**GHCR image:** `ghcr.io/bradleylab/splat-pipeline:<tag>`
**Targets:** H100 (sm_90) only by default; rebuild with
`--build-arg CUDA_ARCHITECTURES="86;89;90"` for multi-arch.

## Inputs / outputs

| | |
|---|---|
| Input | Video (`.mov`, `.mp4`, `.m4v`, `.avi`, `.mkv`) OR directory of images (`.jpg`, `.png`, `.tif`) |
| Output | `<output>/processed/transforms.json`, `colmap/sparse/`, `<output>/exports/splat.ply` |

## CLI

The container's entrypoint is `splat-pipeline`:

```
splat-pipeline run     --input <video|imgdir> --output <dir>     # all 3 stages
splat-pipeline process --input <video|imgdir> --output <dir>     # SfM only
splat-pipeline train   --data <processed>     --output <dir>     # train splat
splat-pipeline export  --output-dir <train>   --export-dir <dir> # .ply
```

Forest-tuned defaults:

- `--feature-type superpoint` and `--matcher-type superpoint+lightglue`
  (SIFT fails on bark/leaf repetition)
- `--num-frames-target 300` (300–500 sweet spot; more is not better)
- `--method splatfacto-big`, `--max-num-iterations 30000`

Override any of these on the command line.

## Run on Compute2

One-time per pipeline version: import the GHCR image to a `.sqsh` cache.

```bash
ssh pliny 'ssh c2 "
  enroot import \
    -o /storage1/fs1/alexander.s.bradley/Active/c2_jobs/bradleylab+splat-pipeline+v1.sqsh \
    docker://ghcr.io#bradleylab/splat-pipeline:v1
"'
```

Then run the pipeline by submitting the templates in
[`scripts/slurm/`](scripts/slurm/), parameterized by env vars:

```bash
# Stage 1: SfM (CPU, ~3-4 hr for a 5-min iPhone clip)
sbatch --parsable --export=ALL,\
INPUT_PATH=/storage1/fs1/.../my_video.mov,\
OUTPUT_DIR=/storage1/fs1/.../processed/myplot,\
IMG_SQSH=/storage1/fs1/.../bradleylab+splat-pipeline+v1.sqsh \
  scripts/slurm/sfm.sbatch
```

Chain SfM → train → export with `--dependency=afterok:<job_id>`.

End-to-end (single job, all 3 stages):

```bash
# Use splat-pipeline run inside an sbatch wrapper — see analysis-repo
# templates for examples.
```

## Run locally (debugging)

```bash
docker pull ghcr.io/bradleylab/splat-pipeline:latest

docker run --rm --gpus all \
  -v /path/to/inputs:/inputs:ro \
  -v /path/to/outputs:/outputs \
  ghcr.io/bradleylab/splat-pipeline:latest \
  run --input /inputs/my_video.mov --output /outputs/myplot
```

Local CUDA arch must include sm_90 if using the default image. For
non-H100 dev GPUs, build a multi-arch variant:

```bash
docker build \
  --build-arg CUDA_ARCHITECTURES="86;89;90" \
  -t splat-pipeline:multiarch \
  splat-pipeline/
```

## Building

CI builds via `.github/workflows/build-splat-pipeline.yml` on:
- Push to `main` → publishes `:latest`
- Tag matching `splat-pipeline-vN` → publishes `:vN` and updates `:latest`
- Manual workflow dispatch with a `version_tag` input

Manual local build (rare; for testing before pushing):

```bash
docker build -t splat-pipeline:dev splat-pipeline/
```

## Stack

| Component | Version | Why |
|---|---|---|
| Base | `nvidia/cuda:11.8.0-devel-ubuntu22.04` | nerfstudio's tested CUDA target |
| COLMAP | 3.9.1 (built from source, CUDA) | SfM with feature-matching |
| PyTorch | 2.1.2 + cu118 | matches nerfstudio 1.1.5 reqs |
| nerfstudio | 1.1.5 | training framework + ns-process-data + ns-export |
| gsplat | tracks nerfstudio dep, recompiled for sm_90 | actual Gaussian Splatting library |
| tinycudann | latest from NVlabs | fused MLP kernels for nerfacto-family methods |
| hloc | master | SuperPoint + LightGlue |
| ffmpeg | apt | video frame extraction |

## Diagnostics

`ns-process-data` writes a log; the line that matters is COLMAP's:

```
Registered images: N / M
```

- N/M ≥ 0.9: good, proceed to training.
- 0.7 ≤ N/M < 0.9: usable but suspect — check failed frames for blur.
- N/M < 0.7: SfM is struggling — try `--matcher-type sequential+lightglue`,
  shoot more video, or accept that the input has too much wind/motion.

If training produces NaNs in the loss, almost always the cause is motion
blur or extreme exposure variation in input frames. Drop learning rate as
a first remediation:

```bash
splat-pipeline train ... \
  --pipeline.model.warmup-length 1000 \
  --optimizers.means.optimizer.lr 1e-5
```

(These flags are forwarded to `ns-train`.)

## Boundaries

This container does NOT do:

- TLS / real-world coordinate registration. Splats come out in arbitrary
  SfM coordinates; align in CloudCompare or via a separate script in the
  analysis repo.
- Mesh extraction or orthophoto generation. Use a different pipeline
  (`ortho-pipeline`, future `mesh-pipeline`) for those.
- Multi-pass appearance compositing (`splatfacto-w` for morning+evening
  passes). Train each pass separately and merge post-hoc.

## See also

- `bradleylab/ml-containers` — sister repo for inference-model containers
- Analysis repos that *use* this pipeline:
  - `tyson-splat` — Tyson forest plot splats
