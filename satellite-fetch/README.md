# satellite-fetch

The clearest public satellite scene of a site, clipped to it: Harmonized
Landsat Sentinel-2 (HLS), Sentinel-2 L2A or Sentinel-1 RTC, from Microsoft
Planetary Computer. It supplies the input of models that take satellite imagery
the lab does not hold (Prithvi-EO, TerraMind, CROMA). For HLS and Sentinel-2 a
small false-color PNG of the scene comes with it, for a chat client to show
inline. The design is `docs/atlas_satellite_fetch_spec_2026-09-30.md` in
`fossettlab/atlas-agent`.

One task, built to the geospatial executor's entrypoint contract v1
(`fossettlab/geospatial-executor`, `docs/contracts/entrypoint-v1.md`):

```bash
satellite-fetch --input-dir <dir> --output-dir <dir> --params-json <file>
```

`satellite_fetch.cwl` describes the same task as a CWL v1.2 tool.

## What it does

1. Takes the site's footprint from the one GeoTIFF under
   `<input-dir>/primary/` (any CRS), and builds the output grid: the footprint's
   bounding box in the WGS 84 UTM zone of its center, snapped outward to whole
   cells of the product's resolution. A site longer than 25 km on a side is
   refused.
2. Searches Planetary Computer's STAC API for the product's collections over the
   footprint in the chosen year and months, and groups the items by collection,
   platform and acquisition day, so one pass across two tiles is one candidate.
3. Scores every candidate by the share of the grid its own quality layer calls
   clear:
   - HLS: `Fmask` bits 1 (cloud), 2 (adjacent to cloud or shadow) and 3 (cloud
     shadow) all unset, and not fill (HLS v2.0 user guide).
   - Sentinel-2: scene classification (`SCL`) 4 (vegetation), 5 (not
     vegetated) or 6 (water). Class 7, which ESA labels both unclassified and
     cloud of low probability, is not counted.
   - Sentinel-1: any data; radar sees through cloud.
4. Takes the highest share, the earlier date on a tie. It refuses the run only
   when no candidate holds data over the site; an all-cloud best candidate is
   still written, with its score in the report.
5. Reads each band of each item onto the grid by nearest neighbor and merges
   the items of the pass, the first item with data winning each cell.
6. For HLS and Sentinel-2, draws the false-color preview described under
   [Preview](#preview) from the merged bands in memory rather than from the
   Cloud Optimized GeoTIFF, whose overviews GDAL would otherwise read in place
   of the full-resolution cells.

Assets are read with an anonymous shared access signature from the
`planetary-computer` package, through GDAL's HTTP reader, one window at a time.

## Parameters

| Name | Values | Default |
|---|---|---|
| `product` | `hls`, `sentinel2_l2a`, `sentinel1_rtc` | `sentinel2_l2a` |
| `year` | 2015 to 2035 | required |
| `month_start`, `month_end` | 1 to 12, inclusive | 1 and 12 |

## Outputs

| File | Role | Contents |
|---|---|---|
| `imagery.tif` | `imagery` | The bands below, a Cloud Optimized GeoTIFF |
| `imagery_preview.png` | `preview` | The scene for display, an 8-bit RGBA PNG at most 1024 px on its longer side: SWIR 2, narrow NIR and red as red, green and blue, each stretched between its own 2nd and 98th percentiles, nodata transparent. HLS and Sentinel-2 only |
| `quality.tif` | `quality` | The chosen scene's `Fmask` or `SCL` on the same grid; not written for Sentinel-1 |
| `fetch_report.json` | `report` | The grid, the chosen items with their ids, times and processing baselines, the offset removed, every candidate with its clear and covered shares, the band table, the preview's file, size, downsampling factor, composite and stretch (`null` for Sentinel-1), and the versions |
| `run.json` | | The contract manifest, written last, with each output's role and sha256, and the format of the rasters and the preview |

Bands and values:

- `hls`: blue, green, red, narrow NIR, SWIR 1, SWIR 2. Sentinel-2-based scenes
  (`hls2-s30`) give B02, B03, B04, B8A, B11, B12; Landsat-based scenes
  (`hls2-l30`) give B02, B03, B04, B05, B06, B07. int16 reflectance × 10000 as
  delivered, nodata -9999, 30 m.
- `sentinel2_l2a`: B01, B02, B03, B04, B05, B06, B07, B08, B8A, B09, B11, B12,
  int16 reflectance × 10000, nodata -9999, 10 m (the 20 and 60 m bands by
  nearest neighbor). From processing baseline 04.00 (2022-01-25) ESA adds 1000
  to every value; the recipe subtracts it when the item's
  `s2:processing_baseline` is 04.00 or later, because Planetary Computer's
  metadata does not declare it.
- `sentinel1_rtc`: VV, VH, float32 gamma-naught backscatter in linear power as
  delivered, radiometrically terrain corrected, nodata NaN, 10 m.

## Preview

`imagery_preview.png` shows SWIR 2, narrow NIR and red as red, green and blue:
`swir2`, `nir_narrow` and `red` for `hls`, and B12, B8A and B04 for
`sentinel2_l2a`. In this composite burned ground and bare soil show
reddish-brown and vegetation green.

- A cell where any of the three bands is nodata is left out of everything
  below and is fully transparent; every other pixel is opaque.
- Each band is stretched linearly between its own 2nd and 98th percentiles,
  taken over the cells left in at full resolution: values at or below the 2nd
  percentile become 0 and values at or above the 98th become 255. When the two
  percentiles are equal there is no range to stretch over, so values above
  them become 255 and the rest 0.
- A grid whose longer side exceeds 1024 cells is averaged down, keeping its
  aspect ratio, until that side is 1024 pixels, and the stretch is applied to
  the averages; a pixel is transparent only where every cell under it was left
  out. A smaller grid is drawn cell for cell and never enlarged. An HLS grid,
  30 m cells at most 25 km on a side, never exceeds 1024 cells; a Sentinel-2
  grid does once the site is longer than 10.24 km on a side.

The report's `preview` block gives the `file`, `width_px`, `height_px`, the
`downsampling_factor`, the `composite` as band names in red, green, blue order,
the `stretch_percentiles` (2 and 98), and `stretch_reflectance`: each band's low
and high stretch values as reflectance, the stored value divided by 10000.

`sentinel1_rtc` gets no preview, because radar backscatter needs display
choices of its own, such as a decibel scale and how to combine the two
polarizations. Its manifest lists none and its report's `preview` is `null`.

## Run

```bash
# input/primary/site.tif, and params.json such as {"product": "hls", "year": "2024"}
docker run --rm -v "$PWD:/work" ghcr.io/bradleylab/satellite-fetch:v2 \
  --input-dir /work/input \
  --output-dir /work/output \
  --params-json /work/params.json
```

## How it is used

On Compute2 the image is imported once to a `.sqsh` cache and run by `srun`,
which names the image's entrypoint program, read from its configuration, and
then the three options. A job step carries the host's `PATH`, not the image's,
so the entrypoint and its interpreter line are absolute paths. The job needs
outbound HTTPS to Planetary Computer.

```bash
# One-time per version: import the GHCR image to a .sqsh cache
ssh pliny 'ssh c2 "enroot import \
  -o /storage3/fs1/alexander.s.bradley/Active/c2_jobs/bradleylab+satellite-fetch+v2.sqsh \
  'docker://ghcr.io#bradleylab/satellite-fetch:v2'"'
```

## Known boundaries

- **Coverage.** On Planetary Computer at the St. Louis sites, Sentinel-2-based
  HLS starts on 2020-01-01 and Landsat-based HLS on 2017-08-21; Sentinel-2 L2A
  starts in 2015.
- **Sentinel-1 account flag.** The `sentinel-1-rtc` collection says a Planetary
  Computer account is required, although anonymous reads worked when this
  image was built. If it is enforced, the signing call fails.
- **Clouds the mask misses** are not detected; the report lists every candidate
  so another date can be chosen by narrowing the months.
- **Catalog changes.** An item can be reprocessed under the same id, so a rerun
  is not guaranteed the same bytes. The report records ids.

## Stack

- Base: `mambaorg/micromamba:1.5.10`
- GDAL 3.9, as `geo-tools` and `terrain-derivatives`
- `pystac-client` 0.9.0 and `planetary-computer` 1.0.0, from conda-forge

## Tests

`tests/smoke.py` runs inside the image in CI with no network. It checks the
parameters, the grid, the clear-sky rules, the Sentinel-2 offset, the merge of
two items and the COG. It then runs the whole recipe for each product with the
catalog search and the reads replaced by synthetic scenes. For HLS and
Sentinel-2 it checks the preview against the `imagery.tif` beside it: a 4-band
8-bit PNG listed in the manifest with role `preview` and format `PNG`, drawn
cell for cell from a grid under 1024 cells, transparent exactly where any of
the three composite bands is nodata and opaque where only another band is, each
color its band stretched between the 2nd and 98th percentiles, and the report's
`preview` block. Each composite band has a patch high in it alone, and the patch
high in SWIR 2 must come out the reddest, the narrow-NIR patch the greenest and
the red-band patch the bluest. A checkered 2048 × 40 grid checks a preview
averaged 2 × 2, each pixel the mean of the valid cells under it, with the
stretch taken from the full-resolution cells. The Sentinel-1 run must write and
list no preview. CI then runs the real ENTRYPOINT on a site too large to fetch
for and expects exit status 2. The network half is exercised by the fixture run
on Compute2.

```bash
docker build -t satellite-fetch:local satellite-fetch
docker run --rm -v "$PWD/satellite-fetch/tests:/tests:ro" \
  --entrypoint python satellite-fetch:local /tests/smoke.py
```
