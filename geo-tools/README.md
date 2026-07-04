# geo-tools

Bounded GDAL/PDAL geoprocessing recipes for bradleylab research compute. Each
recipe turns one input into one geospatial artifact via a fixed GDAL or PDAL
command built from validated arguments, dispatched by the `geo-tools` CLI.

## Kitchen-sink exception (why this is one image, not one-per-recipe)

The repo convention is **one pipeline per container**. This image is a
deliberate, documented exception: it bundles several recipes (`tiff-to-cog`,
`laz-to-copc`, `reproject`, `hillshade`, `reproject-laz`) because every one runs
on the *exact same pinned GDAL+PDAL base*. Splitting them into per-recipe
containers would multiply the build time, GHCR storage, and Compute2 `.sqsh`
cache N-fold for no functional gain — the recipes differ only by a few CLI
arguments, not by environment. Each recipe is still a single, documented,
artifact-producing command, and none accepts a free-form gdal/pdal string.

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

Arguments are validated: CRS must be an authority code (e.g. `EPSG:32615`),
compression/resampling are enums, and hillshade angles are range-checked.
Invalid values are rejected before any tool runs.

## Run

```bash
geo-tools tiff-to-cog   --input in.tif  --output out.tif --compression DEFLATE
geo-tools reproject     --input in.tif  --output out.tif --target-crs EPSG:32615
geo-tools hillshade     --input dem.tif --output hs.tif  --z-factor 1
geo-tools laz-to-copc   --input in.laz  --output out.copc.laz
geo-tools reproject-laz --input in.laz  --output out.laz --target-crs EPSG:32615
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
