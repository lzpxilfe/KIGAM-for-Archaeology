# Changelog

All notable changes to **KIGAM for Archaeology** are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).  
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [0.1.4] – 2026-09-28

### Fixed
- Apply DBF encodings through `setProviderEncoding`; invalid `|encoding=` OGR URIs previously discarded all explicit encoding candidates in QGIS 3.40.
- Validate CPG declarations and sample raw DBF bytes; add manual CP949 / UTF-8 / EUC-KR overrides.
- Decode legacy Korean ZIP filenames, discover bounded nested archives and associate each map sheet with its own symbols.
- Accept QGIS's inert DOCTYPE while rejecting entity declarations/internal subsets; support old `prop` and modern `Option` QML image paths, and QML without a sym directory.
- Isolate SHP/style failures, expose load counts and warnings, and retain extracted sources in the QGIS profile.
- Use metric output grids, explicit raster reprojection and pixel limits; preserve NoData during linework interpolation.
- Export geology as integer categories with UTF-8 CSV codebooks; convert GeoTIFF to ASC; reject mixed or multiple-raster selections instead of silently discarding them.
- Transform zoom extents into the map canvas CRS; list exportable vectors by fields rather than filenames; validate malformed config section types.

### Added
- Polygon raster-pattern multiplier (0.5–6×; default 2× as a starting point for 1:25,000), including existing selected layers and non-compounding updates.
- Side-by-side pattern preview at a shared scale; private layer clones keep cancel non-destructive. Restore original sizes, handle intrinsic pixel-sized images and rebase after manual style changes.
- Isolate corrupt nested ZIPs, support dot-prefixed ZIP paths and tolerate damaged optional Unicode filename metadata.
- Preserve valid QML categories/symbols when some PNGs are missing; resolve local relative image paths outside `sym/`; surface missing-symbol warnings in the dialog.
- Runtime regression suite, QGIS 3.40 / Qt6 CI configuration, release builder and validation checklist.
- Validated source and installable ZIP with 35 tests each on Linux QGIS 3.40.15 and QGIS 4.2.2/Qt6, in addition to Windows QGIS 3.40.5.

### Changed
- Minimum QGIS is now 3.40; maximum metadata version is 4.99. Qt imports and moved QGIS enums use current APIs. See RELEASE_CHECKLIST.md for tested runtimes and remaining compatibility limits.
- Class IDs are deterministic within one export and written to `.categories.csv`; raw alphanumeric geology codes are no longer passed to GDAL as numeric values.
- Citation metadata now matches version 0.1.4 and its release date.

---

## [0.1.3] – 2026-07-27

### Fixed
- **Korean text garbling when loading ZIP layers.**  
  The previous encoding-selection logic scored candidates solely by symbol-match count. Layers without symbols (Frame, Line, etc.) always tied at zero matches, causing CP949 to win by static preference even when the DBF file was encoded in UTF-8, producing mojibake.  
  A new heuristic text-quality scorer (`_score_text_quality`, `_layer_text_score`) now samples string-field values for each candidate encoding and rewards valid Hangul / ASCII while penalising Latin-1 artifacts and C1 control characters. Text quality is inserted as the secondary sort key, so the encoding that produces the most legible Korean text is selected automatically regardless of symbol availability.

### Changed
- **Default litho fill-symbol width raised from `10.0` mm to `50.0` mm** (`fill_symbol_width` in `plugin_config.json`).  
  At 1:50,000 scale the previous default produced a pattern too small to read comfortably. 50 mm gives a visually clear result; the value remains user-configurable via `plugin_config.json`.

---

## [0.1.2] – 2026-03-18

### Changed
- Plugin layout and file organisation synced with the ArchToolkit reference structure.
- README updated to reflect GPLv2 licensing and current behaviour.

### Fixed
- Version metadata pinned correctly after an earlier mis-tag.

---

## [0.1.1] – 2026-02-20

### Added
- **Help / Download Data button** — opens the KIGAM data portal in the system browser directly from the plugin dialog.

### Refactored
- `zip_processor.py`: hardened ZIP-loading workflow; symbol matching and layer-group creation made more robust against edge cases (missing sym folder, duplicate group names, invalid layers).
- Plugin constants (encodings, field priorities, symbol size, font defaults, …) externalised into `plugin_config.json` so users can tune behaviour without editing Python source.

### Fixed
- Raster export now honours the user-specified resolution instead of always falling back to a hard-coded default.
- Fallback path handling cleaned up to prevent silent failures.

---

## [0.1.0] – 2026-02-09

### Added
- **ZIP auto-loader** – extracts a KIGAM 1:50,000 geological-map ZIP, discovers all contained Shapefiles, and loads them into a named layer group in one click.
- **Automatic symbol styling** – matches shapefile attribute values to PNG files in the bundled `sym/` folder using multi-encoding fuzzy matching (CP949 / EUC-KR / UTF-8) and sidecar QML rewriting.
- **Litho layer labeling** – detects `litho` layers and applies Korean-font labels (`LITHOIDX` / `LITHONAME` field candidates) with configurable font family and size.
- **Layer organisation** – reorders loaded layers into Point → Line → Polygon → Reference (hidden) within the ZIP group automatically.
- **GeoChem raster analysis** – converts a vector litho layer to a categorical raster and exports it as GeoTIFF; supports configurable resolution and GDAL data type.
- **MaxEnt / Rasterize export** – rasterises the litho layer to ASC format for use with MaxEnt species-distribution modelling workflows.
- **Progress dialog** – shows a progress bar with cancellation support during long-running raster operations.
- **Legend-based GeoChem styling** – colours the output raster using the existing vector-layer category colours so the result is immediately interpretable.

### Fixed
- Preset keyboard shortcuts replaced with stable copies from the ArchToolkit reference to eliminate intermittent UI freezes.

---

## [0.0.1] – 2026-02-08 *(initial development)*

- Repository initialised.
- Proof-of-concept ZIP extraction and Shapefile loading implemented.
- Basic symbol-based categorised renderer applied from `sym/` PNGs.

[0.1.4]: https://github.com/lzpxilfe/KIGAM-for-Archaeology/releases/tag/v0.1.4
[0.1.3]: https://github.com/lzpxilfe/KIGAM-for-Archaeology/commit/51679ea
[0.1.2]: https://github.com/lzpxilfe/KIGAM-for-Archaeology/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/lzpxilfe/KIGAM-for-Archaeology/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/lzpxilfe/KIGAM-for-Archaeology/releases/tag/v0.1.0
[0.0.1]: https://github.com/lzpxilfe/KIGAM-for-Archaeology/commits/9d98ae7
