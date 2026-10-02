#!/usr/bin/env cwl-runner
# satellite_fetch, described as a CWL v1.2 CommandLineTool for the image
# ghcr.io/bradleylab/satellite-fetch:v2, whose ENTRYPOINT takes --input-dir,
# --output-dir and --params-json (the geospatial executor's entrypoint contract
# v1). The staging layout and params.json are built from the typed inputs below,
# so an engine that honors the image ENTRYPOINT runs it as the executor does.
# Fields under gx: are the executor's extension for what CWL cannot say
# (fossettlab/geospatial-executor, docs/contracts/cwl-extensions-v1.md).
cwlVersion: v1.2
class: CommandLineTool
id: satellite_fetch
label: The clearest public satellite scene of a site, clipped to it
doc: |
  From a raster of a site, finds the HLS, Sentinel-2 L2A or Sentinel-1 RTC scene
  on Microsoft Planetary Computer that its own quality layer calls clearest over
  the site in the chosen year and months, and writes it clipped to the site's
  bounding box in the UTM zone of its center, with that quality layer and a
  report of every candidate scene. For HLS and Sentinel-2 it also writes a
  false-color PNG preview (SWIR 2, narrow NIR and red as red, green and blue).
  Sites longer than 25 km on a side are refused. Needs outbound HTTPS to
  Planetary Computer.

$namespaces:
  s: https://schema.org/
  gx: https://github.com/fossettlab/geospatial-executor/blob/main/docs/contracts/cwl-extensions-v1.md#

s:codeRepository: https://github.com/bradleylab/geo-pipelines
s:license: Apache-2.0
s:version: "2"
gx:model: satellite-fetch
gx:capability: fetch_imagery
gx:tags: [geoprocessing]
gx:output_kind: raster
gx:contract: 1

requirements:
  DockerRequirement:
    dockerPull: ghcr.io/bradleylab/satellite-fetch:v2
  NetworkAccess:
    networkAccess: true
  InlineJavascriptRequirement: {}
  InitialWorkDirRequirement:
    listing:
      # writable: the file is copied into place rather than bind-mounted
      # inside the output directory, a nested mount Docker Desktop refuses.
      - entryname: input/primary/$(inputs.site.basename)
        entry: $(inputs.site)
        writable: true
      # Contract v1 hands the image every value as a string.
      - entryname: params.json
        entry: |-
          ${
            return JSON.stringify({
              product: inputs.product,
              year: String(inputs.year),
              month_start: String(inputs.month_start),
              month_end: String(inputs.month_end)
            });
          }
  ResourceRequirement:
    coresMin: 2
    ramMin: 8192
  ToolTimeLimit:
    timelimit: 3600

inputs:
  site:
    type: File
    label: A GeoTIFF of the site, with a CRS; its footprint is the area fetched
    gx:kind: raster
    gx:primary: true
    gx:formats: [".tif", ".tiff"]
  product:
    type:
      type: enum
      symbols: [hls, sentinel2_l2a, sentinel1_rtc]
    default: sentinel2_l2a
    label: What to fetch
  # Contract 1 takes numbers as the registry's `number`, CWL float; the image
  # refuses any that is not whole.
  year:
    type: float
    label: The year to search
    gx:min: 2015
    gx:max: 2035
  month_start:
    type: float
    default: 1
    label: First month to search
    gx:min: 1
    gx:max: 12
  month_end:
    type: float
    default: 12
    label: Last month to search, inclusive
    gx:min: 1
    gx:max: 12

arguments:
  - --input-dir
  - $(runtime.outdir)/input
  - --output-dir
  - $(runtime.outdir)/output
  - --params-json
  - $(runtime.outdir)/params.json

outputs:
  imagery:
    type: File
    outputBinding: {glob: output/imagery.tif}
    gx:role: imagery
  # Written for the optical products only; Sentinel-1 RTC gets no preview.
  preview:
    type: File?
    outputBinding: {glob: output/imagery_preview.png}
    gx:role: preview
  quality:
    type: File?
    outputBinding: {glob: output/quality.tif}
    gx:role: quality
  report:
    type: File
    outputBinding: {glob: output/fetch_report.json}
    gx:role: report
  manifest:
    type: File
    outputBinding: {glob: output/run.json}
    gx:manifest: true
