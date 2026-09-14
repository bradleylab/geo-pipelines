#!/usr/bin/env bash
# Exercises every geo-tools recipe against tiny synthetic fixtures.
#
# Run inside the built geo-tools image with the entrypoint overridden to
# bash, so `geo-tools`, `python`, gdal, and pdal all resolve from the
# pinned conda env — see build-geo-tools.yml. A failing recipe here fails
# the CI job before the image is pushed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

python "${SCRIPT_DIR}/make_fixtures.py" --out-dir "${WORK}/fixtures"

RASTER="${WORK}/fixtures/tiny.tif"
POINTS="${WORK}/fixtures/tiny.las"
DEM_BEFORE="${WORK}/fixtures/tiny_before.tif"
DEM_AFTER="${WORK}/fixtures/tiny_after.tif"
OUT="${WORK}/out"
mkdir -p "${OUT}"

assert_nonempty() {
    local path="$1"
    if [[ ! -s "${path}" ]]; then
        echo "smoke test FAILED: ${path} missing or empty" >&2
        exit 1
    fi
    echo "ok: ${path} ($(wc -c <"${path}") bytes)"
}

echo "== tiff-to-cog =="
geo-tools tiff-to-cog --input "${RASTER}" --output "${OUT}/cog.tif" --compression DEFLATE
assert_nonempty "${OUT}/cog.tif"

echo "== hillshade =="
geo-tools hillshade --input "${RASTER}" --output "${OUT}/hillshade.tif"
assert_nonempty "${OUT}/hillshade.tif"

echo "== reproject =="
geo-tools reproject --input "${RASTER}" --output "${OUT}/reprojected.tif" --target-crs EPSG:32615
assert_nonempty "${OUT}/reprojected.tif"

echo "== laz-to-copc =="
geo-tools laz-to-copc --input "${POINTS}" --output "${OUT}/tiny.copc.laz"
assert_nonempty "${OUT}/tiny.copc.laz"

echo "== laz-to-dem =="
geo-tools laz-to-dem --input "${POINTS}" --output-dir "${OUT}/dem" --resolution 5
assert_nonempty "${OUT}/dem/dtm.tif"
assert_nonempty "${OUT}/dem/dsm.tif"

echo "== dem-of-difference =="
# The fixtures are flat surfaces 1.5 m apart over 64 one-square-meter cells, so
# every statistic below is exact rather than approximate.
geo-tools dem-of-difference \
    --after "${DEM_AFTER}" --before "${DEM_BEFORE}" \
    --output-dir "${OUT}/dod" --threshold 0.5
assert_nonempty "${OUT}/dod/dod.tif"
assert_nonempty "${OUT}/dod/dod_stats.json"
assert_nonempty "${OUT}/dod/dod_hist.csv"
python - "${OUT}/dod/dod_stats.json" <<'PY'
import json
import sys

stats = json.load(open(sys.argv[1]))
expected = {
    "volume_gain_m3": 96.0,  # 64 cells x 1.5 m x 1 m^2
    "volume_loss_m3": 0.0,
    "n_changed_cells": 64,
    "area_changed_m2": 64.0,
}
for key, want in expected.items():
    got = stats[key]
    if abs(got - want) > 1e-6:
        raise SystemExit(f"dem-of-difference {key}: expected {want}, got {got}")
print("ok: dod_stats.json matches the expected flat-surface difference")
PY

echo "== dem-of-difference refuses a geographic CRS =="
# tiny.tif is EPSG:4326, whose degree-sized cells would make the area and
# volume statistics meaningless; the recipe must refuse it with exit code 2.
set +e
geo-tools dem-of-difference \
    --after "${RASTER}" --before "${DEM_BEFORE}" \
    --output-dir "${OUT}/dod_geographic"
rc=$?
set -e
if [[ "${rc}" -ne 2 ]]; then
    echo "smoke test FAILED: geographic --after should exit 2, got ${rc}" >&2
    exit 1
fi
echo "ok: geographic --after rejected with exit code 2"

echo "geo-tools recipe smoke test passed"
