# -*- coding: utf-8 -*-
import os
import ntpath
import re
import tempfile
import shutil
import unicodedata
from pathlib import Path
from .archive_utils import extract_archive
from .encoding_utils import detect_dbf_encoding, sidecar
from .pattern_utils import scale_patterns
from .defusedxml import ElementTree as ET
from .plugin_config import PLUGIN_CONFIG, DEFAULT_PLUGIN_CONFIG
from qgis.core import (
    QgsProject,
    QgsApplication,
    QgsVectorLayer,
    QgsRasterMarkerSymbolLayer,
    QgsRasterFillSymbolLayer,
    QgsMarkerSymbol,
    QgsFillSymbol,
    QgsCategorizedSymbolRenderer,
    QgsRendererCategory,
    QgsRenderContext,
    QgsMessageLog,
    Qgis
)


ZIP_CONFIG = PLUGIN_CONFIG.get("zip_processor", {})
UI_CONFIG = PLUGIN_CONFIG.get("ui", {})
LABEL_FONT_CONFIG = UI_CONFIG.get("label_font", {})
DEFAULT_ZIP_CONFIG = DEFAULT_PLUGIN_CONFIG.get("zip_processor", {})
DEFAULT_UI_CONFIG = DEFAULT_PLUGIN_CONFIG.get("ui", {})
DEFAULT_LABEL_FONT_CONFIG = DEFAULT_UI_CONFIG.get("label_font", {})

SYMBOL_PRIORITY_FIELDS = [
    str(v).strip() for v in ZIP_CONFIG.get("symbol_priority_fields", DEFAULT_ZIP_CONFIG.get("symbol_priority_fields", []))
    if isinstance(v, str) and str(v).strip()
] or list(DEFAULT_ZIP_CONFIG.get("symbol_priority_fields", []))

CANDIDATE_ENCODINGS = ZIP_CONFIG.get("candidate_encodings", list(
    DEFAULT_ZIP_CONFIG.get("candidate_encodings", [None])))
if not isinstance(CANDIDATE_ENCODINGS, list) or not CANDIDATE_ENCODINGS:
    CANDIDATE_ENCODINGS = list(
        DEFAULT_ZIP_CONFIG.get("candidate_encodings", [None]))

DEFAULT_FONT_FAMILY = str(
    LABEL_FONT_CONFIG.get("default_family", DEFAULT_LABEL_FONT_CONFIG.get(
        "default_family", "Malgun Gothic"))
).strip() or "Malgun Gothic"
QML_WRITE_ENCODING = str(
    ZIP_CONFIG.get("qml_write_encoding", DEFAULT_ZIP_CONFIG.get(
        "qml_write_encoding", "UTF-8"))
).strip() or "UTF-8"
FILL_SYMBOL_WIDTH = float(
    ZIP_CONFIG.get("fill_symbol_width", DEFAULT_ZIP_CONFIG.get(
        "fill_symbol_width", 10.0))
)
MARKER_SYMBOL_SIZE = float(
    ZIP_CONFIG.get("marker_symbol_size",
                   DEFAULT_ZIP_CONFIG.get("marker_symbol_size", 6.0))
)
REFERENCE_LAYER_KEYWORDS = [
    str(v).strip().lower()
    for v in ZIP_CONFIG.get("reference_layer_keywords", DEFAULT_ZIP_CONFIG.get("reference_layer_keywords", []))
    if isinstance(v, str) and str(v).strip()
]
if not REFERENCE_LAYER_KEYWORDS:
    REFERENCE_LAYER_KEYWORDS = [
        str(v).strip().lower()
        for v in DEFAULT_ZIP_CONFIG.get("reference_layer_keywords", [])
        if isinstance(v, str) and str(v).strip()
    ]
if not REFERENCE_LAYER_KEYWORDS:
    REFERENCE_LAYER_KEYWORDS = ["frame", "crosssectionline"]

LITHO_LAYER_KEYWORD = str(
    ZIP_CONFIG.get("litho_layer_keyword", DEFAULT_ZIP_CONFIG.get(
        "litho_layer_keyword", "litho"))
).strip().lower() or "litho"
LABEL_FIELD_CANDIDATES = [
    str(v).strip() for v in ZIP_CONFIG.get("label_field_candidates", DEFAULT_ZIP_CONFIG.get("label_field_candidates", []))
    if isinstance(v, str) and str(v).strip()
]
if not LABEL_FIELD_CANDIDATES:
    LABEL_FIELD_CANDIDATES = [
        str(v).strip() for v in DEFAULT_ZIP_CONFIG.get("label_field_candidates", [])
        if isinstance(v, str) and str(v).strip()
    ]
if not LABEL_FIELD_CANDIDATES:
    LABEL_FIELD_CANDIDATES = ["LITHOIDX", "LITHONAME"]


class ZipProcessor:
    def __init__(self, extract_root=None, log_callback=None):
        self.log_callback = log_callback
        self.last_report = {}
        # Keep sources with the QGIS profile so saved projects survive temp cleanup.
        extract_root_name = str(
            ZIP_CONFIG.get("extract_root_name", DEFAULT_ZIP_CONFIG.get(
                "extract_root_name", "KIGAM_Extract"))
        ).strip() or "KIGAM_Extract"
        self.extract_root = extract_root or os.path.join(
            QgsApplication.qgisSettingsDirPath(), os.path.basename(extract_root_name))
        if not os.path.exists(self.extract_root):
            os.makedirs(self.extract_root)

    def _log(self, message, warning=False):
        QgsMessageLog.logMessage(message, 'KIGAM Plugin',
                                 Qgis.MessageLevel.Warning if warning else Qgis.MessageLevel.Info)
        if warning:
            self.last_report.setdefault('warnings', []).append(message)
        if self.log_callback:
            self.log_callback(message)

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
            except (LookupError, UnicodeEncodeError, UnicodeDecodeError, ValueError):
                converted = None

            if converted and converted != text:
                variants.add(converted)

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

        if not sym_path:
            return raw_map, normalized_map
        for png in sorted(Path(sym_path).rglob('*')):
            if not png.is_file() or png.suffix.lower() != '.png':
                continue

            symbol_name = png.stem
            png_path = str(png)
            raw_map[symbol_name] = png_path if symbol_name not in raw_map else None

            for key in self._value_candidates(symbol_name):
                if key not in normalized_map:
                    normalized_map[key] = png_path
                elif normalized_map[key] != png_path:
                    normalized_map[key] = None  # Do not silently choose an ambiguous image.

        return raw_map, normalized_map

    def _resolve_symbol_path(self, value, raw_sym_files, normalized_sym_files):
        if value is None:
            return None

        raw_value = unicodedata.normalize("NFC", str(value)).strip()
        if not raw_value:
            return None

        if raw_value in raw_sym_files:
            return raw_sym_files[raw_value]

        matches = {normalized_sym_files[candidate] for candidate in self._value_candidates(raw_value)
                   if normalized_sym_files.get(candidate)}
        return next(iter(matches)) if len(matches) == 1 else None

    @staticmethod
    def _image_properties(node):
        for prop in node.iter():
            if prop.tag == 'prop' and prop.get('k') == 'imageFile':
                yield prop, 'v'
            elif prop.tag == 'Option' and prop.get('name') == 'imageFile':
                yield prop, 'value'

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

            image_props = list(ZipProcessor._image_properties(symbol_node))
            if not image_props:
                continue
            image_prop, value_key = image_props[0]
            image_value = (image_prop.get(value_key) or "").replace("\\", "/")
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
        raw_value = unicodedata.normalize("NFC", str(
            value)).strip() if value is not None else ""

        image_stem = None
        if raw_value in qml_value_to_image:
            image_stem = qml_value_to_image[raw_value]
        else:
            for candidate in self._value_candidates(raw_value):
                if candidate in qml_normalized_map:
                    image_stem = qml_normalized_map[candidate]
                    break

        if image_stem:
            path_from_qml = self._resolve_symbol_path(
                image_stem, raw_sym_files, normalized_sym_files)
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

        priority_fields = list(SYMBOL_PRIORITY_FIELDS)
        all_fields = [f.name() for f in layer.fields()]

        field_names = {name.casefold(): name for name in all_fields}
        priority_fields = [field_names.get(name.casefold(), name) for name in priority_fields]
        if qml_field and qml_field in all_fields:
            priority_fields = [qml_field] + \
                [f for f in priority_fields if f != qml_field]

        sorted_fields = [f for f in priority_fields if f in all_fields] + \
            [f for f in all_fields if f not in priority_fields]

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

    def _load_layer_with_best_encoding(self, shp_path, layer_name, sym_path=None,
                                       qml_path=None, encoding_override=None):
        encoding, reason = detect_dbf_encoding(shp_path, encoding_override, CANDIDATE_ENCODINGS)
        # OGR does not accept |encoding=... as a QGIS data-source URI component.
        options = QgsVectorLayer.LayerOptions()
        options.loadDefaultStyle = False  # Apply only the validated/relinked sidecar below.
        layer = QgsVectorLayer(str(shp_path), layer_name, "ogr", options)
        if not layer.isValid():
            return None, encoding, None, 0, 0
        layer.setProviderEncoding(encoding)
        layer.setCustomProperty('kigam/encoding', encoding)
        layer.setCustomProperty('kigam/encoding_reason', reason)
        self._log(f'{layer_name}: {encoding} ({reason})')
        return layer, encoding, None, 0, 0

    def _build_relinked_qml(self, qml_path, raw_sym_files, normalized_sym_files):
        if not qml_path or not os.path.exists(qml_path):
            return None, 0, 0

        try:
            tree = ET.parse(qml_path)
            root = tree.getroot()
        except Exception as exc:
            self._log(f'QML parse failed: {qml_path}: {exc}', True)
            return None, 0, 0

        total_image_props = 0
        relinked_count = 0
        for prop, value_key in self._image_properties(root):
            total_image_props += 1
            image_value = (prop.get(value_key) or "").replace("\\", "/")
            image_name = os.path.basename(image_value)
            image_stem = os.path.splitext(image_name)[0].strip()
            if not image_stem:
                continue

            png_path = self._resolve_symbol_path(
                image_stem, raw_sym_files, normalized_sym_files)
            if not png_path:
                candidate = (Path(image_value) if ntpath.isabs(image_value) else Path(qml_path).parent / image_value).resolve()
                boundary = Path(self.last_report.get('extract_dir', Path(qml_path).parent)).resolve()
                if candidate.is_relative_to(boundary) and candidate.is_file():
                    png_path = str(candidate)
            if not png_path:
                # Never leave an obsolete absolute/remote path for QGIS to load.
                # Only this symbol layer will be replaced after style loading.
                prop.set(value_key, '')
                continue

            prop.set(value_key, png_path.replace("\\", "/"))
            relinked_count += 1

        if total_image_props == 0:
            return qml_path, 0, 0

        if relinked_count != total_image_props:
            self._log(f'QML images unresolved: {qml_path} ({relinked_count}/{total_image_props}); replacing missing images only', True)

        relinked_qml = os.path.join(
            os.path.dirname(qml_path),
            f"{os.path.splitext(os.path.basename(qml_path))[0]}_kigam_relinked.qml"
        )
        tree.write(relinked_qml, encoding=QML_WRITE_ENCODING,
                   xml_declaration=True)
        return relinked_qml, relinked_count, total_image_props

    def _repair_missing_images(self, layer):
        from qgis.PyQt.QtGui import QImageReader

        def repair(symbol):
            count = 0
            for index, symbol_layer in enumerate(symbol.symbolLayers()):
                child = symbol_layer.subSymbol()
                if child is not None:
                    count += repair(child)
                fallback = None
                if isinstance(symbol_layer, QgsRasterFillSymbolLayer):
                    if not QImageReader(symbol_layer.imageFilePath()).canRead():
                        fallback = QgsFillSymbol.createSimple({'color': '#cccccc', 'outline_color': '#666666'})
                elif isinstance(symbol_layer, QgsRasterMarkerSymbolLayer):
                    if not QImageReader(symbol_layer.path()).canRead():
                        fallback = QgsMarkerSymbol.createSimple({'color': '#cc6666', 'size': '3'})
                if fallback is not None:
                    symbol.changeSymbolLayer(index, fallback.symbolLayer(0).clone())
                    count += 1
            return count

        count = sum(repair(symbol) for symbol in layer.renderer().symbols(QgsRenderContext())) if layer.renderer() else 0
        if count:
            self._log(f'{layer.name()}: {count} missing/unreadable raster symbol(s) replaced; other QML styles preserved', True)
        return count

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

    @staticmethod
    def _local_sym_path(shp_path, extract_dir):
        current = Path(shp_path).parent
        boundary = Path(extract_dir)
        while True:
            matches = [p for p in current.iterdir() if p.is_dir() and p.name.casefold() == 'sym']
            if len(matches) == 1:
                return str(matches[0])
            if current == boundary:
                break
            current = current.parent
        # A single shared symbol directory is unambiguous; multiple map sheets are not.
        matches = [p for p in boundary.rglob('*') if p.is_dir() and p.name.casefold() == 'sym']
        return str(matches[0]) if len(matches) == 1 else None

    def process_zip(self, zip_path, font_family=None, font_size=10, encoding_override=None, pattern_scale=2.0):
        """Load every discovered SHP independently and expose all failures to the UI."""
        font_family = font_family or DEFAULT_FONT_FAMILY
        zip_basename = Path(zip_path).stem
        safe_prefix = re.sub(r"[^A-Za-z0-9._-]+", "_", zip_basename).strip("_") or "kigam_map"
        extract_dir = tempfile.mkdtemp(prefix=f"{safe_prefix}_", dir=self.extract_root)
        self.last_report = {'archive': str(zip_path), 'extract_dir': extract_dir,
                            'discovered': 0, 'loaded': 0, 'failed': [], 'warnings': []}
        try:
            archive_report = extract_archive(zip_path, extract_dir)
            for warning in archive_report['warnings']:
                self._log(warning, True)
        except Exception as exc:
            self._log(f'ZIP extraction failed: {exc}', True)
            owned_dir, parent = Path(extract_dir).resolve(), Path(self.extract_root).resolve()
            if owned_dir != parent and owned_dir.is_relative_to(parent):
                shutil.rmtree(owned_dir)
            return []

        paths = sorted(p for p in Path(extract_dir).rglob('*')
                       if p.is_file() and p.suffix.lower() == '.shp')
        self.last_report['discovered'] = len(paths)
        unsupported = [p.relative_to(extract_dir).as_posix() for p in Path(extract_dir).rglob('*')
                       if p.suffix.lower() in ('.gpkg', '.gdb', '.dxf', '.tif', '.tiff', '.img')]
        if unsupported:
            self._log('Unsupported ZIP datasets (SHP loader): ' + ', '.join(sorted(unsupported)[:20]), True)
        if not paths:
            self._log('No Shapefiles found. This loader supports SHP ZIP packages, including nested ZIPs.', True)
            return []
        tree_root = QgsProject.instance().layerTreeRoot()
        loaded_layers, target_group = [], None
        for shp in paths:
            try:
                if sidecar(shp, '.shx') is None:
                    raise ValueError('Missing SHX sidecar')
                sym_path = self._local_sym_path(shp, extract_dir)
                qml = sidecar(shp, '.qml')
                layer, *_ = self._load_layer_with_best_encoding(
                    str(shp), shp.stem, sym_path, str(qml) if qml else None, encoding_override)
                if layer is None or not layer.isValid():
                    raise ValueError('OGR could not open the Shapefile')
                if target_group is None:
                    target_group = tree_root.addGroup(self._build_unique_group_name(tree_root, zip_basename))
                QgsProject.instance().addMapLayer(layer, False)
                target_group.addLayer(layer)
                loaded_layers.append(layer)
            except Exception as exc:
                self.last_report['failed'].append(str(shp.relative_to(extract_dir)))
                self._log(f'{shp.name}: load failed: {exc}', True)
                continue
            # Style failures must never abort the remaining maps in a batch.
            try:
                self.apply_sym_styling(layer, sym_path, str(qml) if qml else None)
                pattern_report = scale_patterns(layer, pattern_scale)
                if pattern_report['skipped']:
                    self._log(f'{shp.name}: {pattern_report["skipped"]} pattern(s) need manual size/data-defined review', True)
                if LITHO_LAYER_KEYWORD in shp.stem.lower() and not layer.labelsEnabled():
                    self.apply_labeling(layer, font_family, font_size)
            except Exception as exc:
                self._log(f'{shp.name}: loaded, but styling failed: {exc}', True)
        if target_group is not None:
            self.organize_layers(target_group, loaded_layers)
        self.last_report['loaded'] = len(loaded_layers)
        self._log(f'{zip_basename}: {len(loaded_layers)}/{len(paths)} SHP loaded; '
                  f'{len(self.last_report["failed"])} failed')
        return loaded_layers

    @staticmethod
    def apply_pattern_scale(layer, multiplier):
        return scale_patterns(layer, multiplier)['changed']

    def apply_sym_styling(self, layer, sym_path, qml_path=None):
        """
        Analyzes the layer to find a field matching the symbols in sym_path,
        and applies a categorized renderer using the PNGs.
        """
        raw_sym_files, normalized_sym_files = self._build_symbol_index(sym_path)

        # Prefer native QML style when available, but relink image paths to extracted sym folder.
        relinked_qml, relinked_count, total_image_props = self._build_relinked_qml(
            qml_path,
            raw_sym_files,
            normalized_sym_files
        )
        if relinked_qml and self._load_named_style(layer, relinked_qml):
            renderer = layer.renderer()
            if isinstance(renderer, QgsCategorizedSymbolRenderer):
                fields = {field.name().casefold(): field.name() for field in layer.fields()}
                attribute = renderer.classAttribute()
                renderer.setClassAttribute(fields.get(attribute.casefold(), attribute))
            self._repair_missing_images(layer)
            layer.triggerRepaint()
            self._log(f'Applied QML: {layer.name()} ({relinked_count}/{total_image_props} image paths linked)')
            return
        if relinked_qml:
            self._log(f'QML could not be applied: {layer.name()}; trying sym renderer', True)

        if not raw_sym_files:
            return

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

        if not best_field or max_matches <= 0:
            all_fields = [f.name() for f in layer.fields()]
            self._log(f'{layer.name()}: PNG symbols did not match fields: {", ".join(all_fields)}', True)
            return

        QgsMessageLog.logMessage(
            f"Applying style to {layer.name()} using field '{best_field}' ({max_matches} matches)", "KIGAM Plugin", Qgis.MessageLevel.Success)

        # 2. Create Categories
        categories = []
        unique_values = layer.uniqueValues(layer.fields().indexOf(best_field))
        missing_values = []

        for val in sorted(unique_values, key=str):
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

                if layer.geometryType() == Qgis.GeometryType.Point:  # Point
                    # Create Raster Marker
                    symbol_layer = QgsRasterMarkerSymbolLayer(png_path)
                    # Configurable default size
                    symbol_layer.setSize(MARKER_SYMBOL_SIZE)
                    symbol = QgsMarkerSymbol()
                    symbol.changeSymbolLayer(0, symbol_layer)

                elif layer.geometryType() == Qgis.GeometryType.Polygon:  # Polygon
                    # Create Raster Fill
                    symbol_layer = QgsRasterFillSymbolLayer()
                    symbol_layer.setImageFilePath(png_path)
                    # Configurable pattern scale
                    symbol_layer.setWidth(FILL_SYMBOL_WIDTH)
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
                if layer.geometryType() == Qgis.GeometryType.Point:
                    symbol = QgsMarkerSymbol.createSimple({'color': '#ff0000'})
                elif layer.geometryType() == Qgis.GeometryType.Polygon:
                    symbol = QgsFillSymbol.createSimple(
                        {'color': '#cccccc', 'outline_color': 'black'})
                else:
                    continue  # Skip lines for now as raster data usually doesn't apply to lines

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
                self._log(f'{layer.name()}: {len(missing_values)} value(s) had no matching PNG in sym ({preview})', True)

    def apply_labeling(self, layer, font_family, font_size):
        from qgis.core import (
            QgsVectorLayerSimpleLabeling, QgsPalLayerSettings,
            QgsTextFormat
        )
        from qgis.PyQt.QtGui import QColor, QFont

        settings = QgsPalLayerSettings()

        fields = [f.name() for f in layer.fields()]
        if not fields:
            return

        label_field = None
        field_names = {name.casefold(): name for name in fields}
        for candidate in LABEL_FIELD_CANDIDATES:
            if candidate.casefold() in field_names:
                label_field = field_names[candidate.casefold()]
                break
        if label_field is None:
            return
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
        settings.placement = Qgis.LabelPlacement.Horizontal

        # Smart Placement Logic
        settings.centroidInside = True  # Force label inside
        settings.fitInPolygonOnly = True  # Don't draw if it doesn't fit
        settings.priority = 5  # Medium priority

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
        reference = []  # Frame/Crosssectionline-like layers configured by keyword

        for layer in layers:
            name = layer.name().lower()
            if any(keyword in name for keyword in REFERENCE_LAYER_KEYWORDS):
                reference.append(layer)
            elif layer.geometryType() == Qgis.GeometryType.Point:  # Point
                points.append(layer)
            elif layer.geometryType() == Qgis.GeometryType.Line:  # Line
                lines.append(layer)
            else:  # Polygon
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
