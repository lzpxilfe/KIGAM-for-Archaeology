"""Metric grids and explicit, reproducible codes for categorical geology rasters."""
import csv
import math
import os
from pathlib import Path
from typing import NamedTuple
from osgeo import gdal
from qgis.core import (
    Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject,
    QgsRectangle, QgsVectorLayer, QgsWkbTypes, QgsField, QgsFeature,
    QgsGeometry, QgsProviderRegistry, QgsVariantUtils,
)
from qgis.PyQt.QtCore import QMetaType


class Grid(NamedTuple):
    extent: QgsRectangle
    crs: QgsCoordinateReferenceSystem
    width: int
    height: int

    @property
    def resolution(self):
        return self.extent.width() / self.width

    def geotransform(self):
        return (self.extent.xMinimum(), self.resolution, 0.0,
                self.extent.yMaximum(), 0.0, -self.resolution)


MAX_PIXELS = 4_000_000


def check_size(width, height, max_pixels=MAX_PIXELS):
    if min(width, height) <= 0 or width * height > max_pixels:
        raise ValueError(f'요청 크기 {width:,} × {height:,}가 유효하지 않습니다. '
                         f'픽셀 한도는 {max_pixels:,}입니다.')


def metric_crs(crs):
    if not crs.isValid():
        raise ValueError('좌표계가 없는 레이어입니다. 올바른 CRS를 먼저 지정하세요.')
    if crs.mapUnits() == Qgis.DistanceUnit.Meters:
        return crs
    # KIGAM maps cover Korea. Always report the chosen output CRS in the UI.
    return QgsCoordinateReferenceSystem('EPSG:5186')


def metric_grid(extent, source_crs, resolution, max_pixels=MAX_PIXELS, *, allow_degenerate=False):
    target = metric_crs(source_crs)
    if source_crs != target:
        transform = QgsCoordinateTransform(source_crs, target, QgsProject.instance())
        extent = transform.transformBoundingBox(extent)
    if (not math.isfinite(resolution) or resolution <= 0 or not extent.isFinite()
            or min(extent.width(), extent.height()) < 0
            or (extent.isEmpty() and not allow_degenerate)):
        raise ValueError('범위 또는 해상도가 유효하지 않습니다.')
    width = max(1, math.ceil(extent.width() / resolution))
    height = max(1, math.ceil(extent.height() / resolution))
    check_size(width, height, max_pixels)
    left, top = extent.xMinimum(), extent.yMaximum()
    if not extent.width():
        left -= resolution / 2
    if not extent.height():
        top += resolution / 2
    aligned = QgsRectangle(left, top - height * resolution, left + width * resolution, top)
    return Grid(aligned, target, width, height)


def open_file_raster(layer):
    """Open the GDAL dataset behind a QGIS layer, keeping provider open options."""
    parts = QgsProviderRegistry.instance().decodeUri('gdal', layer.source())
    path = f"{parts.get('vsiPrefix', '')}{parts.get('path') or layer.source()}{parts.get('vsiSuffix', '')}"
    return gdal.OpenEx(path, gdal.OF_RASTER, open_options=parts.get('openOptions', []) or [])


def is_source_file(layer, destination):
    if layer.providerType() != 'gdal' or not Path(destination).is_file():
        return False
    parts = QgsProviderRegistry.instance().decodeUri('gdal', layer.source())
    path = parts.get('path') or layer.source()
    try:
        return os.path.samefile(path, destination)
    except OSError:
        return False


def reference_grid(layer):
    crs = layer.crs()
    if not crs.isValid() or crs.mapUnits() != Qgis.DistanceUnit.Meters:
        raise ValueError('기준 래스터의 CRS는 미터 단위여야 합니다.')
    if layer.providerType() != 'gdal':
        raise ValueError('기준 격자에는 파일 기반 래스터를 선택하세요.')
    ds = open_file_raster(layer)
    if ds is None:
        raise ValueError('기준 래스터를 열 수 없습니다.')
    gt = ds.GetGeoTransform(can_return_null=True)
    if (gt is None or not all(map(math.isfinite, gt)) or gt[2] or gt[4] or gt[1] <= 0
            or gt[5] >= 0 or not math.isclose(gt[1], -gt[5], rel_tol=1e-9)):
        raise ValueError('기준 래스터는 회전 없는 북향 정방 격자여야 합니다.')
    width, height = ds.RasterXSize, ds.RasterYSize
    check_size(width, height)
    extent = QgsRectangle(gt[0], gt[3] + height * gt[5], gt[0] + width * gt[1], gt[3])
    return Grid(extent, crs, width, height)


def categorical_layers(layers, resolve_field, target=None):
    """Use one codebook across map sheets, even when their field names differ."""
    target = target if target is not None else metric_crs(layers[0].crs())
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
            if geometry.transform(transform) != Qgis.GeometryOperationResult.Success:
                raise RuntimeError(f'{layer.name()}: 지오메트리 좌표 변환에 실패했습니다.')
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
        if copy.featureCount():
            copy.updateExtents()
            output.append(copy)
    if not output:
        raise ValueError('유효한 지질 코드와 지오메트리를 가진 피처가 없습니다.')
    return output, codes, target


def codebook_path(path):
    path = Path(path)
    return path.with_name(path.name + '.categories.csv')


def write_codebook(path, codes):
    target = codebook_path(path)
    with target.open('w', encoding='utf-8-sig', newline='') as fp:
        writer = csv.writer(fp)
        writer.writerow(('KIGAM_ID', 'VALUE'))
        writer.writerows((code, value) for value, code in codes.items())
    return str(target)
