# 🗺️ KIGAM for Archaeology

> KIGAM 지질도 ZIP과 GeoChem 지구화학 래스터를 QGIS에서 빠르게 불러오고, 스타일링하고, 분석용 래스터로 내보내기 위한 플러그인입니다.

## 📌 한눈에 보기

| 항목 | 내용 |
| --- | --- |
| 버전 | `0.1.2` |
| 최소 QGIS 버전 | `3.0` |
| 배포 패키지 | `KigamGeoDownloader-0.1.2.zip` |
| 라이선스 | `GPL-2.0` |

## ✨ 주요 기능

- 📦 KIGAM에서 받은 지질도 ZIP 파일을 QGIS에 바로 불러옵니다.
- 🗂️ ZIP 여러 개를 한 번에 선택해서 연속으로 로드할 수 있습니다.
- 🎨 `sym/` 폴더의 PNG 심볼과 sidecar `.qml` 스타일을 자동으로 적용합니다.
- 🔁 추출된 폴더 기준으로 QML 내부 이미지 경로를 다시 연결해 스타일 깨짐을 줄입니다.
- 🇰🇷 CP949, EUC-KR, UTF-8 등 한글 인코딩 차이를 고려해 심볼 매칭 정확도를 높입니다.
- 🏷️ 암상 레이어에 라벨을 자동으로 적용하고 글꼴/크기를 조정할 수 있습니다.
- 🔬 GeoChem RGB 래스터를 수치 래스터로 변환할 수 있습니다.
- 🧪 `Fe2O3`, `Pb`, `Cu`, `Zn`, `Sr`, `Ba`, `CaO` 프리셋을 제공합니다.
- 🌍 선택한 벡터/래스터 레이어를 GeoTIFF 또는 ASCII Grid로 내보낼 수 있습니다.

## 🚀 빠른 시작

1. QGIS에서 플러그인을 실행합니다.
2. `KIGAM 데이터 다운로드 페이지 열기` 버튼으로 KIGAM 사이트를 엽니다.
3. 필요한 지질도 ZIP을 내려받습니다.
4. 플러그인에서 ZIP 파일을 하나 이상 선택합니다.
5. 라벨 글꼴과 크기를 정한 뒤 `자동 로드 및 스타일 적용`을 누릅니다.
6. 필요하면 GeoChem 분석이나 래스터 내보내기까지 이어서 진행합니다.

## 📥 설치 방법

### ZIP으로 설치

1. QGIS를 엽니다.
2. `Plugins -> Manage and Install Plugins...`로 이동합니다.
3. `Install from ZIP` 탭을 엽니다.
4. 배포 파일 `KigamGeoDownloader-0.1.2.zip`을 선택합니다.

### 개발용 설치

QGIS 플러그인 디렉터리의 `python/plugins/KigamGeoDownloader` 위치에 이 저장소를 복사하거나 심볼릭 링크로 연결하면 로컬 개발이 가능합니다.

예시:

```bash
ln -s /path/to/KigamGeoDownloader \
  ~/Library/Application\ Support/QGIS/QGIS3/profiles/default/python/plugins/KigamGeoDownloader
```

코드를 수정한 뒤에는 QGIS에서 플러그인을 다시 불러오거나 QGIS를 재시작하면 됩니다.

## 🧭 사용 흐름

### 1. 지질도 ZIP 불러오기

- KIGAM에서 받은 ZIP을 선택하면 압축을 풀고 SHP 레이어를 프로젝트에 추가합니다.
- 같은 ZIP에서 나온 레이어는 전용 그룹으로 묶어 정리합니다.
- `sym/` 폴더와 `.qml` 파일이 있으면 스타일을 우선 적용합니다.
- 암상 레이어 이름에 `litho`가 포함되면 라벨을 자동으로 설정합니다.

### 2. GeoChem RGB -> Value 변환

- QGIS에 추가된 래스터 레이어를 선택합니다.
- 원소 프리셋을 고른 뒤 분석 범위와 해상도를 설정합니다.
- 결과는 GeoTIFF 수치 래스터로 저장되며, QGIS에 다시 로드됩니다.

### 3. 분석용 래스터 내보내기

- 선택한 벡터 레이어는 적절한 속성 필드를 찾아 래스터화합니다.
- 선택한 래스터 레이어는 해상도를 맞춰 다시 내보낼 수 있습니다.
- 결과 포맷은 `GeoTIFF (*.tif)` 또는 `ASCII Grids (*.asc)`를 사용할 수 있습니다.

## ⚠️ 알아두면 좋은 점

- `sym/` 폴더가 없는 ZIP도 레이어는 로드될 수 있지만, 심볼 스타일은 적용되지 않을 수 있습니다.
- sidecar `.qml`이 있으면 먼저 사용하고, 실패하면 PNG 기반 categorized renderer로 대체합니다.
- GeoChem 분석은 RGB 범례 색상에 맞춰 값을 추정하므로, 원본 WMS/WFS 스타일이 달라지면 결과도 달라질 수 있습니다.

## 🛠️ 개발 체크

아래 명령으로 기본 점검을 할 수 있습니다.

```bash
flake8 .
bandit -q -r .
python3 -m compileall .
```

## 🔗 링크

- Repository: [KIGAM-for-Archaeology](https://github.com/lzpxilfe/KIGAM-for-Archaeology)
- Issues: [Bug report / feature request](https://github.com/lzpxilfe/KIGAM-for-Archaeology/issues)

## 📄 License

`GPL-2.0`. 자세한 내용은 [LICENSE](LICENSE)를 참고하세요.
