# -*- coding: utf-8 -*-
import copy
import json
import os


DEFAULT_PLUGIN_CONFIG = {
    "ui": {
        "label_font": {
            "default_family": "Malgun Gothic",
            "size_min": 5,
            "size_max": 50,
            "default_size": 10,
        },
        "geochem_resolution": {
            "min": 1,
            "max": 1000,
            "default": 30,
        },
        "export_resolution": {
            "min": 1,
            "max": 1000,
            "default": 10,
        },
    },
    "zip_processor": {
        "extract_root_name": "KIGAM_Extract",
        "symbol_priority_fields": ["LITHOIDX", "TYPE", "ASGN_CODE", "SIGN", "CODE"],
        "candidate_encodings": ["CP949", "EUC-KR", None, "UTF-8"],
        "encoding_preference": {
            "CP949": 4,
            "EUC-KR": 3,
            "default": 2,
            "UTF-8": 1,
        },
        "qml_write_encoding": "UTF-8",
        "marker_symbol_size": 6.0,
        "fill_symbol_width": 10.0,
        "label_field_candidates": ["LITHOIDX", "LITHONAME"],
        "reference_layer_keywords": ["frame", "crosssectionline"],
        "litho_layer_keyword": "litho",
    },
    "raster": {
        "vector_export_field_candidates": ["LITHOIDX", "LITHONAME", "TYPE", "CODE", "ASGN_CODE", "SIGN"],
        "nodata": -9999.0,
        "gdal_data_type": 5,
        "maxent_rasterize_units": 1,
        "maxent_resampling": 0,
        "geochem_fill_nodata_distance": 30,
        "multithreading": False,
    },
}


def _deep_merge(base, override):
    for key, value in override.items():
        if (
            isinstance(value, dict)
            and isinstance(base.get(key), dict)
        ):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _normalize_encoding_list(values):
    normalized = []
    for value in values:
        if value is None:
            normalized.append(None)
            continue
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not text:
            continue
        if text.lower() in ("default", "none", "null"):
            normalized.append(None)
        else:
            normalized.append(text)

    if not normalized:
        return [None]

    deduped = []
    seen = set()
    for value in normalized:
        key = value if value is None else value.upper()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _normalize_plugin_config(config):
    normalized = copy.deepcopy(config)

    zip_cfg = normalized.setdefault("zip_processor", {})
    encodings = zip_cfg.get("candidate_encodings", [])
    if isinstance(encodings, list):
        zip_cfg["candidate_encodings"] = _normalize_encoding_list(encodings)
    else:
        zip_cfg["candidate_encodings"] = [None]

    pref = zip_cfg.get("encoding_preference")
    if not isinstance(pref, dict):
        zip_cfg["encoding_preference"] = {"default": 0}
    else:
        clean = {}
        for k, v in pref.items():
            if not isinstance(v, int):
                continue
            if isinstance(k, str):
                clean[k.upper()] = v
            else:
                clean[str(k)] = v
        if "DEFAULT" not in clean:
            clean["DEFAULT"] = 0
        zip_cfg["encoding_preference"] = clean

    return normalized


def load_plugin_config(plugin_dir=None):
    config = copy.deepcopy(DEFAULT_PLUGIN_CONFIG)
    if not plugin_dir:
        plugin_dir = os.path.dirname(__file__)

    config_path = os.path.join(plugin_dir, "plugin_config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as fp:
                loaded = json.load(fp)
            if isinstance(loaded, dict):
                _deep_merge(config, loaded)
        except Exception:
            # Keep defaults if config is malformed.
            pass

    return _normalize_plugin_config(config)


PLUGIN_CONFIG = load_plugin_config()
