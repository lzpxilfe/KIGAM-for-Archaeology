# 고고학을 위한 KIGAM 지질도 플러그인 (KIGAM for Archaeology)

**KIGAM for Archaeology**는 한국지질자원연구원(KIGAM)에서 제공하는 1:50,000 수치지질도를 고고학 연구에 쉽게 활용할 수 있도록, 데이터 처리와 스타일링을 자동화해주는 QGIS 플러그인입니다.

## 주요 기능 (Features)

-   **자동 ZIP 로드**: 압축을 일일이 풀 필요 없이, 다운로드한 ZIP 파일을 선택하면 자동으로 처리합니다.
-   **한글 깨짐 해결**: `cp949` 인코딩을 자동으로 적용하여 속성 테이블의 한글이 깨지지 않게 불러옵니다.
-   **자동 스타일링**: ZIP 파일 내 `sym` 폴더의 이미지를 분석하여, 지질 기호(심볼)를 자동으로 매칭하고 적용합니다.
-   **스마트 라벨링**: 지질 레이어(Litho)에 최적화된 라벨을 배치합니다 (폴리곤 내부 강제 배치, 겹침 방지).
-   **편리한 인터페이스**: "KIGAM 도구" 대화상자 하나에서 데이터 다운로드 링크 접속과 지도 불러오기를 모두 처리할 수 있습니다.
-   **레이어 정리**: 점 > 선 > 면 순서로 레이어를 정렬하고, 지역명으로 그룹을 만들어 깔끔하게 정리합니다.

## 설치 방법 (Installation)

1.  이 저장소의 **Releases** 페이지에서 최신 ZIP 파일을 다운로드합니다.
2.  QGIS를 실행하고 메뉴에서 **플러그인(Plugins) > 플러그인 관리 및 설치(Manage and Install Plugins)...**를 선택합니다.
3.  좌측 메뉴에서 **ZIP 파일에서 설치(Install from ZIP)**를 선택합니다.
4.  다운로드한 파일을 선택하고 **플러그인 설치(Install Plugin)**를 클릭합니다.

## 사용 방법 (Usage)

1.  QGIS 툴바에서 **"KIGAM Tools"** 아이콘을 클릭합니다.
2.  **데이터 다운로드**: 지질도 파일이 없다면 **"KIGAM 다운로드 페이지 열기"** 버튼을 눌러 데이터를 다운로드합니다.
3.  **지도 불러오기**:
    -   **ZIP 파일**: 다운로드한 수치지질도 ZIP 파일을 선택합니다 (예: `수치지질도_5만축척_GF03_광정.zip`).
    -   **라벨 설정**: 라벨에 사용할 글꼴(Font)과 크기(Size)를 선택합니다.
    -   **"지도 불러오기 (Load Map)"** 버튼을 클릭합니다.
4.  플러그인이 자동으로 압축을 해제하고, 스타일을 적용한 뒤 해당 지역으로 지도를 확대합니다.

## 🌟 인용 및 스타 (Citation & Star)

이 플러그인이 연구나 업무에 유용했다면 **GitHub Star** ⭐를 눌러주세요! 개발자에게 큰 힘이 됩니다.
논문이나 보고서에 인용하실 때는 아래 형식을 참고해 주세요:

```bibtex
@software{KIGAMForArchaeology2026,
  author = {lzpxilfe},
  title = {KIGAM for Archaeology: Automated QGIS plugin for archaeological distribution maps},
  year = {2026},
  url = {https://github.com/lzpxilfe/KIGAM-for-Archaeology},
  version = {0.1.0}
}
```

## 라이선스 (License)

이 프로젝트는 MIT License를 따릅니다.
