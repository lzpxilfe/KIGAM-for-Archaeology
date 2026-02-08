
from qgis.PyQt.QtCore import QSettings, QTranslator, qVersion, QCoreApplication, QUrl, Qt
from qgis.PyQt.QtWidgets import (
    QAction, QMessageBox, QFileDialog, QDialog, QVBoxLayout, 
    QHBoxLayout, QLabel, QFontComboBox, QSpinBox, QDialogButtonBox,
    QPushButton, QLineEdit, QGroupBox, QFormLayout
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
        download_layout = QVBoxLayout()
        download_btn = QPushButton("KIGAM 데이터 다운로드 페이지 열기")
        download_btn.clicked.connect(self.open_kigam_website)
        download_layout.addWidget(QLabel("지질자원연구원 사이트에서 지질도(ZIP)를 다운로드하세요:"))
        download_layout.addWidget(download_btn)
        download_group.setLayout(download_layout)
        layout.addWidget(download_group)
        
        # Section 2: Load Map
        load_group = QGroupBox("2. 지적도 불러오기 (Load Map)")
        load_layout = QFormLayout()
        
        # File Input
        self.file_input = QLineEdit()
        self.browse_btn = QPushButton("...")
        self.browse_btn.clicked.connect(self.browse_zip_file)
        file_layout = QHBoxLayout()
        file_layout.addWidget(self.file_input)
        file_layout.addWidget(self.browse_btn)
        load_layout.addRow("ZIP 파일:", file_layout)
        
        # Font Settings
        self.font_combo = QFontComboBox()
        load_layout.addRow("라벨 글꼴:", self.font_combo)
        
        self.size_spin = QSpinBox()
        self.size_spin.setRange(5, 50)
        self.size_spin.setValue(10)
        load_layout.addRow("글꼴 크기:", self.size_spin)
        
        self.load_btn = QPushButton("지동 로드 및 스타일 적용")
        self.load_btn.clicked.connect(self.accept)
        load_layout.addRow("", self.load_btn)
        
        load_group.setLayout(load_layout)
        layout.addWidget(load_group)
        
        # Section 3: MaxEnt Export
        maxent_group = QGroupBox("3. MaxEnt용 분석 변수 생성 (Rasterize)")
        maxent_layout = QFormLayout()
        
        self.res_spin = QSpinBox()
        self.res_spin.setRange(1, 1000)
        self.res_spin.setValue(10)
        self.res_spin.setSuffix(" m")
        maxent_layout.addRow("해상도 (Resolution):", self.res_spin)
        
        self.export_btn = QPushButton("Litho 레이어를 래스터로 파일로 내보내기")
        self.export_btn.clicked.connect(self.export_maxent_raster)
        maxent_layout.addRow("", self.export_btn)
        
        maxent_group.setLayout(maxent_layout)
        layout.addWidget(maxent_group)
        
        # Section 4: GeoChem Analysis
        geochem_group = QGroupBox("4. 지구화학 분석 (GeoChem RGB -> Value)")
        geochem_layout = QFormLayout()
        
        self.geochem_preset_combo = QgsMapLayerComboBox() # Using it as a simple combo for presets
        # Actually QgsMapLayerComboBox is for layers. Let's use QComboBox and populate presets.
        from qgis.PyQt.QtWidgets import QComboBox
        self.geochem_preset_combo = QComboBox()
        for k, p in geochem_utils.PRESETS.items():
            self.geochem_preset_combo.addItem(p.label, k)
        geochem_layout.addRow("원소 프리셋:", self.geochem_preset_combo)
        
        self.geochem_btn = QPushButton("RGB 래스터 수치화 실행 (WMS -> Raster)")
        self.geochem_btn.clicked.connect(self.run_geochem_analysis)
        geochem_layout.addRow("", self.geochem_btn)
        
        geochem_group.setLayout(geochem_layout)
        layout.addWidget(geochem_group)
        
        # Dialog Buttons (Close only, as we have specific action buttons)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        
        self.setLayout(layout)

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
        Rasterizes the 'Litho' layer using LITHOIDX field.
        """
        # 1. Find Litho Layer
        layers = QgsProject.instance().mapLayers().values()
        litho_layer = next((l for l in layers if 'Litho' in l.name() and l.type() == 0), None)
        
        if not litho_layer:
            QMessageBox.warning(self, "오류", "현재 프로젝트에 'Litho' 레이어가 없습니다. 먼저 지질도를 로드해주세요.")
            return

        # 2. Get Save Path
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "래스터 파일 저장",
            "",
            "ASCII Grids (*.asc);;GeoTIFF (*.tif)"
        )
        if not save_path:
            return

        # 3. Running Rasterization
        resolution = self.res_spin.value()
        
        try:
            # Check if LITHOIDX field exists
            if litho_layer.fields().indexOf('LITHOIDX') == -1:
                QMessageBox.warning(self, "오류", f"레이어에 'LITHOIDX' 필드가 없습니다. ({litho_layer.name()})")
                return

            params = {
                'INPUT': litho_layer,
                'FIELD': 'LITHOIDX',
                'UNITS': 1, # Georeferenced units
                'WIDTH': resolution,
                'HEIGHT': resolution,
                'EXTENT': litho_layer.extent(),
                'NODATA': -9999,
                'DATA_TYPE': 5, # Float32 (or 1 for Int16/Int32 if preferred, but MaxEnt likes ASC)
                'OUTPUT': save_path
            }
            
            # Use gdal:rasterize for better compatibility with .asc
            processing.run("gdal:rasterize", params)
            
            QMessageBox.information(self, "성공", f"래스터 변환이 완료되었습니다:\n{save_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "오류", f"래스터 변환 중 예상치 못한 오류가 발생했습니다:\n{str(e)}")

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

