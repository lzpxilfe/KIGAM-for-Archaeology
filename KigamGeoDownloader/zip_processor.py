# -*- coding: utf-8 -*-
import os
import shutil
import zipfile
import tempfile
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsRasterMarkerSymbolLayer,
    QgsRasterFillSymbolLayer,
    QgsMarkerSymbol,
    QgsFillSymbol,
    QgsSingleSymbolRenderer,
    QgsCategorizedSymbolRenderer,
    QgsRendererCategory,
    QgsMessageLog,
    Qgis
)
from qgis.PyQt.QtCore import QFileInfo

class ZipProcessor:
    def __init__(self):
        # Temp directory to extract files
        self.extract_root = os.path.join(tempfile.gettempdir(), "KIGAM_Extract")
        if not os.path.exists(self.extract_root):
            os.makedirs(self.extract_root)

    def process_zip(self, zip_path):
        """
        Extracts ZIP, loads shapefiles, and applies styling.
        """
        extract_dir = os.path.join(self.extract_root, os.path.splitext(os.path.basename(zip_path))[0])
        
        # Clean up previous extraction if exists
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        os.makedirs(extract_dir)

        # Extract ZIP
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
        except Exception as e:
            QgsMessageLog.logMessage(f"Failed to extract ZIP: {str(e)}", "KIGAM Plugin", Qgis.Critical)
            return

        # Locate 'sym' folder
        sym_path = None
        for root, dirs, files in os.walk(extract_dir):
            if 'sym' in dirs:
                sym_path = os.path.join(root, 'sym')
                break
        
        if not sym_path:
            QgsMessageLog.logMessage("No 'sym' folder found in the ZIP.", "KIGAM Plugin", Qgis.Warning)

        # Load Shapefiles
        loaded_layers = []
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file.lower().endswith(".shp"):
                    shp_path = os.path.join(root, file)
                    layer_name = os.path.splitext(file)[0]
                    
                    # Force cp949 encoding for Korean support
                    layer = QgsVectorLayer(f"{shp_path}|layername={layer_name}", layer_name, "ogr")
                    layer.setProviderEncoding("cp949")
                    
                    if not layer.isValid():
                        QgsMessageLog.logMessage(f"Failed to load layer: {shp_path}", "KIGAM Plugin", Qgis.Warning)
                        continue
                    
                    QgsProject.instance().addMapLayer(layer)
                    loaded_layers.append(layer)

                    # Apply Styling if sym path exists
                    if sym_path:
                        self.apply_sym_styling(layer, sym_path)

        return loaded_layers

    def apply_sym_styling(self, layer, sym_path):
        """
        Analyzes the layer to find a field matching the symbols in sym_path,
        and applies a categorized renderer using the PNGs.
        """
        # Get list of symbol names (without extension)
        sym_files = {os.path.splitext(f)[0]: os.path.join(sym_path, f) for f in os.listdir(sym_path) if f.lower().endswith('.png')}
        
        if not sym_files:
            return

        # 1. Find the best matching field
        best_field = None
        max_matches = 0
        
        # Prioritize certain fields if they exist, but verify content
        priority_fields = ['LITHOIDX', 'TYPE', 'ASGN_CODE', 'SIGN', 'CODE']
        all_fields = [f.name() for f in layer.fields()]
        
        # Sort fields to check priority ones first, then others
        sorted_fields = [f for f in priority_fields if f in all_fields] + [f for f in all_fields if f not in priority_fields]

        for field_name in sorted_fields:
            # Check unique values in this field
            # We limit to first 100 features for performance if dataset is huge, 
            # but usually KIGAM maps fit in memory easily.
            idx = layer.fields().indexOf(field_name)
            unique_values = layer.uniqueValues(idx)
            
            matches = 0
            for val in unique_values:
                if str(val) in sym_files:
                    matches += 1
            
            # Simple heuristic: if we match more than 0 and it's better than before
            if matches > max_matches:
                max_matches = matches
                best_field = field_name

        if not best_field:
            QgsMessageLog.logMessage(f"No matching field found for styling in layer {layer.name()}", "KIGAM Plugin", Qgis.Info)
            return

        QgsMessageLog.logMessage(f"Applying style to {layer.name()} using field '{best_field}' ({max_matches} matches)", "KIGAM Plugin", Qgis.Success)

        # 2. Create Categories
        categories = []
        unique_values = layer.uniqueValues(layer.fields().indexOf(best_field))
        
        for val in unique_values:
            val_str = str(val)
            symbol = None
            
            if val_str in sym_files:
                png_path = sym_files[val_str]
                
                if layer.geometryType() == 0: # Point
                    # Create Raster Marker
                    symbol_layer = QgsRasterMarkerSymbolLayer(png_path)
                    symbol_layer.setSize(6) # Default size
                    symbol = QgsMarkerSymbol()
                    symbol.changeSymbolLayer(0, symbol_layer)
                    
                elif layer.geometryType() == 2: # Polygon
                    # Create Raster Fill
                    symbol_layer = QgsRasterFillSymbolLayer()
                    symbol_layer.setImageFilePath(png_path)
                    symbol_layer.setWidth(10.0) # Adjust pattern scale/width
                    symbol = QgsFillSymbol()
                    symbol.changeSymbolLayer(0, symbol_layer)
            
            # If no symbol found (or geometry not supported for raster), default symbol is used (random color)
            if symbol:
                category = QgsRendererCategory(val, symbol, val_str)
                categories.append(category)
            else:
                # Add a fallback category with default style if needed, 
                # or just let QGIS handle unclassified (it usually doesn't show them if not added)
                # Here we recreate a default symbol for the geometry type
                if layer.geometryType() == 0:
                   symbol = QgsMarkerSymbol.createSimple({'color': '#ff0000'})
                elif layer.geometryType() == 2:
                   symbol = QgsFillSymbol.createSimple({'color': '#cccccc', 'outline_color': 'black'})
                else: 
                   continue # Skip lines for now as raster data usually doesn't apply to lines
                
                category = QgsRendererCategory(val, symbol, val_str)
                categories.append(category)

        # 3. Apply Renderer
        if categories:
            renderer = QgsCategorizedSymbolRenderer(best_field, categories)
            layer.setRenderer(renderer)
            layer.triggerRepaint()
