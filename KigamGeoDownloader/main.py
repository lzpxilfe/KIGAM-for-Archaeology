# -*- coding: utf-8 -*-




from qgis.PyQt.QtCore import QSettings, QTranslator, qVersion, QCoreApplication, QUrl
from qgis.PyQt.QtWidgets import (
    QAction, QMessageBox, QFileDialog, QDialog, QVBoxLayout, 
    QHBoxLayout, QLabel, QFontComboBox, QSpinBox, QDialogButtonBox
)
from qgis.PyQt.QtGui import QIcon, QDesktopServices
from qgis.core import QgsProject

import os.path
from .zip_processor import ZipProcessor

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("KIGAM Load Settings")
        self.resize(300, 150)
        
        layout = QVBoxLayout()
        
        # Font Family
        font_layout = QHBoxLayout()
        font_layout.addWidget(QLabel("Font Family:"))
        self.font_combo = QFontComboBox()
        # Set default to something common if possible, or let it be system default
        font_layout.addWidget(self.font_combo)
        layout.addLayout(font_layout)
        
        # Font Size
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Font Size:"))
        self.size_spin = QSpinBox()
        self.size_spin.setRange(5, 50)
        self.size_spin.setValue(10)
        size_layout.addWidget(self.size_spin)
        layout.addLayout(size_layout)
        
        # Dialog Buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        
        self.setLayout(layout)

    def get_settings(self):
        return {
            'font_family': self.font_combo.currentFont().family(),
            'font_size': self.size_spin.value()
        }

class KigamGeoDownloader:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        self.action = QAction(QIcon(icon_path), "Load KIGAM ZIP", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        # Help/Download Action
        self.help_action = QAction(QIcon(os.path.join(self.plugin_dir, 'icon.png')), "Download KIGAM Data", self.iface.mainWindow()) # Reusing icon for now or can use standard QGIS icon
        self.help_action.triggered.connect(self.open_kigam_website)
        
        # Add to Menu
        self.iface.addPluginToMenu("&KIGAM for Archaeology", self.action)
        self.iface.addPluginToMenu("&KIGAM for Archaeology", self.help_action)
        
        # Add to Dedicated Toolbar
        self.toolbar = self.iface.addToolBar("KIGAM for Archaeology")
        self.toolbar.setObjectName("KIGAMForArchaeology")
        self.toolbar.addAction(self.action)
        self.toolbar.addAction(self.help_action)

    def unload(self):
        # Remove Menu
        self.iface.removePluginMenu("&KIGAM for Archaeology", self.action)
        self.iface.removePluginMenu("&KIGAM for Archaeology", self.help_action)
        
        # Remove Toolbar
        del self.toolbar
        
        del self.action
        del self.help_action

    def open_kigam_website(self):
        QDesktopServices.openUrl(QUrl("https://data.kigam.re.kr/search?subject=Geology"))

    def run(self):
        zip_path, _ = QFileDialog.getOpenFileName(
            self.iface.mainWindow(),
            "Select KIGAM ZIP File",
            "",
            "ZIP Files (*.zip *.ZIP)"
        )
        
        if not zip_path:
            return

        # Show Settings Dialog
        dialog = SettingsDialog(self.iface.mainWindow())
        if dialog.exec_() != QDialog.Accepted:
            return
            
        settings = dialog.get_settings()

        processor = ZipProcessor()
        # Pass settings to processor
        loaded_layers = processor.process_zip(
            zip_path, 
            font_family=settings['font_family'], 
            font_size=settings['font_size']
        )
        
        if loaded_layers:
            QMessageBox.information(self.iface.mainWindow(), "Success", f"Loaded {len(loaded_layers)} layers from ZIP.")
            # Zoom to the first layer (usually the most relevant one if sorted, or just the first)
            # Since we reorder, let's find the 'Litho' layer or just use the extent of the set
            
            # Find Litho layer to zoom to as it is the main map
            litho_layer = next((l for l in loaded_layers if 'Litho' in l.name()), None)
            target_layer = litho_layer if litho_layer else loaded_layers[0]
            
            if target_layer.isValid():
                canvas = self.iface.mapCanvas()
                canvas.setExtent(target_layer.extent())
                canvas.refresh()
        else:
            QMessageBox.warning(self.iface.mainWindow(), "Warning", "No layers were loaded. Check the log for details.")


