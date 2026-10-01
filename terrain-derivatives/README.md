# terrain-derivatives

From one elevation model, a terrain model or a surface model: slope, aspect,
hillshade, roughness, the terrain ruggedness index (TRI) and the topographic
position index (TPI), all on one grid, and contour lines when an interval is
given, with a small PNG of the hillshade that a chat client can show inline and
a report of the settings used and the range of every output.

The image is built to entrypoint contract v1 (`docs/contracts/entrypoint-v1.md`
in `fossettlab/geospatial-executor`). The contract passes an image three
options and no task name, so this image carries one task. The design is
`docs/atlas_terrain_derivatives_spec_2026-09-26.md` in `fossettlab/atlas-agent`.

## Relation to `hillshade`

`geo-tools hillshade` writes a hillshade only, estimates values at the raster's
edges with gdaldem's `-compute_edges`, and runs no check on the input's
coordinate reference system (CRS). This image writes the hillshade with the
other derivatives on one grid, leaves every cell whose 3 × 3 window is
incomplete as nodata, and refuses an input that is not in a projected CRS in
meters.

## Base image and versions

- `mambaorg/micromamba:1.5.10`
- GDAL 3.9 from conda-forge, the same minor series as `geo-tools` and
  `ground-surfaces`. The report records the exact version a run used.

## What a run does

1. Reads band 1 of the one GeoTIFF under `<input-dir>/primary/`. A raster with
   no CRS, a geographic CRS, a horizontal unit other than the meter, or a
   rotated grid is refused, pointing at `reproject` where that applies.
   Elevations are taken to be in meters; the report says so.
2. When `resolution` is above zero, averages the model onto that cell size in
   its own CRS (`gdalwarp -r average -tap`), with the grid's edges on multiples
   of the cell size. A cell size finer than the input's is refused.
3. Computes slope, aspect, hillshade, roughness, TRI and TPI with gdaldem's
   library form, `gdal.DEMProcessing`, without `-compute_edges`: every output
   is nodata wherever its 3 × 3 window holds a nodata cell, including a
   one-cell border.
4. Shrinks the hillshade to a PNG at most 1024 pixels on its longer side, small
   enough for a chat client to show inline, by averaging, keeping its proportions
   and never enlarging it. The average skips nodata cells, so a preview pixel is transparent only
   where every hillshade cell under it is nodata. The preview is made from the
   hillshade before it becomes a Cloud-Optimized GeoTIFF, whose overviews GDAL
   would otherwise read in place of the full-resolution cells.
5. When `contour_interval` is above zero, runs `gdal_contour` on the same model
   and writes the lines to a GeoPackage.
6. Writes each raster as a Cloud-Optimized GeoTIFF, then
   `terrain_report.json`, then the manifest.

## Parameters

Contract v1 delivers every value in `params.json` as a string. The registry has
no optional number, so zero stands for "not set" for `resolution` and
`contour_interval`.

| Name | Default | Accepted | Source of the default |
|---|---|---|---|
| `resolution` | 0, the input's cells | 0–50 m | the bound is `ground_surfaces`' |
| `gradient_method` | `horn` | `horn`, `zevenbergen_thorne` | gdaldem's default (`gdaldem_lib.cpp`, GDAL 3.9.3) |
| `slope_units` | `degrees` | `degrees`, `percent` | gdaldem's default |
| `z_factor` | 1 | 0–100 | the `hillshade` registry entry |
| `azimuth` | 315 | 0–360 | the `hillshade` registry entry |
| `altitude` | 45 | 0–90 | the `hillshade` registry entry |
| `contour_interval` | 0, no contours | 0–100 m | the operator's bound |

`gradient_method` applies to slope, aspect and hillshade. TRI always uses
Riley et al.'s (1999) method, gdaldem's default since GDAL 3.3, which the image
names explicitly.

## Outputs

| File | Role | Contents |
|---|---|---|
| `slope.tif` | `slope` | steepness in degrees or percent; Float32, nodata −9999 |
| `aspect.tif` | `aspect` | the compass direction a slope faces, 0° north and 90° east; nodata −9999, also on flat cells |
| `hillshade.tif` | `hillshade` | shaded relief; 8-bit, nodata 0 |
| `hillshade_preview.png` | `preview` | the hillshade for display, averaged to at most 1024 pixels on its longer side and never enlarged; 8-bit RGBA, gray (red, green and blue all the hillshade value), transparent where the hillshade is nodata |
| `roughness.tif` | `roughness` | highest minus lowest elevation in each 3 × 3 window, in meters; nodata −9999 |
| `tri.tif` | `tri` | square root of the summed squared differences between a cell and its eight neighbors, in meters; nodata −9999 |
| `tpi.tif` | `tpi` | a cell minus the mean of its eight neighbors, in meters; nodata −9999 |
| `contours.gpkg` | `contours` | layer `contour`, attribute `elevation_m`; only when `contour_interval` is above zero |
| `terrain_report.json` | `report` | input grid, resampling, every parameter used, each raster's valid and nodata cells with its minimum, mean and maximum, the preview's file name, width and height in pixels and downsampling factor, contour count and range, the elevation-unit assumption, GDAL version |
| `run.json` | — | the contract manifest, written last, with each output's role and sha256 |

A refused run exits 2 with the reason on standard error and writes no
manifest.

## Run

```bash
# input/primary/dem.tif, and params.json such as {"contour_interval": "1"}
docker run --rm -v "$PWD:/work" ghcr.io/bradleylab/terrain-derivatives:v2 \
  --input-dir /work/input \
  --output-dir /work/output \
  --params-json /work/params.json
```

## How it is used

On Compute2 the image is imported once to a `.sqsh` cache and run by `srun`,
which names the image's entrypoint program, read from its configuration, and
then the three options. A job step carries the host's `PATH`, not the image's,
so the entrypoint, its interpreter line, and the `gdal_contour` it calls are all
absolute paths.

```bash
# One-time per version: import the GHCR image to a .sqsh cache
ssh pliny 'ssh c2 "enroot import \
  -o /storage3/fs1/alexander.s.bradley/Active/c2_jobs/bradleylab+terrain-derivatives+v2.sqsh \
  'docker://ghcr.io#bradleylab/terrain-derivatives:v2'"'
```

## Tests

`tests/smoke.py` runs inside the built image. It builds synthetic elevation
models in EPSG:32615 whose derivatives are known exactly. On a plane rising
east at a grade of 0.5, gdaldem's formulas give a slope of atan(0.5) (26.565°,
or 50%), an aspect of 270°, a roughness of twice the step between neighbors, a
TRI of √6 times that step and a TPI of zero; the test checks each, with both
gradient methods, along with the contour levels, a flat surface (zero slope,
nodata aspect), a nodata cell's 3 × 3 spread, and a resampled run's cell size
and alignment. It checks the preview against the hillshade: a 4-band 8-bit PNG
listed in the manifest with role `preview`, gray, no more than 1024 pixels on a
side, each pixel the mean of the valid hillshade cells under it and transparent
where there are none. A 2048 × 600 washboard, whose ridges make neighboring
hillshade columns differ, checks a preview shrunk by two, and the report's
record of its size. It checks five refusals: a geographic CRS, a rotated grid, a
resolution finer than the input, an unknown parameter, and a contour interval
above its bound. CI also runs the image through its own entrypoint with only
the three options and a host's `PATH` in place of the image's.

```bash
docker build -t terrain-derivatives:local terrain-derivatives
docker run --rm -v "$PWD/terrain-derivatives/tests:/tests:ro" \
  --entrypoint python terrain-derivatives:local /tests/smoke.py
```

## Reference

Riley, S. J., De Gloria, S. D., and Elliot, R. (1999). A Terrain Ruggedness
that Quantifies Topographic Heterogeneity. *Intermountain Journal of Science*,
5(1–4), 23–27. As given in gdaldem's documentation, GDAL 3.9.3.
