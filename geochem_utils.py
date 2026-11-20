"""Classify KIGAM GeoChem WMS pixels using the observed official map palette."""
import csv
import math
import os
from pathlib import Path
from dataclasses import dataclass
from typing import NamedTuple
from urllib.parse import parse_qs, urlsplit

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
from .raster_utils import codebook_path, open_file_raster


WMS_URL = 'https://data.kigam.re.kr/mgeo/geoserver/Geochemical_map/wms'
CLASS_KIND = 'kigam_wms_legend_class'
PALETTE_DATE = '2026-11-20'
MIN_OPAQUE_ALPHA = 250
PERCENTILES = (5, 10, 15, 25, 50, 75, 90, 95, 99, 100)

# Exact colors observed in the official WMS GetMap PNGs on 2026-11-20.
# The published legend illustrations have small RGB differences from the WMS.
WMS_COLORS = (
    0x000064, 0x0000FF, 0x0099FF, 0x00CCFF, 0x00FF00,
    0xFFFF00, 0xF3A85B, 0xE87400, 0xFF0000, 0x850000,
)
ZN_WMS_COLORS = (0x000067, *WMS_COLORS[1:6], 0xF3A85D, *WMS_COLORS[7:])


def rgb_channels(color):
    return color >> 16, (color >> 8) & 255, color & 255


@dataclass(frozen=True)
class GeoChemPreset:
    key: str
    label: str
    unit: str
    upper: tuple
    colors: tuple = WMS_COLORS
    absent_color: int = 0xC0C0C0

    @property
    def wms_id(self):
        return f'L_geochemMP_{self.key.upper()}'

    @property
    def class_ids(self):
        return range(1, len(self.upper) + 1)

    def class_label(self, class_id):
        lower = f'{self.upper[class_id - 2]:g}' if class_id > 1 else '하한 미표기'
        return f'{class_id}등급 · {lower}–{self.upper[class_id - 1]:g} {self.unit}'

    def metadata(self):
        return {
            'KIGAM_VALUE_KIND': CLASS_KIND,
            'KIGAM_PRESET': self.key,
            'KIGAM_WMS_LAYER': self.wms_id,
            'KIGAM_PALETTE_DATE': PALETTE_DATE,
            'KIGAM_INTERVAL_UNIT': self.unit,
            'KIGAM_CLASS_MATCH': 'exact_rgb',
        }


PRESETS = {preset.key: preset for preset in (
    GeoChemPreset('fe2o3', 'Fe₂O₃ (철)', '%', (3.1, 3.5, 3.9, 4.5, 5.7, 7.1, 8.5, 9.4, 12, 51)),
    GeoChemPreset('pb', 'Pb (납)', 'ppm', (18, 20, 21, 24, 28, 32, 36, 41, 57, 1363)),
    GeoChemPreset('cu', 'Cu (구리)', 'ppm', (10, 12, 14, 17, 23, 33, 45, 58, 104, 2104)),
    GeoChemPreset('zn', 'Zn (아연)', 'ppm', (45, 57, 66, 79, 107, 149, 212, 272, 542, 21100),
                  ZN_WMS_COLORS, 0xC0C0C6),
    GeoChemPreset('sr', 'Sr (스트론튬)', 'ppm', (57, 72, 83, 99, 135, 192, 275, 342, 496, 3645)),
    GeoChemPreset('ba', 'Ba (바륨)', 'ppm', (734, 853, 935, 1050, 1268, 1507, 1752, 1920, 2362, 15840)),
    GeoChemPreset('cao', 'CaO (칼슘)', '%', (0.40, 0.50, 0.58, 0.73, 1.18, 1.90, 2.99, 4.05, 9.03, 53.07)),
)}
_WMS_PRESETS = {preset.wms_id.casefold(): preset for preset in PRESETS.values()}


def _wms_layers(parameters):
    return [layer.rsplit(':', 1)[-1].casefold()
            for endpoint in parameters.get('layers', []) for layer in endpoint.split(',')]


def wms_preset(uri):
    layers = _wms_layers(parse_qs(uri, keep_blank_values=True))
    return _WMS_PRESETS.get(layers[0]) if len(layers) == 1 else None


def validate_wms_preset(uri, preset):
    parameters = parse_qs(uri, keep_blank_values=True)
    source = urlsplit(parameters.get('url', [''])[0])
    official = (source.hostname == 'data.kigam.re.kr'
                and '/geoserver/geochemical_map/' in source.path.casefold())
    layers = _wms_layers(parameters)
    known = [name for name in layers if name in _WMS_PRESETS]
    if not official and not known:
        return
    if len(layers) != 1 or len(known) != 1:
        raise ValueError('KIGAM 다목적 지구화학도에서 지원 원소 레이어 하나만 추가하세요.')
    if known[0] != preset.wms_id.casefold():
        actual = _WMS_PRESETS[known[0]]
        raise ValueError(f'선택한 WMS는 {actual.label}입니다. 원소 프리셋을 맞춰 주세요.')
    styles = parameters.get('styles', [''])
    if len(styles) != 1 or styles[0].rsplit(':', 1)[-1].casefold() not in ('', 'raster'):
        raise ValueError('KIGAM WMS의 기본 raster 스타일을 사용하세요.')
    if parameters.get('format', [''])[0].casefold() != 'image/png':
        raise ValueError('등급 색상을 보존하려면 WMS 이미지 형식으로 PNG를 선택하세요.')


def write_class_codebook(path, preset):
    target = codebook_path(path)
    with target.open('w', encoding='utf-8-sig', newline='') as fp:
        writer = csv.writer(fp)
        writer.writerow(('KIGAM_ID', 'PERCENTILE_FROM', 'PERCENTILE_TO', 'LOWER', 'UPPER', 'UNIT', 'WMS_HEX'))
        for i, (upper, color) in enumerate(zip(preset.upper, preset.colors)):
            writer.writerow((i + 1, PERCENTILES[i - 1] if i else '', PERCENTILES[i],
                             preset.upper[i - 1] if i else '', upper, preset.unit, f'#{color:06X}'))
    return target


def read_class_preset(layer):
    """Identify class GeoTIFFs and ASCs reopened from disk."""
    if (layer.providerType() != 'gdal' or layer.bandCount() != 1
            or not Path(layer.source()).is_file()):
        return None
    dataset = open_file_raster(layer)
    if dataset is None:
        return None
    try:
        if dataset.GetMetadataItem('KIGAM_VALUE_KIND') != CLASS_KIND:
            return None
        preset = PRESETS.get(dataset.GetMetadataItem('KIGAM_PRESET'))
        if preset is None or dataset.GetMetadataItem('KIGAM_PALETTE_DATE') != PALETTE_DATE:
            raise ValueError('이 지구화학 등급 래스터의 원소 또는 범례 버전을 확인할 수 없습니다.')
        return preset
    finally:
        close_dataset(dataset)


class RGBInput(NamedTuple):
    r: np.ndarray
    g: np.ndarray
    b: np.ndarray
    coverage: np.ndarray
    opaque: np.ndarray


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


def mask_linework(r, g, b, available, matched):
    """Find dark line cores and their antialiased blends with adjacent colors."""
    core = available & ~matched & mask_black_lines(r, g, b)
    region = core.copy()
    if not core.any():
        return region
    channels = (r, g, b)
    pairs = [_neighbor_slices(core.shape, dy, dx) for dy, dx in _NEIGHBORS]
    for _ in range(2):
        near_line = np.zeros_like(core)
        for center, neighbor in pairs:
            near_line[center] |= region[neighbor]
        ys, xs = np.nonzero(near_line & available & ~region & ~matched)
        if not ys.size:
            break
        colors = np.column_stack([c[ys, xs] for c in channels]).astype(np.float32)
        blend = np.zeros(ys.size, dtype=bool)
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
        if not blend.any():
            break
        region[ys[blend], xs[blend]] = True
    return region


def _line_depth(line_mask, valid, dy, dx, limit):
    """Measure distance through linework to the first original class in one direction."""
    depth = np.zeros(line_mask.shape, dtype=np.int32)
    center, neighbor = _neighbor_slices(line_mask.shape, dy, dx)
    rows, cols = np.nonzero(line_mask[center] & valid[neighbor])
    rows += center[0].start
    cols += center[1].start
    height, width = line_mask.shape
    for step in range(1, limit + 1):
        if not rows.size:
            break
        depth[rows, cols] = step
        rows, cols = rows - dy, cols - dx
        inside = (rows >= 0) & (rows < height) & (cols >= 0) & (cols < width)
        rows, cols = rows[inside], cols[inside]
        continuing = line_mask[rows, cols]
        rows, cols = rows[continuing], cols[continuing]
    return depth


def fill_linework(values, line_mask, nodata, max_distance):
    """Bridge bounded gaps from original classes on opposite sides of linework."""
    result = values.copy()
    result[line_mask | ~np.isfinite(result)] = nodata
    valid = result != nodata
    if max_distance <= 0 or not line_mask.any() or not valid.any():
        return result

    best_width = np.full(result.shape, np.inf, dtype=np.float32)
    best_agreement = np.zeros(result.shape, dtype=bool)
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        forward = _line_depth(line_mask, valid, dy, dx, max_distance)
        backward = _line_depth(line_mask, valid, -dy, -dx, max_distance)
        rows, cols = np.nonzero((forward > 0) & (backward > 0))
        after, before = forward[rows, cols], backward[rows, cols]
        widths = ((after + before - 1) * math.hypot(dy, dx)).astype(np.float32)
        eligible = widths <= max_distance
        rows, cols = rows[eligible], cols[eligible]
        after, before, widths = after[eligible], before[eligible], widths[eligible]
        first = values[rows - before * dy, cols - before * dx]
        second = values[rows + after * dy, cols + after * dx]
        agreement = first == second
        current = best_width[rows, cols]
        take = (widths < current) | ((widths == current) & agreement & ~best_agreement[rows, cols])
        rows, cols = rows[take], cols[take]
        best_width[rows, cols] = widths[take]
        best_agreement[rows, cols] = agreement[take]
        result[rows, cols] = np.where(before[take] <= after[take], first[take], second[take])
    return result


def classify_rgb(rgb, preset, nodata, fill_distance=0):
    """Keep only observed class RGBs and report disjoint NoData reasons."""
    r, g, b, coverage, opaque = rgb
    packed = (r.astype(np.uint32) << 16) | (g.astype(np.uint32) << 8) | b
    visible = coverage & opaque
    absent = visible & (packed == preset.absent_color)
    white = visible & (packed == 0xFFFFFF)
    eligible = visible & ~absent & ~white
    classes = np.full(packed.shape, nodata, dtype=np.int32)
    for class_id, color in enumerate(preset.colors, 1):
        classes[eligible & (packed == color)] = class_id
    matched = classes != nodata
    linework = mask_linework(r, g, b, eligible, matched)
    if fill_distance > 0:
        classes = fill_linework(classes, linework, nodata, fill_distance)
    return classes, {
        'source_masked_pixels': int(np.count_nonzero(~coverage)),
        'alpha_masked_pixels': int(np.count_nonzero(coverage & ~opaque)),
        'absent_pixels': int(np.count_nonzero(absent)),
        'white_pixels': int(np.count_nonzero(white)),
        'available_pixels': int(np.count_nonzero(eligible & ~linework)),
        'off_legend_pixels': int(np.count_nonzero(eligible & ~matched & ~linework)),
        'linework_pixels': int(np.count_nonzero(linework)),
        'filled_pixels': int(np.count_nonzero(linework & (classes != nodata))),
        'valid_pixels': int(np.count_nonzero(classes != nodata)),
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
        opaque = np.ones_like(available)
        if has_alpha:
            band = dataset.GetRasterBand(4) if dataset.RasterCount >= 4 else None
            alpha = band.ReadAsArray() if band is not None else None
            if alpha is None or band.DataType != gdal.GDT_Byte:
                raise RuntimeError('RGB 변환 중 알파 밴드가 누락되었습니다.')
            opaque = alpha >= MIN_OPAQUE_ALPHA
        return RGBInput(*channels, available, opaque)
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
