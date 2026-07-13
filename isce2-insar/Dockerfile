# isce2-insar — Sentinel-1 InSAR (interferogram + coherence) via ISCE2, with
# MintPy for optional time-series. Non-ML geoprocessing (the JPL InSAR stack) →
# geo-pipelines, not ml-containers. One pipeline per container: S1 TOPS
# interferometry. CPU image (ISCE2 has optional GPU modules; not built here).

FROM mambaorg/micromamba:1.5.10

USER root

# ISCE2 + MintPy from conda-forge (the maintained distribution of the JPL stack).
# Let the solver pick a compatible Python/GDAL; the smoke test prints what it got.
RUN micromamba install -y -n base -c conda-forge \
        isce2 \
        mintpy \
    && micromamba clean -a -y

# On Compute2 the image runs via `srun ... bash -lc`, which bypasses the
# micromamba entrypoint (no conda activation). The dispatch script sets the ISCE
# runtime env at run time (the site-packages path is Python-version specific, so
# it is resolved dynamically rather than hard-coded here).
ENV PATH=/opt/conda/bin:$PATH \
    GDAL_DATA=/opt/conda/share/gdal \
    PROJ_DATA=/opt/conda/share/proj \
    PYTHONNOUSERSITE=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY bin/isce2-insar /usr/local/bin/isce2-insar
RUN chmod +x /usr/local/bin/isce2-insar

# Offline build smoke test: import the stack and print resolved versions via
# importlib.metadata (never pkg.__version__ — lab rule).
RUN python -c "import isce; import mintpy; import importlib.metadata as im; \
print('isce2', im.version('isce2'), '| mintpy', im.version('mintpy'))"

ENTRYPOINT ["/usr/local/bin/isce2-insar"]
