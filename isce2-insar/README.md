# isce2-insar

Sentinel-1 InSAR (interferogram + **coherence**) via **ISCE2** (JPL), with
**MintPy** for optional time-series analysis. Non-ML geoprocessing, so it lives
here in `geo-pipelines` (not `ml-containers`).

## Image

`ghcr.io/bradleylab/isce2-insar:latest` (and `:vN` on release tags). CPU only.

## Stack

- Base: `mambaorg/micromamba:1.5.10`
- `isce2` + `mintpy` from conda-forge (solver-selected Python/GDAL)

## Run

The entrypoint (`isce2-insar`) sets `ISCE_HOME`/`PATH` at run time — needed on
Compute2, where `srun ... bash -lc` bypasses conda activation.

```bash
# versions / sanity
docker run --rm ghcr.io/bradleylab/isce2-insar:latest version

# a TOPS interferogram + coherence run (mount an input dir with SLCs + orbits)
docker run --rm -v "$PWD/work:/work" -w /work \
  ghcr.io/bradleylab/isce2-insar:latest topsApp.py topsApp.xml --steps
```

On Compute2 (enroot + pyxis):

```bash
srun --container-image=/storage3/fs1/<user>/Active/c2_jobs/bradleylab+isce2-insar+latest.sqsh \
     --container-mounts=/scratch2/fs1/<user>:/scratch2/fs1/<user> \
     bash -lc "export PYTHONNOUSERSITE=1; isce2-insar topsApp.py topsApp.xml --steps"
```

## Inputs

- Two co-orbit Sentinel-1 **SLC** products (IW, same relative orbit) + their
  precise/restituted **orbit** files, plus a DEM for geocoding.
- For our Black River case: the 6-day pair on the ascending track (e.g.
  2026-07-05 and 2026-07-11). ISCE `topsApp` produces the wrapped interferogram,
  **coherence**, and (optionally) the unwrapped phase.

## Products

- `merged/topophase.cor` — **coherence** (the disturbance-sensitive layer)
- `merged/filt_topophase.flat` — filtered wrapped interferogram
- geocoded outputs under `merged/` after the `geocode` step

## Notes / boundaries

- ISCE2 GPU modules are not built (CPU image); coherence is CPU-fine.
- Orbit/DEM fetch is a run-time step (needs network or pre-staged files) — not
  baked into the image.
