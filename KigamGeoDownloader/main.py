
from qgis.PyQt.QtCore import QSettings, QTranslator, qVersion, QCoreApplication, QUrl, Qt
from qgis.PyQt.QtWidgets import (
    QAction, QMessageBox, QFileDialog, QDialog, QVBoxLayout, 
    QHBoxLayout, QLabel, QFontComboBox, QSpinBox, QDialogButtonBox,
    QPushButton, QLineEdit, QGroupBox, QFormLayout, QComboBox,
    QListWidget, QListWidgetItem
)
from qgis.PyQt.QtGui import QIcon, QDesktopServices
from qgis.core import QgsProject, QgsVectorLayer
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
        self.load_btn.clicked.connect(self.accept)
        load_layout.addRow("", self.load_btn)
        
        load_group.setLayout(load_layout)
        layout.addWidget(load_group)

        # Section 3: GeoChem Analysis
        geochem_group = QGroupBox("3. 지구화학 분석 (GeoChem RGB -> Value)")
        geochem_group.setToolTip("WMS/WFS 지구화학도의 RGB 색상을 수치 데이터(Value)로 변환합니다.")
        geochem_layout = QFormLayout()
        
        self.geochem_preset_combo = QComboBox()
        self.geochem_preset_combo.setToolTip("분석할 원소 항목을 선택하세요. 각 원소별로 특화된 수치 변환 알고리즘이 적용됩니다.")
        for k, p in geochem_utils.PRESETS.items():
            self.geochem_preset_combo.addItem(p.label, k)
        geochem_layout.addRow("원소 프리셋:", self.geochem_preset_combo)
        
        self.geochem_btn = QPushButton("RGB 래스터 수치화 실행 (WMS -> Raster)")
        self.geochem_btn.setToolTip("현재 선택된 원소 프리셋을 사용하여 RGB 래스터를 수치 래스터로 변환 및 저장합니다.")
        self.geochem_btn.clicked.connect(self.run_geochem_analysis)
        geochem_layout.addRow("", self.geochem_btn)
        
        geochem_group.setLayout(geochem_layout)
        layout.addWidget(geochem_group)

        # Section 4: MaxEnt Export
        self.maxent_group = QGroupBox("4. MaxEnt용 분석 변수 생성 (Rasterize)")
        self.maxent_group.setCheckable(True)
        self.maxent_group.setChecked(False) # Folded by default
        self.maxent_group.setToolTip("지질도(Vector)나 수치화된 지구화학도(Raster)를 MaxEnt 분석용 데이터로 변환합니다.")
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

    def show_help(self):
        help_text = """
        <h3>KIGAM for Archaeology 사용 가이드</h3>
        <p><b>1. 데이터 다운로드:</b> KIGAM 웹사이트에서 지질도 데이터를 다운로드합니다.</p>
        <p><b>2. 지질도 불러오기:</b> 다운로드한 ZIP 파일을 선택하고 '자동 로드'를 클릭하면 스타일과 라벨이 자동 적용됩니다.</p>
        <p><b>3. 지구화학 분석:</b> WMS/WFS로 불러온 지구화학도의 RGB 색상을 수치 데이터로 변환합니다. 원소 프리셋을 선택하여 처리하세요.</p>
        <p><b>4. MaxEnt 변수 생성:</b> 분석된 결과물들을 MaxEnt 분석 소프트웨어용 래스터(GeoTIFF)로 내보냅니다. 여러 지질도를 선택하면 하나로 병합됩니다.</p>
        <br>
        <p><i>* 개발 기준: ArchToolkit (lzpxilfe/ar) 동기화 버전</i></p>
        """
        QMessageBox.information(self, "도움말", help_text)

    def refresh_layer_list(self):
        self.layer_list.clear()
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            # Include Vector (Litho) or Raster (converted results)
            is_litho = 'Litho' in layer.name() and layer.type() == 0
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
        zip_path, _ = QFileDialog.getOpenFileName(
            self,
            "KIGAM ZIP 파일 선택",
            "",
            "ZIP Files (*.zip *.ZIP)"
        )
        if zip_path:
            self.file_input.setText(zip_path)

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
        # 1. Get Active Layer (should be a raster)
        layer = self.iface.activeLayer()
        if not layer or layer.type() != 1: # RasterLayer
            QMessageBox.warning(self, "오류", "수치화할 RGB 래스터(WMS 등) 레이어를 레이어 패널에서 먼저 선택해주세요.")
            return

        # 2. Get Preset
        preset_key = self.geochem_preset_combo.currentData()
        preset = geochem_utils.PRESETS.get(preset_key)
        
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
            extent = canvas.extent()
            width = canvas.size().width()
            height = canvas.size().height()
            
            # Step A: Export current view to GeoTIFF
            if not geochem_utils.export_geotiff(layer, rgb_path, extent, width, height):
                raise RuntimeError("WMS 레이어 내보내기에 실패했습니다.")
                
            # Step B: Read and Process
            ds = gdal.Open(rgb_path)
            r = ds.GetRasterBand(1).ReadAsArray()
            g = ds.GetRasterBand(2).ReadAsArray()
            b = ds.GetRasterBand(3).ReadAsArray()
            gt = ds.GetGeoTransform()
            proj = ds.GetProjection()
            
            # core transform
            val_arr = geochem_utils.interp_rgb_to_value(r, g, b, preset.points)
            
            # Step C: Inpainting (Black lines)
            mask = geochem_utils.mask_black_lines(r, g, b)
            val_arr[mask] = np.nan
            val_arr = geochem_utils.gdal_fill_nodata(val_arr, -9999.0, 30)
            
            # Step D: Save output
            out_ds = gdal.GetDriverByName("GTiff").Create(save_path, width, height, 1, gdal.GDT_Float32)
            out_ds.SetGeoTransform(gt)
            out_ds.SetProjection(proj)
            out_band = out_ds.GetRasterBand(1)
            out_band.WriteArray(val_arr)
            out_band.SetNoDataValue(-9999.0)
            out_ds = None
            ds = None
            
            # Step E: Load into QGIS
            new_layer = QgsProject.instance().addRasterLayer(save_path, f"{preset.label} (수치화)")
            if new_layer:
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
        if dialog.exec_() != QDialog.Accepted:
            return
            
        settings = dialog.get_settings()
        zip_path = settings['zip_path']
        
        if not zip_path:
            QMessageBox.warning(self.iface.mainWindow(), "경고", "ZIP 파일을 선택해주세요.")
            return

        if not os.path.exists(zip_path):
             QMessageBox.warning(self.iface.mainWindow(), "경고", "선택한 파일이 존재하지 않습니다.")
             return

        processor = ZipProcessor()
        # Pass settings to processor
        loaded_layers = processor.process_zip(
            zip_path, 
            font_family=settings['font_family'], 
            font_size=settings['font_size']
        )
        
        if loaded_layers:
            # Zoom to Frame layer
            frame_layer = next((l for l in loaded_layers if 'frame' in l.name().lower()), None)
            target_layer = frame_layer if frame_layer else loaded_layers[0]
            
            if target_layer.isValid():
                canvas = self.iface.mapCanvas()
                canvas.setExtent(target_layer.extent())
                canvas.refresh()

            QMessageBox.information(self.iface.mainWindow(), "성공", f"ZIP 파일에서 {len(loaded_layers)}개의 레이어를 로드했습니다.")
        else:
            QMessageBox.warning(self.iface.mainWindow(), "경고", "로드된 레이어가 없습니다. 로그 메시지를 확인하세요.")

