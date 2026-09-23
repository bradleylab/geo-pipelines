# ground-surfaces

From one lidar point cloud, three elevation rasters on one grid: a bare-ground
digital terrain model (DTM), a top-surface digital surface model (DSM), and a
canopy height model (CHM, equal to DSM − DTM), with a report of how the ground
was found and how many returns went into each surface.

The image is built to entrypoint contract v1 (`docs/contracts/entrypoint-v1.md`
in `fossettlab/geospatial-executor`). The contract passes an image three
options and no task name, so this image carries one task. The design is
`docs/atlas_ground_surfaces_spec_2026-09-22.md` in `fossettlab/atlas-agent`.

## Relation to `laz-to-dem`

`geo-tools laz-to-dem` also classifies ground with SMRF and writes a DTM and a
DSM, from two separate PDAL passes whose grids can differ in extent, and with
noise returns included in the DSM. This image adds the CHM, puts all three
rasters on one grid, keeps noise out of every surface, and can keep a file's
own ground classification instead of recomputing it.

## Base image and versions

- `mambaorg/micromamba:1.5.10`
- GDAL 3.9 and PDAL 2.8 from conda-forge, the same minor series as
  `geo-tools`. The report records the exact versions a run used.

## What a run does

1. Reads the one `.las` or `.laz` file under `<input-dir>/primary/`. A cloud
   with no CRS, a geographic CRS, or a horizontal unit other than the meter is
   refused, pointing at `reproject-laz`.
2. Leaves noise out of every surface. In a classified file, noise is ASPRS
   class 7 (low point) and class 18 (high noise), as the LAS 1.4 specification
   defines them. A file whose returns are all class 0 or 1 is passed through
   PDAL's statistical outlier filter at PDAL's defaults, and the returns it
   marks are left out instead.
3. Finds the ground. With `ground_source=classify`, every non-noise return is
   reset to unclassified and SMRF (Pingel et al. 2013) is run with the four
   SMRF parameters. With `ground_source=existing`, the file's class 2 returns
   are used as delivered; a file with none is refused.
4. Builds one grid covering every non-noise return, its edges on multiples of
   `resolution`. The three rasters share its CRS, origin, cell size and
   dimensions.
5. Grids the ground returns to the DTM by inverse-distance weighting, and takes
   the highest non-noise return inside each cell as the DSM.
6. Computes the CHM as DSM − DTM, with nodata where either surface is nodata.
   Cells where the interpolated DTM lies above the DSM keep their negative
   values; the report counts them and the manifest warns.

## Parameters

Contract v1 delivers every value in `params.json` as a string.

| Name | Default | Accepted | Source of the default |
|---|---|---|---|
| `resolution` | 1.0 m | 0.05–50 | the `laz_to_dem` registry entry |
| `ground_source` | `classify` | `classify`, `existing` | — |
| `smrf_slope` | 0.15 | ≥ 0 | PDAL 2.8.1 `filters/SMRFilter.cpp` |
| `smrf_window` | 18 | > 0 | PDAL 2.8.1: 18 × SMRF's cell size, which stays at its default of 1 |
| `smrf_threshold` | 0.5 | ≥ 0 | PDAL 2.8.1 |
| `smrf_scalar` | 1.25 | ≥ 0 | PDAL 2.8.1 |

A parameter left out of `params.json` takes the default. The image build fails
if the pinned PDAL reports different defaults for slope, scalar, threshold or
cell than the ones in this table. Upper limits on the SMRF parameters, where a
deployment wants them, belong in its registry entry.

## Outputs

| File | Role | Contents |
|---|---|---|
| `dtm.tif` | `dtm` | bare-ground elevation, Cloud-Optimized GeoTIFF, Float32, nodata −9999 |
| `dsm.tif` | `dsm` | top-surface elevation, same grid and format |
| `chm.tif` | `chm` | height above ground, same grid and format |
| `surfaces_report.json` | `report` | returns read by class; noise left out and how it was found; returns in each surface; the SMRF values used; the grid; nodata cells per raster; CHM minimum, mean, maximum and negative cells; PDAL and GDAL versions |
| `run.json` | — | the contract manifest, written last, with each output's role and sha256 |

A refused run exits 2 with the reason on standard error and writes no
manifest.

## Run

```bash
# input/primary/cloud.laz, and params.json such as {"resolution": "1.0"}
docker run --rm -v "$PWD:/work" ghcr.io/bradleylab/ground-surfaces:v2 \
  --input-dir /work/input \
  --output-dir /work/output \
  --params-json /work/params.json
```

## How it is used

On Compute2 the image is imported once to a `.sqsh` cache and run by `srun`,
which names the image's entrypoint program, read from its configuration, and
then the three options. pyxis does not hand arguments to an entrypoint through
`--container-entrypoint`, so the step names the program itself. A job step
carries the host's `PATH`, not the image's, so the entrypoint and its
interpreter line are absolute paths.

```bash
# One-time per version: import the GHCR image to a .sqsh cache
ssh pliny 'ssh c2 "enroot import \
  -o /storage3/fs1/alexander.s.bradley/Active/c2_jobs/bradleylab+ground-surfaces+v2.sqsh \
  'docker://ghcr.io#bradleylab/ground-surfaces:v2'"'
```

## Tests

`tests/smoke.py` runs inside the built image. It builds synthetic clouds in
EPSG:32615 whose surfaces are known exactly: a flat ground plane at 100 m, an
8 m block of canopy over part of it with ground returns beneath, and one
isolated return at 180 m. It checks that the DTM is the plane, that the CHM's
maximum is 8 m, that the DSM never reaches 180 m, that the three rasters share
one grid, that the manifest's checksums match, and that the report names the
SMRF values used. It runs the unclassified, classified, supplied-parameter and
existing-ground cases, and checks three refusals: a geographic CRS, an unknown
parameter, and `existing` on a file with no ground class. CI also runs the
image through its own entrypoint with only the three options and a host's
`PATH` in place of the image's, as a Compute2 job step has.

```bash
docker build -t ground-surfaces:local ground-surfaces
docker run --rm -v "$PWD/ground-surfaces/tests:/tests:ro" \
  --entrypoint python ground-surfaces:local /tests/smoke.py
```
