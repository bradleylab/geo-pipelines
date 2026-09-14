# geo-tools

Bounded GDAL/PDAL geoprocessing recipes for bradleylab research compute. Each
recipe turns one input into one geospatial artifact via a fixed GDAL or PDAL
command built from validated arguments, dispatched by the `geo-tools` CLI.

## Kitchen-sink exception (why this is one image, not one-per-recipe)

The repo convention is **one pipeline per container**. This image is a
deliberate, documented exception: it bundles several recipes (`tiff-to-cog`,
`laz-to-copc`, `reproject`, `hillshade`, `reproject-laz`, `laz-to-dem`,
`dem-of-difference`) because every one runs on the *exact same pinned GDAL+PDAL
base*. Splitting them into per-recipe containers would multiply the build time,
GHCR storage, and Compute2 `.sqsh` cache N-fold for no functional gain — the
recipes differ only by a few CLI arguments, not by environment. Each recipe is
still a single, documented, artifact-producing command, and none accepts a
free-form gdal/pdal string.

## Base image and versions

- `mambaorg/micromamba:1.5.10`
- GDAL and PDAL from conda-forge (pinned to a minor series via `--build-arg`;
  the build's smoke test prints the exact resolved versions). GDAL provides the
  COG driver and DEFLATE/ZSTD/LZW codecs; PDAL provides the COPC reader/writer
  and the reprojection filter.

## Recipes

| Recipe | Tool | Input → Output | Key args (defaults) |
|--------|------|----------------|---------------------|
| `tiff-to-cog` | `gdal_translate -of COG` | raster → Cloud-Optimized GeoTIFF | `--compression` (DEFLATE), auto overviews |
| `reproject` | `gdalwarp` | raster → reprojected raster | `--target-crs` (req), `--resampling` (bilinear) |
| `hillshade` | `gdaldem hillshade` | DEM → hillshade | `--z-factor` (1), `--azimuth` (315), `--altitude` (45) |
| `laz-to-copc` | `pdal translate` | LAS/LAZ → `.copc.laz` | (none) |
| `reproject-laz` | `pdal translate` | LAS/LAZ → reprojected LAS/LAZ | `--target-crs` (req) |
| `laz-to-dem` | `pdal translate` (SMRF) | LAS/LAZ → `dtm.tif` + `dsm.tif` | `--output-dir` (req), `--resolution` (1.0) |
| `dem-of-difference` | `gdalwarp` + GDAL/numpy | two DEMs → `dod.tif` + stats + histogram | `--after`/`--before`/`--output-dir` (req), `--threshold` (0), `--resampling` (bilinear) |

Arguments are validated: CRS must be an authority code (e.g. `EPSG:32615`),
compression/resampling are enums, and hillshade angles and DEM resolution are
range-checked. Invalid values are rejected before any tool runs.

`laz-to-dem` classifies ground with SMRF (Pingel et al. 2013) and writes two
GeoTIFFs into `--output-dir`: a bare-earth **DTM** (ground returns, ASPRS class
2, inverse-distance-weighted onto the grid) and a **DSM** (maximum Z per cell
across all returns). Both inherit the input CRS — no reprojection.

`dem-of-difference` measures how much the ground moved between two surveys of
the same place: give it the later elevation surface as `--after` and the earlier
one as `--before`, and it reports where the surface rose, where it fell, and how
much material that adds up to. Use it for a park DTM from 2024 against one from
2022, or a river reach before and after a flood.

The later surface sets the output grid; the earlier one is resampled onto it, so
the two line up cell for cell. Four files land in `--output-dir`: `dod.tif`
(elevation change per cell, later minus earlier, in meters — positive where the
surface rose), `dod_stats.json` (how many cells changed, over what area, the
mean and spread of the change, and the gained, lost, and net volumes in cubic
meters), `dod_hist.csv` (the distribution of elevation change, in 100 bins), and
`before_aligned.tif` (the resampled earlier surface, kept so the subtraction can
be checked).

`--threshold` is the smallest elevation change worth believing, in meters. Cells
that moved by no more than that are left out of the change counts and the
volumes — the usual way to keep survey noise out of a volume estimate (Wheaton
et al. 2010). It defaults to 0, which counts every changed cell. Both surfaces
must already be in a projected CRS in meters, since areas and volumes are
computed from the grid's own cell size; run `reproject` first if they are not.

## Run

```bash
geo-tools tiff-to-cog   --input in.tif  --output out.tif --compression DEFLATE
geo-tools reproject     --input in.tif  --output out.tif --target-crs EPSG:32615
geo-tools hillshade     --input dem.tif --output hs.tif  --z-factor 1
geo-tools laz-to-copc   --input in.laz  --output out.copc.laz
geo-tools reproject-laz --input in.laz  --output out.laz --target-crs EPSG:32615
geo-tools laz-to-dem    --input in.laz  --output-dir out/  --resolution 1.0
geo-tools dem-of-difference --after 2024.tif --before 2022.tif --output-dir out/ --threshold 0.1
```

## How it is used

On Compute2 the image is imported once to a per-host `.sqsh` cache and run via
`srun`. The resagent Compute2 profiles (`runtime/resagent_app/config/compute2_profiles.yaml`)
invoke `geo-tools <recipe> ...` with server-validated arguments; the Slack agent
(`@atlas`) reaches the recipes through the `submit_c2_job` dispatch op. See the
build plan `ResearchClaw_builder/docs/planning/slack_agent_c2_processing_plan_2026-07-02.md`.

```bash
# One-time per version: import the GHCR image to a .sqsh cache
ssh pliny 'ssh c2 "enroot import \
  -o /storage3/fs1/alexander.s.bradley/Active/c2_jobs/bradleylab+geo-tools+v1.sqsh \
  'docker://ghcr.io#bradleylab/geo-tools:v1'"'
```
