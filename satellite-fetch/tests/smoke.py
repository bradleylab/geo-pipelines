#!/usr/bin/env python3
"""Offline smoke test for satellite-fetch, run inside the built image.

The recipe's network half (the catalog search and the reads) needs Planetary
Computer and is exercised by the fixture run on Compute2. This test covers the
rest with synthetic inputs whose answers are known: parameter checks, the output
grid, the clear-sky rules for each quality layer, the Sentinel-2 offset, how
items of one pass are merged, and the COG written. ``--fixtures-only DIR`` writes
a site too large to fetch for, so CI can run the image's real ENTRYPOINT and see
it refuse before any network call.
"""

from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from types import ModuleType

import numpy as np
from osgeo import gdal, osr

gdal.UseExceptions()

PROGRAM_PATHS = (
    Path("/usr/local/bin/satellite-fetch"),
    Path(__file__).resolve().parents[1] / "bin" / "satellite-fetch",
)
EPSG = 32615  # UTM 15N: the St. Louis sites
ORIGIN = (736000.0, 4276000.0)  # top-left corner
SITE_SIDE_M = 2000.0
TOO_LARGE_SIDE_M = 30_000.0


def load_program() -> ModuleType:
    path = next(p for p in PROGRAM_PATHS if p.exists())
    loader = importlib.machinery.SourceFileLoader("satellite_fetch", str(path))
    spec = importlib.util.spec_from_loader("satellite_fetch", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules["satellite_fetch"] = module
    loader.exec_module(module)
    return module


def write_site(path: Path, side_m: float, epsg: int | None = EPSG, origin=ORIGIN) -> None:
    """A one-band GeoTIFF of side_m on a side, 100 cells across."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cells = 100
    dataset = gdal.GetDriverByName("GTiff").Create(str(path), cells, cells, 1, gdal.GDT_Byte)
    dataset.SetGeoTransform((origin[0], side_m / cells, 0.0, origin[1], 0.0, -side_m / cells))
    if epsg is not None:
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(epsg)
        dataset.SetProjection(srs.ExportToWkt())
    dataset.GetRasterBand(1).Fill(1)
    dataset.FlushCache()


def corner_lonlat(side_m: float) -> tuple[float, float, float, float]:
    """The site's corners in lon/lat, by a separate transform: west, south, east, north."""
    utm, wgs84 = osr.SpatialReference(), osr.SpatialReference()
    utm.ImportFromEPSG(EPSG)
    wgs84.ImportFromEPSG(4326)
    for srs in (utm, wgs84):
        srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    transform = osr.CoordinateTransformation(utm, wgs84)
    x0, y0 = ORIGIN
    corners = [(x0, y0), (x0 + side_m, y0), (x0, y0 - side_m), (x0 + side_m, y0 - side_m)]
    lonlat = np.array([transform.TransformPoint(x, y)[:2] for x, y in corners])
    return (*lonlat.min(axis=0), *lonlat.max(axis=0))


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"ok  {message}")


def refused(program: ModuleType, call) -> str:
    try:
        call()
    except program.Refused as exc:
        return str(exc)
    raise AssertionError("expected a refusal")


def test_params(program: ModuleType, work: Path) -> None:
    def params(values: dict) -> object:
        path = work / "params.json"
        path.write_text(json.dumps(values))
        return program.read_params(path)

    got = params({"year": "2025"})
    check(
        (got.product, got.year, got.month_start, got.month_end) == ("sentinel2_l2a", 2025, 1, 12),
        "defaults: Sentinel-2 L2A, the whole year",
    )
    for values, fragment in (
        ({}, "year is required"),
        ({"year": "2014"}, "2015-2035"),
        ({"year": "2025.5"}, "whole number"),
        ({"year": "2025", "product": "landsat"}, "product must be one of"),
        ({"year": "2025", "month_start": "9", "month_end": "3"}, "comes after"),
        ({"year": "2025", "window": "1"}, "unknown parameters"),
    ):
        message = refused(program, lambda values=values: params(values))
        check(fragment in message, f"refused {values}: {fragment}")


def test_grid(program: ModuleType, work: Path) -> None:
    site = work / "grid" / "site.tif"
    write_site(site, SITE_SIDE_M)
    grid = program.site_grid(site, 10.0)
    check(grid.epsg == EPSG, "a site in UTM 15N keeps zone 15")
    check(all(value % 10.0 == 0 for value in grid.bounds), "bounds snap to whole 10 m cells")
    check((grid.width, grid.height) == (200, 200), "a 2 km site is 200 x 200 cells of 10 m")
    check(
        np.allclose(grid.footprint_wgs84, corner_lonlat(SITE_SIDE_M), atol=1e-6),
        "footprint in lon/lat matches the corners carried directly",
    )

    lonlat = work / "grid" / "lonlat.tif"
    write_site(lonlat, 0.02, epsg=4326, origin=(-90.31, 38.66))
    check(program.site_grid(lonlat, 30.0).epsg == 32615, "a lon/lat site gets its center's zone")
    south_site = work / "grid" / "south.tif"
    write_site(south_site, 0.02, epsg=4326, origin=(147.30, -42.88))
    check(program.site_grid(south_site, 30.0).epsg == 32755, "a southern site gets a 327xx zone")

    large = work / "grid" / "large.tif"
    write_site(large, TOO_LARGE_SIDE_M)
    message = refused(program, lambda: program.site_grid(large, 10.0))
    check("25 km" in message, "a 30 km site is refused")
    bare = work / "grid" / "bare.tif"
    write_site(bare, SITE_SIDE_M, epsg=None)
    check("no CRS" in refused(program, lambda: program.site_grid(bare, 10.0)), "no CRS refused")


def test_clear_rules(program: ModuleType) -> None:
    hls = program.PRODUCTS["hls"]
    # 0 clear; bit 1 cloud; bit 2 adjacent; bit 3 shadow; bits 6-7 aerosol only; fill
    fmask = np.array([0, 2, 4, 8, 64 + 128, 255], dtype=np.uint8)
    clear, covered = program.clear_and_covered(hls, fmask)
    check(clear.tolist() == [True, False, False, False, True, False], "Fmask clear rule")
    check(covered.tolist() == [True] * 5 + [False], "Fmask fill is not covered")

    s2 = program.PRODUCTS["sentinel2_l2a"]
    scl = np.array([0, 3, 4, 5, 6, 7, 8, 9, 10, 11], dtype=np.uint8)
    clear, covered = program.clear_and_covered(s2, scl)
    check(clear.tolist() == [False, False, True, True, True] + [False] * 5, "SCL clear: 4, 5, 6")
    check(covered.tolist() == [False] + [True] * 9, "SCL 0 is not covered")

    s1 = program.PRODUCTS["sentinel1_rtc"]
    vv = np.array([0.2, np.nan, -32768.0], dtype=np.float32)
    clear, covered = program.clear_and_covered(s1, vv)
    check(covered.tolist() == [True, False, False] and (clear == covered).all(), "S1 data rule")


class _Item:
    def __init__(self, baseline: str | None) -> None:
        self.properties = {} if baseline is None else {"s2:processing_baseline": baseline}


def test_offset_and_merge(program: ModuleType) -> None:
    offsets = [program.s2_offset(_Item(b)) for b in ("02.12", "03.00", "04.00", "05.11", None)]
    check(offsets == [0, 0, 1000, 1000, 0], "offset 1000 from baseline 04.00")

    first = np.array([[5, -9999], [-9999, -9999]], dtype=np.int16)
    second = np.array([[7, 8], [-9999, 9]], dtype=np.int16)
    merged = program._first_valid([first, second], [first != -9999, second != -9999], -9999)
    check(merged.tolist() == [[5, 8], [-9999, 9]], "items of one pass merge first-valid")


def test_cog(program: ModuleType, work: Path) -> None:
    grid = program.Grid(
        epsg=EPSG,
        resolution=10.0,
        bounds=(ORIGIN[0], ORIGIN[1] - 100.0, ORIGIN[0] + 100.0, ORIGIN[1]),
        width=10,
        height=10,
        footprint_wgs84=(0.0, 0.0, 0.0, 0.0),
    )
    array = np.arange(200, dtype=np.int16).reshape(2, 10, 10)
    path = work / "cog.tif"
    program.write_cog(path, array, grid, gdal.GDT_Int16, -9999, ("a", "b"))
    dataset = gdal.Open(str(path))
    check(dataset.GetMetadataItem("LAYOUT", "IMAGE_STRUCTURE") == "COG", "output is a COG")
    check((dataset.ReadAsArray() == array).all(), "values round-trip")
    band = dataset.GetRasterBand(2)
    check((band.GetDescription(), band.GetNoDataValue()) == ("b", -9999), "band names and nodata")


def write_fixtures(root: Path) -> None:
    write_site(root / "cases" / "too_large" / "input" / "primary" / "site.tif", TOO_LARGE_SIDE_M)
    (root / "cases" / "too_large" / "params.json").write_text(json.dumps({"year": "2025"}))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures-only", type=Path)
    args = parser.parse_args()
    if args.fixtures_only:
        write_fixtures(args.fixtures_only)
        return 0
    program = load_program()
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        test_params(program, work)
        test_grid(program, work)
        test_clear_rules(program)
        test_offset_and_merge(program)
        test_cog(program, work)
    print("satellite-fetch smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
