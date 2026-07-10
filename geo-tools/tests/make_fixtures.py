#!/usr/bin/env python3
"""Generate tiny synthetic fixtures for the geo-tools recipe smoke test.

Uses only the GDAL and PDAL Python bindings already baked into the
geo-tools image (no numpy, no network, no committed binaries). Run
inside the built image — see run_recipe_smoke.sh, which is what CI
actually invokes.

Local (non-CI) usage, with gdal + pdal python bindings on PATH:
    python make_fixtures.py --out-dir fixtures
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from osgeo import gdal, osr
import pdal

RASTER_SIZE = 8  # pixels, square
RASTER_EPSG = 4326
RASTER_ORIGIN_LON_LAT = (-90.0, 40.0)  # upper-left corner
RASTER_PIXEL_DEGREES = 0.001
RASTER_FILL_VALUE = 100

# readers.faux "ramp" mode linearly interpolates count points from the
# bounds minimum to the bounds maximum in each dimension — deterministic,
# no RNG, so the fixture is identical across CI runs.
POINTS_BOUNDS = "([0,50],[0,50],[0,20])"
POINTS_COUNT = 500


def make_raster(path: Path) -> None:
    driver = gdal.GetDriverByName("GTiff")
    dataset = driver.Create(str(path), RASTER_SIZE, RASTER_SIZE, 1, gdal.GDT_Byte)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(RASTER_EPSG)
    dataset.SetProjection(srs.ExportToWkt())
    ulx, uly = RASTER_ORIGIN_LON_LAT
    dataset.SetGeoTransform([ulx, RASTER_PIXEL_DEGREES, 0, uly, 0, -RASTER_PIXEL_DEGREES])
    band = dataset.GetRasterBand(1)
    band.Fill(RASTER_FILL_VALUE)
    band.FlushCache()
    dataset.FlushCache()
    dataset = None
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"failed to create raster fixture at {path}")


def make_points(path: Path) -> None:
    pipeline_def = {
        "pipeline": [
            {
                "type": "readers.faux",
                "bounds": POINTS_BOUNDS,
                "count": POINTS_COUNT,
                "mode": "ramp",
            },
            {
                "type": "writers.las",
                "filename": str(path),
            },
        ]
    }
    pipeline = pdal.Pipeline(json.dumps(pipeline_def))
    pipeline.execute()
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"failed to create point cloud fixture at {path}")


def main() -> None:
    default_out_dir = Path(__file__).resolve().parent / "fixtures"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=default_out_dir,
        help=f"directory for generated fixtures (default: {default_out_dir})",
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    make_raster(args.out_dir / "tiny.tif")
    make_points(args.out_dir / "tiny.las")
    print(f"fixtures written to {args.out_dir}")


if __name__ == "__main__":
    main()
