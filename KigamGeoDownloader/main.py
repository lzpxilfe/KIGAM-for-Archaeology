
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
from .zip_processor import ZipProcessor

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

