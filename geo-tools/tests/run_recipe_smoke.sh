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

echo "geo-tools recipe smoke test passed"
