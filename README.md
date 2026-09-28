# 🗺️ KIGAM for Archaeology

> **한국지질자원연구원(KIGAM)** 지질도 ZIP과 지구화학(GeoChem) 래스터를 QGIS에서 한 번에 불러오고, 스타일링하고, 분석용 래스터로 내보내는 플러그인입니다.  
> 고고학적 유적 입지 분석·MaxEnt 종분포 모델링·지화학 이상대 탐지 등의 작업 흐름을 지원합니다.

[![QGIS Plugin Repository](https://img.shields.io/badge/QGIS_Plugin_Repository-4701-green?logo=qgis)](https://plugins.qgis.org/plugins/KigamGeoDownloader/)
[![Version](https://img.shields.io/badge/version-0.1.4-blue)](CHANGELOG.md)
[![License: GPL v2](https://img.shields.io/badge/License-GPL_v2-blue.svg)](LICENSE)
[![Star this repository](https://img.shields.io/github/stars/lzpxilfe/KIGAM-for-Archaeology?style=social)](https://github.com/lzpxilfe/KIGAM-for-Archaeology)

---

## 📌 한눈에 보기

| 항목 | 내용 |
|---|---|
| 버전 | `0.1.4` |
| 최소 QGIS | `3.40` |
| 플러그인 ID | `KigamGeoDownloader` |
| 라이선스 | `GPL-2.0` |
| Qt 호환성 | Qt5 / Qt6 (허용 범위 3.40 ~ 4.99, 검증: Windows 3.40.5 / Linux 3.40.15·4.2.2) |

---

## ✨ 주요 기능

### 📦 1. 지질도 ZIP 자동 로드
- KIGAM에서 받은 1:50,000 지질도 **ZIP 파일을 바로 QGIS에 로드**합니다.
- ZIP 여러 개를 한 번에 선택해 **일괄 로드**할 수 있습니다.
- 로드된 레이어는 ZIP 이름으로 **전용 레이어 그룹**에 자동 정리됩니다.
- 레이어 순서를 자동 배치합니다: 점(Point) → 선(Line) → 면(Polygon) → 참조(Reference, 숨김)

### 🎨 2. 심볼 & 스타일 자동 적용
- ZIP 내 `sym/` 폴더의 **PNG 심볼**을 속성 값과 매칭해 카테고리 렌더러로 적용합니다.
- **Sidecar `.qml` 파일**이 있으면 이를 우선 적용하고, 이미지 경로를 추출 폴더 기준으로 자동 재연결합니다.
- **CP949 · EUC-KR · UTF-8 혼재 환경** 자동 감지: 한글 텍스트 품질 점수(Hangul scoring)로 올바른 인코딩을 선택합니다.
- `litho` 키워드가 포함된 레이어에 **암상 코드 라벨**을 자동 설정합니다 (글꼴·크기 조정 가능).
- **Fill 심볼 기본 너비 50 mm** — 1:50,000 스케일에서 패턴이 선명하게 보입니다.

### 🔬 3. 지구화학(GeoChem) RGB → 수치 래스터 변환
- QGIS에 로드된 WMS **지구화학도 래스터의 RGB 색상**을 원소 농도 수치로 변환합니다.
- 분석 범위를 **벡터 레이어로 제한**하거나 전체 화면으로 처리할 수 있습니다.
- **출력 해상도(m)** 를 직접 설정합니다 (기본 30 m).
- 결과 수치 래스터는 **범례 기반 의사색(Pseudo-color)** 스타일로 QGIS에 바로 로드됩니다.

**내장 원소 프리셋:**

| 프리셋 | 대상 원소 |
|---|---|
| Fe₂O₃ | 철(산화철) |
| Pb | 납 |
| Cu | 구리 |
| Zn | 아연 |
| Sr | 스트론튬 |
| Ba | 바륨 |
| CaO | 산화칼슘 |

### 🌍 4. 래스터 변환 및 내보내기 (Rasterize / ASC)
- 선택한 **벡터 지질 레이어**를 래스터화합니다 (`LITHOIDX`, `LITHONAME`, `TYPE`, `CODE` 등 필드 자동 탐지).
- **여러 레이어를 하나로 병합**해 내보냅니다.
- **지구화학 수치 래스터**도 선택해 해상도 재조정 후 내보낼 수 있습니다.
- 출력 포맷: **GeoTIFF (`.tif`)** 또는 **ASCII Grid (`.asc`, MaxEnt 호환)**

---

## 🚀 빠른 시작

### 1. 데이터 준비
플러그인의 **KIGAM 데이터 다운로드 페이지 열기** 버튼을 클릭하거나, 아래 주소에서 직접 다운로드합니다.

> 🔗 https://data.kigam.re.kr/search?subject=Geology

### 2. 지질도 불러오기
1. QGIS 메뉴 → **플러그인 → KIGAM Tools** 실행
2. ZIP 파일을 선택 (여러 개 동시 선택 가능)
3. 라벨 **글꼴**과 **크기** 설정
4. **자동 로드 및 스타일 적용** 클릭
5. 완료 후 지도가 해당 영역으로 자동 이동합니다

### 3. 지구화학 분석 (선택)
1. WMS로 불러온 지구화학도 레이어 선택
2. 분석 범위(대상지) 설정 — 벡터 레이어 or 전체 화면
3. 원소 프리셋과 해상도 설정
4. **RGB 래스터 수치화 실행** 클릭

### 4. 래스터 내보내기 (선택)
1. **래스터 변환 및 내보내기** 섹션 펼치기
2. 내보낼 레이어 체크 선택 (지질도 벡터 or 수치화 래스터)
3. 해상도 설정 후 **선택한 레이어를 래스터로 내보내기** 클릭
4. 저장 경로와 포맷 선택

---

## 📥 설치 방법

### QGIS 플러그인 저장소에서 설치 (권장)

**플러그인 → 플러그인 관리 및 설치** → "KIGAM" 검색 → **KIGAM for Archaeology** 설치

### ZIP으로 직접 설치

1. [최신 릴리스](https://github.com/lzpxilfe/KIGAM-for-Archaeology/releases)에서 `KIGAM_for_Archaeology_vX.X.X.zip` 다운로드
2. **플러그인 → 플러그인 관리 및 설치 → ZIP에서 설치** 탭 선택
3. 다운로드한 ZIP 파일 선택 후 설치

### 개발용 설치

QGIS 플러그인 디렉터리에 저장소를 클론합니다.

```bash
# Windows
git clone https://github.com/lzpxilfe/KIGAM-for-Archaeology.git ^
  "%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\KigamGeoDownloader"

# macOS / Linux
git clone https://github.com/lzpxilfe/KIGAM-for-Archaeology.git \
  ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/KigamGeoDownloader
```

코드를 수정한 뒤에는 QGIS Plugin Reloader를 사용하거나 QGIS를 재시작합니다.

---

## ⚙️ 동작 설명

### 인코딩과 ZIP 처리 (v0.1.4)

1. ZIP의 UTF-8 표시와 Unicode Path 정보를 우선 사용하고, 기존 한글 파일명은 CP949로 복원합니다. 중첩 ZIP도 탐색합니다.
2. 각 SHP의 CPG 선언을 최대 256개 DBF 레코드와 필드명으로 검사합니다. 선언이 없거나 모순되면 엄격한 UTF-8 → CP949 디코딩 순서로 확인합니다. CP949에는 EUC-KR 문자 집합이 포함됩니다.
3. `QgsVectorLayer.setProviderEncoding()`으로 실제 provider 인코딩을 설정합니다. 속성 문자열을 추측으로 다시 써서 원본을 바꾸지 않습니다.
4. 자동 판정이 맞지 않으면 **속성 인코딩**에서 CP949 / UTF-8 / EUC-KR을 직접 선택해 다시 불러옵니다. 두 인코딩으로 모두 읽히는 데이터나 파일 내부 혼합 인코딩은 완전 자동 판별할 수 없습니다.

각 도엽에 가까운 `sym/` 폴더를 사용합니다. 발견/성공/실패 SHP 수와 실패 이유는 분석 로그에 표시됩니다. 지원 범위는 **Shapefile ZIP**입니다. GPKG·GDB·DXF·래스터 ZIP이나 KIGAM 웹 서비스 전체 카탈로그를 자동으로 가져오는 기능은 아닙니다.

### 1:25,000 지도에서 패턴 조절

- **패턴 확대 2배**로 시작하고 지도를 보면서 1.5~3배 범위로 조절하세요. 실제 모양은 원본 PNG/QML의 타일 크기·단위와 출력 DPI에 따라 달라집니다.
- 이미 불러온 면 레이어는 레이어 패널에서 선택한 뒤 **선택한 면 레이어에 패턴 확대 적용**을 누르면 됩니다. 같은 배율을 반복해도 누적 확대되지 않습니다.
- **현재 스타일과 나란히 비교…**를 누르면 현재 스타일과 변경안을 같은 축척으로 비교합니다. 기본 1:25,000이며 1:10,000·1:50,000·1:100,000도 선택할 수 있습니다. **원본 레이어에 적용** 전까지는 복제본만 바뀌며, 취소하면 원본은 그대로입니다.
- **원래 크기 (1배)**로 되돌릴 수 있습니다. 수동으로 심볼 크기나 스타일을 바꾼 뒤에는 그 크기를 새 기준으로 사용합니다. 타일 크기가 0으로 지정된 원본 픽셀 크기 모드도 지원합니다.
- 배율은 래스터 면 패턴에 적용합니다. 점 심볼·선·라벨·단색 면에는 적용하지 않습니다. QML에 두 치수가 지정된 타일은 가로·세로를 함께 확대합니다.
- 데이터 정의가 있는 면 패턴은 표현식을 보존하기 위해 배율 적용에서 제외하고 개수를 표시합니다.
- 인터넷 지도의 배경지도·투명도·경계선·라벨을 그대로 복제하는 기능은 아닙니다. 인쇄 레이아웃에서도 최종 크기를 확인하세요.

### 스타일 적용 우선순위

```
1순위  Sidecar .qml → 이미지 경로 재연결 → 로드
          ↓ 실패 시
2순위  sym/ 폴더 PNG + 속성값 매칭 → Categorized Renderer
          ↓ 해당 없음
3순위  기본 심볼 (랜덤 색상)
```

QML의 일부 PNG가 없거나 읽을 수 없어도 나머지 범주·심볼·라벨은 보존하며, 누락된 래스터 심볼만 기본 심볼로 대체합니다. `sym/` 외에 QML과 같은 자료 폴더에 있는 상대 이미지 경로도 인식합니다. 손상된 중첩 ZIP은 경고 후 건너뛰고 정상 도엽은 계속 읽습니다. 전체 압축 해제 용량·항목 한도 초과는 작업을 중단합니다.

### 커스터마이즈 (`plugin_config.json`)

플러그인 폴더의 `plugin_config.json`을 편집해 동작을 변경할 수 있습니다.

```json
{
  "zip_processor": {
    "fill_symbol_width": 50.0,
    "marker_symbol_size": 6.0,
    "candidate_encodings": ["CP949", "EUC-KR", null, "UTF-8"],
    "symbol_priority_fields": ["LITHOIDX", "TYPE", "ASGN_CODE", "SIGN", "CODE"]
  },
  "ui": {
    "label_font": {
      "default_family": "Malgun Gothic",
      "default_size": 10
    }
  }
}
```

---

## ⚠️ 알아두면 좋은 점

- `sym/` 폴더가 없어도 레이어는 로드됩니다 (스타일만 미적용).
- GeoChem 분석은 **원본 WMS 범례 색상**을 기준으로 수치를 역추정합니다. 서버 스타일이 바뀌면 결과도 달라질 수 있습니다.
- 지질 래스터는 지질 코드를 정렬한 정수 ID로 저장하며, 같은 이름의 `.categories.csv`에 대응표를 기록합니다. ID는 서열/농도가 아닌 범주입니다. MaxEnt에서는 범주형 변수로 지정하고, 서로 다른 내보내기 결과를 비교할 때는 대응표를 확인하세요.
- 여러 벡터의 좌표계는 출력 CRS에 맞춰 변환합니다. 미터 단위 CRS를 유지하고, 경위도·피트 단위 입력은 한국 지역용 EPSG:5186으로 변환합니다. 선택한 대상지의 **경계 상자**를 사용하며 폴리곤 마스킹은 하지 않습니다.
- 벡터와 래스터 혼합 선택 또는 여러 래스터 동시 내보내기는 허용하지 않습니다. GeoTIFF와 ASC를 지원하며, ASC는 중간 GeoTIFF에서 변환합니다.
- 요청당 출력 한도는 400만 픽셀입니다. ZIP은 전체 중첩 구조 기준 2 GiB·50,000개 항목·4단계 중첩으로 제한합니다.
- 추출 자료는 QGIS 프로필의 `KIGAM_Extract` 폴더에 보존합니다. 저장한 프로젝트가 이 경로를 참조하므로 해당 폴더를 지우거나 다른 컴퓨터로 프로젝트만 옮기면 연결이 끊깁니다. 프로젝트 공유 시 원본 자료도 함께 관리하세요.
- 레이어 로딩 세부 내용은 QGIS **메시지 로그 패널** (뷰 → 패널 → 로그 메시지) 또는 다이얼로그 하단 **분석 로그**에서 확인할 수 있습니다.

---

## 🛠️ 개발 체크

```bash
# QGIS Python 환경에서 실행
python tests/run_tests.py
python -m compileall -q .
# 일반 Python 환경에서 정적 검사 / 설치 ZIP 생성
python -m ruff check --select E,F --ignore E501 .
python tools/build_release.py
```

---

검증 범위와 배포 전 남은 항목은 [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)를 참고하세요.
GitHub Actions에서 QGIS 3.40.15와 QGIS 4.2.2/Qt6의 소스·설치 ZIP 각각 35개 회귀 테스트를 통과했습니다. Windows QGIS 3.40.5도 검증했습니다. 4.99는 메타데이터의 허용 상한이며, 향후 모든 4.x 버전의 실행을 보증하는 값은 아닙니다.

## 🔗 링크

- **QGIS Plugin Repository**: https://plugins.qgis.org/plugins/KigamGeoDownloader/
- **Repository**: https://github.com/lzpxilfe/KIGAM-for-Archaeology
- **Issues / Feature requests**: https://github.com/lzpxilfe/KIGAM-for-Archaeology/issues
- **KIGAM 데이터 포털**: https://data.kigam.re.kr/search?subject=Geology

---

## 📄 라이선스

`GPL-2.0` — 자세한 내용은 [LICENSE](LICENSE)를 참고하세요.

---

## Citation

이 저장소가 연구, 수업, 현장 업무에 도움이 되었다면 GitHub의 **Cite this repository** 버튼으로 인용해 주세요.

[![Cite this repository](https://img.shields.io/badge/Cite_this-repository-2ea44f?logo=github)](https://github.com/lzpxilfe/KIGAM-for-Archaeology)

인용 메타데이터는 [CITATION.cff](CITATION.cff)에 보관합니다.
