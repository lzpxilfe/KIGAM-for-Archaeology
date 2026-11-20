from qgis.PyQt.QtCore import QUrl, Qt
from qgis.PyQt.QtWidgets import (
    QMessageBox, QFileDialog, QDialog, QVBoxLayout,
    QHBoxLayout, QLabel, QFontComboBox, QSpinBox, QDialogButtonBox,
    QPushButton, QLineEdit, QGroupBox, QFormLayout, QComboBox,
    QListWidget, QListWidgetItem, QTextEdit, QDoubleSpinBox, QScrollArea, QWidget,
    QCheckBox, QProgressDialog,
)
from qgis.PyQt.QtGui import QIcon, QDesktopServices, QFont, QAction
from qgis.core import QgsProject, QgsCoordinateTransform, QgsRasterLayer, Qgis
import processing

import os.path
from pathlib import Path
import tempfile
import numpy as np
from osgeo import gdal
from .zip_processor import ZipProcessor
from .pattern_utils import scale_patterns
from .pattern_preview import PatternPreviewDialog
from . import geochem_utils, raster_output, raster_utils
from .plugin_config import PLUGIN_CONFIG, DEFAULT_PLUGIN_CONFIG


def _cfg_int(value, default):
    try:
        return int(value)
    except Exception:
        return int(default)


def _cfg_float(value, default):
    try:
        return float(value)
    except Exception:
        return float(default)


def _cfg_str(value, default):
    text = str(value).strip() if value is not None else ""
    return text or str(default)


def _cfg_str_list(value, default):
    if not isinstance(value, list):
        return list(default)
    parsed = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text:
            parsed.append(text)
    return parsed or list(default)


def _cfg_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("1", "true", "yes", "y", "on"):
            return True
        if text in ("0", "false", "no", "n", "off", ""):
            return False
    return bool(default)


UI_CONFIG = PLUGIN_CONFIG.get("ui", {})
ZIP_CONFIG = PLUGIN_CONFIG.get("zip_processor", {})
RASTER_CONFIG = PLUGIN_CONFIG.get("raster", {})
DEFAULT_UI_CONFIG = DEFAULT_PLUGIN_CONFIG.get("ui", {})
DEFAULT_ZIP_CONFIG = DEFAULT_PLUGIN_CONFIG.get("zip_processor", {})
DEFAULT_RASTER_CONFIG = DEFAULT_PLUGIN_CONFIG.get("raster", {})
LABEL_FONT_CONFIG = UI_CONFIG.get("label_font", {})
GEOCHEM_RES_CONFIG = UI_CONFIG.get("geochem_resolution", {})
EXPORT_RES_CONFIG = UI_CONFIG.get("export_resolution", {})
DEFAULT_LABEL_FONT_CONFIG = DEFAULT_UI_CONFIG.get("label_font", {})
DEFAULT_GEOCHEM_RES_CONFIG = DEFAULT_UI_CONFIG.get("geochem_resolution", {})
DEFAULT_EXPORT_RES_CONFIG = DEFAULT_UI_CONFIG.get("export_resolution", {})

DEFAULT_LABEL_FONT_FAMILY = _cfg_str(
    LABEL_FONT_CONFIG.get("default_family"),
    DEFAULT_LABEL_FONT_CONFIG.get("default_family", "Malgun Gothic"),
)
LABEL_FONT_SIZE_MIN = _cfg_int(
    LABEL_FONT_CONFIG.get("size_min"),
    DEFAULT_LABEL_FONT_CONFIG.get("size_min", 5),
)
LABEL_FONT_SIZE_MAX = _cfg_int(
    LABEL_FONT_CONFIG.get("size_max"),
    DEFAULT_LABEL_FONT_CONFIG.get("size_max", 50),
)
LABEL_FONT_SIZE_DEFAULT = _cfg_int(
    LABEL_FONT_CONFIG.get("default_size"),
    DEFAULT_LABEL_FONT_CONFIG.get("default_size", 10),
)

GEOCHEM_RES_MIN = _cfg_int(
    GEOCHEM_RES_CONFIG.get("min"),
    DEFAULT_GEOCHEM_RES_CONFIG.get("min", 1),
)
GEOCHEM_RES_MAX = _cfg_int(
    GEOCHEM_RES_CONFIG.get("max"),
    DEFAULT_GEOCHEM_RES_CONFIG.get("max", 1000),
)
GEOCHEM_RES_DEFAULT = _cfg_int(
    GEOCHEM_RES_CONFIG.get("default"),
    DEFAULT_GEOCHEM_RES_CONFIG.get("default", 30),
)

EXPORT_RES_MIN = _cfg_int(
    EXPORT_RES_CONFIG.get("min"),
    DEFAULT_EXPORT_RES_CONFIG.get("min", 1),
)
EXPORT_RES_MAX = _cfg_int(
    EXPORT_RES_CONFIG.get("max"),
    DEFAULT_EXPORT_RES_CONFIG.get("max", 1000),
)
EXPORT_RES_DEFAULT = _cfg_int(
    EXPORT_RES_CONFIG.get("default"),
    DEFAULT_EXPORT_RES_CONFIG.get("default", 10),
)

REFERENCE_LAYER_KEYWORDS = [
    k.lower() for k in _cfg_str_list(
        ZIP_CONFIG.get("reference_layer_keywords"),
        DEFAULT_ZIP_CONFIG.get("reference_layer_keywords", [
                               "frame", "crosssectionline"])
    )
]

VECTOR_EXPORT_FIELD_CANDIDATES = _cfg_str_list(
    RASTER_CONFIG.get("vector_export_field_candidates"),
    DEFAULT_RASTER_CONFIG.get(
        "vector_export_field_candidates",
        ["LITHOIDX", "LITHONAME", "TYPE", "CODE", "ASGN_CODE", "SIGN"]
    )
)
NODATA_VALUE = _cfg_float(RASTER_CONFIG.get(
    "nodata"), DEFAULT_RASTER_CONFIG.get("nodata", -9999.0))
WARP_FLOAT32 = 6  # QGIS gdal:warpreproject option index, including "use input type".
RASTERIZE_INT32 = 4  # QGIS gdal:rasterize option index.
EXPORT_GEOMETRIES = (Qgis.GeometryType.Point, Qgis.GeometryType.Line, Qgis.GeometryType.Polygon)
MAXENT_RESAMPLING = _cfg_int(
    RASTER_CONFIG.get("maxent_resampling"),
    DEFAULT_RASTER_CONFIG.get("maxent_resampling", 0),
)
GEOCHEM_FILL_NODATA_DISTANCE = _cfg_int(
    RASTER_CONFIG.get("geochem_fill_nodata_distance"),
    DEFAULT_RASTER_CONFIG.get("geochem_fill_nodata_distance", 30),
)
MAXENT_MULTITHREADING = _cfg_bool(
    RASTER_CONFIG.get("multithreading"),
    DEFAULT_RASTER_CONFIG.get("multithreading", False),
)


def output_nodata(*, categorical=False):
    if NODATA_VALUE > 0 or NODATA_VALUE < -(2 ** 31) or not NODATA_VALUE.is_integer():
        raise ValueError('NoData 설정에는 Int32 범위의 0 이하 정수를 입력하세요.')
    return int(NODATA_VALUE) if categorical else float(np.float32(NODATA_VALUE))


class MainDialog(QDialog):
    def __init__(self, parent=None, iface=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("KIGAM Tools")
        self.resize(600, 780)

        layout = QVBoxLayout()

        # Section 1: Data Download
        download_group = QGroupBox("1. KIGAM 데이터 다운로드")
        download_group.setToolTip(
            "지질자원연구원 웹사이트에서 필요한 데이터를 다운로드할 수 있는 링크를 제공합니다.")
        download_layout = QVBoxLayout()
        download_btn = QPushButton("KIGAM 데이터 다운로드 페이지 열기")
        download_btn.setToolTip("KIGAM 지오빅데이터 오픈플랫폼 검색 페이지를 브라우저에서 엽니다.")
        download_btn.clicked.connect(self.open_kigam_website)
        download_layout.addWidget(QLabel("지질자원연구원 사이트에서 지질도(ZIP)를 다운로드하세요:"))
        download_layout.addWidget(download_btn)
        download_group.setLayout(download_layout)
        layout.addWidget(download_group)

        # Section 2: Load Map
        load_group = QGroupBox("2. 지질도 불러오기 (Load Map)")
        load_group.setToolTip("다운로드한 ZIP 파일을 프로젝트에 불러오고 표준 스타일 및 라벨을 적용합니다.")
        load_layout = QFormLayout()

        # File Input
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("ZIP 파일을 선택하거나 경로를 입력하세요...")
        self.file_input.setToolTip("KIGAM에서 다운로드한 ZIP 파일의 경로입니다.")
        self.browse_btn = QPushButton("...")
        self.browse_btn.setToolTip("파일 브라우저를 열어 ZIP 파일을 선택합니다.")
        self.browse_btn.clicked.connect(self.browse_zip_file)
        file_layout = QHBoxLayout()
        file_layout.addWidget(self.file_input)
        file_layout.addWidget(self.browse_btn)
        load_layout.addRow("ZIP 파일:", file_layout)

        # Font Settings
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(DEFAULT_LABEL_FONT_FAMILY))
        self.font_combo.setToolTip("지층 코드 라벨에 사용할 글꼴을 선택합니다.")
        load_layout.addRow("라벨 글꼴:", self.font_combo)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(LABEL_FONT_SIZE_MIN, LABEL_FONT_SIZE_MAX)
        self.size_spin.setValue(LABEL_FONT_SIZE_DEFAULT)
        self.size_spin.setToolTip("지층 코드 라벨의 크기를 설정합니다.")
        load_layout.addRow("글꼴 크기:", self.size_spin)

        self.encoding_combo = QComboBox()
        self.encoding_combo.addItem('자동 (CPG / DBF 바이트 확인)', None)
        for encoding in ('CP949', 'UTF-8', 'EUC-KR'):
            self.encoding_combo.addItem(encoding, encoding)
        load_layout.addRow('속성 인코딩:', self.encoding_combo)

        self.pattern_scale_spin = QDoubleSpinBox()
        self.pattern_scale_spin.setRange(0.5, 6.0)
        self.pattern_scale_spin.setSingleStep(0.5)
        self.pattern_scale_spin.setValue(2.0)
        self.pattern_scale_spin.setSuffix(' 배')
        self.pattern_scale_spin.setToolTip('면 패턴 타일을 확대해 반복 밀도를 낮춥니다. 1배는 원본, 2배는 1:25,000 작업의 시작값입니다.')
        load_layout.addRow('패턴 확대:', self.pattern_scale_spin)
        pattern_btn = QPushButton('선택한 면 레이어에 패턴 확대 적용')
        pattern_btn.clicked.connect(self.apply_selected_pattern_scale)
        load_layout.addRow('', pattern_btn)
        preview_btn = QPushButton('현재 스타일과 나란히 비교…')
        preview_btn.clicked.connect(self.preview_selected_patterns)
        load_layout.addRow('', preview_btn)

        self.load_btn = QPushButton("자동 로드 및 스타일 적용")
        self.load_btn.setToolTip(
            "ZIP 압축을 해제하고 SHP 파일을 로드한 뒤 표준 심볼과 라벨을 적용합니다.")
        self.load_btn.clicked.connect(self.load_selected_zips)
        load_layout.addRow("", self.load_btn)

        load_group.setLayout(load_layout)
        layout.addWidget(load_group)

        # Section 3: GeoChem Analysis
        geochem_group = QGroupBox("3. 지구화학 분석 (GeoChem RGB -> Value)")
        geochem_group.setToolTip(
            "WMS 또는 파일 기반 RGB 지구화학도에서 범례를 기준으로 농도를 추정합니다.")
        geochem_layout = QFormLayout()

        # WMS Layer Selection (new!)
        self.wms_layer_combo = QComboBox()
        self.wms_layer_combo.setToolTip(
            "분석할 렌더링된 WMS 또는 RGB 래스터를 선택하세요.")
        geochem_layout.addRow("WMS / RGB 레이어", self.wms_layer_combo)

        # Preset Selection
        self.geochem_preset_combo = QComboBox()
        self.geochem_preset_combo.setToolTip(
            "레이어의 원소·스타일과 범례가 일치하는 프리셋을 선택하세요. 결과는 범례 색상으로 추정한 값입니다.")
        self.geochem_preset_combo.addItem('원본 범례와 일치하는 원소 선택', None)
        for k, p in geochem_utils.PRESETS.items():
            self.geochem_preset_combo.addItem(p.label, k)
        geochem_layout.addRow("원소 프리셋:", self.geochem_preset_combo)
        geochem_group.setLayout(geochem_layout)
        layout.addWidget(geochem_group)

        # Extent Setting
        self.extent_layer_combo = QComboBox()
        self.extent_layer_combo.setToolTip(
            "분석 범위를 제한할 기준 레이어를 선택하세요. (선택 안 함 = 전체 화면)")
        geochem_layout.addRow("분석 범위 (대상지):", self.extent_layer_combo)

        self.geochem_res_spin = QSpinBox()
        self.geochem_res_spin.setRange(GEOCHEM_RES_MIN, GEOCHEM_RES_MAX)
        self.geochem_res_spin.setValue(GEOCHEM_RES_DEFAULT)
        self.geochem_res_spin.setSuffix(" m")
        self.geochem_res_spin.setToolTip("변환될 결과 래스터의 해상도(픽셀 크기)를 설정합니다.")
        geochem_layout.addRow("해상도 (Resolution):", self.geochem_res_spin)

        self.geochem_fill_lines = QCheckBox('경계선 픽셀에 가까운 유효값 복사')
        self.geochem_fill_lines.setToolTip('채운 값은 주변 셀에서 복사한 추정값입니다. 채운 셀 수는 로그와 GeoTIFF에 기록합니다.')
        geochem_layout.addRow('', self.geochem_fill_lines)

        # Refresh Button for layer combos
        refresh_layers_btn = QPushButton("레이어 목록 새로고침")
        refresh_layers_btn.clicked.connect(self.refresh_geochem_layer_combos)
        geochem_layout.addRow("", refresh_layers_btn)

        self.geochem_btn = QPushButton("RGB 래스터 수치화 실행 (WMS -> Raster)")
        self.geochem_btn.setToolTip(
            "현재 선택된 원소 프리셋과 범위/해상도를 사용하여 RGB 래스터를 수치 래스터로 변환합니다.")
        self.geochem_btn.clicked.connect(self.run_geochem_analysis)
        geochem_layout.addRow("", self.geochem_btn)

        # Add Refresh Button for Extent Combo (Reuse logic if possible or separate)
        # Actually refresh_layer_list can serve both

        # Section 4: Rasterize / Export
        self.maxent_group = QGroupBox("4. 래스터 변환 및 내보내기 (Rasterize / ASC)")
        self.maxent_group.setCheckable(True)
        self.maxent_group.setChecked(False)  # Folded by default
        self.maxent_group.setToolTip(
            "지질도(Vector)나 지구화학도(Raster)를 분석용 데이터(GeoTIFF/ASC)로 변환합니다.")
        maxent_layout = QVBoxLayout()

        maxent_layout.addWidget(QLabel("변환할 레이어를 선택하세요 (지질도 또는 지구화학도):"))

        # Add descriptive help text (In-place help)
        help_lbl = QLabel(
            "💡 팁: 여러 지질도(Vector)를 선택하면 하나로 병합됩니다.\n      수치화된 지구화학도(Raster)도 선택하여 변환할 수 있습니다.")
        help_lbl.setStyleSheet(
            "color: #666666; font-size: 11px; margin-bottom: 5px;")
        maxent_layout.addWidget(help_lbl)

        self.layer_list = QListWidget()
        self.layer_list.setMaximumHeight(150)
        self.layer_list.setToolTip("현재 프로젝트에서 지질 정보가 포함된 레이어 목록입니다.")
        maxent_layout.addWidget(self.layer_list)

        refresh_btn = QPushButton("레이어 목록 새로고침")
        refresh_btn.clicked.connect(self.refresh_layer_list)
        maxent_layout.addWidget(refresh_btn)

        form_layout = QFormLayout()
        self.res_spin = QSpinBox()
        self.res_spin.setRange(EXPORT_RES_MIN, EXPORT_RES_MAX)
        self.res_spin.setValue(EXPORT_RES_DEFAULT)
        self.res_spin.setSuffix(" m")
        form_layout.addRow("해상도 (Resolution):", self.res_spin)
        self.export_reference_combo = QComboBox()
        self.export_reference_combo.setToolTip(
            'MaxEnt에 함께 넣을 출력에는 같은 기준 래스터를 선택하세요. 기준의 CRS, 범위, 해상도와 행·열을 재사용합니다.')
        self.export_reference_combo.currentIndexChanged.connect(
            lambda: self.res_spin.setEnabled(self.export_reference_combo.currentData() is None))
        form_layout.addRow('기준 래스터 격자', self.export_reference_combo)
        maxent_layout.addLayout(form_layout)

        self.export_btn = QPushButton("선택한 레이어를 래스터로 내보내기")
        self.export_btn.setToolTip("선택한 레이어들을 하나의 래스터 파일로 병합하여 저장합니다.")
        self.export_btn.clicked.connect(self.export_maxent_raster)
        maxent_layout.addWidget(self.export_btn)

        self.maxent_group.setLayout(maxent_layout)
        layout.addWidget(self.maxent_group)

        # Log Panel (Collapsible)
        self.log_group = QGroupBox("📋 분석 로그")
        self.log_group.setCheckable(True)
        self.log_group.setChecked(True)
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 11px; background-color: #1e1e1e; color: #d4d4d4;")
        log_layout.addWidget(self.log_text)

        clear_log_btn = QPushButton("로그 지우기")
        clear_log_btn.clicked.connect(lambda: self.log_text.clear())
        log_layout.addWidget(clear_log_btn)

        self.log_group.setLayout(log_layout)
        layout.addWidget(self.log_group)

        # Bottom Buttons
        bottom_layout = QHBoxLayout()

        self.help_btn = QPushButton("도움말 (?)")
        self.help_btn.clicked.connect(self.show_help)
        bottom_layout.addWidget(self.help_btn)

        bottom_layout.addStretch()

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.rejected.connect(self.reject)
        bottom_layout.addWidget(self.buttons)

        layout.addLayout(bottom_layout)

        contents = QWidget()
        contents.setLayout(layout)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(contents)
        outer = QVBoxLayout(self)
        outer.addWidget(scroll)

        # Auto-populate layer combo boxes on dialog open
        self.refresh_layer_list()
        self.refresh_geochem_layer_combos()

    def show_help(self):
        help_text = """
        <h3>KIGAM for Archaeology 사용 가이드</h3>
        <p><b>1. 데이터 다운로드:</b> KIGAM 웹사이트에서 지질도 데이터를 다운로드합니다.</p>
        <p><b>2. 지질도 불러오기:</b> 다운로드한 ZIP 파일을 선택하고 '자동 로드'를 클릭하면 스타일과 라벨이 자동 적용됩니다.</p>
        <p><b>3. 지구화학 분석</b> WMS 또는 RGB 지구화학도의 색상에서 농도를 추정합니다. 원본 범례와 일치하는 원소를 선택하세요.</p>
        <p><b>4. 래스터 변환</b> 같은 지오메트리 유형의 지질도를 병합하거나 지구화학 래스터 하나를 내보냅니다.
        MaxEnt에 함께 사용할 파일은 동일한 기준 래스터 격자를 선택하세요.</p>
        <br>
        <p><i>* 개발 기준: ArchToolkit (lzpxilfe/ar) 동기화 버전</i></p>
        """
        QMessageBox.information(self, "도움말", help_text)

    def apply_selected_pattern_scale(self):
        layers = self.iface.layerTreeView().selectedLayers() if self.iface else []
        count = skipped = 0
        for layer in layers:
            if layer.type() == Qgis.LayerType.Vector and layer.geometryType() == Qgis.GeometryType.Polygon:
                report = scale_patterns(layer, self.pattern_scale_spin.value())
                count += bool(report['changed'])
                skipped += report['skipped']
        if not count:
            self.log('변경할 래스터 면 패턴이 없습니다. 레이어 패널에서 패턴이 있는 면 레이어를 선택하세요.')
        else:
            self.log(f'면 패턴 확대: {count}개 레이어에 {self.pattern_scale_spin.value():g}배 적용')
        if skipped:
            self.log(f'데이터 정의 또는 이미지 크기 확인이 필요한 패턴 {skipped}개는 변경하지 않았습니다.')

    def preview_selected_patterns(self):
        layers = self.iface.layerTreeView().selectedLayers() if self.iface else []
        polygons = [layer for layer in layers if layer.type() == Qgis.LayerType.Vector
                    and layer.geometryType() == Qgis.GeometryType.Polygon]
        if not polygons:
            self.log('비교할 면 레이어를 레이어 패널에서 선택하세요.')
            return
        dialog = PatternPreviewDialog(self.iface.mapCanvas(), polygons, self.pattern_scale_spin.value(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.pattern_scale_spin.setValue(dialog.selected_multiplier())
            self.apply_selected_pattern_scale()
        dialog.deleteLater()

    def log(self, message: str):
        """Write a message to the built-in log panel."""
        self.log_text.append(str(message).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum())
        self.log_text.viewport().repaint()

    def refresh_geochem_layer_combos(self):
        """Refresh the WMS layer and extent layer combo boxes."""
        # Save current selections
        current_wms = self.wms_layer_combo.currentData()
        current_extent = self.extent_layer_combo.currentData()

        # Clear and repopulate WMS combo (raster layers only)
        self.wms_layer_combo.clear()
        self.wms_layer_combo.addItem("(레이어 선택)", None)

        # Clear and repopulate extent combo (VECTOR layers only, as requested)
        self.extent_layer_combo.clear()
        self.extent_layer_combo.addItem("(전체 화면)", None)

        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if (isinstance(layer, QgsRasterLayer) and layer.isValid()
                    and (layer.providerType() == 'wms'
                         or (layer.renderer() and layer.renderer().type() == 'multibandcolor'))):
                self.wms_layer_combo.addItem(layer.name(), layer.id())

            # Extent combo: VECTOR layers only
            if layer.type() == Qgis.LayerType.Vector:  # VectorLayer
                self.extent_layer_combo.addItem(
                    f"[대상지] {layer.name()}", layer.id())

        # Restore selections if possible
        if current_wms:
            idx = self.wms_layer_combo.findData(current_wms)
            if idx >= 0:
                self.wms_layer_combo.setCurrentIndex(idx)
        if current_extent:
            idx = self.extent_layer_combo.findData(current_extent)
            if idx >= 0:
                self.extent_layer_combo.setCurrentIndex(idx)

        self.log(
            f"레이어 새로고침: WMS/RGB {self.wms_layer_combo.count() - 1}개, "
            f"대상지 {self.extent_layer_combo.count() - 1}개"
        )

    def refresh_layer_list(self):
        checked = {}
        for index in range(self.layer_list.count()):
            item = self.layer_list.item(index)
            checked[item.data(Qt.ItemDataRole.UserRole)] = item.checkState()
        self.layer_list.clear()
        reference = self.export_reference_combo.currentData()
        self.export_reference_combo.clear()
        self.export_reference_combo.addItem('입력 범위와 해상도 사용', None)
        layers = QgsProject.instance().mapLayers().values()
        vectors, rasters = [], []
        for layer in layers:
            if not layer.isValid():
                continue
            if isinstance(layer, QgsRasterLayer):
                if (layer.providerType() == 'gdal' and layer.crs().isValid()
                        and layer.crs().mapUnits() == Qgis.DistanceUnit.Meters):
                    self.export_reference_combo.addItem(layer.name(), layer.id())
                if '(수치화)' in layer.name() or layer.customProperty('kigam/geochem_preset'):
                    rasters.append(layer)
            elif (layer.type() == Qgis.LayerType.Vector and layer.geometryType() in EXPORT_GEOMETRIES
                  and self._resolve_vector_export_field(layer) is not None):
                vectors.append(layer)
        if reference:
            index = self.export_reference_combo.findData(reference)
            if index >= 0:
                self.export_reference_combo.setCurrentIndex(index)

        defaults = set()
        if not checked and vectors:
            types = [layer.geometryType() for layer in vectors]
            preferred = Qgis.GeometryType.Polygon if Qgis.GeometryType.Polygon in types else types[0]
            defaults = {layer.id() for layer in vectors if layer.geometryType() == preferred}
        elif not checked and rasters:
            defaults = {rasters[0].id()}
        for layer in vectors + rasters:
            item = QListWidgetItem(layer.name())
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            default = Qt.CheckState.Checked if layer.id() in defaults else Qt.CheckState.Unchecked
            item.setCheckState(checked.get(layer.id(), default))
            item.setData(Qt.ItemDataRole.UserRole, layer.id())
            self.layer_list.addItem(item)

    def open_kigam_website(self):
        QDesktopServices.openUrl(
            QUrl("https://data.kigam.re.kr/search?subject=Geology"))

    def browse_zip_file(self):
        zip_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "KIGAM ZIP 파일 선택",
            "",
            "ZIP Files (*.zip *.ZIP)"
        )
        if zip_paths:
            self.file_input.setText("; ".join(zip_paths))

    def _collect_zip_paths(self):
        raw_text = self.file_input.text().strip()
        if not raw_text:
            return []

        parts = raw_text.replace("\n", ";").split(";")
        zip_paths = []
        seen = set()
        for part in parts:
            path = part.strip().strip('"').strip("'")
            if not path or path in seen:
                continue
            seen.add(path)
            zip_paths.append(path)
        return zip_paths

    def _zoom_to_loaded_layers(self, loaded_layers):
        frame_layer = next(
            (
                loaded_layer for loaded_layer in loaded_layers
                if any(keyword in loaded_layer.name().lower() for keyword in REFERENCE_LAYER_KEYWORDS)
            ),
            None
        )
        target_layer = frame_layer if frame_layer else loaded_layers[0]

        if target_layer.isValid():
            canvas = self.iface.mapCanvas()
            transform = QgsCoordinateTransform(target_layer.crs(), canvas.mapSettings().destinationCrs(), QgsProject.instance())
            canvas.setExtent(transform.transformBoundingBox(target_layer.extent()))
            canvas.refresh()

    def load_selected_zips(self):
        """
        Load one or multiple ZIP files without closing the dialog.
        """
        zip_paths = self._collect_zip_paths()
        if not zip_paths:
            QMessageBox.warning(
                self, "Warning", "Please select one or more ZIP files.")
            return

        # Runtime trace to confirm which installed plugin copy is executing.
        plugin_dir = os.path.dirname(__file__)
        version = "unknown"
        metadata_path = os.path.join(plugin_dir, "metadata.txt")
        try:
            with open(metadata_path, "r", encoding="utf-8", errors="ignore") as fp:
                for line in fp:
                    if line.startswith("version="):
                        version = line.split("=", 1)[1].strip()
                        break
        except OSError:
            version = "unknown"
        self.log(f"Plugin runtime: {plugin_dir} (version {version})")

        self.load_btn.setEnabled(False)
        self.browse_btn.setEnabled(False)

        processor = ZipProcessor(log_callback=self.log)
        warning_count = 0
        loaded_zip_count = 0
        total_layer_count = 0
        failed_paths = []
        last_loaded_layers = None

        try:
            for idx, zip_path in enumerate(zip_paths, start=1):
                if not os.path.exists(zip_path):
                    failed_paths.append(zip_path)
                    self.log(
                        f"[{idx}/{len(zip_paths)}] Missing ZIP: {zip_path}")
                    continue

                self.log(f"[{idx}/{len(zip_paths)}] Loading ZIP: {zip_path}")
                try:
                    loaded_layers = processor.process_zip(
                        zip_path,
                        font_family=self.font_combo.currentFont().family(),
                        font_size=self.size_spin.value(),
                        encoding_override=self.encoding_combo.currentData(),
                        pattern_scale=self.pattern_scale_spin.value()
                    )
                    warning_count += len(processor.last_report.get('warnings', []))
                except Exception as exc:
                    loaded_layers = []
                    self.log(f'{zip_path}: {exc}')

                if loaded_layers:
                    loaded_zip_count += 1
                    total_layer_count += len(loaded_layers)
                    last_loaded_layers = loaded_layers
                    self.log(f"  -> Loaded {len(loaded_layers)} layer(s)")
                else:
                    failed_paths.append(zip_path)
                    self.log("  -> No layers loaded")

            if last_loaded_layers:
                self._zoom_to_loaded_layers(last_loaded_layers)

            # Keep UI current for follow-up work in the same dialog.
            self.refresh_layer_list()
            self.refresh_geochem_layer_combos()

            if loaded_zip_count > 0:
                msg = f"{loaded_zip_count}/{len(zip_paths)} ZIP loaded, total {total_layer_count} layers."
                if failed_paths:
                    msg += f"\nFailed: {len(failed_paths)}"
                if warning_count:
                    msg += f'\nWarnings: {warning_count}. 분석 로그에서 누락/스타일 오류를 확인하세요.'
                    QMessageBox.warning(self, '일부 항목 확인 필요', msg)
                else:
                    QMessageBox.information(self, "Success", msg)
            else:
                QMessageBox.warning(
                    self, "Warning", "No layers were loaded. Check the log panel for details.")
        finally:
            self.load_btn.setEnabled(True)
            self.browse_btn.setEnabled(True)

    def _resolve_vector_export_field(self, layer):
        fields = {f.name().casefold(): f.name() for f in layer.fields()}
        for candidate in VECTOR_EXPORT_FIELD_CANDIDATES:
            if candidate.casefold() in fields:
                return fields[candidate.casefold()]
        return None

    def export_maxent_raster(self):
        project = QgsProject.instance()
        selected = []
        for index in range(self.layer_list.count()):
            item = self.layer_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(project.mapLayer(item.data(Qt.ItemDataRole.UserRole)))
        if not selected or any(layer is None or not layer.isValid() for layer in selected):
            QMessageBox.warning(self, '선택 확인', '유효한 레이어를 선택하세요. 목록을 새로고침할 수 있습니다.')
            return

        vectors = [layer for layer in selected if layer.type() == Qgis.LayerType.Vector]
        rasters = [layer for layer in selected if isinstance(layer, QgsRasterLayer)]
        if (vectors and rasters) or len(rasters) > 1:
            QMessageBox.warning(self, '선택 확인', '지질 벡터 여러 개 또는 수치 래스터 한 개를 선택하세요.')
            return
        if len({layer.geometryType() for layer in vectors}) > 1:
            QMessageBox.warning(self, '선택 확인', '병합할 벡터의 지오메트리 유형을 맞추세요. 점·선·면은 각각 내보내야 합니다.')
            return

        try:
            reference_id = self.export_reference_combo.currentData()
            reference = project.mapLayer(reference_id) if reference_id else None
            if reference_id and reference is None:
                raise ValueError('기준 래스터가 삭제되었습니다. 목록을 새로고침하세요.')
            grid = raster_utils.reference_grid(reference) if reference is not None else None
            nodata = output_nodata(categorical=bool(vectors))
        except (ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, '격자 또는 설정 확인', str(exc))
            return

        path, selected_filter = QFileDialog.getSaveFileName(
            self, '분석용 래스터 저장', '', 'GeoTIFF (*.tif *.tiff);;ASCII Grids (*.asc)')
        if not path:
            return
        destination = Path(path)
        if not destination.suffix:
            destination = destination.with_suffix('.asc' if '*.asc' in selected_filter else '.tif')
        suffix = destination.suffix.lower()
        if suffix not in ('.tif', '.tiff', '.asc'):
            QMessageBox.warning(self, '형식 확인', '확장자는 .tif, .tiff 또는 .asc여야 합니다.')
            return

        resolution = self.res_spin.value()
        if any(raster_utils.is_source_file(layer, destination)
               for layer in rasters + ([reference] if reference is not None else [])):
            QMessageBox.warning(self, '출력 경로 확인', '입력이나 기준 래스터와 다른 경로에 저장하세요.')
            return
        self.export_btn.setEnabled(False)
        try:
            with raster_output.staging_directory(destination) as temp_dir:
                temp = Path(temp_dir)
                intermediate = temp / 'processing' / 'intermediate.tif'
                intermediate.parent.mkdir()
                staged = temp / destination.name
                codes = None
                if vectors:
                    prepared, codes, target_crs = raster_utils.categorical_layers(
                        vectors, self._resolve_vector_export_field, grid.crs if grid else None)
                    merged = prepared[0] if len(prepared) == 1 else processing.run(
                        'native:mergevectorlayers', {'LAYERS': prepared, 'CRS': target_crs,
                                                     'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']
                    grid = grid or raster_utils.metric_grid(
                        merged.extent(), target_crs, resolution, allow_degenerate=True)
                    processing.run('gdal:rasterize', {
                        'INPUT': merged, 'FIELD': 'KIGAM_ID', 'UNITS': 0,
                        'WIDTH': grid.width, 'HEIGHT': grid.height, 'EXTENT': grid.extent,
                        'NODATA': nodata, 'INIT': nodata, 'DATA_TYPE': RASTERIZE_INT32,
                        'OUTPUT': str(intermediate)})
                    data_type = gdal.GDT_Int32
                else:
                    raster = rasters[0]
                    grid = grid or raster_utils.metric_grid(raster.extent(), raster.crs(), resolution)
                    if not raster.crs().isValid():
                        raise ValueError('수치 래스터에 올바른 CRS를 지정하세요.')
                    processing.run('gdal:warpreproject', {
                        'INPUT': raster, 'SOURCE_CRS': raster.crs(), 'TARGET_CRS': grid.crs,
                        'RESAMPLING': MAXENT_RESAMPLING, 'NODATA': nodata,
                        'TARGET_RESOLUTION': grid.resolution, 'OPTIONS': '', 'DATA_TYPE': WARP_FLOAT32,
                        'TARGET_EXTENT': grid.extent, 'TARGET_EXTENT_CRS': grid.crs,
                        'MULTITHREADING': MAXENT_MULTITHREADING, 'EXTRA': '', 'OUTPUT': str(intermediate)})
                    data_type = gdal.GDT_Float32
                gdal.ErrorReset()
                output = gdal.Translate(str(staged), str(intermediate),
                                        format='AAIGrid' if suffix == '.asc' else 'GTiff')
                if output is None:
                    raise RuntimeError('GDAL 출력 생성에 실패했습니다.')
                raster_output.close_dataset(output)
                output = None
                if gdal.GetLastErrorType() >= gdal.CE_Failure:
                    raise RuntimeError(gdal.GetLastErrorMsg())
                omitted = raster_output.verify_raster(
                    staged, grid, nodata, data_type,
                    class_ids=codes.values() if codes is not None else None,
                    ascii_source=intermediate if suffix == '.asc' else None)
                if codes is not None:
                    raster_utils.write_codebook(staged, codes)
                raster_output.publish_raster(staged, destination, categories=codes is not None)
            if codes is not None:
                self.log(f'지질 분류 ID 대응표: {raster_utils.codebook_path(destination)}')
            self.log(f'내보내기: {grid.crs.authid()}, {grid.width} × {grid.height}, {grid.resolution:g} m')
            message = f'래스터 내보내기 완료: {destination}'
            if omitted:
                missing = [value for value, code in codes.items() if code in omitted]
                preview = ', '.join(missing[:8]) + ('…' if len(missing) > 8 else '')
                detail = f'출력 격자에 기록되지 않은 지질 분류 {len(missing)}개: {preview}'
                self.log(detail)
                QMessageBox.warning(self, '출력 범위 및 해상도 확인', f'{message}\n{detail}')
            else:
                QMessageBox.information(self, '성공', message)
        except Exception as exc:
            QMessageBox.critical(self, '오류', f'내보내기 중 오류: {exc}')
        finally:
            self.export_btn.setEnabled(True)

    def run_geochem_analysis(self):
        project = QgsProject.instance()
        layer_id = self.wms_layer_combo.currentData()
        layer = project.mapLayer(layer_id) if layer_id else None
        if not isinstance(layer, QgsRasterLayer) or not layer.isValid():
            QMessageBox.warning(self, '선택 확인', '지구화학 WMS 또는 RGB 래스터를 선택하세요.')
            return
        preset = geochem_utils.PRESETS.get(self.geochem_preset_combo.currentData())
        if preset is None:
            QMessageBox.warning(self, '프리셋 확인', '원본 범례의 원소와 스타일에 맞는 프리셋을 선택하세요.')
            return

        try:
            has_alpha = geochem_utils.source_has_alpha(layer)
            nodata = output_nodata()
            canvas = self.iface.mapCanvas()
            extent, source_crs = canvas.extent(), canvas.mapSettings().destinationCrs()
            selected_id = self.extent_layer_combo.currentData()
            if selected_id is not None:
                selected = project.mapLayer(selected_id)
                if selected is None:
                    raise ValueError('대상지 레이어가 삭제되었습니다. 목록을 새로고침하세요.')
                extent, source_crs = selected.extent(), selected.crs()
            grid = raster_utils.metric_grid(extent, source_crs, self.geochem_res_spin.value())
        except Exception as exc:
            QMessageBox.warning(self, '입력 확인', str(exc))
            return

        path, _ = QFileDialog.getSaveFileName(self, '추정 농도 래스터 저장', '', 'GeoTIFF (*.tif *.tiff)')
        if not path:
            return
        destination = Path(path)
        if not destination.suffix:
            destination = destination.with_suffix('.tif')
        if destination.suffix.lower() not in ('.tif', '.tiff'):
            QMessageBox.warning(self, '형식 확인', '확장자는 .tif 또는 .tiff여야 합니다.')
            return
        if raster_utils.is_source_file(layer, destination):
            QMessageBox.warning(self, '출력 경로 확인', '원본 RGB 파일과 다른 경로에 저장하세요.')
            return

        progress = QProgressDialog('지구화학 RGB 준비 중…', '취소', 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        self.geochem_btn.setEnabled(False)
        fill_distance = max(0, GEOCHEM_FILL_NODATA_DISTANCE) if self.geochem_fill_lines.isChecked() else 0
        try:
            with tempfile.TemporaryDirectory(prefix='KigamRGB_') as temp_dir:
                rgb_path = os.path.join(temp_dir, 'rgb.tif')
                progress.setValue(10)
                self.log(f'GeoChem 입력: {layer.name()} · 프리셋: {preset.label} · '
                         f'{grid.crs.authid()}, {grid.width} × {grid.height}, {grid.resolution:g} m')
                if progress.wasCanceled():
                    return
                if not geochem_utils.export_geotiff(
                        layer, rgb_path, grid.extent, grid.width, grid.height, grid.crs):
                    raise RuntimeError('지구화학 RGB 래스터를 내보낼 수 없습니다.')
                progress.setValue(40)
                progress.setLabelText('범례 색상 매칭 중…')
                if progress.wasCanceled():
                    return
                r, g, b, available = geochem_utils.read_rgb(rgb_path, grid, has_alpha)
                values, stats = geochem_utils.convert_rgb(
                    r, g, b, preset.points, available, nodata, fill_distance)

            if not stats['valid_pixels']:
                raise RuntimeError('범례와 일치하는 유효한 픽셀이 없습니다. 원소·스타일·분석 범위를 확인하세요.')
            rejected = stats['off_legend_pixels']
            percent = 100 * rejected / max(1, stats['available_pixels'])
            report = (f'범례 밖 {rejected:,}셀 ({percent:.1f}%), 경계선 {stats["linework_pixels"]:,}셀, '
                      f'주변 값 복사 {stats["filled_pixels"]:,}셀, 유효 {stats["valid_pixels"]:,}셀')
            self.log(report)
            progress.setLabelText('추정 농도 파일 검증 중…')
            progress.setValue(80)
            if progress.wasCanceled():
                return
            metadata = {
                'KIGAM_VALUE_KIND': 'legend_color_estimate',
                'KIGAM_PRESET': preset.key,
                'KIGAM_UNIT': preset.unit,
                'KIGAM_RGB_TOLERANCE': str(geochem_utils.RGB_MATCH_TOLERANCE),
                'KIGAM_LINE_FILL_DISTANCE_PX': str(fill_distance),
                **{f'KIGAM_{key.upper()}': str(value) for key, value in stats.items()},
            }
            with raster_output.staging_directory(destination) as temp_dir:
                staged = Path(temp_dir) / destination.name
                raster_output.write_value_raster(staged, values, grid, nodata, metadata)
                raster_output.publish_raster(staged, destination)

            output = QgsRasterLayer(str(destination), f'{preset.label} (수치화)')
            if not output.isValid():
                raise RuntimeError(f'파일은 저장됐지만 QGIS에 결과 레이어를 불러오지 못했습니다. {destination}')
            output.setCustomProperty('kigam/geochem_preset', preset.key)
            self._style_geochem_result(output, preset)
            project.addMapLayer(output)
            self.refresh_layer_list()
            progress.setValue(100)
            progress.close()
            message = f'범례 기반 추정 농도를 저장했습니다.\n{destination}\n{report}'
            if percent >= 5:
                QMessageBox.warning(self, '범례 일치 확인', message + '\n원본 범례와 프리셋을 다시 확인하세요.')
            else:
                QMessageBox.information(self, '완료', message)
        except Exception as exc:
            progress.close()
            QMessageBox.critical(self, '오류', f'분석 중 오류: {exc}')
        finally:
            progress.close()
            self.geochem_btn.setEnabled(True)

    @staticmethod
    def _style_geochem_result(layer, preset):
        from qgis.core import QgsColorRampShader, QgsRasterShader, QgsSingleBandPseudoColorRenderer
        from qgis.PyQt.QtGui import QColor

        points = [point for point in preset.points if point != geochem_utils.ABSENT_STOP]
        minimum, maximum = points[0].value, points[-1].value
        ramp = QgsColorRampShader()
        ramp.setColorRampType(Qgis.ShaderInterpolationMethod.Linear)
        ramp.setColorRampItemList([
            QgsColorRampShader.ColorRampItem(point.value, QColor(*point.rgb),
                                             f'{point.value:g} {preset.unit}')
            for point in points
        ])
        ramp.setMinimumValue(minimum)
        ramp.setMaximumValue(maximum)
        shader = QgsRasterShader()
        shader.setRasterShaderFunction(ramp)
        renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
        renderer.setClassificationMin(minimum)
        renderer.setClassificationMax(maximum)
        layer.setRenderer(renderer)

    def get_settings(self):
        return {
            'zip_path': self.file_input.text(),
            'font_family': self.font_combo.currentFont().family(),
            'font_size': self.size_spin.value()
        }


class KigamGeoDownloader:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        # Single Action for Tools
        self.action = QAction(
            QIcon(icon_path), "KIGAM Tools", self.iface.mainWindow())
        self.action.triggered.connect(self.run)

        # Add to Menu
        self.iface.addPluginToMenu("&KIGAM for Archaeology", self.action)

        # Add to Dedicated Toolbar
        self.toolbar = self.iface.addToolBar("KIGAM for Archaeology")
        self.toolbar.setObjectName("KIGAMForArchaeology")
        self.toolbar.addAction(self.action)

    def unload(self):
        # Remove Menu
        self.iface.removePluginMenu("&KIGAM for Archaeology", self.action)

        # Remove Toolbar
        if hasattr(self, 'toolbar'):
            self.iface.mainWindow().removeToolBar(self.toolbar)
            del self.toolbar
        del self.action

    def run(self):
        # Show Main Dialog
        dialog = MainDialog(self.iface.mainWindow(), self.iface)
        dialog.exec()
