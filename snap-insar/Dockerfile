# snap-insar — Sentinel-1 InSAR via ESA SNAP 12 + the Sentinel-1 Toolbox:
# TOPS coregistration, interferogram, **coherence**, Goldstein filtering, and
# SNAPHU export/unwrap. ESA's official InSAR toolbox — non-ML geoprocessing →
# geo-pipelines. SNAP is a Java app from ESA's installer (not a conda package),
# so this recipe diverges from the micromamba base used elsewhere in the repo.
#
# SNAP 12 is pinned because it supports Sentinel-1C/1D (SNAP 9 predates them).

FROM debian:bookworm-slim

ARG SNAP_VERSION=12.0.0
ARG SNAP_URL=https://download.esa.int/step/snap/12.0/installers/esa-snap_all_linux-12.0.0.sh

RUN apt-get update && apt-get install -y --no-install-recommends \
        wget ca-certificates snaphu \
    && rm -rf /var/lib/apt/lists/*

# Headless (unattended) install to /opt/snap via the install4j response varfile.
COPY response.varfile /tmp/response.varfile
RUN wget -q "${SNAP_URL}" -O /tmp/snap.sh \
    && sh /tmp/snap.sh -q -varfile /tmp/response.varfile \
    && rm -f /tmp/snap.sh /tmp/response.varfile

# Don't let gpt phone home for module updates inside batch jobs.
RUN printf 'snap.versionCheck.interval=NEVER\n' >> /opt/snap/etc/snap.properties || true

ENV PATH=/opt/snap/bin:$PATH

COPY bin/snap-insar /usr/local/bin/snap-insar
RUN chmod +x /usr/local/bin/snap-insar

# Offline build smoke test: gpt initialises its module graph and prints help
# (exits 0). snaphu resolves on PATH for the unwrap step.
RUN /opt/snap/bin/gpt -h >/dev/null && echo "SNAP ${SNAP_VERSION} gpt OK" \
    && command -v snaphu

ENTRYPOINT ["/usr/local/bin/snap-insar"]
