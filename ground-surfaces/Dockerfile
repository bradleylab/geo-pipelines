# ground-surfaces — DTM, DSM and canopy height from one lidar file.
#
# One task, built to entrypoint contract v1 (fossettlab/geospatial-executor,
# docs/contracts/entrypoint-v1.md): the ENTRYPOINT takes --input-dir,
# --output-dir and --params-json and nothing else. The contract names no task,
# so this image carries exactly one; it is not a geo-tools subcommand.

FROM mambaorg/micromamba:1.5.10

USER root

# The same pinned GDAL + PDAL minor series as geo-tools, so a surface built here
# and one built by laz_to_dem come from the same libraries.
ARG GDAL_VERSION=3.9
ARG PDAL_VERSION=2.8
RUN micromamba install -y -n base -c conda-forge \
        "python=3.12" \
        "gdal=${GDAL_VERSION}" \
        "pdal=${PDAL_VERSION}" \
        "python-pdal" \
    && micromamba clean -a -y

# The conda env is on PATH for tools run inside the image. The entrypoint does
# not rely on it: a job step on Compute2 carries the host's PATH rather than
# this one, and there a `#!/usr/bin/env python3` entrypoint could not find its
# interpreter. So the ENTRYPOINT is an absolute path and its interpreter line
# names /opt/conda/bin/python.
# PYTHONNOUSERSITE stops an enroot $HOME bind-mount from shadowing the env.
ENV PATH=/opt/conda/bin:$PATH \
    GDAL_DATA=/opt/conda/share/gdal \
    PROJ_DATA=/opt/conda/share/proj \
    PYTHONNOUSERSITE=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY bin/ground-surfaces /usr/local/bin/ground-surfaces

# Offline build check: the bindings the recipe uses import, the COG driver is
# present, the entrypoint parses even with an empty environment, and the SMRF
# defaults the recipe reports are the ones this PDAL applies (window is not
# listed by PDAL; it is 18 * cell). No network, no data.
RUN chmod +x /usr/local/bin/ground-surfaces \
    && python -c "from osgeo import gdal; import pdal, numpy; assert gdal.GetDriverByName('COG') is not None, 'COG driver missing'" \
    && pdal --version \
    && pdal --options filters.smrf --showjson | python -c "import json, sys; listed = {o['name']: o.get('default') for o in json.load(sys.stdin)[1]}; expected = {'slope': '0.15', 'scalar': '1.25', 'threshold': '0.5', 'cell': '1', 'returns': 'last, only'}; wrong = {k: listed.get(k) for k, v in expected.items() if listed.get(k) != v}; assert not wrong, f'PDAL SMRF defaults changed: {wrong}'" \
    && env -i /usr/local/bin/ground-surfaces --help >/dev/null \
    && echo "ground-surfaces build check passed"

WORKDIR /work
ENTRYPOINT ["/usr/local/bin/ground-surfaces"]

LABEL org.opencontainers.image.source="https://github.com/bradleylab/geo-pipelines"
LABEL org.opencontainers.image.description="DTM, DSM and canopy height model from one lidar file (entrypoint contract v1)"
LABEL org.opencontainers.image.licenses="Apache-2.0"
