#!/usr/bin/env python3
"""Contract smoke test for ground-surfaces, run inside the built image.

Builds small synthetic point clouds whose surfaces are known exactly, runs the
recipe through its three contract options, and checks what it wrote. No
network and no committed binaries. CI runs it with the entrypoint overridden
to ``python``; ``--fixtures-only DIR`` writes the inputs without running them,
so CI can also drive the image's real ENTRYPOINT against them.

The cloud: a flat ground plane, an 8 m block of canopy over part of it with
ground returns beneath (as a lidar pulse reaches the ground through
vegetation), and one isolated return far above everything. The DTM must be
the plane, the CHM's maximum must be the canopy height, and the DSM must not
see the isolated return.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pdal
from osgeo import gdal

gdal.UseExceptions()

PROGRAM = "ground-surfaces"
EPSG = 32615  # UTM 15N: metric, and covers the course sites
ORIGIN = (734600.0, 4281160.0)
SPACING = 0.5  # m between synthetic returns
GROUND_SIZE = 40.0  # m square
GROUND_Z = 100.0
CANOPY_HEIGHT = 8.0
CANOPY_SPAN = (16.0, 22.0)  # m from the origin, both axes
STRAY_Z = 180.0  # the isolated return; a DSM that includes it tops out here
RESOLUTION = "1.0"  # contract v1 sends every value as a string
TOLERANCE = 1e-3

GROUND_CLASS, HIGH_VEGETATION, HIGH_NOISE = 2, 5, 18
DTYPE = [
    ("X", "f8"),
    ("Y", "f8"),
    ("Z", "f8"),
    ("Classification", "u1"),
    ("ReturnNumber", "u1"),
    ("NumberOfReturns", "u1"),
]


def _returns(xy: np.ndarray, z: float, cls: int) -> np.ndarray:
    points = np.zeros(len(xy), dtype=DTYPE)
    points["X"] = ORIGIN[0] + xy[:, 0]
    points["Y"] = ORIGIN[1] + xy[:, 1]
    points["Z"] = z
    points["Classification"] = cls
    points["ReturnNumber"] = 1
    points["NumberOfReturns"] = 1
    return points


def cloud(classified: bool) -> np.ndarray:
    axis = np.arange(0.0, GROUND_SIZE, SPACING)
    ground_xy = np.array([(x, y) for x in axis for y in axis])
    # Canopy returns sit between the ground returns so no two share an XY.
    span = np.arange(CANOPY_SPAN[0], CANOPY_SPAN[1], SPACING) + SPACING / 2
    canopy_xy = np.array([(x, y) for x in span for y in span])
    stray_xy = np.array([(GROUND_SIZE / 2, GROUND_SIZE / 4)])
    parts = [
        _returns(ground_xy, GROUND_Z, GROUND_CLASS if classified else 0),
        _returns(canopy_xy, GROUND_Z + CANOPY_HEIGHT, HIGH_VEGETATION if classified else 0),
        _returns(stray_xy, STRAY_Z, HIGH_NOISE if classified else 0),
    ]
    return np.concatenate(parts)


def write_las(points: np.ndarray, path: Path, epsg: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = pdal.Writer.las(
        filename=str(path), a_srs=f"EPSG:{epsg}", minor_version=4, dataformat_id=6
    )
    writer.pipeline(points).execute()


def make_case(root: Path, name: str, points: np.ndarray, params: dict, epsg: int = EPSG) -> Path:
    case = root / "cases" / name
    write_las(points, case / "input" / "primary" / "cloud.las", epsg)
    (case / "params.json").write_text(json.dumps(params))
    return case


def make_fixtures(root: Path) -> dict[str, Path]:
    base = {"resolution": RESOLUTION}
    return {
        "unclassified": make_case(
            root, "unclassified", cloud(False), base | {"ground_source": "classify"}
        ),
        "classify": make_case(root, "classify", cloud(True), base | {"ground_source": "classify"}),
        "smrf_supplied": make_case(
            root,
            "smrf_supplied",
            cloud(True),
            base | {"ground_source": "classify", "smrf_window": "10", "smrf_slope": "0.2"},
        ),
        "existing": make_case(root, "existing", cloud(True), base | {"ground_source": "existing"}),
        "geographic": make_case(root, "geographic", _geographic(), base, epsg=4326),
        "unknown_param": make_case(root, "unknown_param", cloud(True), base | {"color": "red"}),
        "existing_unclassified": make_case(
            root, "existing_unclassified", cloud(False), base | {"ground_source": "existing"}
        ),
    }


def _geographic() -> np.ndarray:
    points = cloud(True)[:100]
    points["X"], points["Y"] = -90.2, 38.6  # degrees; the recipe must refuse these
    return points


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


def band(path: Path) -> tuple[np.ndarray, tuple, str]:
    dataset = gdal.Open(str(path))
    values = dataset.GetRasterBand(1).ReadAsArray()
    return values, dataset.GetGeoTransform(), dataset.GetProjection()


def valid(values: np.ndarray) -> np.ndarray:
    return values[values != np.float32(-9999.0)]


def check_success(name: str, case: Path, noise_source: str, smrf: dict | str) -> None:
    result = run_case(case)
    if result.returncode != 0:
        fail(f"{name}: exit {result.returncode}: {result.stderr.strip()}")
    out = case / "output"
    manifest = json.loads((out / "run.json").read_text())
    if manifest.get("contract_version") != 1:
        fail(f"{name}: contract_version is {manifest.get('contract_version')!r}")
    roles = {entry["role"]: entry for entry in manifest["outputs"]}
    if set(roles) != {"dtm", "dsm", "chm", "report"}:
        fail(f"{name}: manifest roles are {sorted(roles)}")
    for entry in manifest["outputs"]:
        if hashlib.sha256((out / entry["path"]).read_bytes()).hexdigest() != entry["sha256"]:
            fail(f"{name}: sha256 of {entry['path']} does not match the manifest")

    dtm, dtm_gt, dtm_srs = band(out / "dtm.tif")
    dsm, dsm_gt, _ = band(out / "dsm.tif")
    chm, chm_gt, _ = band(out / "chm.tif")
    if not dtm_gt == dsm_gt == chm_gt:
        fail(f"{name}: the three rasters do not share one grid: {dtm_gt} {dsm_gt} {chm_gt}")
    if f'"EPSG","{EPSG}"' not in dtm_srs.replace(" ", ""):
        fail(f"{name}: DTM CRS is not EPSG:{EPSG}")
    if np.abs(valid(dtm) - GROUND_Z).max() > TOLERANCE:
        fail(
            f"{name}: DTM departs from the ground plane (range {valid(dtm).min()}-{valid(dtm).max()})"
        )
    if abs(valid(dsm).max() - (GROUND_Z + CANOPY_HEIGHT)) > TOLERANCE:
        fail(f"{name}: DSM maximum is {valid(dsm).max()}; the isolated return reached the surface")
    if abs(valid(chm).max() - CANOPY_HEIGHT) > TOLERANCE:
        fail(f"{name}: CHM maximum is {valid(chm).max()}, expected {CANOPY_HEIGHT}")

    report = json.loads((out / "surfaces_report.json").read_text())
    if report["noise_source"] != noise_source or report["noise_left_out"] < 1:
        fail(f"{name}: noise {report['noise_left_out']} from {report['noise_source']!r}")
    reported = report["smrf"]
    if isinstance(smrf, str):
        if reported != smrf:
            fail(f"{name}: report smrf is {reported!r}, expected {smrf!r}")
    elif {key: reported.get(key) for key in smrf} != smrf:
        fail(f"{name}: report smrf is {reported!r}, expected to include {smrf!r}")
    print(
        f"ok: {name} (DTM {GROUND_Z}, CHM max {valid(chm).max():.3f}, "
        f"noise {report['noise_left_out']} via {report['noise_source']})"
    )


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
        # PDAL 2.8.1's defaults when nothing is supplied; supplied values win.
        defaults = {"slope": 0.15, "window": 18.0, "threshold": 0.5, "scalar": 1.25, "supplied": []}
        supplied = defaults | {"slope": 0.2, "window": 10.0, "supplied": ["slope", "window"]}
        check_success("unclassified", cases["unclassified"], "outlier_filter", defaults)
        check_success("classify", cases["classify"], "classified", defaults)
        check_success("smrf_supplied", cases["smrf_supplied"], "classified", supplied)
        check_success("existing", cases["existing"], "classified", "not used")
        check_refused("geographic", cases["geographic"], "reproject_laz")
        check_refused("unknown_param", cases["unknown_param"], "unknown parameters")
        check_refused("existing_unclassified", cases["existing_unclassified"], "no class 2")
    print("ground-surfaces smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
