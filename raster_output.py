"""Validate raster files and publish them with their associated files."""
import math
import os
from pathlib import Path
import tempfile
from uuid import uuid4

import numpy as np
from osgeo import gdal, osr
from qgis.PyQt.QtCore import QLockFile

from .raster_utils import codebook_path


def check_grid(dataset, grid):
    if (dataset.RasterXSize, dataset.RasterYSize) != (grid.width, grid.height):
        raise RuntimeError('래스터의 행·열 수가 요청한 격자와 다릅니다.')
    gt = dataset.GetGeoTransform(can_return_null=True)
    expected = grid.geotransform()
    tolerance = max(1e-8, grid.resolution * 1e-7)
    if gt is None or any(not math.isclose(a, b, rel_tol=0, abs_tol=tolerance)
                         for a, b in zip(gt, expected)):
        raise RuntimeError('래스터의 원점, 셀 크기 또는 방향이 요청한 격자와 다릅니다.')
    crs = dataset.GetSpatialRef()
    if crs is None:
        raise RuntimeError('래스터의 CRS를 읽을 수 없습니다.')
    # QGIS and GDAL can spell the same EPSG CRS with different projected axes.
    if f'{crs.GetAuthorityName(None)}:{crs.GetAuthorityCode(None)}' == grid.crs.authid():
        return
    # AAIGrid writes ESRI WKT, which can represent the CRS without an EPSG ID.
    expected_crs = osr.SpatialReference(wkt=grid.crs.toWkt())
    crs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    expected_crs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    if not crs.IsSame(expected_crs):
        raise RuntimeError('래스터의 CRS가 요청한 격자와 다릅니다.')


def verify_raster(path, grid, nodata, data_type, *, class_ids=None, ascii_source=None):
    dataset = gdal.Open(str(path))
    if dataset is None:
        raise RuntimeError('출력 래스터를 다시 열 수 없습니다.')
    band = None
    try:
        check_grid(dataset, grid)
        if dataset.RasterCount != 1:
            raise RuntimeError('출력 래스터가 단일 밴드가 아닙니다.')
        band = dataset.GetRasterBand(1)
        actual_nodata = band.GetNoDataValue()
        type_mismatch = ascii_source is None and band.DataType != data_type
        if type_mismatch or actual_nodata != float(nodata):
            raise RuntimeError(f'출력 자료형 {gdal.GetDataTypeName(band.DataType)}, NoData {actual_nodata}. '
                               f'예상 자료형 {gdal.GetDataTypeName(data_type)}, NoData {nodata}.')
        values = band.ReadAsArray()
        if values is None or not np.isfinite(values).all():
            raise RuntimeError('출력 셀을 읽을 수 없거나 NoData로 표시되지 않은 비유한 값이 있습니다.')
        if not np.any(values != nodata):
            raise RuntimeError('출력 래스터에 유효한 셀이 없습니다. 입력 범위와 기준 격자를 확인하세요.')
        if ascii_source is not None:
            _check_ascii_values(values, ascii_source, data_type, nodata)
        if class_ids is not None:
            present = set(np.unique(values)) - {nodata}
            if not present.issubset(class_ids):
                raise RuntimeError('출력 래스터에 분류표에 없는 값이 있습니다.')
            return set(class_ids) - present
    finally:
        band = None
        close_dataset(dataset)


def _check_ascii_values(values, source_path, data_type, nodata):
    # ASCII Grid stores text. GDAL can read the same file as Float32 or Float64
    # depending on the reader configuration, so check the values themselves.
    source = gdal.Open(str(source_path))
    if source is None:
        raise RuntimeError('ASCII Grid와 대조할 원본 래스터를 열 수 없습니다.')
    band = None
    try:
        band = source.GetRasterBand(1)
        if band.DataType != data_type or band.GetNoDataValue() != float(nodata):
            raise RuntimeError('ASCII Grid 변환 전 래스터의 자료형 또는 NoData가 예상과 다릅니다.')
        expected = band.ReadAsArray()
        actual = values.astype(np.float32, copy=False) if data_type == gdal.GDT_Float32 else values
        if expected is None or not np.array_equal(actual, expected):
            raise RuntimeError('ASCII Grid의 셀 값이 변환 전 래스터와 다릅니다.')
    finally:
        band = None
        close_dataset(source)


def _check_gdal_result(result):
    if result not in (0, None):
        raise RuntimeError(gdal.GetLastErrorMsg() or f'GDAL error {result}')


def close_dataset(dataset):
    close = getattr(dataset, 'Close', None)  # Added in GDAL 3.8.
    if close is not None:
        _check_gdal_result(close())


def write_value_raster(path, values, grid, nodata, metadata, *, data_type=gdal.GDT_Float32, class_ids=None):
    gdal.ErrorReset()
    dataset = gdal.GetDriverByName('GTiff').Create(
        str(path), grid.width, grid.height, 1, data_type,
        ['TILED=YES', 'COMPRESS=LZW'])
    if dataset is None:
        raise RuntimeError('출력 GeoTIFF를 만들 수 없습니다.')
    band = None
    try:
        _check_gdal_result(dataset.SetGeoTransform(grid.geotransform()))
        _check_gdal_result(dataset.SetProjection(grid.crs.toWkt()))
        _check_gdal_result(dataset.SetMetadata(metadata))
        band = dataset.GetRasterBand(1)
        _check_gdal_result(band.SetNoDataValue(float(nodata)))
        _check_gdal_result(band.WriteArray(values))
        _check_gdal_result(band.FlushCache())
        _check_gdal_result(dataset.FlushCache())
    finally:
        band = None
        close_dataset(dataset)
        dataset = None
    if gdal.GetLastErrorType() >= gdal.CE_Failure:
        raise RuntimeError(gdal.GetLastErrorMsg() or 'GeoTIFF 쓰기에 실패했습니다.')
    verify_raster(path, grid, nodata, data_type, class_ids=class_ids)


def staging_directory(destination):
    """Stage on the same volume and preserve GDAL's filename-based sidecars."""
    return tempfile.TemporaryDirectory(prefix='.kigam-', dir=Path(destination).parent)


def _replace_files(pairs):
    """Restore the previous files if publishing an associated file fails."""
    backups, published = {}, []
    try:
        for source, target in pairs:
            if target.exists():
                backup = target.with_name(f'.kigam-{uuid4().hex}.backup')
                os.replace(target, backup)
                backups[target] = backup
        for source, target in pairs:
            if source is not None:
                os.replace(source, target)
                published.append(target)
    except OSError as original:
        failures = []
        for target in reversed(published):
            if target not in backups:
                try:
                    target.unlink()
                except OSError:
                    failures.append(str(target))
        for target, backup in reversed(list(backups.items())):
            try:
                os.replace(backup, target)
            except OSError:
                failures.append(str(backup))
        if failures:
            raise RuntimeError(f'출력 복구에 실패했습니다. 확인할 파일: {", ".join(failures)}') from original
        raise
    for backup in backups.values():
        try:
            backup.unlink()
        except OSError:
            pass  # The complete new result is already in place.


def publish_raster(staged, destination, *, categories=False):
    staged, destination = Path(staged), Path(destination)
    if not staged.is_file() or (categories and not codebook_path(staged).is_file()):
        raise RuntimeError('내보낼 래스터 또는 분류표가 없습니다.')
    if destination.suffix.lower() == '.asc' and not staged.with_suffix('.prj').is_file():
        raise RuntimeError('ASCII Grid의 CRS 파일(.prj)이 생성되지 않았습니다.')
    pairs = [(codebook_path(staged) if categories else None, codebook_path(destination))]
    for suffix in ('.aux.xml', '.msk', '.ovr'):
        source = staged.with_name(staged.name + suffix)
        pairs.append((source if source.is_file() else None,
                      destination.with_name(destination.name + suffix)))
    if destination.suffix.lower() == '.asc':
        pairs.append((staged.with_suffix('.prj'), destination.with_suffix('.prj')))
    pairs.append((staged, destination))
    lock = QLockFile(str(destination) + '.kigam.lock')
    if not lock.tryLock(0):
        raise RuntimeError('다른 내보내기 작업이 이 출력 경로를 사용 중입니다.')
    try:
        if any(target.exists() and not target.is_file() for _, target in pairs):
            raise RuntimeError('출력 파일 경로에 디렉터리가 이미 있습니다.')
        _replace_files(pairs)
    finally:
        lock.unlock()
