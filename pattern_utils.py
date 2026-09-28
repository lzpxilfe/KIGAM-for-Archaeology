"""Reversible raster-fill scaling, including styles with intrinsic image sizing."""
import json
import math
from qgis.core import Qgis, QgsRasterFillSymbolLayer, QgsRenderContext
from qgis.PyQt.QtGui import QImageReader

STATE_KEY = 'kigam/pattern_baselines'


def symbol_layers(symbol, prefix=''):
    """Include subsymbols used by geometry generators and nested styles."""
    for index, symbol_layer in enumerate(symbol.symbolLayers()):
        key = f'{prefix}/{index}'
        yield key, symbol_layer
        child = symbol_layer.subSymbol()
        if child is not None:
            yield from symbol_layers(child, key)


def dimensions(symbol_layer):
    return [symbol_layer.width(), symbol_layer.height(), symbol_layer.sizeUnit().name]


def same_dimensions(left, right):
    return (len(left) == len(right) == 3 and left[2] == right[2]
            and math.isclose(float(left[0]), float(right[0]))
            and math.isclose(float(left[1]), float(right[1])))


def valid_dimensions(value):
    try:
        return (isinstance(value, list) and len(value) == 3
                and all(math.isfinite(float(v)) and float(v) >= 0 for v in value[:2])
                and isinstance(value[2], str) and hasattr(Qgis.RenderUnit, value[2]))
    except (TypeError, ValueError):
        return False


def scale_patterns(layer, multiplier):
    """Use original sizes, rebase manually edited styles, and report skipped items."""
    multiplier = float(multiplier)
    if not math.isfinite(multiplier) or not 0.5 <= multiplier <= 6:
        raise ValueError('Pattern multiplier must be between 0.5 and 6')
    report = {'changed': 0, 'skipped': 0}
    if layer.type() != Qgis.LayerType.Vector or layer.geometryType() != Qgis.GeometryType.Polygon or not layer.renderer():
        return report
    try:
        previous_state = json.loads(str(layer.customProperty(STATE_KEY, '{}')))
        if not isinstance(previous_state, dict):
            previous_state = {}
    except (ValueError, TypeError):
        previous_state = {}
    # Migrate layers saved by the first 0.1.4 candidate.
    try:
        legacy_scale = float(layer.customProperty('kigam/pattern_scale', 1)) if not previous_state else 1
        if not math.isfinite(legacy_scale) or legacy_scale <= 0:
            legacy_scale = 1
    except (ValueError, TypeError):
        legacy_scale = 1
    state = {}
    for index, symbol in enumerate(layer.renderer().symbols(QgsRenderContext())):
        for key, symbol_layer in symbol_layers(symbol, str(index)):
            if not isinstance(symbol_layer, QgsRasterFillSymbolLayer):
                continue
            if symbol_layer.dataDefinedProperties().hasActiveProperties():
                report['skipped'] += 1
                if key in previous_state:
                    state[key] = previous_state[key]
                continue
            image_path = symbol_layer.imageFilePath()
            current = dimensions(symbol_layer)
            prior = previous_state.get(key, {})
            if not isinstance(prior, dict):
                prior = {}
            try:
                unchanged = (prior.get('image') == image_path and valid_dimensions(prior.get('base'))
                             and same_dimensions(current, prior.get('expected', [])))
            except (TypeError, ValueError):
                unchanged = False
            base = prior['base'] if unchanged else [current[0] / legacy_scale, current[1] / legacy_scale, current[2]]
            width, height, unit_name = base
            if width == height == 0 and multiplier != 1:
                size = QImageReader(image_path).size()
                if not size.isValid():
                    report['skipped'] += 1
                    continue
                width, unit_name = size.width(), 'Pixels'
            symbol_layer.setSizeUnit(getattr(Qgis.RenderUnit, unit_name))
            symbol_layer.setWidth(width * multiplier)
            symbol_layer.setHeight(height * multiplier)
            state[key] = {'image': image_path, 'base': base, 'expected': dimensions(symbol_layer)}
            report['changed'] += 1
    if report['changed']:
        layer.setCustomProperty(STATE_KEY, json.dumps(state, ensure_ascii=False))
        layer.setCustomProperty('kigam/pattern_scale', multiplier)
        layer.triggerRepaint()
    return report
