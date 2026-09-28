# -*- coding: utf-8 -*-

def classFactory(iface):
    from .main import KigamGeoDownloader
    return KigamGeoDownloader(iface)
