# 0.1.6 업로드 준비

- [x] 2026-11-20에 KIGAM 다목적 지구화학도 WMS의 7개 레이어 ID, 기본 스타일, 공개 PNG 응답과 공식 범례 이미지 주소를 확인했습니다.
- [x] Windows QGIS 3.40.3에서 KIGAM WMS 7개를 불러와 동일한 시험 범위에서 재투영했습니다. 원소별로 RGBA를 읽고 1~10등급을 모두 포함하는 GeoTIFF와 구간 CSV 저장을 확인했습니다.
- [x] 같은 WMS 표본 7개에서 보간 전후를 비교했습니다. 검은 경계선으로 판정한 셀에만 원본 등급을 채웠고 기존 등급과 회색 무자료, 흰색 및 투명 배경을 보존했습니다.
- [x] 회귀 테스트로 7종의 등급 색 70개와 CSV 경계값 70개, 원소·스타일 검증, NoData 사유 분리, 재내보내기 시 최근접 등급 보존을 확인합니다.
- [x] 실제 1:50,000 지질도 ZIP 4개에서 37개 레이어를 불러오고, 지질 분류 GeoTIFF와 대응 CSV를 저장했습니다. README 시연은 실제 도엽과 WMS의 일부를 표시하며 지명, 좌표, 도엽명과 파일 경로를 가렸습니다.
- 배포 ZIP은 QGIS 3.40 및 4.x의 새 프로필에서 설치와 활성화를 확인합니다. 검증에는 소스 및 설치 ZIP 회귀 테스트, Qt6 호환성 검사와 로컬 Bandit, detect-secrets, Flake8 및 ZIP 구조 검사를 사용합니다.
- [ ] QGIS 플러그인 저장소 업로드 후 서버 검사 결과와 승인 상태를 확인합니다.

[공식 WMS 메타데이터](https://data.kigam.re.kr/mgeo/geoserver/Geochemical_map/wms?service=WMS&request=GetCapabilities&version=1.3.0)

---

# 0.1.6 release validation

- [x] Run all 52 regression tests on Windows with QGIS 3.40.3 / Qt 5 and QGIS 4.2.3 / Qt 6, against both the source tree and the extracted installation ZIP.
- [x] Compare Float32 GeoTIFF and ASCII Grid cell values, verify exact shared grids, and exercise independent codebooks and rollback after a failed file replacement.
- [x] Exercise the QGIS WMS provider with a local WMS fixture and verify RGB export, transparency, off-legend colors, the lowest valid interval, and optional linework filling.
- [x] Verify QML symbology import without form or action settings, image path precedence, and cleanup after ZIP imports that register no layers.
- [ ] Check the preset palettes against the current KIGAM WMS and repeat the workflow with a current portal download.

---

# 0.1.5 release validation

Release date: 2026-10-21. Changes are based on main commit `3877927`.

## Verified locally
- [x] QGIS 3.40.5 / Qt5 / Python 3.12 on Windows: regression suite (36 tests) passes.
- [x] Actual user-supplied 1:50,000 KIGAM ZIP: all 10 Shapefiles loaded with QML styles and symbol path relinking without `charmap` encode errors.
- [x] Pre-decoded unicode filename handling without UTF-8 flag (0x7075 Info-ZIP extra field) test added and verified.
- [x] Version and release date recorded in `metadata.txt`, `CHANGELOG.md`, `CITATION.cff`, `README.md`.

---

# 0.1.4 release validation

Release date: 2026-09-28. Changes are based on main commit `51679ea`.

## Verified locally and in CI

- [x] QGIS 3.40.5 / Qt5 / Python 3.12 on Windows: regression suite passes.
- [x] Linux CI: QGIS 3.40.15 / Qt5 and QGIS 4.2.2 / Qt6 each pass all 35 tests against both the source tree and the installable ZIP.
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

- [x] Run the included QGIS 4 / Qt6 tests in CI, including dialog construction, preview isolation and raster export actions.
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

The release includes 35 regression tests. The comparison and preview images use synthetic polygons and textures rendered by QGIS at 1:25,000. They are not the user's original map. The QGIS 4 CI job checks the actual major version, runs the installed ZIP's code and fails if the migration tool changes Python files. Test fixtures also work with PYTHONOPTIMIZE=2, used by the Qt6 image. No original incident ZIP or manual QGIS 4 plugin-manager installation was available for validation.
