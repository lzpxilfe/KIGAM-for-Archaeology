# KIGAM for Archaeology (QGIS Plugin) v0.1.4

KIGAM 1:50,000 수치지질도 ZIP을 QGIS로 불러오고, `sym`/`qml` 기반 심볼링을 적용한 뒤 지구화학 수치화와 래스터 내보내기까지 지원하는 플러그인입니다.

## 주요 기능

### 1. 지질도 ZIP 로드 + 심볼링
- ZIP 다중 선택 로드 지원
- 로드 후 플러그인 창을 자동으로 닫지 않음
- ZIP별로 **독립 그룹** 생성 (이전 로드 그룹과 혼합 방지)
- `sym` 폴더 PNG와 레이어 속성값 자동 매칭
- `qml`의 `imageFile` 경로를 추출 경로로 자동 relink
- 인코딩 후보를 비교해 로딩하며 `CP949/EUC-KR` 우선 처리

### 2. GeoChem RGB -> Value 변환
- WMS 래스터 RGB 색상을 수치 래스터로 변환
- Fe2O3, Pb, Cu, Zn, Sr, Ba, CaO 프리셋 제공
- 대상지 레이어 범위 + 해상도 기반 출력

### 3. Rasterize / Export
- 지질도 벡터(설정된 후보 필드) 래스터화
- 수치화 래스터 GeoTIFF/ASC 저장

## 설치

### QGIS에서 ZIP 설치
1. GitHub Releases에서 플러그인 ZIP 다운로드
2. QGIS 메뉴 `플러그인 > 플러그인 관리 및 설치 > ZIP 파일에서 설치`
3. 다운로드한 ZIP 선택

### 개발 설치
1. 저장소를 클론
2. `KigamGeoDownloader` 폴더를 QGIS 플러그인 경로에 복사
3. QGIS 재시작 후 플러그인 활성화

## 사용 방법

1. QGIS에서 `KIGAM Tools` 실행
2. `2. 지질도 불러오기`에서 ZIP 1개 이상 선택 후 로드
3. `3. 지구화학 분석`에서 WMS/프리셋/대상지/해상도 선택 후 변환
4. `4. 래스터 변환 및 내보내기`에서 분석용 래스터 저장

## 트러블슈팅

- 로그 패널에 `Plugin runtime: ... (version ...)`가 표시됩니다.
  - 실제 실행 중인 플러그인 경로/버전 확인용입니다.
- `?` 심볼/라벨이 보이면:
  - ZIP 내부 `sym` 폴더 존재 여부 확인
  - 해당 레이어 `.qml` 존재 여부 확인
  - 인코딩이 강제로 UTF-8로 고정되지 않았는지 확인
- ZIP을 여러 개 불러올 때 그룹이 합쳐지면:
  - 최신 버전(0.1.4) 적용 여부를 먼저 확인하세요.

## 설정 파일 (하드코딩 제거)

- 경로: `KigamGeoDownloader/plugin_config.json`
- 주요 설정:
  - `zip_processor.symbol_priority_fields`
  - `zip_processor.candidate_encodings`
  - `zip_processor.marker_symbol_size`
  - `zip_processor.fill_symbol_width`
  - `raster.vector_export_field_candidates`
  - `raster.nodata`
- 코드 수정 없이 위 값을 바꿔 동작을 조정할 수 있습니다.

## 개발/패키징

```bash
python create_package.py
```

`metadata.txt`의 버전을 읽어 바탕화면에 `KIGAM_for_Archaeology_v<version>.zip`를 생성합니다.

## Citation

이 저장소에는 `CITATION.cff`가 포함되어 있습니다.  
학술/보고서 인용 시 `CITATION.cff` 또는 아래 BibTeX를 사용하세요.

```bibtex
@software{kigam_for_archaeology,
  author = {balguljang2 (lzpxilfe)},
  title = {KIGAM for Archaeology: QGIS Plugin for Geological Map and GeoChem Workflows},
  year = {2026},
  url = {https://github.com/lzpxilfe/KIGAM-for-Archaeology}
}
```

## Star 부탁

프로젝트가 도움이 되었다면 GitHub Star를 부탁드립니다.  
짧은 사용 피드백이나 이슈 리포트도 큰 도움이 됩니다.

자세한 문구는 `SUPPORT.md`를 참고하세요.

## License

GNU GPL v3
