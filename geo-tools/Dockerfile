# geo-tools — bounded GDAL/PDAL geoprocessing recipes for bradleylab research compute.
#
# KITCHEN-SINK EXCEPTION (per geo-pipelines/README.md "one pipeline per container"):
# this image intentionally bundles several bounded recipes (tiff->COG, laz->COPC,
# reproject, hillshade) instead of one-per-container. Reason: every recipe runs on
# the exact same pinned GDAL+PDAL base, so splitting would multiply the build,
# storage, and Compute2 .sqsh cost N-fold for no functional gain. Each recipe is
# still a single documented artifact-producing command dispatched by bin/geo-tools,
# and no recipe accepts a free-form gdal/pdal string.

FROM mambaorg/micromamba:1.5.10

USER root

# Matched GDAL + PDAL from conda-forge: GDAL ships the COG driver and
# DEFLATE/ZSTD/LZW codecs; PDAL ships the COPC reader/writer and the
# reprojection filter. Pin the minor series; the smoke test prints the exact
# resolved versions.
ARG GDAL_VERSION=3.9
ARG PDAL_VERSION=2.8
RUN micromamba install -y -n base -c conda-forge \
        "python=3.12" \
        "gdal=${GDAL_VERSION}" \
        "pdal=${PDAL_VERSION}" \
        "python-pdal" \
    && micromamba clean -a -y

# Put the conda env on PATH directly. On Compute2 the image runs via
# `srun ... bash -lc "<cmd>"`, which bypasses the micromamba entrypoint, so the
# tools must resolve without shell activation. PYTHONNOUSERSITE stops an enroot
# $HOME bind-mount from shadowing the pinned env.
ENV PATH=/opt/conda/bin:$PATH \
    GDAL_DATA=/opt/conda/share/gdal \
    PROJ_DATA=/opt/conda/share/proj \
    PYTHONNOUSERSITE=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY bin/geo-tools /usr/local/bin/geo-tools

# Offline build smoke test: python bindings import, the COG driver is present,
# both CLIs resolve, and the recipe dispatcher parses. No network, no data.
RUN chmod +x /usr/local/bin/geo-tools \
    && python -c "from osgeo import gdal; import pdal; assert gdal.GetDriverByName('COG') is not None, 'COG driver missing'; print('python bindings ok')" \
    && gdal_translate --version \
    && pdal --version \
    && geo-tools --help >/dev/null \
    && echo "geo-tools smoke test passed"

WORKDIR /work
ENTRYPOINT ["geo-tools"]
CMD ["--help"]

LABEL org.opencontainers.image.source="https://github.com/bradleylab/geo-pipelines"
LABEL org.opencontainers.image.description="bounded GDAL/PDAL geoprocessing recipes — tiff->COG, laz->COPC, reproject, hillshade"
LABEL org.opencontainers.image.licenses="Apache-2.0"
