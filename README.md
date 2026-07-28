# 🗺️ KIGAM for Archaeology

> **한국지질자원연구원(KIGAM)** 지질도 ZIP과 지구화학(GeoChem) 래스터를 QGIS에서 한 번에 불러오고, 스타일링하고, 분석용 래스터로 내보내는 플러그인입니다.  
> 고고학적 유적 입지 분석·MaxEnt 종분포 모델링·지화학 이상대 탐지 등의 작업 흐름을 지원합니다.

[![QGIS Plugin Repository](https://img.shields.io/badge/QGIS_Plugin_Repository-4701-green?logo=qgis)](https://plugins.qgis.org/plugins/KigamGeoDownloader/)
[![Version](https://img.shields.io/badge/version-0.1.3-blue)](CHANGELOG.md)
[![License: GPL v2](https://img.shields.io/badge/License-GPL_v2-blue.svg)](LICENSE)
[![Star this repository](https://img.shields.io/github/stars/lzpxilfe/KIGAM-for-Archaeology?style=social)](https://github.com/lzpxilfe/KIGAM-for-Archaeology)

---

## 📌 한눈에 보기

| 항목 | 내용 |
|---|---|
| 버전 | `0.1.3` |
| 최소 QGIS | `3.0` |
| 플러그인 ID | `KigamGeoDownloader` |
| 라이선스 | `GPL-2.0` |
| Qt 호환성 | Qt5 / Qt6 (QGIS 3.x ~ 3.99) |

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
- QGIS에 로드된 WMS/WFS **지구화학도 래스터의 RGB 색상**을 원소 농도 수치로 변환합니다.
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

### 인코딩 자동 감지 (v0.1.3)

KIGAM ZIP의 DBF 파일은 CP949 또는 UTF-8로 인코딩되어 있을 수 있습니다.  
플러그인은 각 인코딩으로 레이어를 읽은 뒤, **한글 음절 포함 여부와 문자 품질 점수**를 계산해 가장 자연스러운 텍스트를 만드는 인코딩을 자동 선택합니다.

```
후보 인코딩: [CP949, EUC-KR, (기본), UTF-8]
           ↓ 각각 레이어 로드
           ↓ 한글 텍스트 품질 점수 계산
           ↓ 심볼 매칭 수 + 텍스트 품질 기준으로 최적 인코딩 선택
```

### 스타일 적용 우선순위

```
1순위  Sidecar .qml → 이미지 경로 재연결 → 로드
          ↓ 실패 시
2순위  sym/ 폴더 PNG + 속성값 매칭 → Categorized Renderer
          ↓ 해당 없음
3순위  기본 심볼 (랜덤 색상)
```

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
- 여러 지질도를 래스터로 병합할 때 **레이어 좌표계(CRS)** 가 일치하는지 확인하세요.
- 레이어 로딩 세부 내용은 QGIS **메시지 로그 패널** (뷰 → 패널 → 로그 메시지) 또는 다이얼로그 하단 **분석 로그**에서 확인할 수 있습니다.

---

## 🛠️ 개발 체크

```bash
flake8 .
python -m compileall .
```

---

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
