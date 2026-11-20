# -*- coding: utf-8 -*-
"""
GeoChem utilities for KIGAM for Archaeology
Ported from ArchToolkit (lzpxilfe/ar) - geochem_polygonize_dialog.py

This module contains functions and data for converting WMS RGB raster
to numerical value rasters based on legend color mapping.
"""
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from osgeo import gdal
from qgis.core import (
    Qgis,
    QgsRasterLayer,
    QgsRectangle,
    QgsProject,
    QgsRasterPipe,
    QgsRasterFileWriter,
    QgsRasterProjector,
)
from .raster_output import check_grid, close_dataset
from .raster_utils import open_file_raster


@dataclass(frozen=True)
class LegendPoint:
    value: float
    rgb: Tuple[int, int, int]


@dataclass(frozen=True)
class GeoChemPreset:
    key: str
    label: str
    unit: str
    points: Sequence[LegendPoint]


# EXACT COPY from ArchToolkit (lzpxilfe/ar) geochem_polygonize_dialog.py lines 91-204
FE2O3_POINTS: List[LegendPoint] = [
    LegendPoint(0.0, (204, 204, 204)),
    LegendPoint(3.1, (0, 38, 115)),
    LegendPoint(3.5, (0, 112, 255)),
    LegendPoint(3.9, (0, 197, 255)),
    LegendPoint(4.5, (0, 255, 0)),
    LegendPoint(5.7, (85, 255, 0)),
    LegendPoint(7.1, (255, 255, 0)),
    LegendPoint(8.5, (255, 170, 0)),
    LegendPoint(9.4, (255, 85, 0)),
    LegendPoint(12.0, (230, 0, 0)),
    LegendPoint(51.0, (115, 12, 12)),
]

PB_POINTS: List[LegendPoint] = [
    # Legend from percentile ramp (ppm): 5=18, 10=20, 15=21, 25=24, 50=28, 75=32, 90=36, 95=41, 99=57, 100=1363
    LegendPoint(0.0, (204, 204, 204)),  # Absent data
    LegendPoint(18.0, (0, 38, 115)),  # 5%
    LegendPoint(20.0, (0, 112, 255)),  # 10%
    LegendPoint(21.0, (0, 197, 255)),  # 15%
    LegendPoint(24.0, (0, 255, 0)),  # 25%
    LegendPoint(28.0, (85, 255, 0)),  # 50%
    LegendPoint(32.0, (255, 255, 0)),  # 75%
    LegendPoint(36.0, (255, 170, 0)),  # 90%
    LegendPoint(41.0, (255, 85, 0)),  # 95%
    LegendPoint(57.0, (230, 0, 0)),  # 99%
    LegendPoint(1363.0, (115, 12, 12)),  # 100%
]

CU_POINTS: List[LegendPoint] = [
    # Legend from percentile ramp (ppm): 5=10, 10=12, 15=14, 25=17, 50=23, 75=33, 90=45, 95=58, 99=104, 100=2104
    LegendPoint(0.0, (204, 204, 204)),  # Absent data
    LegendPoint(10.0, (0, 38, 115)),  # 5%
    LegendPoint(12.0, (0, 112, 255)),  # 10%
    LegendPoint(14.0, (0, 197, 255)),  # 15%
    LegendPoint(17.0, (0, 255, 0)),  # 25%
    LegendPoint(23.0, (85, 255, 0)),  # 50%
    LegendPoint(33.0, (255, 255, 0)),  # 75%
    LegendPoint(45.0, (255, 170, 0)),  # 90%
    LegendPoint(58.0, (255, 85, 0)),  # 95%
    LegendPoint(104.0, (230, 0, 0)),  # 99%
    LegendPoint(2104.0, (115, 12, 12)),  # 100%
]

ZN_POINTS: List[LegendPoint] = [
    # Legend from percentile ramp (ppm): 5=45, 10=57, 15=66, 25=79, 50=107, 75=149, 90=212, 95=272, 99=542, 100=21100
    LegendPoint(0.0, (204, 204, 204)),  # Absent data
    LegendPoint(45.0, (0, 38, 115)),  # 5%
    LegendPoint(57.0, (0, 112, 255)),  # 10%
    LegendPoint(66.0, (0, 197, 255)),  # 15%
    LegendPoint(79.0, (0, 255, 0)),  # 25%
    LegendPoint(107.0, (85, 255, 0)),  # 50%
    LegendPoint(149.0, (255, 255, 0)),  # 75%
    LegendPoint(212.0, (255, 170, 0)),  # 90%
    LegendPoint(272.0, (255, 85, 0)),  # 95%
    LegendPoint(542.0, (230, 0, 0)),  # 99%
    LegendPoint(21100.0, (115, 12, 12)),  # 100%
]

SR_POINTS: List[LegendPoint] = [
    # Legend from percentile ramp (ppm): 5=57, 10=72, 15=83, 25=99, 50=135, 75=192, 90=275, 95=342, 99=496, 100=3645
    LegendPoint(0.0, (204, 204, 204)),  # Absent data
    LegendPoint(57.0, (0, 38, 115)),  # 5%
    LegendPoint(72.0, (0, 112, 255)),  # 10%
    LegendPoint(83.0, (0, 197, 255)),  # 15%
    LegendPoint(99.0, (0, 255, 0)),  # 25%
    LegendPoint(135.0, (85, 255, 0)),  # 50%
    LegendPoint(192.0, (255, 255, 0)),  # 75%
    LegendPoint(275.0, (255, 170, 0)),  # 90%
    LegendPoint(342.0, (255, 85, 0)),  # 95%
    LegendPoint(496.0, (230, 0, 0)),  # 99%
    LegendPoint(3645.0, (115, 12, 12)),  # 100%
]

BA_POINTS: List[LegendPoint] = [
    # Legend from percentile ramp (ppm): 5=734, 10=853, 15=935, 25=1050, 50=1268, 75=1507, 90=1752, 95=1920, 99=2362, 100=15840
    LegendPoint(0.0, (204, 204, 204)),  # Absent data
    LegendPoint(734.0, (0, 38, 115)),  # 5%
    LegendPoint(853.0, (0, 112, 255)),  # 10%
    LegendPoint(935.0, (0, 197, 255)),  # 15%
    LegendPoint(1050.0, (0, 255, 0)),  # 25%
    LegendPoint(1268.0, (85, 255, 0)),  # 50%
    LegendPoint(1507.0, (255, 255, 0)),  # 75%
    LegendPoint(1752.0, (255, 170, 0)),  # 90%
    LegendPoint(1920.0, (255, 85, 0)),  # 95%
    LegendPoint(2362.0, (230, 0, 0)),  # 99%
    LegendPoint(15840.0, (115, 12, 12)),  # 100%
]

CAO_POINTS: List[LegendPoint] = [
    # Legend from percentile ramp (%): 5=0.40, 10=0.50, 15=0.58, 25=0.73, 50=1.18, 75=1.90, 90=2.99, 95=4.05, 99=9.03, 100=53.07
    LegendPoint(0.0, (204, 204, 204)),  # Absent data
    LegendPoint(0.40, (0, 38, 115)),  # 5%
    LegendPoint(0.50, (0, 112, 255)),  # 10%
    LegendPoint(0.58, (0, 197, 255)),  # 15%
    LegendPoint(0.73, (0, 255, 0)),  # 25%
    LegendPoint(1.18, (85, 255, 0)),  # 50%
    LegendPoint(1.90, (255, 255, 0)),  # 75%
    LegendPoint(2.99, (255, 170, 0)),  # 90%
    LegendPoint(4.05, (255, 85, 0)),  # 95%
    LegendPoint(9.03, (230, 0, 0)),  # 99%
    LegendPoint(53.07, (115, 12, 12)),  # 100%
]

PRESETS: Dict[str, GeoChemPreset] = {
    "fe2o3": GeoChemPreset(key="fe2o3", label="Fe2O3 (산화철)", unit="%", points=FE2O3_POINTS),
    "pb": GeoChemPreset(key="pb", label="Pb (납)", unit="ppm", points=PB_POINTS),
    "cu": GeoChemPreset(key="cu", label="Cu (구리)", unit="ppm", points=CU_POINTS),
    "zn": GeoChemPreset(key="zn", label="Zn (아연)", unit="ppm", points=ZN_POINTS),
    "sr": GeoChemPreset(key="sr", label="Sr (스트론튬)", unit="ppm", points=SR_POINTS),
    "ba": GeoChemPreset(key="ba", label="Ba (바륨)", unit="ppm", points=BA_POINTS),
    "cao": GeoChemPreset(key="cao", label="CaO (칼슘)", unit="%", points=CAO_POINTS),
}


RGB_MATCH_TOLERANCE = 48.0
MIN_OPAQUE_ALPHA = 250
ABSENT_STOP = LegendPoint(0.0, (204, 204, 204))


def interp_rgb_to_value(
    *,
    r: np.ndarray,
    g: np.ndarray,
    b: np.ndarray,
    points: Sequence[LegendPoint],
    max_distance: Optional[float] = None,
) -> np.ndarray:
    """Vectorized mapping: RGB -> scalar value by projecting to the nearest legend polyline segment in RGB space.

    Adapted from ArchToolkit's geochem_legend.py.
    """
    if r.shape != g.shape or r.shape != b.shape:
        raise ValueError("RGB bands must have the same shape")
    if len(points) < 2:
        raise ValueError("Need at least 2 legend points")

    rr = r.astype(np.float32, copy=False)
    gg = g.astype(np.float32, copy=False)
    bb = b.astype(np.float32, copy=False)

    out = np.full(rr.shape, np.nan, dtype=np.float32)
    min_dist = np.full(rr.shape, np.float32(np.inf), dtype=np.float32)

    for start, end in zip(points, points[1:]):
        c1r, c1g, c1b = map(np.float32, start.rgb)
        if start == ABSENT_STOP:
            # The grey swatch is a discrete background color.
            dist_sq = (rr - c1r) ** 2 + (gg - c1g) ** 2 + (bb - c1b) ** 2
            mask = dist_sq < min_dist
            out[mask] = ABSENT_STOP.value
            min_dist[mask] = dist_sq[mask]
            continue
        vr, vg, vb = [np.float32(right - left) for left, right in zip(start.rgb, end.rgb)]
        v_len_sq = np.float32(vr * vr + vg * vg + vb * vb)
        if v_len_sq <= 0:
            continue

        t = ((rr - c1r) * vr + (gg - c1g) * vg + (bb - c1b) * vb) / v_len_sq
        np.clip(t, np.float32(0.0), np.float32(1.0), out=t)
        pr = c1r + t * vr
        pg = c1g + t * vg
        pb = c1b + t * vb
        dist_sq = (rr - pr) ** 2 + (gg - pg) ** 2 + (bb - pb) ** 2

        mask = dist_sq < min_dist
        if not np.any(mask):
            continue

        base = np.float32(start.value)
        delta = np.float32(end.value - start.value)
        out[mask] = base + t[mask].astype(np.float32, copy=False) * delta
        min_dist[mask] = dist_sq[mask].astype(np.float32, copy=False)

    if max_distance is not None:
        out[min_dist > max_distance ** 2] = np.nan
    return out


def mask_black_lines(r: np.ndarray, g: np.ndarray, b: np.ndarray) -> np.ndarray:
    maximum = np.maximum(np.maximum(r, g), b)
    minimum = np.minimum(np.minimum(r, g), b)
    return (maximum < 90) & (maximum - minimum < 30)


_NEIGHBORS = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1))


def _neighbor_slices(shape, dy, dx):
    height, width = shape
    center = (slice(max(0, -dy), height - max(0, dy)),
              slice(max(0, -dx), width - max(0, dx)))
    neighbor = (slice(max(0, dy), height - max(0, -dy)),
                slice(max(0, dx), width - max(0, -dx)))
    return center, neighbor


def mask_linework(r, g, b, available, matched, points):
    """Find dark line cores and their antialiased blends with adjacent colors."""
    core = available & mask_black_lines(r, g, b)
    region = core.copy()
    if not core.any():
        return region
    channels = (r, g, b)
    pairs = [_neighbor_slices(core.shape, dy, dx) for dy, dx in _NEIGHBORS]
    for _ in range(2):
        near_line = np.zeros_like(core)
        for center, neighbor in pairs:
            near_line[center] |= region[neighbor]
        ys, xs = np.nonzero(near_line & available & ~region)
        if not ys.size:
            break
        colors = np.column_stack([c[ys, xs] for c in channels]).astype(np.float32)
        protected = np.zeros(ys.size, dtype=bool)
        for point in points:
            protected |= np.sum((colors - np.asarray(point.rgb, dtype=np.float32)) ** 2, axis=1) <= 100
        blend = np.zeros_like(protected)
        height, width = core.shape
        for dy, dx in _NEIGHBORS:
            yy, xx = ys + dy, xs + dx
            inside = (yy >= 0) & (yy < height) & (xx >= 0) & (xx < width)
            yy, xx = yy.clip(0, height - 1), xx.clip(0, width - 1)
            donor = np.column_stack([c[yy, xx] for c in channels]).astype(np.float32)
            scale = (colors * donor).sum(axis=1) / np.maximum((donor ** 2).sum(axis=1), 1)
            error = ((colors - donor * scale[:, None]) ** 2).sum(axis=1)
            blend |= (inside & matched[yy, xx] & ~region[yy, xx]
                      & (scale >= 0.08) & (scale <= 0.92) & (error <= 16 ** 2))
        keep = blend & ~protected
        if not keep.any():
            break
        region[ys[keep], xs[keep]] = True
    return region


def fill_linework(values, line_mask, nodata, max_distance):
    """Copy neighboring values across linework without synthesizing averages."""
    result = values.copy()
    result[line_mask | ~np.isfinite(result)] = nodata
    todo = line_mask.copy()
    pairs = [_neighbor_slices(todo.shape, dy, dx) for dy, dx in _NEIGHBORS]
    for _ in range(max_distance):
        if not todo.any():
            break
        filled = np.zeros_like(todo)
        previous = result.copy()
        for center, neighbor in pairs:
            take = todo[center] & ~filled[center] & ~todo[neighbor]
            result[center][take] = previous[neighbor][take]
            filled[center] |= take
        if not filled.any():
            break
        todo &= ~filled
    return result


def convert_rgb(r, g, b, points, available, nodata, fill_distance=0):
    values = interp_rgb_to_value(r=r, g=g, b=b, points=points, max_distance=RGB_MATCH_TOLERANCE)
    background = ((r == 255) & (g == 255) & (b == 255))
    if points[0] == ABSENT_STOP:
        background |= values == ABSENT_STOP.value
    available = available & ~background
    matched = available & np.isfinite(values)
    linework = mask_linework(r, g, b, available, matched, points)
    values[~matched | linework] = nodata
    if fill_distance > 0:
        values = fill_linework(values, linework, nodata, fill_distance)
    return values, {
        'available_pixels': int(np.count_nonzero(available & ~linework)),
        'off_legend_pixels': int(np.count_nonzero(available & ~matched & ~linework)),
        'linework_pixels': int(np.count_nonzero(linework)),
        'filled_pixels': int(np.count_nonzero(linework & (values != nodata))),
        'valid_pixels': int(np.count_nonzero(values != nodata)),
    }


def _check_rgb_bands(dataset):
    rgb = (gdal.GCI_RedBand, gdal.GCI_GreenBand, gdal.GCI_BlueBand)
    if dataset is None or dataset.RasterCount < 3:
        raise ValueError('RGB 색상 밴드가 있는 래스터를 선택하세요.')
    for index, channel in enumerate(rgb, 1):
        band = dataset.GetRasterBand(index)
        if band.DataType != gdal.GDT_Byte or band.GetColorInterpretation() != channel:
            raise ValueError('첫 세 밴드가 8비트 빨강·초록·파랑으로 지정된 래스터가 필요합니다.')


def source_has_alpha(layer):
    provider = layer.dataProvider()
    if layer.providerType() == 'wms' and provider.dataType(1) in (
            Qgis.DataType.ARGB32, Qgis.DataType.ARGB32_Premultiplied):
        return True  # QGIS expands the rendered WMS image to RGBA.
    if layer.providerType() != 'gdal':
        raise ValueError('렌더링된 WMS 또는 파일 기반 RGB 래스터를 선택하세요.')
    dataset = open_file_raster(layer)
    _check_rgb_bands(dataset)
    if dataset.RasterCount > 4:
        raise ValueError('RGB 또는 RGBA로 내보낸 래스터를 선택하세요.')
    return (dataset.RasterCount == 4
            and dataset.GetRasterBand(4).GetColorInterpretation() == gdal.GCI_AlphaBand)


def read_rgb(path, grid, has_alpha):
    dataset = gdal.Open(str(path))
    band = None
    try:
        _check_rgb_bands(dataset)
        check_grid(dataset, grid)
        channels = []
        available = np.ones((grid.height, grid.width), dtype=bool)
        for index in range(1, 4):
            band = dataset.GetRasterBand(index)
            pixels = band.ReadAsArray()
            if pixels is None:
                raise RuntimeError('RGB 채널을 읽을 수 없습니다.')
            channels.append(pixels)
            flags = band.GetMaskFlags()
            # A new RGBA-looking GeoTIFF can infer alpha for an unrelated fourth band.
            if not flags & (gdal.GMF_ALL_VALID | gdal.GMF_ALPHA):
                coverage = band.GetMaskBand().ReadAsArray()
                if coverage is None:
                    raise RuntimeError('RGB 유효 범위를 읽을 수 없습니다.')
                available &= coverage != 0
        if has_alpha:
            band = dataset.GetRasterBand(4) if dataset.RasterCount >= 4 else None
            alpha = band.ReadAsArray() if band is not None else None
            if alpha is None or band.DataType != gdal.GDT_Byte:
                raise RuntimeError('RGB 변환 중 알파 밴드가 누락되었습니다.')
            available &= alpha >= MIN_OPAQUE_ALPHA
        return (*channels, available)
    finally:
        band = None
        close_dataset(dataset)


def export_geotiff(layer: QgsRasterLayer, path: str, extent: QgsRectangle, width: int, height: int,
                  target_crs=None) -> bool:
    """
    Export a raster layer (including WMS) to a GeoTIFF.
    Uses QgsRasterFileWriter, falls back to GDAL warp if needed.

    BASED ON ArchToolkit (lzpxilfe/ar) geochem_polygonize_dialog.py lines 1968-2030
    """
    import processing

    target_crs = target_crs or layer.crs()

    try:
        provider = layer.dataProvider()
        pipe = QgsRasterPipe()
        if not pipe.set(provider.clone()):
            raise RuntimeError("provider.clone() failed")
        ctx = QgsProject.instance().transformContext()
        if layer.crs() != target_crs:
            projector = QgsRasterProjector()
            projector.setCrs(layer.crs(), target_crs, ctx)
            if not pipe.set(projector):
                raise RuntimeError('Raster reprojection setup failed')
        writer = QgsRasterFileWriter(path)
        writer.setOutputFormat("GTiff")
        if hasattr(writer, 'setCreationOptions'):  # QGIS 3.44+ / 4.x
            writer.setCreationOptions(["COMPRESS=LZW", "TILED=YES"])
        else:
            writer.setCreateOptions(["COMPRESS=LZW", "TILED=YES"])
        res = writer.writeRaster(pipe, int(width), int(
            height), extent, target_crs, ctx)
        if res != 0:
            print(f"[GeoChem] writeRaster returned {res}")
            raise RuntimeError(f"writeRaster failed ({res})")
        if os.path.exists(path):
            return True
    except Exception as e:
        print(f"[GeoChem] QGIS export failed, trying GDAL warp... ({e})")

    # Fallback: GDAL warp through Processing (more provider-compatible)
    try:
        extent_str = f"{extent.xMinimum()},{extent.xMaximum()},{extent.yMinimum()},{extent.yMaximum()}"
        # Match the requested width/height via target resolution in layer CRS units.
        px = max(extent.width() / max(1, int(width)),
                 extent.height() / max(1, int(height)))
        px = float(px) if px > 0 else None
        processing.run(
            "gdal:warpreproject",
            {
                "INPUT": layer,
                "SOURCE_CRS": None,
                "TARGET_CRS": target_crs,
                "RESAMPLING": 0,  # Nearest (preserve legend colors)
                "NODATA": None,
                "TARGET_RESOLUTION": px,
                "OPTIONS": "COMPRESS=LZW|TILED=YES",
                "DATA_TYPE": 0,
                "TARGET_EXTENT": extent_str,
                "TARGET_EXTENT_CRS": target_crs,
                "MULTITHREADING": False,
                "EXTRA": "",
                "OUTPUT": path,
            },
        )
        if os.path.exists(path):
            return True
    except Exception as e2:
        print(f"[GeoChem] GDAL warp fallback also failed: {e2}")

    return False
