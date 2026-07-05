# Pipeline Cards

One section per pipeline. Mirrors `bradleylab/ml-containers/MODEL_CARDS.md`.

---

## splat-pipeline

**Purpose.** Produce a 3D Gaussian Splat (`.ply`) of a scene from a video
(iPhone/drone) or a directory of images. Photogrammetry → SfM → 3DGS
training → export.

**Inputs.**
- `--input <path>` — either a video file (`.mov`, `.mp4`) or a directory
  of images (`.jpg`, `.png`). Auto-detected.

**Products.**
- `<output>/processed/transforms.json` — nerfstudio dataset format
- `<output>/processed/colmap/sparse/` — COLMAP sparse cloud + camera poses
- `<output>/exports/splat.ply` — 3D Gaussian Splat in standard 3DGS format
- `<output>/exports/screenshots/` — viewer renderings for sanity-check

**Pipeline stages** (each is a separate CLI subcommand for SLURM
chaining):

1. `process` — ffmpeg frame extract (if video) → COLMAP SfM with
   SuperPoint+LightGlue front-end → write `transforms.json`.
   CPU-heavy. ~3–4 hr for a 5-min iPhone clip on 16 cores.
2. `train` — `ns-train splatfacto-big` for 30k iterations.
   GPU-heavy. ~2 hr on H100 80 GB.
3. `export` — `ns-export gaussian-splat` to `.ply`.
   Fast (CPU-only).

`splat-pipeline run` runs all three in sequence.

**Stack.**
- Base: `nvidia/cuda:11.8.0-devel-ubuntu22.04`
- COLMAP 3.9.1 built from source with CUDA support (sm_90)
- PyTorch 2.1.2 + CUDA 11.8
- nerfstudio 1.1.5
- gsplat (compiled from source for sm_90)
- hloc (Hierarchical-Localization) for SuperPoint+LightGlue
- ffmpeg

**Targets.** H100 only (sm_90). `TORCH_CUDA_ARCH_LIST=9.0` baked in for
fast compile + small image. To target other GPUs, build a `:vN-multiarch`
variant.

**Forest-tuned defaults** (from prior CLAUDE.md guidance):
- `--num-frames-target 300` (300–500 sweet spot; more is not better)
- Feature: `superpoint`, matcher: `superpoint+lightglue`. SIFT fails on
  bark/leaf repetition.
- 30k training iterations (50k for very dense scenes).

**Known boundaries.**
- Container does NOT do TLS registration. Splat comes out in arbitrary
  SfM coordinates; alignment to TLS/real-world frame is a separate
  post-processing step in the analysis repo (CloudCompare or scripted).
- Container does NOT do mesh/orthorectification. Use `ortho-pipeline`
  for those.

**Lab status.** Active development. v1 target: forest plot splats for
TLS-anchored visualization figures.

---

## ortho-pipeline

*Planned.* Drone imagery → orthophoto + DEM via OpenDroneMap.

(Card to be filled in when the pipeline is built.)

---

## geo-tools

**Purpose.** Bounded GDAL/PDAL geoprocessing recipes: turn one input into one
geospatial artifact via a fixed, validated command. Kitchen-sink exception to
the one-pipeline-per-container rule (documented in `geo-tools/README.md`): the
recipes share the exact same GDAL+PDAL base, so bundling avoids N-fold build /
storage / `.sqsh` cost.

**Inputs.** A single raster (`.tif`) or point cloud (`.las`/`.laz`), plus
per-recipe arguments — all validated (CRS as an authority code, compression /
resampling enums, angle ranges).

**Products.** One artifact per recipe (except `laz-to-dem`, which pairs a DTM
with a DSM):
- `tiff-to-cog` → Cloud-Optimized GeoTIFF (DEFLATE default)
- `reproject` → reprojected raster
- `hillshade` → hillshade raster
- `laz-to-copc` → Cloud-Optimized Point Cloud (`.copc.laz`)
- `reproject-laz` → reprojected LAS/LAZ
- `laz-to-dem` → `dtm.tif` (SMRF-classified bare earth, IDW grid) + `dsm.tif`
  (max-Z surface) into `--output-dir`

**Run.** `geo-tools <recipe> --input <in> --output <out> [recipe args]`. No
recipe accepts a free-form gdal/pdal string; commands run as an argv list.

**Stack.**
- Base: `mambaorg/micromamba:1.5.10`
- GDAL + PDAL from conda-forge (pinned minor series; COG driver, DEFLATE/ZSTD/LZW,
  COPC reader/writer, reprojection filter)

**Known boundaries.**
- `laz-to-dem` fixes the ground-classification method to SMRF and the surfaces
  to DTM (IDW) + DSM (max-Z). PMF, first-return DSMs, and gap-fill windows are
  intentionally not exposed — add them only on a stated methods need.
- Recipes are single-input. Most are single-output; `laz-to-dem` is the one
  two-output recipe (DTM + DSM). Batch / mosaic workflows belong in an analysis
  repo.

**Lab status.** Active. v1 target: natural-language geoprocessing via `@atlas`
(the Slack agent) on Compute2.
