# ortho-pipeline: drone image dir -> orthophoto + DSM/DTM + point cloud
#
# Thin wrapper over the official OpenDroneMap image. ODM already ships the full
# photogrammetry stack (OpenSfM, MVS, meshing, orthorectification, GDAL/PDAL);
# this layer only adds a clean `ortho-pipeline` CLI over ODM's run.py so the
# SLURM templates and the lab's dispatch story match the other geo-pipelines.
#
# CPU-only by default (ODM runs the whole chain on CPU). A GPU SIFT variant
# exists upstream (opendronemap/odm:gpu) but is not used here.

FROM opendronemap/odm:3.5.6

# Wrapper CLI. ODM's own entrypoint is /code/run.py; we call it from here.
COPY bin/ortho-pipeline /usr/local/bin/ortho-pipeline
RUN chmod +x /usr/local/bin/ortho-pipeline

# Build-time smoke test: ODM present and the wrapper parses. Offline, no GPU.
RUN test -f /code/run.py && python3 /usr/local/bin/ortho-pipeline --help >/dev/null

ENTRYPOINT ["ortho-pipeline"]
CMD ["--help"]
