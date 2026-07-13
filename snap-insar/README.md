# snap-insar

Sentinel-1 InSAR via **ESA SNAP 12** + the Sentinel-1 Toolbox: TOPS
coregistration → interferogram → **coherence** → Goldstein filter → SNAPHU
export/unwrap. ESA's official toolbox — non-ML geoprocessing, so it lives here in
`geo-pipelines` (not `ml-containers`).

## Image

`ghcr.io/bradleylab/snap-insar:latest` (and `:vN` on release tags). amd64, CPU.
SNAP **12** is pinned because it supports Sentinel-1C/1D (SNAP 9 predates them).

## Stack

- Base: `debian:bookworm-slim`
- ESA SNAP 12.0.0 (official installer, bundled JRE) at `/opt/snap`
- SNAPHU (phase unwrapping) **not bundled** — not in bookworm apt, and coherence
  doesn't need it. Add via conda-forge / source only if unwrapping is required.

## Run

```bash
docker run --rm ghcr.io/bradleylab/snap-insar:latest version

# gpt with an InSAR graph (mount work dir with SLCs)
docker run --rm -v "$PWD/work:/work" -w /work \
  ghcr.io/bradleylab/snap-insar:latest \
  gpt /work/insar_coherence.xml -Pin1=S1_pre.zip -Pin2=S1_post.zip -Pout=/work/coh.dim -c 8G
```

On Compute2 (enroot + pyxis):

```bash
srun --container-image=/storage3/fs1/<user>/Active/c2_jobs/bradleylab+snap-insar+latest.sqsh \
     --container-mounts=/scratch2/fs1/<user>:/scratch2/fs1/<user> \
     bash -lc "snap-insar gpt coherence.xml -Pin1=... -Pin2=... -Pout=... -c 16G"
```

## Typical InSAR/coherence chain (gpt operators)

`Read` → `TOPSAR-Split` (pick sub-swath/bursts) → `Apply-Orbit-File` →
`Back-Geocoding` (coregister the pair) → `Interferogram` (with coherence) →
`TOPSAR-Deburst` → `TopoPhaseRemoval` → `GoldsteinPhaseFiltering` →
`Write`. The coherence band from `Interferogram` is the disturbance-sensitive
product; unwrapping (SNAPHU) is optional and only needed for displacement.

## Inputs / products

- **In:** two co-orbit S1 IW **SLC** products (same relative orbit) + a DEM
  (SNAP auto-downloads SRTM/Copernicus at run time). For Black River: the
  ascending 6-day pair (e.g. 2026-07-05 / 2026-07-11).
- **Out:** a `.dim`/`.data` product with the coherence band (and interferogram);
  export to GeoTIFF via a final `Write` in GeoTIFF format.

## Notes / boundaries

- `-c <heap>` sets gpt tile cache; give it real memory for InSAR (8–16 G).
- Orbit + DEM fetch are run-time (network) steps; pre-stage for offline nodes.
- Update checks are disabled (`snap.versionCheck.interval=NEVER`) for batch use.
