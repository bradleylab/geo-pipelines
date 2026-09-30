# satellite-fetch — the clearest public satellite scene of a site, clipped to
# it: HLS, Sentinel-2 L2A or Sentinel-1 RTC from Microsoft Planetary Computer.
#
# One task, built to entrypoint contract v1 (fossettlab/geospatial-executor,
# docs/contracts/entrypoint-v1.md): the ENTRYPOINT takes --input-dir,
# --output-dir and --params-json and nothing else. The contract names no task,
# so this image carries exactly one. It needs outbound HTTPS to
# planetarycomputer.microsoft.com and its Azure blob storage at run time.

FROM mambaorg/micromamba:1.5.10

USER root

# The same pinned GDAL minor series as geo-tools and terrain-derivatives. The
# STAC client and Planetary Computer's signing package are the versions the
# recipe was tested with.
ARG GDAL_VERSION=3.9
RUN micromamba install -y -n base -c conda-forge \
        "python=3.12" \
        "gdal=${GDAL_VERSION}" \
        "numpy" \
        "pystac-client=0.9.0" \
        "planetary-computer=1.0.0" \
    && micromamba clean -a -y

# The conda env is on PATH for tools run inside the image. The entrypoint does
# not rely on it: a job step on Compute2 carries the host's PATH rather than
# this one, so the ENTRYPOINT is an absolute path whose interpreter line names
# /opt/conda/bin/python. PYTHONNOUSERSITE stops an enroot $HOME bind-mount from
# shadowing the env.
ENV PATH=/opt/conda/bin:$PATH \
    GDAL_DATA=/opt/conda/share/gdal \
    PROJ_DATA=/opt/conda/share/proj \
    PYTHONNOUSERSITE=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY bin/satellite-fetch /usr/local/bin/satellite-fetch

# Offline build check: the bindings and the STAC packages import, the COG
# driver and GDAL's HTTP reader are present, and the entrypoint parses even
# with an empty environment. No network.
RUN chmod +x /usr/local/bin/satellite-fetch \
    && python -c "from osgeo import gdal; import numpy, pystac_client, planetary_computer; assert gdal.GetDriverByName('COG') is not None, 'COG driver missing'; assert '/vsicurl/' in gdal.GetFileSystemsPrefixes(), 'GDAL built without its HTTP reader'" \
    && gdalinfo --version \
    && env -i /usr/local/bin/satellite-fetch --help >/dev/null \
    && echo "satellite-fetch build check passed"

WORKDIR /work
ENTRYPOINT ["/usr/local/bin/satellite-fetch"]

LABEL org.opencontainers.image.source="https://github.com/bradleylab/geo-pipelines"
LABEL org.opencontainers.image.description="The clearest HLS, Sentinel-2 L2A or Sentinel-1 RTC scene of a site from Microsoft Planetary Computer, clipped to it (entrypoint contract v1)"
LABEL org.opencontainers.image.licenses="Apache-2.0"
