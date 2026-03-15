# KIGAM for Archaeology

QGIS plugin for loading KIGAM 1:50,000 geological ZIP packages, applying
sidecar sym/QML styling, labeling lithology layers, and exporting analysis
rasters for archaeology workflows.

## Features

- Load downloaded KIGAM ZIP map packages directly into QGIS
- Apply symbol styles from `sym/` and sidecar `QML` files
- Relink image-based QML symbol paths after extraction
- Label lithology layers with configurable font settings
- Convert GeoChem RGB rasters into numeric rasters
- Export vector and raster layers for downstream analysis

## Install

### Install from ZIP

1. Open QGIS
2. Go to `Plugins -> Manage and Install Plugins...`
3. Open `Install from ZIP`
4. Select the release package `KigamGeoDownloader-0.1.2.zip`

### Development Install

This workspace is set up for live local development through a symbolic link:

- Local source:
  `/Users/hwangjinseo/Desktop/Coding/KigamGeoDownloader`
- QGIS plugin link:
  `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/KigamGeoDownloader`

After editing code in this folder, reload the plugin in QGIS or restart QGIS.

## Development Notes

- Git working branch: `plugin-root-dev`
- Remote: `https://github.com/lzpxilfe/KIGAM-for-Archaeology.git`
- Quality checks used for this workspace:
  - `flake8 .`
  - `bandit -q -r .`
  - `python3 -m compileall .`

## Release

- Current workspace release version: `0.1.2`
- QGIS upload package target:
  `~/Desktop/KigamGeoDownloader-0.1.2.zip`

## License

GPL-2.0. See [LICENSE](LICENSE).
