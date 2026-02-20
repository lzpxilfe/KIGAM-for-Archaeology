
from qgis.PyQt.QtCore import QSettings, QTranslator, qVersion, QCoreApplication, QUrl, Qt
from qgis.PyQt.QtWidgets import (
    QAction, QMessageBox, QFileDialog, QDialog, QVBoxLayout, 
    QHBoxLayout, QLabel, QFontComboBox, QSpinBox, QDialogButtonBox,
    QPushButton, QLineEdit, QGroupBox, QFormLayout, QComboBox,
    QListWidget, QListWidgetItem, QTextEdit
)
from qgis.PyQt.QtGui import QIcon, QDesktopServices
from qgis.core import QgsProject, QgsVectorLayer, QgsCoordinateTransform
import processing

import os.path
import tempfile
import shutil
import uuid
import numpy as np
from osgeo import gdal
from .zip_processor import ZipProcessor
from . import geochem_utils

class MainDialog(QDialog):
    def __init__(self, parent=None, iface=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("KIGAM Tools")
        self.resize(450, 450)
        
        layout = QVBoxLayout()
        
        # Section 1: Data Download
        download_group = QGroupBox("1. KIGAM 데이터 다운로드")
        download_group.setToolTip("지질자원연구원 웹사이트에서 필요한 데이터를 다운로드할 수 있는 링크를 제공합니다.")
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
        self.font_combo.setToolTip("지층 코드 라벨에 사용할 글꼴을 선택합니다.")
        load_layout.addRow("라벨 글꼴:", self.font_combo)
        
        self.size_spin = QSpinBox()
        self.size_spin.setRange(5, 50)
        self.size_spin.setValue(10)
        self.size_spin.setToolTip("지층 코드 라벨의 크기를 설정합니다.")
        load_layout.addRow("글꼴 크기:", self.size_spin)
        
        self.load_btn = QPushButton("자동 로드 및 스타일 적용")
        self.load_btn.setToolTip("ZIP 압축을 해제하고 SHP 파일을 로드한 뒤 표준 심볼과 라벨을 적용합니다.")
        self.load_btn.clicked.connect(self.load_selected_zips)
        load_layout.addRow("", self.load_btn)
        
        load_group.setLayout(load_layout)
        layout.addWidget(load_group)

        # Section 3: GeoChem Analysis
        geochem_group = QGroupBox("3. 지구화학 분석 (GeoChem RGB -> Value)")
        geochem_group.setToolTip("WMS/WFS 지구화학도의 RGB 색상을 수치 데이터(Value)로 변환합니다.")
        geochem_layout = QFormLayout()
        
        # WMS Layer Selection (new!)
        self.wms_layer_combo = QComboBox()
        self.wms_layer_combo.setToolTip("분석할 지구화학 WMS 레이어를 선택하세요. (래스터 레이어만 표시됨)")
        geochem_layout.addRow("WMS 레이어:", self.wms_layer_combo)
        
        # Preset Selection
        self.geochem_preset_combo = QComboBox()
        self.geochem_preset_combo.setToolTip("분석할 원소 항목을 선택하세요. 각 원소별로 특화된 수치 변환 알고리즘이 적용됩니다.")
        for k, p in geochem_utils.PRESETS.items():
            self.geochem_preset_combo.addItem(p.label, k)
        geochem_layout.addRow("원소 프리셋:", self.geochem_preset_combo)
        
        
        geochem_group.setLayout(geochem_layout)
        layout.addWidget(geochem_group)

        # Extent Setting
        self.extent_layer_combo = QComboBox()
        self.extent_layer_combo.setToolTip("분석 범위를 제한할 기준 레이어를 선택하세요. (선택 안 함 = 전체 화면)")
        geochem_layout.addRow("분석 범위 (대상지):", self.extent_layer_combo)

        self.geochem_res_spin = QSpinBox()
        self.geochem_res_spin.setRange(1, 1000)
        self.geochem_res_spin.setValue(30)
        self.geochem_res_spin.setSuffix(" m")
        self.geochem_res_spin.setToolTip("변환될 결과 래스터의 해상도(픽셀 크기)를 설정합니다.")
        geochem_layout.addRow("해상도 (Resolution):", self.geochem_res_spin)

        # Refresh Button for layer combos
        refresh_layers_btn = QPushButton("레이어 목록 새로고침")
        refresh_layers_btn.clicked.connect(self.refresh_geochem_layer_combos)
        geochem_layout.addRow("", refresh_layers_btn)

        self.geochem_btn = QPushButton("RGB 래스터 수치화 실행 (WMS -> Raster)")
        self.geochem_btn.setToolTip("현재 선택된 원소 프리셋과 범위/해상도를 사용하여 RGB 래스터를 수치 래스터로 변환합니다.")
        self.geochem_btn.clicked.connect(self.run_geochem_analysis)
        geochem_layout.addRow("", self.geochem_btn)
        
        # Add Refresh Button for Extent Combo (Reuse logic if possible or separate)
        # Actually refresh_layer_list can serve both

        # Section 4: Rasterize / Export
        self.maxent_group = QGroupBox("4. 래스터 변환 및 내보내기 (Rasterize / ASC)")
        self.maxent_group.setCheckable(True)
        self.maxent_group.setChecked(False) # Folded by default
        self.maxent_group.setToolTip("지질도(Vector)나 지구화학도(Raster)를 분석용 데이터(GeoTIFF/ASC)로 변환합니다.")
        maxent_layout = QVBoxLayout()
        
        maxent_layout.addWidget(QLabel("변환할 레이어를 선택하세요 (지질도 또는 지구화학도):"))
        
        # Add descriptive help text (In-place help)
        help_lbl = QLabel("💡 팁: 여러 지질도(Vector)를 선택하면 하나로 병합됩니다.\n      수치화된 지구화학도(Raster)도 선택하여 변환할 수 있습니다.")
        help_lbl.setStyleSheet("color: #666666; font-size: 11px; margin-bottom: 5px;")
        maxent_layout.addWidget(help_lbl)

        self.layer_list = QListWidget()
        self.layer_list.setMaximumHeight(150)
        self.layer_list.setToolTip("현재 프로젝트에서 지질 정보가 포함된 레이어 목록입니다.")
        self.refresh_layer_list()
        maxent_layout.addWidget(self.layer_list)
        
        refresh_btn = QPushButton("레이어 목록 새로고침")
        refresh_btn.clicked.connect(self.refresh_layer_list)
        maxent_layout.addWidget(refresh_btn)

        form_layout = QFormLayout()
        self.res_spin = QSpinBox()
        self.res_spin.setRange(1, 1000)
        self.res_spin.setValue(10)
        self.res_spin.setSuffix(" m")
        form_layout.addRow("해상도 (Resolution):", self.res_spin)
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
        self.log_text.setStyleSheet("font-family: Consolas, monospace; font-size: 11px; background-color: #1e1e1e; color: #d4d4d4;")
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
        
        self.buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.buttons.rejected.connect(self.reject)
        bottom_layout.addWidget(self.buttons)
        
        layout.addLayout(bottom_layout)
        
        self.setLayout(layout)
        
        # Auto-populate layer combo boxes on dialog open
        self.refresh_geochem_layer_combos()

    def show_help(self):
        help_text = """
        <h3>KIGAM for Archaeology 사용 가이드</h3>
        <p><b>1. 데이터 다운로드:</b> KIGAM 웹사이트에서 지질도 데이터를 다운로드합니다.</p>
        <p><b>2. 지질도 불러오기:</b> 다운로드한 ZIP 파일을 선택하고 '자동 로드'를 클릭하면 스타일과 라벨이 자동 적용됩니다.</p>
        <p><b>3. 지구화학 분석:</b> WMS/WFS로 불러온 지구화학도의 RGB 색상을 수치 데이터로 변환합니다. 원소 프리셋을 선택하여 처리하세요.</p>
        <p><b>4. 래스터 변환:</b> 지질도나 지구화학도 결과물을 분석용 래스터(GeoTIFF/ASC)로 변환 및 내보냅니다. 여러 지질도를 선택하면 하나로 병합됩니다.</p>
        <br>
        <p><i>* 개발 기준: ArchToolkit (lzpxilfe/ar) 동기화 버전</i></p>
        """
        QMessageBox.information(self, "도움말", help_text)

    def log(self, message: str):
        """Write a message to the built-in log panel."""
        from PyQt5.QtCore import QCoreApplication
        self.log_text.append(message)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
        QCoreApplication.processEvents()

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
            # WMS combo: raster layers only
            if layer.type() == 1:  # RasterLayer
                self.wms_layer_combo.addItem(layer.name(), layer.id())
            
            # Extent combo: VECTOR layers only
            if layer.type() == 0: # VectorLayer
                self.extent_layer_combo.addItem(f"[대상지] {layer.name()}", layer.id())
        
        # Restore selections if possible
        if current_wms:
            idx = self.wms_layer_combo.findData(current_wms)
            if idx >= 0:
                self.wms_layer_combo.setCurrentIndex(idx)
        if current_extent:
            idx = self.extent_layer_combo.findData(current_extent)
            if idx >= 0:
                self.extent_layer_combo.setCurrentIndex(idx)
        
        self.log(f"레이어 새로고침: WMS {self.wms_layer_combo.count()-1}개, 대상지 {self.extent_layer_combo.count()-1}개")

    def refresh_layer_list(self):
        self.layer_list.clear()
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            # Include Vector (Litho) or Raster (converted results)
            is_litho = 'litho' in layer.name().lower() and layer.type() == 0
            is_result = '(수치화)' in layer.name() and layer.type() == 1
            
            if is_litho or is_result:
                item = QListWidgetItem(layer.name())
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                item.setData(Qt.UserRole, layer.id())
                self.layer_list.addItem(item)

    def open_kigam_website(self):
        QDesktopServices.openUrl(QUrl("https://data.kigam.re.kr/search?subject=Geology"))

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
        frame_layer = next((l for l in loaded_layers if 'frame' in l.name().lower()), None)
        target_layer = frame_layer if frame_layer else loaded_layers[0]

        if target_layer.isValid():
            canvas = self.iface.mapCanvas()
            canvas.setExtent(target_layer.extent())
            canvas.refresh()

    def load_selected_zips(self):
        """
        Load one or multiple ZIP files without closing the dialog.
        """
        zip_paths = self._collect_zip_paths()
        if not zip_paths:
            QMessageBox.warning(self, "Warning", "Please select one or more ZIP files.")
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
        except Exception:
            pass
        self.log(f"Plugin runtime: {plugin_dir} (version {version})")

        self.load_btn.setEnabled(False)
        self.browse_btn.setEnabled(False)

        processor = ZipProcessor()
        loaded_zip_count = 0
        total_layer_count = 0
        failed_paths = []
        last_loaded_layers = None

        try:
            for idx, zip_path in enumerate(zip_paths, start=1):
                if not os.path.exists(zip_path):
                    failed_paths.append(zip_path)
                    self.log(f"[{idx}/{len(zip_paths)}] Missing ZIP: {zip_path}")
                    continue

                self.log(f"[{idx}/{len(zip_paths)}] Loading ZIP: {zip_path}")
                loaded_layers = processor.process_zip(
                    zip_path,
                    font_family=self.font_combo.currentFont().family(),
                    font_size=self.size_spin.value()
                )

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
                QMessageBox.information(self, "Success", msg)
            else:
                QMessageBox.warning(self, "Warning", "No layers were loaded. Check the log panel for details.")
        finally:
            self.load_btn.setEnabled(True)
            self.browse_btn.setEnabled(True)

    def export_maxent_raster(self):
        """
        Rasterizes selected vector layers or exports selected raster layers for MaxEnt.
        """
        # 1. Get Selected Layers
        selected_layer_ids = []
        for i in range(self.layer_list.count()):
            item = self.layer_list.item(i)
            if item.checkState() == Qt.Checked:
                selected_layer_ids.append(item.data(Qt.UserRole))
        
        if not selected_layer_ids:
            QMessageBox.warning(self, "오류", "내보낼 레이어를 하나 이상 선택해주세요.")
            return

        all_layers = QgsProject.instance().mapLayers()
        selected_layers = [all_layers[lid] for lid in selected_layer_ids if lid in all_layers]
        
        # 2. Separate Vector and Raster
        vector_layers = [l for l in selected_layers if l.type() == 0]
        raster_layers = [l for l in selected_layers if l.type() == 1]

        if not vector_layers and not raster_layers:
            QMessageBox.warning(self, "오류", "유효한 레이어가 선택되지 않았습니다.")
            return

        # 3. Get Save Path
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "MaxEnt용 래스터 파일 저장",
            "",
            "GeoTIFF (*.tif);;ASCII Grids (*.asc)"
        )
        if not save_path:
            return

        resolution = self.res_spin.value()
        
        try:
            target_layers = []
            
            # A. Process Vector Layers (Merge if multiple, or use single)
            if vector_layers:
                if len(vector_layers) > 1:
                    merge_params = {
                        'LAYERS': vector_layers,
                        'CRS': vector_layers[0].crs(),
                        'OUTPUT': 'TEMPORARY_OUTPUT'
                    }
                    merged = processing.run("native:mergevectorlayers", merge_params)['OUTPUT']
                    # Ensure LITHOIDX exists in merged
                    if merged.fields().indexOf('LITHOIDX') == -1:
                         raise ValueError("통합된 레이어에 'LITHOIDX' 필드가 없습니다.")
                    target_layers.append(('vector', merged))
                else:
                    if vector_layers[0].fields().indexOf('LITHOIDX') == -1:
                        raise ValueError(f"'{vector_layers[0].name()}' 레이어에 'LITHOIDX' 필드가 없습니다.")
                    target_layers.append(('vector', vector_layers[0]))

            # B. Process Raster Layers (GeoTIFF clipping/resampling to match if needed)
            # For simplicity, we process each and the user might want them merged or separate.
            # MaxEnt usually wants separate files in a folder or stacked.
            # Here we follow the previous 'single output' pattern for geological maps.
            # If user selected both, we might need to handle it.
            # RATIONAL: If user selected MULTIPLE types, we should probably warn or handle merging.
            # But the user said "변수로 생성", usually they are separate files.
            
            # Implementation choice: if it's a single vector merge, we rasterize.
            # if they selected rasters, we just export them (maybe resampled).
            
            # Let's handle the VECTORS first as a single output.
            if target_layers and target_layers[0][0] == 'vector':
                v_layer = target_layers[0][1]
                params = {
                    'INPUT': v_layer,
                    'FIELD': 'LITHOIDX',
                    'UNITS': 1,
                    'WIDTH': resolution,
                    'HEIGHT': resolution,
                    'EXTENT': v_layer.extent(),
                    'NODATA': -9999,
                    'DATA_TYPE': 5, # Float32
                    'OUTPUT': save_path
                }
                processing.run("gdal:rasterize", params)
                QMessageBox.information(self, "성공", f"래스터 변환이 완료되었습니다:\n{save_path}")
                return

            # C. If they selected Rasters
            if raster_layers:
                # If multiple rasters, we just export the first one to the save_path for now
                # as the UI only asks for ONE save_path.
                # Better: Export them as separate files in a directory if multiple?
                # The user's request: "변수 생성할 수 있게 해주고"
                r_layer = raster_layers[0]
                params = {
                    'INPUT': r_layer,
                    'OUTPUT': save_path,
                    'RESOLUTION': resolution,
                    'RESAMPLING': 0, # Nearest Neighbour
                    'DATA_TYPE': 5
                }
                # Use gdal:translate for resampling
                translate_params = {
                    'INPUT': r_layer,
                    'TARGET_CRS': r_layer.crs(),
                    'NODATA': -9999,
                    'COPY_SUBDATASETS': False,
                    'OPTIONS': '',
                    'DATA_TYPE': 5,
                    'OUTPUT': save_path
                }
                # Add resolution override if possible or use warp
                processing.run("gdal:translate", translate_params)
                QMessageBox.information(self, "성공", f"래스터 내보내기가 완료되었습니다:\n{save_path}")

        except Exception as e:
            QMessageBox.critical(self, "오류", f"내보내기 중 오류가 발생했습니다:\n{str(e)}")

    def run_geochem_analysis(self):
        """
        Converts an RGB raster (WMS) to a numerical value raster based on legend.
        """
        # 1. Get WMS Layer from combo box (not active layer!)
        wms_layer_id = self.wms_layer_combo.currentData()
        if not wms_layer_id:
            QMessageBox.warning(self, "오류", "WMS 레이어를 선택해주세요.\n(레이어 목록 새로고침 버튼을 눌러 목록을 갱신하세요)")
            return
        
        layer = QgsProject.instance().mapLayer(wms_layer_id)
        if not layer or layer.type() != 1: # RasterLayer
            QMessageBox.warning(self, "오류", "선택한 레이어가 유효하지 않습니다. 래스터 레이어를 선택해주세요.")
            return

        # 2. Get Preset
        preset_key = self.geochem_preset_combo.currentData()
        preset_text = self.geochem_preset_combo.currentText()
        preset = geochem_utils.PRESETS.get(preset_key)
        
        # Log to built-in panel
        self.log("=========== GeoChem 분석 시작 ===========")
        self.log(f"활성 레이어: {layer.name()}")
        self.log(f"선택한 프리셋: {preset_text} (key={preset_key})")
        self.log(f"프리셋 확인: {preset.label if preset else 'NOT FOUND!'}")
        
        if not preset:
            QMessageBox.warning(self, "오류", f"프리셋을 찾을 수 없습니다: {preset_key}")
            return
        
        # 3. Get Save Path
        save_path, _ = QFileDialog.getSaveFileName(
            self, "수치화된 래스터 저장", "", "GeoTIFF (*.tif)"
        )
        if not save_path:
            return

        # 4. Processing
        tmp_dir = tempfile.mkdtemp(prefix="KigamGeo_")
        try:
            run_id = uuid.uuid4().hex[:6]
            rgb_path = os.path.join(tmp_dir, f"rgb_{run_id}.tif")
            
            # Use current canvas extent and resolution
            canvas = self.iface.mapCanvas()
            
            # DEFAULT: Canvas Extent and Size
            extent = canvas.extent()
            width = canvas.size().width()
            height = canvas.size().height()

            # IF Layer Selected: Use Layer Extent and Calculated Size
            target_res = self.geochem_res_spin.value()
            selected_extent_data = self.extent_layer_combo.currentData()
            selected_extent_layer = None

            if isinstance(selected_extent_data, str):
                selected_extent_layer = QgsProject.instance().mapLayer(selected_extent_data)
            elif selected_extent_data is not None and hasattr(selected_extent_data, "id"):
                # Backward compatibility for old combo values stored as layer objects.
                selected_extent_layer = selected_extent_data
            
            if selected_extent_layer:
                
                full_extent = selected_extent_layer.extent()
                # Transform to project CRS before export requests.
                tr = QgsCoordinateTransform(selected_extent_layer.crs(), QgsProject.instance().crs(), QgsProject.instance())
                extent = tr.transformBoundingBox(full_extent)
                
                # Calculate W/H based on resolution
                width = int(extent.width() / target_res)
                height = int(extent.height() / target_res)
                
                # Sanity check
                if width <= 0 or height <= 0:
                     raise ValueError("계산된 이미지 크기가 너무 작습니다. 해상도를 확인하세요.")
                
                self.log(f"분석 범위 (대상지): {selected_extent_layer.name()}")
            elif selected_extent_data is not None:
                self.log("[WARNING] 선택된 대상지 레이어를 찾을 수 없습니다. 전체 화면 범위로 진행합니다.")
            else:
                # If using Canvas Extent but want specific resolution?
                # User might zoom in and out. The original logic used canvas pixels (screenshot-like).
                # If user wants specific resolution on canvas extent:
                width = int(extent.width() / target_res)
                height = int(extent.height() / target_res)

            # Step A: Export current view to GeoTIFF
            if not geochem_utils.export_geotiff(layer, rgb_path, extent, width, height):
                raise RuntimeError("WMS 레이어 내보내기에 실패했습니다.")
                
            # Step B: Read and Process with Progress Dialog
            from PyQt5.QtWidgets import QProgressDialog
            from PyQt5.QtCore import Qt
            from qgis.core import QgsColorRampShader, QgsRasterShader, QgsSingleBandPseudoColorRenderer
            from PyQt5.QtGui import QColor
            
            progress = QProgressDialog("지구화학 분석 중...", "취소", 0, 100, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setValue(10)
            QCoreApplication.processEvents()
            
            ds = gdal.Open(rgb_path)
            band_count = ds.RasterCount
            if band_count < 3:
                raise RuntimeError("RGB 래스터는 최소 3밴드(R,G,B)가 필요합니다.")
            r = ds.GetRasterBand(1).ReadAsArray()
            g = ds.GetRasterBand(2).ReadAsArray()
            b = ds.GetRasterBand(3).ReadAsArray()
            alpha = None
            if band_count >= 4:
                try:
                    alpha = ds.GetRasterBand(4).ReadAsArray()
                except Exception:
                    alpha = None
            gt = ds.GetGeoTransform()
            proj = ds.GetProjection()
            
            progress.setValue(30)
            progress.setLabelText("RGB → 수치 변환 중...")
            QCoreApplication.processEvents()
            
            if progress.wasCanceled():
                raise RuntimeError("사용자가 취소했습니다.")
            
            # core transform (ArchToolkit-compatible, keyword-only args)
            val_arr = geochem_utils.interp_rgb_to_value(
                r=r, g=g, b=b,
                points=preset.points,
                snap_last_t=None # No snap
            )
            nodata_val = np.float32(-9999.0)
            
            progress.setValue(60)
            progress.setLabelText("NoData 처리 중...")
            QCoreApplication.processEvents()
            
            # Transparent pixels (if alpha band exists) -> NoData
            if alpha is not None:
                try:
                    transparent = alpha.astype(np.int16) <= 0
                    val_arr = val_arr.astype(np.float32)
                    val_arr[transparent] = nodata_val
                except Exception:
                    pass
            
            # Low values as NoData (like ArchToolkit)
            try:
                breaks = geochem_utils._points_to_breaks(preset.points)
                min_valid = float(breaks[1]) if len(breaks) >= 2 else None
                if min_valid is not None:
                    low_mask = np.isfinite(val_arr) & (val_arr != nodata_val) & (val_arr < np.float32(min_valid))
                    val_arr[low_mask] = nodata_val
            except Exception:
                pass
            
            progress.setValue(70)
            progress.setLabelText("경계선 보정 중...")
            QCoreApplication.processEvents()
            
            # Step C: Inpainting (Black lines)
            mask = geochem_utils.mask_black_lines(r, g, b)
            val_arr[mask] = nodata_val
            val_arr = geochem_utils.gdal_fill_nodata(val_arr, nodata_val, 30)
            
            progress.setValue(85)
            progress.setLabelText("파일 저장 중...")
            QCoreApplication.processEvents()
            
            # Step D: Save output
            out_ds = gdal.GetDriverByName("GTiff").Create(save_path, width, height, 1, gdal.GDT_Float32)
            out_ds.SetGeoTransform(gt)
            out_ds.SetProjection(proj)
            out_band = out_ds.GetRasterBand(1)
            out_band.WriteArray(val_arr)
            out_band.SetNoDataValue(float(nodata_val))
            out_ds = None
            ds = None
            
            progress.setValue(95)
            progress.setLabelText("레이어 스타일 적용 중...")
            QCoreApplication.processEvents()
            
            # Step E: Load into QGIS with Legend Styling
            from qgis.core import QgsRasterLayer
            new_layer = QgsRasterLayer(save_path, f"{preset.label} (수치화)")
            if new_layer.isValid():
                # Apply legend-based pseudo-color styling (ArchToolkit method)
                shader = QgsRasterShader()
                ramp = QgsColorRampShader()
                ramp.setColorRampType(QgsColorRampShader.Interpolated)
                items = []
                for p in preset.points:
                    try:
                        val = float(p.value)
                        col = QColor(int(p.rgb[0]), int(p.rgb[1]), int(p.rgb[2]))
                        items.append(QgsColorRampShader.ColorRampItem(val, col, f"{val:g}{preset.unit}"))
                    except Exception:
                        continue
                if items:
                    ramp.setColorRampItemList(items)
                    try:
                        ramp.setMinimumValue(float(items[0].value))
                        ramp.setMaximumValue(float(items[-1].value))
                    except Exception:
                        pass
                    shader.setRasterShaderFunction(ramp)
                    renderer = QgsSingleBandPseudoColorRenderer(new_layer.dataProvider(), 1, shader)
                    try:
                        renderer.setClassificationMin(float(items[0].value))
                        renderer.setClassificationMax(float(items[-1].value))
                    except Exception:
                        pass
                    new_layer.setRenderer(renderer)
                
                QgsProject.instance().addMapLayer(new_layer)
            
            progress.setValue(100)
            progress.close()
            QMessageBox.information(self, "성공", f"수치화 분석이 완료되었습니다:\n{save_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "오류", f"분석 중 오류 발생: {str(e)}")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

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
        self.action = QAction(QIcon(icon_path), "KIGAM Tools", self.iface.mainWindow())
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
        dialog.exec_()
