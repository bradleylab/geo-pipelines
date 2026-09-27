# terrain-derivatives — slope, aspect, hillshade, roughness, TRI, TPI and
# contours from one elevation model.
#
# One task, built to entrypoint contract v1 (fossettlab/geospatial-executor,
# docs/contracts/entrypoint-v1.md): the ENTRYPOINT takes --input-dir,
# --output-dir and --params-json and nothing else. The contract names no task,
# so this image carries exactly one.

FROM mambaorg/micromamba:1.5.10

USER root

# The same pinned GDAL minor series as geo-tools and ground-surfaces, so a
# hillshade built here and one built by geo-tools come from the same library.
ARG GDAL_VERSION=3.9
RUN micromamba install -y -n base -c conda-forge \
        "python=3.12" \
        "gdal=${GDAL_VERSION}" \
        "numpy" \
    && micromamba clean -a -y

# The conda env is on PATH for tools run inside the image. The entrypoint does
# not rely on it: a job step on Compute2 carries the host's PATH rather than
# this one. So the ENTRYPOINT is an absolute path, its interpreter line names
# /opt/conda/bin/python, and it calls gdal_contour beside that interpreter.
# PYTHONNOUSERSITE stops an enroot $HOME bind-mount from shadowing the env.
ENV PATH=/opt/conda/bin:$PATH \
    GDAL_DATA=/opt/conda/share/gdal \
    PROJ_DATA=/opt/conda/share/proj \
    PYTHONNOUSERSITE=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY bin/terrain-derivatives /usr/local/bin/terrain-derivatives

# Offline build check: the bindings import, the COG and GeoPackage drivers are
# present, gdal_contour sits where the entrypoint calls it, and the entrypoint
# parses even with an empty environment. No network, no data.
RUN chmod +x /usr/local/bin/terrain-derivatives \
    && python -c "from osgeo import gdal, ogr; import numpy; assert gdal.GetDriverByName('COG') is not None, 'COG driver missing'; assert ogr.GetDriverByName('GPKG') is not None, 'GPKG driver missing'" \
    && test -x /opt/conda/bin/gdal_contour \
    && gdalinfo --version \
    && env -i /usr/local/bin/terrain-derivatives --help >/dev/null \
    && echo "terrain-derivatives build check passed"

WORKDIR /work
ENTRYPOINT ["/usr/local/bin/terrain-derivatives"]

LABEL org.opencontainers.image.source="https://github.com/bradleylab/geo-pipelines"
LABEL org.opencontainers.image.description="Slope, aspect, hillshade, roughness, TRI, TPI and contours from one elevation model (entrypoint contract v1)"
LABEL org.opencontainers.image.licenses="Apache-2.0"
