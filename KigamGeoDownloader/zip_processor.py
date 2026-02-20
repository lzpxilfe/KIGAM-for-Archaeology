# -*- coding: utf-8 -*-
import os
import re
import zipfile
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsRasterMarkerSymbolLayer,
    QgsRasterFillSymbolLayer,
    QgsMarkerSymbol,
    QgsFillSymbol,
    QgsCategorizedSymbolRenderer,
    QgsRendererCategory,
    QgsMessageLog,
    Qgis
)

class ZipProcessor:
    def __init__(self):
        # Temp directory to extract files
        self.extract_root = os.path.join(tempfile.gettempdir(), "KIGAM_Extract")
        if not os.path.exists(self.extract_root):
            os.makedirs(self.extract_root)

    @staticmethod
    def _normalize_token(text):
        if text is None:
            return ""
        normalized = unicodedata.normalize("NFC", str(text)).strip()
        if not normalized:
            return ""
        normalized = normalized.casefold()
        normalized = re.sub(r"[\s_\-./]+", "", normalized)
        return normalized

    @staticmethod
    def _redecode_variants(text):
        """
        Recover common mojibake cases caused by wrong codec assumptions.
        """
        variants = set()
        if not text:
            return variants

        codec_pairs = [
            ("latin1", "utf-8"),
            ("cp1252", "utf-8"),
            ("latin1", "cp949"),
            ("cp1252", "cp949"),
            ("latin1", "euc-kr"),
            ("cp1252", "euc-kr"),
            ("utf-8", "cp949"),
            ("cp949", "utf-8")
        ]

        for src_codec, dst_codec in codec_pairs:
            try:
                converted = text.encode(src_codec).decode(dst_codec)
                if converted and converted != text:
                    variants.add(converted)
            except Exception:
                continue

        return variants

    def _value_candidates(self, value):
        """
        Build multiple comparable keys from a field value/symbol name.
        This absorbs region prefixes and small text-format differences.
        """
        if value is None:
            return set()

        raw = unicodedata.normalize("NFC", str(value)).strip()
        if not raw:
            return set()

        candidates = set()

        def add_candidate(text):
            token = self._normalize_token(text)
            if token:
                candidates.add(token)

        source_values = {raw}
        source_values.update(self._redecode_variants(raw))

        for src in source_values:
            add_candidate(src)
            add_candidate(src.replace(" ", ""))
            add_candidate(src.replace("_", ""))
            add_candidate(src.replace("-", ""))
            add_candidate(re.sub(r"\(.*?\)|\[.*?\]", "", src).strip())

            # Remove common map index prefixes like FF23_, GF03_, etc.
            add_candidate(re.sub(r"^[A-Za-z]{1,4}\d{2,3}_", "", src))

            if "_" in src:
                add_candidate(src.split("_")[-1])
            if "-" in src:
                add_candidate(src.split("-")[-1])
            if "/" in src:
                add_candidate(src.split("/")[-1])

        return candidates

    def _build_symbol_index(self, sym_path):
        """
        Returns:
        - raw name -> png path
        - normalized candidate -> png path
        """
        raw_map = {}
        normalized_map = {}

        for file_name in os.listdir(sym_path):
            if not file_name.lower().endswith(".png"):
                continue

            symbol_name = os.path.splitext(file_name)[0]
            png_path = os.path.join(sym_path, file_name)
            raw_map[symbol_name] = png_path

            for key in self._value_candidates(symbol_name):
                if key not in normalized_map:
                    normalized_map[key] = png_path

        return raw_map, normalized_map

    def _resolve_symbol_path(self, value, raw_sym_files, normalized_sym_files):
        if value is None:
            return None

        raw_value = unicodedata.normalize("NFC", str(value)).strip()
        if not raw_value:
            return None

        if raw_value in raw_sym_files:
            return raw_sym_files[raw_value]

        for candidate in self._value_candidates(raw_value):
            if candidate in normalized_sym_files:
                return normalized_sym_files[candidate]

        return None

    @staticmethod
    def _parse_qml_mapping(qml_path):
        """
        Parse sidecar QML and extract:
        - categorized field name (renderer attr)
        - category value -> image stem mapping
        """
        if not qml_path or not os.path.exists(qml_path):
            return None, {}

        try:
            tree = ET.parse(qml_path)
            root = tree.getroot()
        except Exception:
            return None, {}

        renderer = root.find(".//renderer-v2")
        if renderer is None or renderer.get("type") != "categorizedSymbol":
            return None, {}

        field_name = (renderer.get("attr") or "").strip() or None

        symbol_to_image = {}
        for symbol_node in renderer.findall("./symbols/symbol"):
            symbol_id = symbol_node.get("name")
            if not symbol_id:
                continue

            image_prop = symbol_node.find(".//prop[@k='imageFile']")
            if image_prop is None:
                continue

            image_value = (image_prop.get("v") or "").replace("\\", "/")
            image_name = os.path.basename(image_value)
            image_stem = os.path.splitext(image_name)[0].strip()
            if image_stem:
                symbol_to_image[symbol_id] = image_stem

        value_to_image = {}
        for category_node in renderer.findall("./categories/category"):
            symbol_id = category_node.get("symbol")
            if not symbol_id:
                continue

            image_stem = symbol_to_image.get(symbol_id)
            if not image_stem:
                continue

            value = (category_node.get("value") or "").strip()
            value_to_image[value] = image_stem

        return field_name, value_to_image

    def _resolve_symbol_with_qml_map(
        self,
        value,
        qml_value_to_image,
        qml_normalized_map,
        raw_sym_files,
        normalized_sym_files
    ):
        """
        Resolve symbol path from QML category mapping first, then from direct value matching.
        """
        raw_value = unicodedata.normalize("NFC", str(value)).strip() if value is not None else ""

        image_stem = None
        if raw_value in qml_value_to_image:
            image_stem = qml_value_to_image[raw_value]
        else:
            for candidate in self._value_candidates(raw_value):
                if candidate in qml_normalized_map:
                    image_stem = qml_normalized_map[candidate]
                    break

        if image_stem:
            path_from_qml = self._resolve_symbol_path(image_stem, raw_sym_files, normalized_sym_files)
            if path_from_qml:
                return path_from_qml

        return self._resolve_symbol_path(raw_value, raw_sym_files, normalized_sym_files)

    def _find_best_matching_field(
        self,
        layer,
        raw_sym_files,
        normalized_sym_files,
        qml_field,
        qml_value_to_image,
        qml_normalized_map
    ):
        best_field = None
        max_matches = -1
        best_value_count = 0

        priority_fields = ['LITHOIDX', 'TYPE', 'ASGN_CODE', 'SIGN', 'CODE']
        all_fields = [f.name() for f in layer.fields()]

        if qml_field and qml_field in all_fields:
            priority_fields = [qml_field] + [f for f in priority_fields if f != qml_field]

        sorted_fields = [f for f in priority_fields if f in all_fields] + [f for f in all_fields if f not in priority_fields]

        for field_name in sorted_fields:
            idx = layer.fields().indexOf(field_name)
            if idx < 0:
                continue

            unique_values = layer.uniqueValues(idx)
            value_count = len(unique_values)
            matches = 0

            for val in unique_values:
                png_path = self._resolve_symbol_with_qml_map(
                    val,
                    qml_value_to_image,
                    qml_normalized_map,
                    raw_sym_files,
                    normalized_sym_files
                )
                if png_path:
                    matches += 1

            if matches > max_matches:
                max_matches = matches
                best_field = field_name
                best_value_count = value_count

        return best_field, max_matches, best_value_count

    @staticmethod
    def _encoding_preference_rank(encoding):
        # KIGAM shapefiles are predominantly CP949/EUC-KR encoded.
        # Prefer Korean legacy encodings on tie to avoid mojibake labels/category values.
        order = {
            "CP949": 4,
            "EUC-KR": 3,
            None: 2,
            "UTF-8": 1,
        }
        return order.get(encoding, 0)

    def _load_layer_with_best_encoding(self, shp_path, layer_name, sym_path=None, qml_path=None):
        raw_sym_files, normalized_sym_files = self._build_symbol_index(sym_path) if sym_path else ({}, {})
        qml_field, qml_value_to_image = self._parse_qml_mapping(qml_path)

        qml_normalized_map = {}
        for raw_value, image_stem in qml_value_to_image.items():
            for candidate in self._value_candidates(raw_value):
                if candidate not in qml_normalized_map:
                    qml_normalized_map[candidate] = image_stem

        candidate_encodings = ["CP949", "EUC-KR", None, "UTF-8"]
        best_layer = None
        best_encoding = None
        best_field = None
        best_matches = -1
        best_total_values = 0
        best_score = None

        for encoding in candidate_encodings:
            uri = shp_path if encoding is None else f"{shp_path}|encoding={encoding}"
            layer = QgsVectorLayer(uri, layer_name, "ogr")
            if not layer.isValid():
                continue

            if raw_sym_files:
                field_name, matches, total_values = self._find_best_matching_field(
                    layer,
                    raw_sym_files,
                    normalized_sym_files,
                    qml_field,
                    qml_value_to_image,
                    qml_normalized_map
                )
            else:
                field_name, matches, total_values = (None, 0, 0)

            score = (matches, self._encoding_preference_rank(encoding))
            if best_score is None or score > best_score:
                best_score = score
                best_layer = layer
                best_encoding = encoding
                best_field = field_name
                best_matches = matches
                best_total_values = total_values

        return best_layer, best_encoding, best_field, best_matches, best_total_values

    def _build_relinked_qml(self, qml_path, raw_sym_files, normalized_sym_files):
        if not qml_path or not os.path.exists(qml_path):
            return None, 0, 0

        try:
            tree = ET.parse(qml_path)
            root = tree.getroot()
        except Exception:
            return None, 0, 0

        total_image_props = 0
        relinked_count = 0
        for prop in root.findall(".//prop[@k='imageFile']"):
            total_image_props += 1
            image_value = (prop.get("v") or "").replace("\\", "/")
            image_name = os.path.basename(image_value)
            image_stem = os.path.splitext(image_name)[0].strip()
            if not image_stem:
                continue

            png_path = self._resolve_symbol_path(image_stem, raw_sym_files, normalized_sym_files)
            if not png_path:
                continue

            prop.set("v", png_path.replace("\\", "/"))
            relinked_count += 1

        if total_image_props == 0:
            return None, 0, 0

        relinked_qml = os.path.join(
            os.path.dirname(qml_path),
            f"{os.path.splitext(os.path.basename(qml_path))[0]}_kigam_relinked.qml"
        )
        tree.write(relinked_qml, encoding="UTF-8", xml_declaration=True)
        return relinked_qml, relinked_count, total_image_props

    @staticmethod
    def _load_named_style(layer, style_path):
        if not style_path or not os.path.exists(style_path):
            return False

        try:
            result = layer.loadNamedStyle(style_path)
        except Exception:
            return False

        if isinstance(result, bool):
            return result
        if isinstance(result, tuple):
            # QGIS versions differ: (message, ok) or (ok, message)
            for item in result:
                if isinstance(item, bool):
                    return item
            return False

        return True

    @staticmethod
    def _build_unique_group_name(root, base_name):
        unique_group_name = base_name
        suffix = 2
        while root.findGroup(unique_group_name) is not None:
            unique_group_name = f"{base_name}_{suffix}"
            suffix += 1
        return unique_group_name

    def process_zip(self, zip_path, font_family="Malgun Gothic", font_size=10):
        """
        Extracts ZIP, loads shapefiles, and applies styling.
        """
        zip_basename = os.path.splitext(os.path.basename(zip_path))[0]
        safe_prefix = re.sub(r"[^A-Za-z0-9._-]+", "_", zip_basename).strip("_") or "kigam_map"
        # Keep a unique extraction folder per load so symbol file paths remain valid.
        extract_dir = tempfile.mkdtemp(prefix=f"{safe_prefix}_", dir=self.extract_root)

        # Extract ZIP
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
        except Exception as e:
            QgsMessageLog.logMessage(f"Failed to extract ZIP: {str(e)}", "KIGAM Plugin", Qgis.Critical)
            return []

        # Locate 'sym' folder
        sym_path = None
        for root, dirs, files in os.walk(extract_dir):
            sym_dir = next((d for d in dirs if d.lower() == 'sym'), None)
            if sym_dir:
                sym_path = os.path.join(root, sym_dir)
                break
        
        if not sym_path:
            QgsMessageLog.logMessage("No 'sym' folder found in the ZIP.", "KIGAM Plugin", Qgis.Warning)

        # Load Shapefiles
        tree_root = QgsProject.instance().layerTreeRoot()
        loaded_layers = []
        target_group = None
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file.lower().endswith(".shp"):
                    shp_path = os.path.join(root, file)
                    layer_name = os.path.splitext(file)[0]
                    qml_path = os.path.join(root, f"{layer_name}.qml")
                    qml_path = qml_path if os.path.exists(qml_path) else None
                    layer, used_encoding, pre_field, pre_matches, pre_total = self._load_layer_with_best_encoding(
                        shp_path,
                        layer_name,
                        sym_path=sym_path,
                        qml_path=qml_path
                    )
                    
                    if not layer or not layer.isValid():
                        QgsMessageLog.logMessage(f"Failed to load layer: {shp_path}", "KIGAM Plugin", Qgis.Warning)
                        continue

                    if used_encoding is None:
                        enc_label = "default"
                    else:
                        enc_label = used_encoding
                    QgsMessageLog.logMessage(
                        f"{layer_name}: loaded with encoding '{enc_label}' (pre-match {pre_matches}/{pre_total}, field={pre_field})",
                        "KIGAM Plugin",
                        Qgis.Info
                    )

                    if target_group is None:
                        unique_group_name = self._build_unique_group_name(tree_root, zip_basename)
                        target_group = tree_root.addGroup(unique_group_name)
                        QgsMessageLog.logMessage(
                            f"Created layer group: {unique_group_name}",
                            "KIGAM Plugin",
                            Qgis.Info
                        )

                    # Add to project without auto-placement, then place directly in this ZIP group.
                    # This avoids inheriting currently selected layer-tree insertion context.
                    QgsProject.instance().addMapLayer(layer, False)
                    target_group.addLayer(layer)
                    loaded_layers.append(layer)

                    # Apply Styling if sym path exists
                    if sym_path:
                        self.apply_sym_styling(layer, sym_path, qml_path)
                    
                    # Apply Labeling for Litho layers
                    if 'Litho' in layer_name:
                         self.apply_labeling(layer, font_family, font_size)

        # Reorder inside the dedicated group.
        if target_group is not None and loaded_layers:
            self.organize_layers(target_group, loaded_layers)

        return loaded_layers

    def apply_sym_styling(self, layer, sym_path, qml_path=None):
        """
        Analyzes the layer to find a field matching the symbols in sym_path,
        and applies a categorized renderer using the PNGs.
        """
        raw_sym_files, normalized_sym_files = self._build_symbol_index(sym_path)
        if not raw_sym_files:
            return

        # Prefer native QML style when available, but relink image paths to extracted sym folder.
        relinked_qml, relinked_count, total_image_props = self._build_relinked_qml(
            qml_path,
            raw_sym_files,
            normalized_sym_files
        )
        if relinked_qml and self._load_named_style(layer, relinked_qml):
            layer.triggerRepaint()
            QgsMessageLog.logMessage(
                f"Applied sidecar QML to {layer.name()} (relinked {relinked_count}/{total_image_props} image paths)",
                "KIGAM Plugin",
                Qgis.Success
            )
            return
        if relinked_qml:
            QgsMessageLog.logMessage(
                f"Failed to apply relinked QML to {layer.name()}, falling back to sym-based renderer",
                "KIGAM Plugin",
                Qgis.Warning
            )

        qml_field, qml_value_to_image = self._parse_qml_mapping(qml_path)

        qml_normalized_map = {}
        for raw_value, image_stem in qml_value_to_image.items():
            for candidate in self._value_candidates(raw_value):
                if candidate not in qml_normalized_map:
                    qml_normalized_map[candidate] = image_stem
        
        # 1. Find the best matching field
        best_field, max_matches, _ = self._find_best_matching_field(
            layer,
            raw_sym_files,
            normalized_sym_files,
            qml_field,
            qml_value_to_image,
            qml_normalized_map
        )

        if not best_field:
            all_fields = [f.name() for f in layer.fields()]
            QgsMessageLog.logMessage(f"No matching field found for styling in layer {layer.name()}. Available fields: {', '.join(all_fields)}", "KIGAM Plugin", Qgis.Info)
            return

        QgsMessageLog.logMessage(f"Applying style to {layer.name()} using field '{best_field}' ({max_matches} matches)", "KIGAM Plugin", Qgis.Success)

        # 2. Create Categories
        categories = []
        unique_values = layer.uniqueValues(layer.fields().indexOf(best_field))
        missing_values = []
        
        for val in unique_values:
            val_str = str(val)
            symbol = None

            png_path = self._resolve_symbol_with_qml_map(
                val,
                qml_value_to_image,
                qml_normalized_map,
                raw_sym_files,
                normalized_sym_files
            )
            if png_path:
                
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
                missing_values.append(val_str)

        # 3. Apply Renderer
        if categories:
            renderer = QgsCategorizedSymbolRenderer(best_field, categories)
            layer.setRenderer(renderer)
            layer.triggerRepaint()

            if missing_values:
                preview = ", ".join(missing_values[:8])
                if len(missing_values) > 8:
                    preview += ", ..."
                QgsMessageLog.logMessage(
                    f"{layer.name()}: {len(missing_values)} value(s) had no matching PNG in sym ({preview})",
                    "KIGAM Plugin",
                    Qgis.Warning
                )

    def apply_labeling(self, layer, font_family, font_size):
        from qgis.core import (
            QgsVectorLayerSimpleLabeling, QgsPalLayerSettings, 
            QgsTextFormat, QgsTextBufferSettings
        )
        from qgis.PyQt.QtGui import QColor, QFont

        settings = QgsPalLayerSettings()
        
        # Determine Label Field (LITHOIDX is usually preferred)
        fields = [f.name() for f in layer.fields()]
        label_field = 'LITHOIDX' if 'LITHOIDX' in fields else 'LITHONAME' if 'LITHONAME' in fields else fields[0]
        settings.fieldName = label_field
        
        # Text Format
        text_format = QgsTextFormat()
        text_format.setFont(QFont(font_family))
        text_format.setSize(font_size)
        text_format.setColor(QColor("black"))
        
        # Buffer REMOVED as per request
        # buffer_settings = QgsTextBufferSettings()
        # buffer_settings.setEnabled(True)
        # ...
        
        settings.setFormat(text_format)

        # Placement: Horizontal (0), Free (1), etc.
        # For Polygons, we want "Over Point" or "Horizontal"
        settings.placement = QgsPalLayerSettings.Horizontal
        
        # Smart Placement Logic
        settings.centroidInside = True # Force label inside
        settings.fitInPolygonOnly = True # Don't draw if it doesn't fit
        settings.priority = 5 # Medium priority
        
        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
        layer.setLabelsEnabled(True)

    def organize_layers(self, group, layers):
        """
        Organize layers in an existing ZIP group:
        2. Points (Top)
        3. Lines (Middle)
        4. Polygons (Bottom)
        5. Reference/Frame (Very Bottom, Hidden)
        """
        if group is None or not layers:
            return

        # Separate layers by type/role
        points = []
        lines = []
        polygons = []
        reference = [] # Frame, Crosssectionline

        for layer in layers:
            name = layer.name().lower()
            if 'frame' in name or 'crosssectionline' in name:
                reference.append(layer)
            elif layer.geometryType() == 0: # Point
                points.append(layer)
            elif layer.geometryType() == 1: # Line
                lines.append(layer)
            else: # Polygon
                polygons.append(layer)

        # Desired Order in Group (Bottom to Top):
        # Reference -> Polygons -> Lines -> Points
        all_ordered = reference + polygons + lines + points
        
        for layer in all_ordered:
            node = group.findLayer(layer.id())
            if node:
                # Move into group
                clone = node.clone()
                # Insert at top of group (index 0) so reversed order works?
                # No, if we append, they go to bottom.
                # If we want Points at top, we should insert them last or ...
                # Let's verify standard behavior. addGroup adds to TOP of Tree.
                # We want Points at Top of Group. 
                # So if we iterate All Ordered (Ref -> ... -> Points) and insert at 0,
                # Reference goes to 0.
                # Polygon goes to 0 (Ref becomes 1).
                # ...
                # Point goes to 0.
                # So the order at 0 will be Points. Correct.
                
                group.insertChildNode(0, clone)
                group.removeChildNode(node)
                
                # Check visibility for reference layers
                if layer in reference:
                    # We need to get the node from the group now
                    # But wait, clone is the new node? No, clone is a QgsLayerTreeLayer object.
                    # QgsLayerTreeNode.setItemVisibilityChecked(False)
                    clone.setItemVisibilityChecked(False)
                
                # Expand group
                group.setExpanded(True)
