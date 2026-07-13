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

# Offline build smoke test: the real gate is that the stack imports. Versions
# come from conda metadata (`micromamba list`), not importlib.metadata — conda
# packages have no PEP-621 .dist-info, so importlib.metadata.version() fails for
# them even though the import works.
RUN python -c "import isce, mintpy; print('isce2 + mintpy import OK')" \
    && micromamba list -n base 2>/dev/null | grep -iE "^\s*(isce2|mintpy|gdal)\b" || true

ENTRYPOINT ["/usr/local/bin/isce2-insar"]
