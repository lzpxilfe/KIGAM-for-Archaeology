"""Metric grids and explicit, reproducible codes for categorical geology rasters."""
import csv
import math
from pathlib import Path
from qgis.core import (
    Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject,
    QgsRectangle, QgsVectorLayer, QgsWkbTypes, QgsField, QgsFeature,
    QgsGeometry, QgsVariantUtils,
)
from qgis.PyQt.QtCore import QMetaType


def metric_crs(crs):
    if not crs.isValid():
        raise ValueError('좌표계가 없는 레이어입니다. 올바른 CRS를 먼저 지정하세요.')
    if crs.mapUnits() == Qgis.DistanceUnit.Meters:
        return crs
    # KIGAM maps cover Korea. Always report the chosen output CRS in the UI.
    return QgsCoordinateReferenceSystem('EPSG:5186')


def metric_grid(extent, source_crs, resolution, max_pixels=4_000_000):
    target = metric_crs(source_crs)
    if source_crs != target:
        transform = QgsCoordinateTransform(source_crs, target, QgsProject.instance())
        extent = transform.transformBoundingBox(extent)
    if resolution <= 0 or extent.isEmpty() or not extent.isFinite():
        raise ValueError('범위 또는 해상도가 유효하지 않습니다.')
    width = max(1, math.ceil(extent.width() / resolution))
    height = max(1, math.ceil(extent.height() / resolution))
    if width * height > max_pixels:
        raise ValueError(f'요청 크기 {width:,} × {height:,}가 {max_pixels:,} 픽셀 한도를 초과합니다. 범위를 줄이거나 해상도를 높이세요.')
    aligned = QgsRectangle(extent.xMinimum(), extent.yMaximum() - height * resolution,
                           extent.xMinimum() + width * resolution, extent.yMaximum())
    return aligned, target, width, height


def categorical_layers(layers, resolve_field):
    """Use one codebook across map sheets, even when their field names differ."""
    target = metric_crs(layers[0].crs())
    fields, values = [], set()
    for layer in layers:
        field = resolve_field(layer)
        if not field:
            raise ValueError(f'{layer.name()}: 지질 분류 필드를 찾을 수 없습니다.')
        fields.append(field)
        for value in layer.uniqueValues(layer.fields().indexOf(field)):
            if not QgsVariantUtils.isNull(value) and str(value).strip():
                values.add(str(value).strip())
    codes = {value: index for index, value in enumerate(sorted(values), 1)}
    if not codes:
        raise ValueError('내보낼 지질 코드가 없습니다.')
    output = []
    for layer, field in zip(layers, fields):
        if not layer.crs().isValid():
            raise ValueError(f'{layer.name()}: CRS가 없습니다.')
        copy = QgsVectorLayer(QgsWkbTypes.displayString(layer.wkbType()), layer.name(), 'memory')
        copy.setCrs(target)
        provider = copy.dataProvider()
        provider.addAttributes([QgsField('KIGAM_ID', QMetaType.Type.Int)])
        copy.updateFields()
        transform = QgsCoordinateTransform(layer.crs(), target, QgsProject.instance())
        batch = []
        for feature in layer.getFeatures():
            value = feature[field]
            if QgsVariantUtils.isNull(value) or not str(value).strip() or not feature.hasGeometry():
                continue
            geometry = QgsGeometry(feature.geometry())
            geometry.transform(transform)
            converted = QgsFeature(copy.fields())
            converted.setGeometry(geometry)
            converted.setAttributes([codes[str(value).strip()]])
            batch.append(converted)
            if len(batch) >= 1000:
                if not provider.addFeatures(batch)[0]:
                    raise RuntimeError('Failed to prepare categorical features')
                batch = []
        if batch and not provider.addFeatures(batch)[0]:
            raise RuntimeError('Failed to prepare categorical features')
        copy.updateExtents()
        output.append(copy)
    return output, codes, target


def write_codebook(path, codes):
    target = Path(path).with_suffix('.categories.csv')
    with target.open('w', encoding='utf-8-sig', newline='') as fp:
        writer = csv.writer(fp)
        writer.writerow(('KIGAM_ID', 'VALUE'))
        writer.writerows((code, value) for value, code in codes.items())
    return str(target)
