# geo-pipelines

Containerized geospatial compute pipelines for bradleylab research compute
(WashU RIS Compute2, EC2). Each subdirectory is one pipeline with its own
Dockerfile, CLI, SLURM templates, and GHCR image tag.

For per-pipeline task / inputs / outputs / weights / lab-status, see
[`PIPELINE_CARDS.md`](PIPELINE_CARDS.md).

## Conventions

These rules govern what belongs in this repo and how images are built and
shipped. Adapted from the sister repo `bradleylab/ml-containers`, with one
boundary distinction: `ml-containers` holds **trained-model + inference**
images; `geo-pipelines` holds **fitting/processing pipelines** that produce
per-job products (splats, orthos, DEMs, etc.).

**One pipeline per container.** Each container holds a single processing
pipeline (video → splat, photos → ortho, lidar tile → segmented cloud, ...).
Kitchen-sink images are not allowed by default; the exception clause
requires a documented reason in the pipeline's README.

**The source recipe lives here.** Every container the lab runs must have
its `Dockerfile` (and any build-context files) committed under
`<pipeline-name>/`, with a `README.md` describing the pipeline, base image,
inputs, outputs, and run command. Ad-hoc `docker build` invocations on a
host (Compute2, EC2, Mac) without a committed recipe are not acceptable.

**GHCR is the publish target.** Push to
`ghcr.io/bradleylab/<pipeline-name>:<tag>` via the per-pipeline GitHub
Actions workflow at `.github/workflows/build-<pipeline-name>.yml`. Never
`docker push` from a laptop or compute node.

**Compute2 `.sqsh` files are caches, not source.** They are produced by
`enroot import 'docker://ghcr.io#bradleylab/<pipeline>:<tag>'` and live on
RIS storage at `/storage3/fs1/<user>/Active/c2_jobs/`. They can be deleted
whenever space is tight; the canonical recipe + image lives in this repo
+ GHCR.

**Tag scheme.** `:latest` tracks `main` and is identical to the most
recent stable `:vN`. `:v1`, `:v2`, ... are stable, immutable releases
(do not delete published tags). `:vN-<variant>` for same-base alternate
configs. `:deprecated` for images intentionally being replaced.

**What does NOT belong here.**

- **ML inference containers** (trained model + weights + entrypoint). Those
  go in `bradleylab/ml-containers`.
- **General-purpose libraries** (lidR, GDAL, PDAL alone). Use upstream
  images or install locally.
- **Notebook environments / IDE shims.** Use `rocker/geospatial`,
  `pytorch/pytorch`, or `jupyter/datascience-notebook` directly.

**Boundary test (mandatory before adding a new pipeline):** "Does this
container produce a research artifact (splat, ortho, DEM, segmented
cloud, ...) from inputs by running a documented end-to-end command?"
If yes, it's a geo-pipeline. If it instead runs inference of a named
model, it belongs in `ml-containers`. If it's just a packaged toolkit,
it belongs in an analysis repo as a uv/conda env.

## Pipelines

| GHCR image | Source dir | Inputs | Products | Status |
|------------|-----------|--------|----------|--------|
| `splat-pipeline` | [`splat-pipeline/`](splat-pipeline/) | iPhone/drone video or image dir | 3DGS `.ply` + COLMAP sparse | active (v1 in progress) |
| `geo-tools` | [`geo-tools/`](geo-tools/) | raster `.tif` or point cloud `.las`/`.laz` | COG / COPC / reprojected / hillshade | active (v1) |
| `ortho-pipeline` | — | drone image dir + GCPs | ortho `.tif` + DSM/DTM + point cloud | planned |

## Using a pipeline

Compute2 pattern (per `~/.claude/rules/research-infrastructure.md`):

```bash
# 1. One-time per pipeline version: import GHCR image to a per-host .sqsh cache
ssh pliny 'ssh c2 "
  enroot import \
    -o /storage3/fs1/alexander.s.bradley/Active/c2_jobs/bradleylab+splat-pipeline+v1.sqsh \
    'docker://ghcr.io#bradleylab/splat-pipeline:v1'
"'

# 2. Submit a job that runs the pipeline inside the container
ssh pliny 'ssh c2 "sbatch <analysis-repo>/scripts/run_clip.sbatch <args>"'
```

The analysis repo provides the data + the SLURM submit script; the
`.sqsh` cache provides the environment. The pipeline's own
`scripts/slurm/` directory in this repo holds reference templates.

## Adding a new pipeline

1. Read the boundary test above. If unsure, file an issue first.
2. `mkdir <pipeline-name>/` with `Dockerfile`, `README.md`, `bin/<pipeline-name>`, `scripts/slurm/`.
3. Add an entry to `PIPELINE_CARDS.md` and the table above.
4. Add `.github/workflows/build-<pipeline-name>.yml`.
5. PR. CI builds and pushes `:latest`; manually trigger the workflow with
   a `version_tag: vN` input or push a git tag for stable releases.
