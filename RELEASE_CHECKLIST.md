# 0.1.4 release validation

Release date: 2026-09-28. Changes are based on main commit `51679ea`.

## Verified locally

- [x] QGIS 3.40.5 / Qt5 / Python 3.12 on Windows: regression suite passes.
- [x] Actual GDAL-created CP949, UTF-8 and EUC-KR Shapefiles; missing/incorrect CPG and manual override.
- [x] Korean legacy ZIP names, nested ZIPs, independent failure reporting and local sheet symbols.
- [x] QGIS-generated QML, modern Option paths, old prop paths, QML without symbols and XML entity rejection.
- [x] Pattern multiplier and repeated application without compounding.
- [x] Pattern before/after preview with private clones, cancel behavior, intrinsic image sizes, manual style changes and exact rendered-image restoration at 1×.
- [x] Partial QML styles, local relative PNG paths, corrupt nested ZIP isolation and dot-prefixed archive paths.
- [x] Actual GeoTIFF/ASC export with category CSV, geographic-to-metric raster reprojection and NoData preservation.
- [x] Main dialog creation, vector export action and GeoChem conversion action.
- [x] Python syntax and focused E/F lint checks.

## Validation status and remaining follow-ups

- [ ] Run the included tests and plugin install/open/export flows on QGIS 4 / Qt6. No QGIS 4 runtime or Docker was available locally; the CI workflow has been prepared but has not run.
- [ ] Recheck with the user's original KIGAM ZIP or several representative current portal downloads. The incident ZIP was unavailable; fixtures reproduce the defects, but do not establish coverage of every KIGAM package.
- [ ] Visually compare pattern multipliers 1, 1.5, 2 and 3 on the user's map at 1:25,000, including the final print layout. Default 2 is a starting point, not a universal cartographic standard.
- [ ] Confirm the source geological field has consistent meaning across sheets and inspect `.categories.csv`. Mark IDs as categorical in MaxEnt.
- [x] Version and release date recorded in CHANGELOG, metadata and CITATION.
- [x] Build the installable ZIP and run all 35 regression tests against its code extracted into a fresh directory.
- [ ] Manually install/open the plugin through the QGIS plugin manager in a clean QGIS 4 profile.

## Compatibility policy

`qgisMinimumVersion=3.40`, `qgisMaximumVersion=4.99`. The upper bound admits QGIS 4.x in the plugin manager; it is not a test result for future versions. No obsolete `supportsQt6` flag is needed under the current [QGIS migration guidance](https://plugins.qgis.org/docs/migrate-qgis4).

## Scope and known limits

- The ZIP loader discovers Shapefiles, including nested ZIPs. GPKG, GDB, DXF and raster ZIP datasets are reported as unsupported. `kigam_api_client.py` remains an unused placeholder; no WMS/WFS catalogue enumeration is claimed.
- Encoding detection samples at most 256 records plus field names. Ambiguous byte sequences, mixed encodings within one DBF, and already-corrupted source strings need manual inspection.
- The multiplier handles raster polygon fills. Symbol layers with active data-defined properties are skipped and counted; external web-map styling still needs manual adjustment.
- Source files remain in the QGIS profile's `KIGAM_Extract` directory. Saved projects depend on those files; manage them with the project when moving machines.
- GeoChem is a legend-color estimate, not recovery of original measured concentrations. The chosen preset must match the source WMS legend. Unknown colors and changed server styles cannot be scientifically validated by the software tests.
- Extent selection uses bounding boxes. It does not clip to an irregular polygon boundary.
- ZIP limits: 2 GiB cumulative uncompressed data, 50,000 members, 4 nested levels. Raster output limit: 4 million pixels per operation.
- WMS export and interpolation remain synchronous; cancel is checked between processing phases rather than during each network request/GDAL call.

## Follow-up validation

The improved candidate adds 15 targeted tests (35 total). The comparison and preview images use synthetic polygons and textures rendered by QGIS at 1:25,000. They are not the user's original map. The QGIS 4 CI job now checks the actual major version, runs the installed ZIP's code and fails if the migration tool changes Python files; the remote job remains unexecuted locally.
