# -*- coding: utf-8 -*-
import os
import math
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from osgeo import gdal, ogr
from qgis.core import (
    QgsRasterLayer,
    QgsRectangle,
    QgsCoordinateTransform,
    QgsProject,
    QgsGeometry
)

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

# Ported presets from ArchToolkit
FE2O3_POINTS = [
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

PB_POINTS = [
    LegendPoint(0.0, (204, 204, 204)),
    LegendPoint(18.0, (0, 38, 115)),
    LegendPoint(20.0, (0, 112, 255)),
    LegendPoint(21.0, (0, 197, 255)),
    LegendPoint(24.0, (0, 255, 0)),
    LegendPoint(28.0, (85, 255, 0)),
    LegendPoint(32.0, (255, 255, 0)),
    LegendPoint(36.0, (255, 170, 0)),
    LegendPoint(41.0, (255, 85, 0)),
    LegendPoint(57.0, (230, 0, 0)),
    LegendPoint(1363.0, (115, 12, 12)),
]

CU_POINTS = [
    LegendPoint(0.0, (204, 204, 204)),
    LegendPoint(10.0, (0, 38, 115)),
    LegendPoint(12.0, (0, 112, 255)),
    LegendPoint(14.0, (0, 197, 255)),
    LegendPoint(17.0, (0, 255, 0)),
    LegendPoint(23.0, (85, 255, 0)),
    LegendPoint(33.0, (255, 255, 0)),
    LegendPoint(45.0, (255, 170, 0)),
    LegendPoint(58.0, (255, 85, 0)),
    LegendPoint(104.0, (230, 0, 0)),
    LegendPoint(2104.0, (115, 12, 12)),
]

PRESETS: Dict[str, GeoChemPreset] = {
    "fe2o3": GeoChemPreset(key="fe2o3", label="Fe2O3 (산화철)", unit="%", points=FE2O3_POINTS),
    "pb": GeoChemPreset(key="pb", label="Pb (납)", unit="ppm", points=PB_POINTS),
    "cu": GeoChemPreset(key="cu", label="Cu (구리)", unit="ppm", points=CU_POINTS),
}

def interp_rgb_to_value(
    r: np.ndarray,
    g: np.ndarray,
    b: np.ndarray,
    points: Sequence[LegendPoint],
    snap_last_t: Optional[float] = None,
) -> np.ndarray:
    """Vectorized mapping: RGB -> scalar value by projecting to the nearest legend segments."""
    rr = r.astype(np.float32, copy=False)
    gg = g.astype(np.float32, copy=False)
    bb = b.astype(np.float32, copy=False)

    out = np.full(rr.shape, np.nan, dtype=np.float32)
    min_dist = np.full(rr.shape, np.float32(np.inf), dtype=np.float32)

    pts = list(points)
    last_seg_idx = len(pts) - 2

    for i in range(len(pts) - 1):
        v1, v2 = float(pts[i].value), float(pts[i + 1].value)
        c1, c2 = pts[i].rgb, pts[i + 1].rgb

        c1r, c1g, c1b = np.float32(c1[0]), np.float32(c1[1]), np.float32(c1[2])
        vr, vg, vb = np.float32(c2[0] - c1[0]), np.float32(c2[1] - c1[1]), np.float32(c2[2] - c1[2])
        v_len_sq = vr * vr + vg * vg + vb * vb
        if v_len_sq <= 0: continue

        t = ((rr - c1r) * vr + (gg - c1g) * vg + (bb - c1b) * vb) / v_len_sq
        np.clip(t, 0.0, 1.0, out=t)
        
        if snap_last_t is not None and i == last_seg_idx:
            t[t > np.float32(snap_last_t)] = 1.0

        pr, pg, pb = c1r + t * vr, c1g + t * vg, c1b + t * vb
        dist_sq = (rr - pr) ** 2 + (gg - pg) ** 2 + (bb - pb) ** 2

        mask = dist_sq < min_dist
        if not np.any(mask): continue

        out[mask] = np.float32(v1) + t[mask] * np.float32(v2 - v1)
        min_dist[mask] = dist_sq[mask]

    return out

def mask_black_lines(r: np.ndarray, g: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Detect neutral dark 'linework' mask."""
    rr, gg, bb = r.astype(np.int16), g.astype(np.int16), b.astype(np.int16)
    return (rr < 75) & (gg < 75) & (bb < 75) & (np.abs(rr - gg) < 15) & (np.abs(gg - bb) < 15)

def gdal_fill_nodata(arr: np.ndarray, nodata: float, max_dist_px: int) -> np.ndarray:
    """Fill nodata using GDAL FillNodata."""
    a = arr.astype(np.float32, copy=True)
    a[~np.isfinite(a)] = float(nodata)
    ysize, xsize = a.shape
    ds = gdal.GetDriverByName("MEM").Create("", xsize, ysize, 1, gdal.GDT_Float32)
    band = ds.GetRasterBand(1)
    band.WriteArray(a)
    band.SetNoDataValue(float(nodata))
    gdal.FillNodata(targetBand=band, maskBand=None, maxSearchDist=max_dist_px, smoothingIterations=0)
    filled = band.ReadAsArray()
    ds = None
    return filled

def export_geotiff(layer: QgsRasterLayer, path: str, extent: QgsRectangle, width: int, height: int):
    """Export a raster layer to a GeoTIFF using QGIS Processing."""
    import processing
    params = {
        'INPUT': layer,
        'EXTENT': extent,
        'WIDTH': width,
        'HEIGHT': height,
        'NODATA': None,
        'OPTIONS': 'COMPRESS=DEFLATE',
        'DATA_TYPE': 5, # Float32
        'OUTPUT': path
    }
    processing.run("gdal:translate", params)
    return os.path.exists(path)
