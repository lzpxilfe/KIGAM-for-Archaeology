# -*- coding: utf-8 -*-
"""
GeoChem utilities for KIGAM for Archaeology
Ported from ArchToolkit (lzpxilfe/ar)

This module contains functions and data for converting WMS RGB raster
to numerical value rasters based on legend color mapping.
"""
import os
import math
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from osgeo import gdal, ogr
from qgis.core import (
    Qgis,
    QgsRasterLayer,
    QgsRectangle,
    QgsCoordinateTransform,
    QgsProject,
    QgsGeometry,
    QgsRasterPipe,
    QgsRasterFileWriter,
    QgsRasterProjector
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

ZN_POINTS = [LegendPoint(v, p.rgb) for v, p in zip([0.0, 45.0, 57.0, 66.0, 79.0, 107.0, 149.0, 212.0, 272.0, 542.0, 21100.0], CU_POINTS)]
SR_POINTS = [LegendPoint(v, p.rgb) for v, p in zip([0.0, 57.0, 72.0, 83.0, 99.0, 135.0, 192.0, 275.0, 342.0, 496.0, 3645.0], CU_POINTS)]
BA_POINTS = [LegendPoint(v, p.rgb) for v, p in zip([0.0, 734.0, 853.0, 935.0, 1050.0, 1268.0, 1507.0, 1752.0, 1920.0, 2362.0, 15840.0], CU_POINTS)]
CAO_POINTS = [LegendPoint(v, p.rgb) for v, p in zip([0.0, 0.40, 0.50, 0.58, 0.73, 1.18, 1.90, 2.99, 4.05, 9.03, 53.07], CU_POINTS)]

PRESETS: Dict[str, GeoChemPreset] = {
    "fe2o3": GeoChemPreset(key="fe2o3", label="Fe2O3 (산화철)", unit="%", points=FE2O3_POINTS),
    "pb": GeoChemPreset(key="pb", label="Pb (납)", unit="ppm", points=PB_POINTS),
    "cu": GeoChemPreset(key="cu", label="Cu (구리)", unit="ppm", points=CU_POINTS),
    "zn": GeoChemPreset(key="zn", label="Zn (아연)", unit="ppm", points=ZN_POINTS),
    "sr": GeoChemPreset(key="sr", label="Sr (스트론튬)", unit="ppm", points=SR_POINTS),
    "ba": GeoChemPreset(key="ba", label="Ba (바륨)", unit="ppm", points=BA_POINTS),
    "cao": GeoChemPreset(key="cao", label="CaO (칼슘)", unit="%", points=CAO_POINTS),
}


def _points_to_breaks(points: Sequence[LegendPoint]) -> List[float]:
    """Extract break values from legend points."""
    vals = [float(p.value) for p in points]
    vals = sorted(set(vals))
    return vals


def interp_rgb_to_value(
    *,
    r: np.ndarray,
    g: np.ndarray,
    b: np.ndarray,
    points: Sequence[LegendPoint],
    snap_last_t: Optional[float] = None,
) -> np.ndarray:
    """Vectorized mapping: RGB -> scalar value by projecting to the nearest legend polyline segment in RGB space.
    
    This is the exact algorithm from ArchToolkit.
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

    pts = list(points)
    last_seg_idx = len(pts) - 2
    snap_last = None
    if snap_last_t is not None:
        try:
            snap_last = float(snap_last_t)
        except Exception:
            snap_last = None
    if snap_last is not None and not (0.0 <= snap_last <= 1.0):
        snap_last = None

    for i in range(len(pts) - 1):
        v1 = float(pts[i].value)
        v2 = float(pts[i + 1].value)
        c1 = pts[i].rgb
        c2 = pts[i + 1].rgb

        c1r = np.float32(c1[0])
        c1g = np.float32(c1[1])
        c1b = np.float32(c1[2])
        vr = np.float32(c2[0] - c1[0])
        vg = np.float32(c2[1] - c1[1])
        vb = np.float32(c2[2] - c1[2])
        v_len_sq = np.float32(vr * vr + vg * vg + vb * vb)
        if v_len_sq <= 0:
            continue

        t = ((rr - c1r) * vr + (gg - c1g) * vg + (bb - c1b) * vb) / v_len_sq
        np.clip(t, np.float32(0.0), np.float32(1.0), out=t)
        if snap_last is not None and i == last_seg_idx:
            # Important: apply snap BEFORE distance comparison (affects which segment wins).
            try:
                t[t > np.float32(snap_last)] = np.float32(1.0)
            except Exception:
                pass
        pr = c1r + t * vr
        pg = c1g + t * vg
        pb = c1b + t * vb
        dist_sq = (rr - pr) ** 2 + (gg - pg) ** 2 + (bb - pb) ** 2

        mask = dist_sq < min_dist
        if not np.any(mask):
            continue

        base = np.float32(v1)
        delta = np.float32(v2 - v1)
        out[mask] = base + t[mask].astype(np.float32, copy=False) * delta
        min_dist[mask] = dist_sq[mask].astype(np.float32, copy=False)

    return out


def mask_black_lines(r: np.ndarray, g: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Detect neutral dark 'linework' (not intense red/brown) and return mask."""
    rr = r.astype(np.int16, copy=False)
    gg = g.astype(np.int16, copy=False)
    bb = b.astype(np.int16, copy=False)
    return (
        (rr < 75)
        & (gg < 75)
        & (bb < 75)
        & (np.abs(rr - gg) < 15)
        & (np.abs(gg - bb) < 15)
    )


def gdal_fill_nodata(arr: np.ndarray, nodata: float, max_dist_px: int) -> np.ndarray:
    """Fill nodata using GDAL FillNodata."""
    a = arr.astype(np.float32, copy=True)
    a[~np.isfinite(a)] = float(nodata)
    ysize, xsize = a.shape
    ds = gdal.GetDriverByName("MEM").Create("", xsize, ysize, 1, gdal.GDT_Float32)
    band = ds.GetRasterBand(1)
    band.WriteArray(a)
    band.SetNoDataValue(float(nodata))
    gdal.FillNodata(targetBand=band, maskBand=None, maxSearchDist=max(1, max_dist_px), smoothingIterations=0)
    filled = band.ReadAsArray()
    ds = None
    return filled


def export_geotiff(layer: QgsRasterLayer, path: str, extent: QgsRectangle, width: int, height: int) -> bool:
    """
    Export a raster layer (including WMS) to a GeoTIFF.
    Uses QgsRasterFileWriter, falls back to GDAL warp if needed.
    Ported from ArchToolkit.
    """
    import processing
    
    try:
        provider = layer.dataProvider()
        pipe = QgsRasterPipe()
        if not pipe.set(provider.clone()):
            # Fallback: some providers may not support clone() cleanly.
            if not pipe.set(provider):
                raise RuntimeError("pipe.set(provider) failed")
        writer = QgsRasterFileWriter(path)
        writer.setOutputFormat("GTiff")
        writer.setCreateOptions(["COMPRESS=LZW", "TILED=YES"])
        ctx = QgsProject.instance().transformContext()
        res = writer.writeRaster(pipe, int(width), int(height), extent, layer.crs(), ctx)
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
        px = max(extent.width() / max(1, int(width)), extent.height() / max(1, int(height)))
        px = float(px) if px > 0 else None
        processing.run(
            "gdal:warpreproject",
            {
                "INPUT": layer,
                "SOURCE_CRS": None,
                "TARGET_CRS": None,
                "RESAMPLING": 0,  # Nearest (preserve legend colors)
                "NODATA": None,
                "TARGET_RESOLUTION": px,
                "OPTIONS": "COMPRESS=LZW|TILED=YES",
                "DATA_TYPE": 0,
                "TARGET_EXTENT": extent_str,
                "TARGET_EXTENT_CRS": layer.crs().authid() if layer.crs() else None,
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
