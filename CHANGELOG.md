# Changelog

All notable changes to **KIGAM for Archaeology** are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).  
Versioning follows [Semantic Versioning](https://semver.org/).

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

[0.1.3]: https://github.com/lzpxilfe/KIGAM-for-Archaeology/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/lzpxilfe/KIGAM-for-Archaeology/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/lzpxilfe/KIGAM-for-Archaeology/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/lzpxilfe/KIGAM-for-Archaeology/releases/tag/v0.1.0
[0.0.1]: https://github.com/lzpxilfe/KIGAM-for-Archaeology/commits/9d98ae7
