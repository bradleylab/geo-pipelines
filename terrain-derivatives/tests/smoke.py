#!/usr/bin/env python3
"""Contract smoke test for terrain-derivatives, run inside the built image.

Builds small synthetic elevation models whose derivatives are known exactly,
runs the recipe through its three contract options, and checks what it wrote.
No network and no committed binaries. CI runs it with the entrypoint overridden
to ``python``; ``--fixtures-only DIR`` writes the inputs without running them,
so CI can also drive the image's real ENTRYPOINT against them.

The main surface is a plane rising to the east at a known grade. On a plane,
every 3 x 3 window holds three cells a grade-step below the center, three a
step above and two level with it, so gdaldem's formulas (gdaldem_lib.cpp,
GDAL 3.9.3) give exact values: slope atan(grade), aspect 270 (the plane faces
west), roughness 2 * step (highest minus lowest cell in the window), TRI
sqrt(6) * step (Riley: root of the summed squared differences from the
center), and TPI 0 (center minus the mean of its neighbors).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from osgeo import gdal, ogr, osr

gdal.UseExceptions()
ogr.UseExceptions()

PROGRAM = "terrain-derivatives"
EPSG = 32615  # UTM 15N: metric, and covers the course sites
ORIGIN = (734600.0, 4281200.0)  # top-left corner, on whole meters
SIZE = 40  # cells a side
CELL = 1.0  # m
BASE = 100.3  # m; keeps every cell-center elevation off a whole meter
GRADE = 0.5  # rise per meter, eastward
STEP = GRADE * CELL
FLOAT_NODATA = -9999.0
HILLSHADE_NODATA = 0
INPUT_NODATA = -32768.0
TOLERANCE = 1e-3
RASTER_ROLES = {"slope", "aspect", "hillshade", "roughness", "tri", "tpi"}


def plane(size: int = SIZE, cell: float = CELL) -> np.ndarray:
    x_centers = (np.arange(size) + 0.5) * cell
    return np.tile(BASE + GRADE * x_centers, (size, 1)).astype(np.float32)


def write_dem(
    path: Path,
    values: np.ndarray,
    *,
    cell: float = CELL,
    origin: tuple[float, float] = ORIGIN,
    epsg: int = EPSG,
    nodata: float | None = None,
    rotation: float = 0.0,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows, cols = values.shape
    dataset = gdal.GetDriverByName("GTiff").Create(str(path), cols, rows, 1, gdal.GDT_Float32)
    dataset.SetGeoTransform((origin[0], cell, rotation, origin[1], 0.0, -cell))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    dataset.SetProjection(srs.ExportToWkt())
    band = dataset.GetRasterBand(1)
    if nodata is not None:
        band.SetNoDataValue(nodata)
    band.WriteArray(values)
    dataset = None


def make_case(root: Path, name: str, values: np.ndarray, params: dict, **grid) -> Path:
    case = root / "cases" / name
    write_dem(case / "input" / "primary" / "dem.tif", values, **grid)
    (case / "params.json").write_text(json.dumps(params))
    return case


def make_fixtures(root: Path) -> dict[str, Path]:
    holed = plane()
    holed[20, 20] = INPUT_NODATA
    return {
        "plane": make_case(root, "plane", plane(), {"contour_interval": "1"}),
        "percent_zt": make_case(
            root,
            "percent_zt",
            plane(),
            {"slope_units": "percent", "gradient_method": "zevenbergen_thorne"},
        ),
        "flat": make_case(root, "flat", np.full((SIZE, SIZE), BASE, np.float32), {}),
        "hole": make_case(root, "hole", holed, {}, nodata=INPUT_NODATA),
        # 0.5 m cells whose corner sits a quarter meter off the 1 m lattice.
        "resampled": make_case(
            root,
            "resampled",
            plane(size=2 * SIZE, cell=CELL / 2),
            {"resolution": "1.0"},
            cell=CELL / 2,
            origin=(ORIGIN[0] + 0.25, ORIGIN[1] - 0.25),
        ),
        "geographic": make_case(root, "geographic", plane(), {}, origin=(-90.2, 38.6), epsg=4326),
        "rotated": make_case(root, "rotated", plane(), {}, rotation=0.1),
        "too_fine": make_case(root, "too_fine", plane(), {"resolution": "0.5"}),
        "unknown_param": make_case(root, "unknown_param", plane(), {"color": "red"}),
        "interval_too_large": make_case(
            root, "interval_too_large", plane(), {"contour_interval": "150"}
        ),
    }


def run_case(case: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            PROGRAM,
            "--input-dir",
            str(case / "input"),
            "--output-dir",
            str(case / "output"),
            "--params-json",
            str(case / "params.json"),
        ],
        capture_output=True,
        text=True,
        check=False,  # the caller judges the exit status
    )


def fail(message: str) -> None:
    print(f"smoke test FAILED: {message}", file=sys.stderr)
    sys.exit(1)


def read(path: Path) -> tuple[np.ndarray, tuple, str]:
    dataset = gdal.Open(str(path))
    values = dataset.GetRasterBand(1).ReadAsArray()
    return values, dataset.GetGeoTransform(), dataset.GetProjection()


def interior(values: np.ndarray) -> np.ndarray:
    return values[1:-1, 1:-1]


def run_ok(name: str, case: Path, expected_roles: set[str]) -> tuple[Path, dict]:
    result = run_case(case)
    if result.returncode != 0:
        fail(f"{name}: exit {result.returncode}: {result.stderr.strip()}")
    out = case / "output"
    manifest = json.loads((out / "run.json").read_text())
    if manifest.get("contract_version") != 1:
        fail(f"{name}: contract_version is {manifest.get('contract_version')!r}")
    roles = {entry["role"] for entry in manifest["outputs"]}
    if roles != expected_roles:
        fail(f"{name}: manifest roles are {sorted(roles)}, expected {sorted(expected_roles)}")
    for entry in manifest["outputs"]:
        if hashlib.sha256((out / entry["path"]).read_bytes()).hexdigest() != entry["sha256"]:
            fail(f"{name}: sha256 of {entry['path']} does not match the manifest")
    transforms = {read(out / f"{role}.tif")[1] for role in RASTER_ROLES}
    if len(transforms) != 1:
        fail(f"{name}: the rasters do not share one grid: {transforms}")
    report = json.loads((out / "terrain_report.json").read_text())
    return out, report


def expect_close(name: str, what: str, values: np.ndarray, target: float) -> None:
    if values.size == 0 or np.abs(values.astype(np.float64) - target).max() > TOLERANCE:
        low, high = (values.min(), values.max()) if values.size else (None, None)
        fail(f"{name}: {what} ranges {low}-{high}, expected {target}")


def expect_border_nodata(name: str, out: Path) -> None:
    for role in RASTER_ROLES:
        values, _, _ = read(out / f"{role}.tif")
        nodata = HILLSHADE_NODATA if role == "hillshade" else FLOAT_NODATA
        ring = np.concatenate([values[0], values[-1], values[:, 0], values[:, -1]])
        if not (ring == values.dtype.type(nodata)).all():
            fail(f"{name}: {role} has data on its outer ring")


def check_plane(case: Path) -> None:
    out, report = run_ok("plane", case, RASTER_ROLES | {"contours", "report"})
    expect_close(
        "plane",
        "slope (degrees)",
        interior(read(out / "slope.tif")[0]),
        math.degrees(math.atan(GRADE)),
    )
    expect_close("plane", "aspect", interior(read(out / "aspect.tif")[0]), 270.0)
    expect_close("plane", "roughness", interior(read(out / "roughness.tif")[0]), 2 * STEP)
    expect_close("plane", "TRI", interior(read(out / "tri.tif")[0]), math.sqrt(6) * STEP)
    expect_close("plane", "TPI", interior(read(out / "tpi.tif")[0]), 0.0)
    shade, _, srs = read(out / "hillshade.tif")
    if shade.dtype != np.uint8 or len(np.unique(interior(shade))) != 1 or interior(shade).min() < 1:
        fail(
            f"plane: hillshade interior is {np.unique(interior(shade))}; one value in 1-255 expected"
        )
    if f'"EPSG","{EPSG}"' not in srs.replace(" ", ""):
        fail(f"plane: output CRS is not EPSG:{EPSG}")
    expect_border_nodata("plane", out)

    elevations = plane()
    levels = set(range(math.ceil(elevations.min()), math.floor(elevations.max()) + 1))
    source = ogr.Open(str(out / "contours.gpkg"))  # held: the layer belongs to it
    drawn = {
        round(feature.GetField("elevation_m"), 6) for feature in source.GetLayerByName("contour")
    }
    if drawn != {float(level) for level in levels}:
        fail(f"plane: contour levels are {sorted(drawn)}, expected {sorted(levels)}")
    if report["contours"]["lines"] < len(levels):
        fail(f"plane: report counts {report['contours']['lines']} contour lines")
    if report["methods"]["tri"] != "Riley" or report["resampled"] != "no":
        fail(f"plane: report methods {report['methods']}, resampled {report['resampled']!r}")
    print(
        f"ok: plane (slope {math.degrees(math.atan(GRADE)):.3f} deg, {len(levels)} contour levels)"
    )


def check_percent_zt(case: Path) -> None:
    out, report = run_ok("percent_zt", case, RASTER_ROLES | {"report"})
    expect_close("percent_zt", "slope (percent)", interior(read(out / "slope.tif")[0]), 100 * GRADE)
    expect_close("percent_zt", "aspect", interior(read(out / "aspect.tif")[0]), 270.0)
    if report["methods"]["gradient"] != "ZevenbergenThorne" or report["contours"] != "not written":
        fail(f"percent_zt: report {report['methods']}, contours {report['contours']!r}")
    print("ok: percent_zt (slope 50%, no contours)")


def check_flat(case: Path) -> None:
    out, _ = run_ok("flat", case, RASTER_ROLES | {"report"})
    expect_close("flat", "slope", interior(read(out / "slope.tif")[0]), 0.0)
    expect_close("flat", "aspect", interior(read(out / "aspect.tif")[0]), FLOAT_NODATA)
    expect_close("flat", "roughness", interior(read(out / "roughness.tif")[0]), 0.0)
    expect_close("flat", "TPI", interior(read(out / "tpi.tif")[0]), 0.0)
    print("ok: flat (zero slope, aspect nodata)")


def check_hole(case: Path) -> None:
    out, _ = run_ok("hole", case, RASTER_ROLES | {"report"})
    for role in RASTER_ROLES:
        values, _, _ = read(out / f"{role}.tif")
        nodata = HILLSHADE_NODATA if role == "hillshade" else FLOAT_NODATA
        if not (values[19:22, 19:22] == values.dtype.type(nodata)).all():
            fail(f"hole: {role} has data in the 3 x 3 neighborhood of the nodata cell")
    print("ok: hole (nodata spreads to its 3 x 3 neighborhood only)")


def check_resampled(case: Path) -> None:
    out, report = run_ok("resampled", case, RASTER_ROLES | {"report"})
    _, transform, _ = read(out / "slope.tif")
    if abs(transform[1] - CELL) > TOLERANCE or abs(-transform[5] - CELL) > TOLERANCE:
        fail(f"resampled: output cell size is {transform[1]} x {-transform[5]}")
    if any(abs(edge - round(edge)) > TOLERANCE for edge in (transform[0], transform[3])):
        fail(f"resampled: output grid corner {transform[0]}, {transform[3]} is not on whole meters")
    if report["resampled"] == "no" or abs(report["resampled"]["to_cell_m"] - CELL) > TOLERANCE:
        fail(f"resampled: report says {report['resampled']!r}")
    expect_close("resampled", "aspect", interior(read(out / "aspect.tif")[0]), 270.0)
    print("ok: resampled (0.5 m averaged onto the 1 m lattice)")


def check_refused(name: str, case: Path, expected: str) -> None:
    result = run_case(case)
    if result.returncode != 2 or expected not in result.stderr:
        fail(
            f"{name}: expected refusal mentioning {expected!r}, got exit "
            f"{result.returncode}: {result.stderr.strip()}"
        )
    if (case / "output" / "run.json").exists():
        fail(f"{name}: a refused run wrote a manifest")
    print(f"ok: {name} refused")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures-only", type=Path, help="write the inputs here and stop")
    args = parser.parse_args()
    if args.fixtures_only:
        make_fixtures(args.fixtures_only)
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        cases = make_fixtures(Path(tmp))
        check_plane(cases["plane"])
        check_percent_zt(cases["percent_zt"])
        check_flat(cases["flat"])
        check_hole(cases["hole"])
        check_resampled(cases["resampled"])
        check_refused("geographic", cases["geographic"], "reproject")
        check_refused("rotated", cases["rotated"], "rotated grid")
        check_refused("too_fine", cases["too_fine"], "finer than")
        check_refused("unknown_param", cases["unknown_param"], "unknown parameters")
        check_refused("interval_too_large", cases["interval_too_large"], "contour_interval")
    print("terrain-derivatives smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
