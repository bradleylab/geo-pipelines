#!/usr/bin/env python3
"""Offline smoke test for satellite-fetch, run inside the built image.

The recipe's network half (the catalog search and the reads) needs Planetary
Computer and is exercised by the fixture run on Compute2. This test covers the
rest with synthetic inputs whose answers are known: parameter checks, the output
grid, the clear-sky rules for each quality layer, the Sentinel-2 offset, how
items of one pass are merged, and the COG written. It then runs the whole recipe
for each product with the search and the reads replaced by synthetic layers, and
checks the false-color preview of the optical products against the imagery.tif
written beside it, and that radar gets none. ``--fixtures-only DIR`` writes a
site too large to fetch for, so CI can run the image's real ENTRYPOINT and see
it refuse before any network call.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
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

NODATA = -9999  # imagery.tif's reflectance nodata
PREVIEW_FILE = "imagery_preview.png"
PREVIEW_MAX_SIDE = 1024  # px, as the entrypoint caps it
PERCENTILES = (2, 98)
REFLECTANCE_SCALE = 10_000
CHANNELS = ("red", "green", "blue")

# Cells of the synthetic optical scenes, as (rows, columns); all fit the
# smallest grid, HLS's 30 m over a 2 km site.
CORNER = (slice(0, 5), slice(0, 5))  # no band holds data
# One patch per composite band, in red, green, blue order: high in that band.
PATCHES = (
    (slice(10, 18), slice(10, 18)),
    (slice(10, 18), slice(30, 38)),
    (slice(10, 18), slice(50, 58)),
)
FIRST_MISSING = (40, slice(30, 40))  # only the band shown as red is nodata
OTHER_MISSING = (45, slice(30, 40))  # only a band outside the composite is nodata


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


def test_preview_shrinks(program: ModuleType, work: Path) -> None:
    """A grid twice the preview's cap, checkered so a mean is told apart from one cell."""
    product = program.PRODUCTS["hls"]
    rows, cols = 40, 2 * PREVIEW_MAX_SIDE
    checkered = np.where(np.indices((rows, cols)).sum(axis=0) % 2 == 1, 3000, 1000)
    stack = np.full((len(product.band_names), rows, cols), 1500, dtype=np.int16)
    composite = [product.band_names.index(name) for name in ("swir2", "nir_narrow", "red")]
    stack[composite] = checkered
    stack[:, 0:2, 0:2] = NODATA  # a 2 x 2 block with no data at all
    stack[composite[0], 0, 2] = NODATA  # and one with a cell missing a composite band
    reported = program.write_preview(stack, product, work / PREVIEW_FILE)

    preview = gdal.Open(str(work / PREVIEW_FILE)).ReadAsArray().astype(np.float64)
    valid = (stack[composite] != NODATA).all(axis=0)
    blocks = (rows // 2, 2, cols // 2, 2)
    counts = valid.reshape(blocks).sum(axis=(1, 3))
    shown = counts > 0
    check(
        preview.shape == (4, rows // 2, cols // 2),
        f"a {cols} x {rows} grid is averaged 2 x 2 to {cols // 2} x {rows // 2} px",
    )
    check(
        np.array_equal(preview[3], np.where(shown, 255, 0)),
        "a pixel is transparent only where every cell under it lacks a composite band",
    )
    for index, band in enumerate(composite):
        sums = np.where(valid, stack[band], 0).astype(np.float64).reshape(blocks).sum(axis=(1, 3))
        expected = np.clip((sums / np.maximum(counts, 1) - 1000.0) / 2000.0, 0.0, 1.0) * 255.0
        # One level for rounding to 8 bits.
        check(
            np.abs(preview[index] - expected)[shown].max() <= 1.0,
            f"{CHANNELS[index]}: each pixel the mean of the valid cells under it, stretched",
        )
    # The checkers' 2nd and 98th percentiles are 1000 and 3000, but every 2 x 2
    # mean but one is 2000, so a stretch taken from the means would be empty.
    stretch = reported["stretch_reflectance"].values()
    check(
        reported["downsampling_factor"] == 2.0
        and (reported["width_px"], reported["height_px"]) == (cols // 2, rows // 2)
        and all(np.allclose([s["low"], s["high"]], [0.1, 0.3]) for s in stretch),
        "the report's stretch comes from the full-resolution cells, 0.1 to 0.3",
    )


class _Asset:
    def __init__(self, href: str) -> None:
        self.href = href


class _Scene:
    """The parts of a STAC item the recipe reads, for one synthetic acquisition."""

    def __init__(self, collection: str, keys: list[str], properties: dict) -> None:
        self.id = f"{collection}-synthetic"
        self.collection_id = collection
        self.datetime = datetime(2025, 6, 1, 16, 30, tzinfo=timezone.utc)
        self.properties = {"platform": "synthetic", **properties}
        self.assets = {key: _Asset(f"synthetic://{collection}/{key}") for key in keys}


@dataclass(frozen=True)
class Optical:
    """How one optical product's assets hold a scene, and the preview it should get."""

    product: str
    composite: tuple[str, str, str]  # the bands expected as red, green and blue
    other: str  # a band outside the composite
    dtype: type
    offset: int  # what the catalog adds to every value
    fill: int  # the assets' own nodata
    quality: tuple[str, int, int]  # the quality asset, a clear value, its fill
    properties: dict


OPTICAL = (
    Optical(
        product="hls",
        composite=("swir2", "nir_narrow", "red"),
        other="blue",
        dtype=np.int16,
        offset=0,
        fill=NODATA,
        quality=("Fmask", 0, 255),
        properties={},
    ),
    # A baseline from 04.00 on, so the catalog's values carry ESA's offset of 1000.
    Optical(
        product="sentinel2_l2a",
        composite=("B12", "B8A", "B04"),
        other="B01",
        dtype=np.int32,
        offset=1000,
        fill=0,
        quality=("SCL", 4, 0),
        properties={"s2:processing_baseline": "05.11"},
    ),
)


def staged_site(program: ModuleType, work: Path, product: str) -> tuple[Path, object]:
    case = work / product
    site = case / "input" / "primary" / "site.tif"
    write_site(site, SITE_SIDE_M)
    return case, program.site_grid(site, program.PRODUCTS[product].resolution)


def run_offline(
    program: ModuleType, case: Path, product: str, layers: dict, properties: dict
) -> tuple[Path, dict, dict]:
    """The real run(), with the catalog search and every asset read replaced by ``layers``."""
    collection = next(iter(program.PRODUCTS[product].collections))
    scene = _Scene(collection, list(layers), properties)
    saved = program.search, program.warp
    program.search = lambda *_: [scene]
    program.warp = lambda href, *_: layers[href.rsplit("/", 1)[1]].copy()
    try:
        program.run(case / "input", case / "output", program.Params(product, 2025, 1, 12))
    finally:
        program.search, program.warp = saved
    out = case / "output"
    manifest = json.loads((out / "run.json").read_text())
    return out, manifest, json.loads((out / "fetch_report.json").read_text())


def optical_layers(program: ModuleType, spec: Optical, grid) -> dict[str, np.ndarray]:
    """Per asset, a scene in which each band of the composite has a patch of its own.

    Outside the patches the three bands share one gentle west-to-east ramp; in a
    band's own patch it is far above the ramp and the other two far below it, so
    the patch should come out in that band's color alone.
    """
    product = program.PRODUCTS[spec.product]
    shape = (grid.height, grid.width)
    east = np.broadcast_to(np.linspace(0.0, 200.0, grid.width), shape)
    values = {name: np.full(shape, 1500.0) for name in product.band_names}
    for name in spec.composite:
        values[name] = 1000.0 + east
    for own, patch in zip(spec.composite, PATCHES, strict=True):
        for name in spec.composite:
            values[name][patch] = 3000.0 if name == own else 500.0
    stored = {name: (np.rint(v) + spec.offset).astype(spec.dtype) for name, v in values.items()}
    for layer in stored.values():
        layer[CORNER] = spec.fill
    stored[spec.composite[0]][FIRST_MISSING] = spec.fill
    stored[spec.other][OTHER_MISSING] = spec.fill

    key, clear, fill = spec.quality
    quality = np.full(shape, clear, dtype=np.uint8)
    quality[CORNER] = fill
    assets = dict(zip(product.band_names, next(iter(product.collections.values())), strict=True))
    return {assets[name]: layer for name, layer in stored.items()} | {key: quality}


def check_preview(out: Path, manifest: dict, report: dict, spec: Optical) -> None:
    """The preview against the imagery.tif written beside it."""
    name = spec.product
    listed = [entry for entry in manifest["outputs"] if entry["path"] == PREVIEW_FILE]
    digest = hashlib.sha256((out / PREVIEW_FILE).read_bytes()).hexdigest()
    check(
        [(e["role"], e.get("format"), e["sha256"]) for e in listed] == [("preview", "PNG", digest)],
        f"{name}: run.json lists the preview with role preview, format PNG and its checksum",
    )
    preview = gdal.Open(str(out / PREVIEW_FILE))
    types = [preview.GetRasterBand(i).DataType for i in range(1, preview.RasterCount + 1)]
    check(
        preview.GetDriver().ShortName == "PNG" and types == [gdal.GDT_Byte] * 4,
        f"{name}: the preview is a 4-band 8-bit PNG",
    )
    imagery = gdal.Open(str(out / "imagery.tif"))
    named = {
        imagery.GetRasterBand(i).GetDescription(): imagery.GetRasterBand(i).ReadAsArray()
        for i in range(1, imagery.RasterCount + 1)
    }
    size = (preview.RasterXSize, preview.RasterYSize)
    # The grid is far under the cap, so the preview is imagery.tif cell for cell.
    check(
        size == (imagery.RasterXSize, imagery.RasterYSize) and max(size) <= PREVIEW_MAX_SIDE,
        f"{name}: {size[0]} x {size[1]} px, imagery.tif cell for cell and not enlarged",
    )

    bands = np.stack([named[band] for band in spec.composite]).astype(np.float64)
    valid = (bands != NODATA).all(axis=0)
    rgba = preview.ReadAsArray().astype(np.float64)
    check(
        np.array_equal(rgba[3], np.where(valid, 255, 0)) and not valid[FIRST_MISSING].any(),
        f"{name}: transparent exactly where any of {', '.join(spec.composite)} is nodata",
    )
    check(
        (named[spec.other][OTHER_MISSING] == NODATA).all()
        and (rgba[3][OTHER_MISSING] == 255).all(),
        f"{name}: a cell missing only {spec.other}, outside the composite, stays opaque",
    )
    limits = np.percentile(bands[:, valid], PERCENTILES, axis=1).T
    for index, (band, (low, high)) in enumerate(zip(spec.composite, limits, strict=True)):
        expected = np.clip((bands[index] - low) / (high - low), 0.0, 1.0) * 255.0
        # One level for rounding to 8 bits.
        check(
            np.abs(rgba[index] - expected)[valid].max() <= 1.0,
            f"{name}: {CHANNELS[index]} is {band} stretched from its 2nd to its 98th percentile",
        )
    for index, patch in enumerate(PATCHES):
        excess = rgba[index] - np.delete(rgba[:3], index, axis=0).max(axis=0)
        inside = np.zeros(valid.shape, dtype=bool)
        inside[patch] = True
        check(
            excess[inside].min() > excess[valid & ~inside].max(),
            f"{name}: the patch high in {spec.composite[index]} is the most {CHANNELS[index]}",
        )

    reported = report["preview"]
    expected_block = {
        "file": PREVIEW_FILE,
        "width_px": size[0],
        "height_px": size[1],
        "downsampling_factor": 1.0,
        "composite": list(spec.composite),
        "stretch_percentiles": list(PERCENTILES),
    }
    stretch = reported["stretch_reflectance"]
    check(
        {key: reported[key] for key in expected_block} == expected_block
        and list(stretch) == list(spec.composite)
        and np.allclose(
            [[stretch[band]["low"], stretch[band]["high"]] for band in spec.composite],
            limits / REFLECTANCE_SCALE,
        ),
        f"{name}: the report gives the preview's size, composite and stretch in reflectance",
    )


def test_optical_runs(program: ModuleType, work: Path) -> None:
    for spec in OPTICAL:
        case, grid = staged_site(program, work, spec.product)
        layers = optical_layers(program, spec, grid)
        out, manifest, report = run_offline(program, case, spec.product, layers, spec.properties)
        roles = sorted(entry["role"] for entry in manifest["outputs"])
        check(
            roles == ["imagery", "preview", "quality", "report"],
            f"{spec.product}: run.json lists imagery, preview, quality and report",
        )
        check_preview(out, manifest, report, spec)


def test_radar_run(program: ModuleType, work: Path) -> None:
    case, grid = staged_site(program, work, "sentinel1_rtc")
    layers = {
        key: np.full((grid.height, grid.width), 0.1, dtype=np.float32) for key in ("vv", "vh")
    }
    for layer in layers.values():
        layer[CORNER] = np.nan
    out, manifest, report = run_offline(program, case, "sentinel1_rtc", layers, {})
    check(not (out / PREVIEW_FILE).exists(), "sentinel1_rtc: no preview is written")
    check(
        sorted(entry["role"] for entry in manifest["outputs"]) == ["imagery", "report"],
        "sentinel1_rtc: run.json lists imagery and report, and no preview",
    )
    check(
        "preview" in report and report["preview"] is None,
        "sentinel1_rtc: the report's preview is null",
    )


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
        test_preview_shrinks(program, work)
        test_optical_runs(program, work)
        test_radar_run(program, work)
    print("satellite-fetch smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
