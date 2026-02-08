# -*- coding: utf-8 -*-





from qgis.PyQt.QtCore import QSettings, QTranslator, qVersion, QCoreApplication, QUrl
from qgis.PyQt.QtWidgets import (
    QAction, QMessageBox, QFileDialog, QDialog, QVBoxLayout, 
    QHBoxLayout, QLabel, QFontComboBox, QSpinBox, QDialogButtonBox,
    QPushButton, QLineEdit, QGroupBox, QFormLayout
)
from qgis.PyQt.QtGui import QIcon, QDesktopServices
from qgis.core import QgsProject

import os.path
from .zip_processor import ZipProcessor

class MainDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("KIGAM Tools")
        self.resize(400, 300)
        
        layout = QVBoxLayout()
        
        # Section 1: Data Download
        download_group = QGroupBox("1. KIGAM Data Download")
        download_layout = QVBoxLayout()
        download_btn = QPushButton("Open KIGAM Download Page")
        download_btn.clicked.connect(self.open_kigam_website)
        download_layout.addWidget(QLabel("Visit the KIGAM website to download geological maps:"))
        download_layout.addWidget(download_btn)
        download_group.setLayout(download_layout)
        layout.addWidget(download_group)
        
        # Section 2: Load Map
        load_group = QGroupBox("2. Load Map")
        load_layout = QFormLayout()
        
        # File Input
        self.file_input = QLineEdit()
        self.browse_btn = QPushButton("...")
        self.browse_btn.clicked.connect(self.browse_file)
        file_layout = QHBoxLayout()
        file_layout.addWidget(self.file_input)
        file_layout.addWidget(self.browse_btn)
        load_layout.addRow("ZIP File:", file_layout)
        
        # Font Settings
        self.font_combo = QFontComboBox()
        load_layout.addRow("Label Font:", self.font_combo)
        
        self.size_spin = QSpinBox()
        self.size_spin.setRange(5, 50)
        self.size_spin.setValue(10)
        load_layout.addRow("Font Size:", self.size_spin)
        
        load_group.setLayout(load_layout)
        layout.addWidget(load_group)
        
        # Dialog Buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Load Map")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        
        self.setLayout(layout)

    def open_kigam_website(self):
        QDesktopServices.openUrl(QUrl("https://data.kigam.re.kr/search?subject=Geology"))

    def browse_file(self):
        zip_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select KIGAM ZIP File",
            "",
            "ZIP Files (*.zip *.ZIP)"
        )
        if zip_path:
            self.file_input.setText(zip_path)

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
        del self.toolbar
        del self.action

    def run(self):
        # Show Main Dialog
        dialog = MainDialog(self.iface.mainWindow())
        if dialog.exec_() != QDialog.Accepted:
            return
            
        settings = dialog.get_settings()
        zip_path = settings['zip_path']
        
        if not zip_path:
            QMessageBox.warning(self.iface.mainWindow(), "Warning", "Please select a ZIP file.")
            return

        if not os.path.exists(zip_path):
             QMessageBox.warning(self.iface.mainWindow(), "Warning", "File does not exist.")
             return

        processor = ZipProcessor()
        # Pass settings to processor
        loaded_layers = processor.process_zip(
            zip_path, 
            font_family=settings['font_family'], 
            font_size=settings['font_size']
        )
        
        if loaded_layers:
            QMessageBox.information(self.iface.mainWindow(), "Success", f"Loaded {len(loaded_layers)} layers from ZIP.")
            
            # Zoom to Frame layer
            frame_layer = next((l for l in loaded_layers if 'frame' in l.name().lower()), None)
            target_layer = frame_layer if frame_layer else loaded_layers[0]
            
            if target_layer.isValid():
                canvas = self.iface.mapCanvas()
                canvas.setExtent(target_layer.extent())
                canvas.refresh()
        else:
            QMessageBox.warning(self.iface.mainWindow(), "Warning", "No layers were loaded. Check the log for details.")



