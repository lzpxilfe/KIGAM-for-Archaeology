"""Offline help for the tools in the main plugin dialog."""
from qgis.PyQt.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTabWidget, QTextBrowser, QVBoxLayout, QWidget,
)


WMS_URL = 'https://data.kigam.re.kr/mgeo/geoserver/Geochemical_map/wms'
WMS_PAGE = 1

PAGES = (
    ('시작하기', """
        <h2>지질도 ZIP 불러오기</h2>
        <ol>
          <li><b>KIGAM 데이터 다운로드 페이지 열기</b>에서 필요한 1:50,000 지질도
          Shapefile ZIP을 받습니다.</li>
          <li><b>지질도 불러오기</b>에서 ZIP을 선택합니다. 여러 도엽을 함께 선택할 수 있습니다.</li>
          <li><b>자동 로드 및 스타일 적용</b>을 누르면 지질도 레이어가 QGIS에 추가되고
          ZIP에 포함된 심볼과 라벨을 적용합니다.</li>
        </ol>
        <p>한글이 깨지면 <b>속성 인코딩</b>을 확인하세요. 면 패턴이 너무 촘촘하면
        레이어를 선택한 뒤 <b>현재 스타일과 나란히 비교</b>에서 배율을 조절하세요.</p>
    """),
    ('WMS 연결', """
        <h2>다목적 지구화학도 WMS 추가</h2>
        <ol>
          <li>QGIS에서 <b>레이어 → 레이어 추가 → WMS/WMTS 레이어 추가</b>를 엽니다.</li>
          <li><b>새로 만들기</b>를 누르고 이름을 정한 뒤 아래 주소를 URL에 붙여넣습니다.
          <b>연결</b>을 누릅니다.</li>
          <li>원하는 원소 레이어 하나를 선택합니다. 스타일은 <b>raster</b>,
          이미지 형식은 <b>PNG</b>로 선택하고 추가합니다.</li>
          <li>이 플러그인에서 <b>레이어 목록 새로고침</b>을 누르고 추가한 레이어를 선택합니다.</li>
        </ol>
        <p>지원 원소는 Fe₂O₃, Pb, Cu, Zn, Sr, Ba, CaO입니다. 여러 원소를 보려면 하나씩 추가하세요.</p>
    """),
    ('등급과 보간', """
        <h2>범례 등급 래스터와 대응표 저장</h2>
        <ol>
          <li>WMS 또는 같은 범례 팔레트의 RGB 파일을 선택합니다. RGB 파일은 같은 원소를 직접 선택합니다.</li>
          <li>분석 범위와 출력 해상도를 정한 뒤 <b>범례 등급 래스터와 대응표 저장</b>을 누릅니다.</li>
        </ol>
        <p>래스터에는 공식 범례의 <b>1~10 등급 ID</b>가 저장됩니다.
        등급별 농도 구간과 단위는 함께 저장되는 CSV를 확인하세요.</p>
        <p><b>검은 경계선 보간</b>을 켜면 양쪽에 원본 등급이 있는 좁은 검은 틈을
        가까운 쪽 등급으로 채웁니다. 기본값은 꺼짐이며, 채운 셀 수를 분석 로그와
        GeoTIFF에 기록합니다. 회색 무자료와 투명 배경은 NoData로 유지합니다.</p>
    """),
    ('래스터 내보내기', """
        <h2>분석 격자 맞추기</h2>
        <ol>
          <li><b>래스터 변환 및 내보내기</b>를 활성화하고 변환할 레이어를 선택합니다.</li>
          <li>같은 지오메트리 유형의 지질도 레이어 여러 개 또는 지구화학 등급 레이어 한 개를
          선택해 GeoTIFF나 ASCII Grid로 내보냅니다.</li>
          <li>MaxEnt에 함께 넣을 레이어는 같은 <b>기준 래스터 격자</b>를 사용해
          좌표계, 범위, 해상도, 행·열 수를 맞춥니다.</li>
        </ol>
        <p>지질 분류와 지구화학 등급은 범주형으로 지정하고, 래스터와 대응 CSV를 함께 보관하세요.</p>
    """),
)


class HelpDialog(QDialog):
    def __init__(self, parent=None, page=0):
        super().__init__(parent)
        self.setWindowTitle('KIGAM Tools 도움말')
        self.resize(660, 440)
        self.tabs = QTabWidget()
        for index, (title, text) in enumerate(PAGES):
            panel = QWidget()
            layout = QVBoxLayout(panel)
            guide = QTextBrowser()
            guide.setAccessibleName(title + ' 도움말 내용')
            guide.setHtml(text)
            layout.addWidget(guide)
            if index == WMS_PAGE:
                address_row = QHBoxLayout()
                self.address = QLineEdit(WMS_URL)
                self.address.setAccessibleName('KIGAM WMS 주소')
                self.address.setReadOnly(True)
                self.copy_button = QPushButton('WMS 주소 복사')
                self.copy_button.clicked.connect(self.copy_wms_url)
                address_row.addWidget(self.address, 1)
                address_row.addWidget(self.copy_button)
                layout.addLayout(address_row)
                self.copy_status = QLabel()
                layout.addWidget(self.copy_status)
            self.tabs.addTab(panel, title)
        self.tabs.setCurrentIndex(page)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(buttons)

    def copy_wms_url(self):
        QApplication.clipboard().setText(WMS_URL)
        self.copy_status.setText('WMS 주소를 복사했습니다.')
