# -*- coding: utf-8 -*-


from qgis.PyQt.QtCore import QSettings, QTranslator, qVersion, QCoreApplication
from qgis.PyQt.QtWidgets import QAction, QMessageBox, QFileDialog
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProject

import os.path
from .zip_processor import ZipProcessor

class KigamGeoDownloader:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        self.action = QAction(QIcon(icon_path), "Load KIGAM ZIP", self.iface.mainWindow())
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
        zip_path, _ = QFileDialog.getOpenFileName(
            self.iface.mainWindow(),
            "Select KIGAM ZIP File",
            "",
            "ZIP Files (*.zip *.ZIP)"
        )
        
        if not zip_path:
            return

        processor = ZipProcessor()
        loaded_layers = processor.process_zip(zip_path)
        
        if loaded_layers:
            QMessageBox.information(self.iface.mainWindow(), "Success", f"Loaded {len(loaded_layers)} layers from ZIP.")
            # Zoom to the first layer
            if loaded_layers[0].isValid():
                canvas = self.iface.mapCanvas()
                canvas.setExtent(loaded_layers[0].extent())
                canvas.refresh()
        else:
            QMessageBox.warning(self.iface.mainWindow(), "Warning", "No layers were loaded. Check the log for details.")

