# ortho-pipeline

Containerized pipeline for producing a georeferenced **orthophoto** (plus DSM,
DTM, and dense point cloud) from a directory of overlapping drone images, via
[OpenDroneMap](https://www.opendronemap.org/). Thin wrapper over the official
`opendronemap/odm` image with an `ortho-pipeline` CLI and Compute2 SLURM
templates.

**GHCR image:** `ghcr.io/bradleylab/ortho-pipeline:<tag>`
**Base:** `opendronemap/odm:3.5.6` (CPU; no GPU required)

## Inputs / outputs

| | |
|---|---|
| Input | Directory of overlapping images (`.jpg`, `.png`, `.tif`); optional ODM `gcp_list.txt` |
| Output | `orthophoto.cog.tif`, `dsm.cog.tif`, `dtm.cog.tif` (all Cloud-Optimized GeoTIFF), `point_cloud.laz`, `report.pdf` |

## Georeferencing

- **With GCPs** — pass `--gcp gcp_list.txt` (ODM format: a projection line then
  `geo_x geo_y geo_z im_x im_y image_name` rows, each ground control point marked
  in ≥3 images). Survey-grade absolute accuracy. Producing this file requires
  marking the GCPs in the images (WebODM's GCP tool, or POSM GCP interface) —
  world coordinates alone are not enough.
- **Without GCPs** — georeferencing comes from the images' onboard GPS EXIF,
  ~1–3 m absolute accuracy. Adequate for planform / change-extent orthophotos.

## CLI

The container entrypoint is `ortho-pipeline`:

```
ortho-pipeline run --images <dir> --output <dir> \
    [--gcp <gcp_list.txt>] [--resolution CM_PER_PX] \
    [--pc-quality medium] [--feature-quality high] \
    [--no-dsm] [--no-dtm] [--extra "<ODM flags>"]
```

Defaults: `--dsm --dtm`, `--pc-quality medium`, `--feature-quality high`, COG
outputs, `--auto-boundary`, orthophoto resolution auto from GSD. Products are
collected into `<output>/` with flat names. Anything not exposed as a flag can
be forwarded to ODM's `run.py` via `--extra`.

## Run on Compute2

One-time per version: import the GHCR image to a `.sqsh` cache.

```bash
ssh pliny 'ssh c2 "
  enroot import \
    -o /storage3/fs1/alexander.s.bradley/Active/c2_jobs/bradleylab+ortho-pipeline+v1.sqsh \
    docker://ghcr.io#bradleylab/ortho-pipeline:v1
"'
```

Then submit one job per site (images must be on RIS storage3, the zero-transfer
pliny↔C2 share):

```bash
sbatch --parsable --export=ALL,\
IMAGES=/storage3/fs1/.../site/images,\
OUTPUT_DIR=/storage3/fs1/.../site/ortho,\
IMG_SQSH=/storage3/fs1/.../bradleylab+ortho-pipeline+v1.sqsh \
  scripts/slurm/ortho.sbatch
```

Optional env vars: `GCP`, `RESOLUTION`, `PC_QUALITY`, `FEATURE_QUALITY`, `EXTRA`.
ODM is CPU-only here; the template requests `general-cpu`, 32 cores, 128 GB, 12 h.

## Run locally (debugging)

```bash
docker run --rm \
  -v /path/to/images:/inputs:ro \
  -v /path/to/out:/outputs \
  ghcr.io/bradleylab/ortho-pipeline:latest \
  run --images /inputs --output /outputs
```

## Building

CI builds via `.github/workflows/build-ortho-pipeline.yml` on push to `main`
(→ `:latest`), tag `ortho-pipeline-vN` (→ `:vN` + `:latest`), or manual dispatch.

## Diagnostics

ODM writes `report.pdf` (collected to the output dir) and a full log under the
project's `odm_report/`. If the orthophoto has holes or the reconstruction is
partial, the usual causes are insufficient overlap (aim for ≥70% front / 60%
side), motion blur, or too-uniform terrain (water, dense canopy). Raising
`--feature-quality ultra` and `--pc-quality high` helps at a compute cost.

## Boundaries

This container does NOT do:

- GCP image-marking. Provide a ready `gcp_list.txt`; this pipeline consumes it,
  it does not create it.
- 3D Gaussian splats or NeRF (use `splat-pipeline`).
- Multispectral index products or radiometric calibration.

## See also

- `splat-pipeline` — 3DGS from the same kind of image/video input
- `geo-tools` — COG/COPC/reproject/hillshade post-processing of these outputs
