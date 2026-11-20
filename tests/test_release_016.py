import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse
import zipfile

import numpy as np
from osgeo import gdal
from qgis.core import (
    Qgis, QgsAction, QgsCoordinateReferenceSystem, QgsGeometry, QgsProject, QgsRasterLayer, QgsVectorLayer,
)
from qgis.PyQt.QtCore import QBuffer, QIODevice, Qt
from qgis.PyQt.QtGui import QColor, QImage
from qgis.PyQt.QtWidgets import QApplication

from kigam import geochem_utils, raster_output, raster_utils
from kigam.help_dialog import HelpDialog
from kigam.main import MainDialog
from kigam.zip_processor import ZipProcessor
from test_regressions import shapefile, png


def wms_capabilities(url):
    endpoint = f'<DCPType><HTTP><Get><OnlineResource xlink:type="simple" xlink:href="{url}"/></Get></HTTP></DCPType>'
    return f"""<WMT_MS_Capabilities version="1.1.1" xmlns:xlink="http://www.w3.org/1999/xlink">
    <Service><Name>OGC:WMS</Name><Title>Test WMS</Title></Service>
    <Capability><Request>
      <GetCapabilities><Format>application/vnd.ogc.wms_xml</Format>{endpoint}</GetCapabilities>
      <GetMap><Format>image/png</Format>{endpoint}</GetMap>
    </Request><Exception><Format>application/vnd.ogc.se_xml</Format></Exception>
    <Layer><Name>L_geochemMP_FE2O3</Name><Title>GeoChem</Title><SRS>EPSG:5186</SRS>
    <LatLonBoundingBox minx="126" miny="36" maxx="128" maxy="38"/>
    <BoundingBox SRS="EPSG:5186" minx="200000" miny="500000" maxx="200100" maxy="500100"/>
    </Layer></Capability></WMT_MS_Capabilities>""".encode()


class WmsHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        query = {key.upper(): value[0] for key, value in parse_qs(urlparse(self.path).query).items()}
        if query.get('REQUEST', '').lower() == 'getmap':
            image = QImage(int(query['WIDTH']), int(query['HEIGHT']), QImage.Format.Format_ARGB32)
            image.fill(QColor(0, 255, 0))
            image.setPixelColor(0, 0, QColor(0, 0, 0, 0))
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            image.save(buffer, 'PNG')
            payload, content_type = bytes(buffer.data()), 'image/png'
        else:
            url = 'http://127.0.0.1:%d/wms' % self.server.server_port
            payload, content_type = wms_capabilities(url), 'text/xml'
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class Release016Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='kigam_016_', ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.project = QgsProject.instance()
        self.addCleanup(self.project.removeAllMapLayers)

    def raster(self, filename, data, *, gt=(200000, 10, 0, 500100, 0, -10), rgb=False):
        data = np.asarray(data)
        if data.ndim == 2:
            data = data[None, :, :]
        count, height, width = data.shape
        path = self.root / filename
        dtype = gdal.GDT_Byte if rgb else gdal.GDT_Float32
        dataset = gdal.GetDriverByName('GTiff').Create(str(path), width, height, count, dtype)
        dataset.SetGeoTransform(gt)
        dataset.SetProjection(QgsCoordinateReferenceSystem('EPSG:5186').toWkt())
        rgb_channels = (gdal.GCI_RedBand, gdal.GCI_GreenBand, gdal.GCI_BlueBand, gdal.GCI_AlphaBand)
        for i, values in enumerate(data, 1):
            band = dataset.GetRasterBand(i)
            if rgb:
                band.SetColorInterpretation(rgb_channels[i - 1])
            else:
                band.SetNoDataValue(-9999)
            band.WriteArray(values)
        band = dataset = None
        return path

    def select_exports(self, dialog, *layers):
        ids = {layer.id() for layer in layers}
        for index in range(dialog.layer_list.count()):
            item = dialog.layer_list.item(index)
            state = Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in ids else Qt.CheckState.Unchecked
            item.setCheckState(state)

    def export(self, dialog, path):
        with patch('kigam.main.QFileDialog.getSaveFileName', return_value=(str(path), '')), \
                patch('kigam.main.QMessageBox.information') as done, \
                patch('kigam.main.QMessageBox.critical') as errors, \
                patch('kigam.main.QMessageBox.warning') as warnings:
            dialog.export_maxent_raster()
        self.assertFalse(errors.called, errors.call_args)
        self.assertFalse(warnings.called, warnings.call_args)
        self.assertTrue(done.called)

    def test_help_buttons_open_the_right_page_and_copy_official_wms_address(self):
        dialog = MainDialog()
        self.addCleanup(dialog.close)
        visited = []
        clipboard = QApplication.clipboard()
        old_text = clipboard.text()
        self.addCleanup(clipboard.setText, old_text)

        def inspect(help_dialog):
            visited.append(help_dialog.tabs.tabText(help_dialog.tabs.currentIndex()))
            self.assertEqual(help_dialog.tabs.count(), 4)
            if help_dialog.tabs.currentIndex() == 1:
                self.assertTrue(help_dialog.address.isReadOnly())
                help_dialog.copy_button.click()
                self.assertEqual(
                    clipboard.text(),
                    'https://data.kigam.re.kr/mgeo/geoserver/Geochemical_map/wms',
                )
                self.assertTrue(help_dialog.copy_status.text())

        with patch.object(HelpDialog, 'exec', inspect):
            dialog.help_btn.click()
            dialog.wms_help_btn.click()
        self.assertEqual(visited, ['시작하기', 'WMS 연결'])

    def test_observed_iron_rgb_and_disjoint_nodata_reasons(self):
        pixels = np.array([[(0, 0, 255), (243, 168, 91), (133, 0, 0), (0, 0, 100),
                            (192, 192, 192), (85, 255, 0), (255, 255, 255), (0, 255, 0),
                            (0, 255, 0)]], dtype=np.uint8)
        coverage = np.array([[True] * 8 + [False]])
        opaque = np.array([[True] * 7 + [False, False]])
        rgb = geochem_utils.RGBInput(*np.moveaxis(pixels, -1, 0), coverage, opaque)
        values, stats = geochem_utils.classify_rgb(rgb, geochem_utils.PRESETS['fe2o3'], -9999)
        np.testing.assert_array_equal(values, [[2, 7, 10, 1, -9999, -9999, -9999, -9999, -9999]])
        self.assertEqual(stats['off_legend_pixels'], 1)
        self.assertEqual(stats['absent_pixels'], 1)
        self.assertEqual(stats['white_pixels'], 1)
        self.assertEqual(stats['alpha_masked_pixels'], 1)
        self.assertEqual(stats['source_masked_pixels'], 1)

    def test_linework_and_halo_get_neighbor_classes_only_on_request(self):
        pixels = [(255, 255, 255), (255, 0, 0), (115, 0, 0), (0, 0, 0),
                  (255, 255, 0), (133, 0, 0)]
        channels = np.array([pixels] * 3, dtype=np.uint8)
        visible = np.ones(channels.shape[:2], bool)
        rgb = geochem_utils.RGBInput(*np.moveaxis(channels, -1, 0), visible, visible)
        args = (rgb, geochem_utils.PRESETS['fe2o3'], -9999)
        values, stats = geochem_utils.classify_rgb(*args)
        self.assertTrue(np.all(values[:, 2:4] == -9999))
        self.assertEqual(stats['filled_pixels'], 0)
        filled, stats = geochem_utils.classify_rgb(*args, fill_distance=3)
        self.assertTrue(np.all(filled[:, 0] == -9999))
        self.assertTrue(np.all(filled[:, 2] == 9))
        self.assertTrue(np.all(filled[:, 3] == 6))
        self.assertTrue(np.all(filled[:, 5] == 10))
        self.assertEqual(stats['filled_pixels'], 6)

    def test_fill_only_bridges_a_gap_with_two_original_sides(self):
        nodata = -9999
        values = np.array([[3, nodata, nodata, 3, nodata, nodata, 9]], dtype=np.int32)
        line = np.array([[False, True, True, False, False, True, False]])
        filled = geochem_utils.fill_linework(values, line, nodata, 2)
        np.testing.assert_array_equal(filled, [[3, 3, 3, 3, nodata, nodata, 9]])
        np.testing.assert_array_equal(geochem_utils.fill_linework(values, line, nodata, 1), values)

    def test_bridge_preserves_distinct_classes_on_either_side(self):
        values = np.array([[2, -9999, -9999, 9]], dtype=np.int32)
        filled = geochem_utils.fill_linework(values, values == -9999, -9999, 2)
        np.testing.assert_array_equal(filled, [[2, 2, 9, 9]])

    def test_diagonal_bridge_uses_physical_pixel_distance(self):
        nodata = -9999
        values = np.full((3, 3), nodata, dtype=np.int32)
        values[0, 2] = values[2, 0] = 8
        line = np.zeros(values.shape, dtype=bool)
        line[1, 1] = True
        self.assertEqual(geochem_utils.fill_linework(values, line, nodata, 1)[1, 1], nodata)
        self.assertEqual(geochem_utils.fill_linework(values, line, nodata, 2)[1, 1], 8)

    def test_geochem_checkbox_and_output_metadata(self):
        colors = np.array([[(0, 0, 255, 255), (0, 0, 0, 255), (0, 0, 0, 255), (0, 0, 255, 255),
                           (192, 192, 192, 255), (0, 0, 0, 255), (255, 0, 0, 255), (0, 255, 0, 127)]],
                          dtype=np.uint8)
        path = self.raster('gap_rgb.tif', np.moveaxis(colors, -1, 0), rgb=True)
        layer = self.project.addMapLayer(QgsRasterLayer(str(path), 'RGB'))
        iface = MagicMock()
        iface.mapCanvas().extent.return_value = layer.extent()
        iface.mapCanvas().mapSettings().destinationCrs.return_value = layer.crs()
        dialog = MainDialog(iface=iface)
        self.addCleanup(dialog.close)
        self.assertFalse(dialog.geochem_fill_lines.isChecked())
        dialog.geochem_res_spin.setValue(10)
        dialog.wms_layer_combo.setCurrentIndex(dialog.wms_layer_combo.findData(layer.id()))
        dialog.geochem_preset_combo.setCurrentIndex(dialog.geochem_preset_combo.findData('fe2o3'))
        for enabled, method, valid in [(False, 'off', -9999), (True, 'opposite_side_nearest_class', 2)]:
            dialog.geochem_fill_lines.setChecked(enabled)
            output = self.root / f'gap-{enabled}.tif'
            with patch('kigam.main.QFileDialog.getSaveFileName', return_value=(str(output), '')), \
                    patch('kigam.main.QMessageBox.critical') as errors, \
                    patch('kigam.main.QMessageBox.warning') as warnings, patch('kigam.main.QMessageBox.information'):
                dialog.run_geochem_analysis()
            self.assertFalse(errors.called, errors.call_args)
            self.assertFalse(warnings.called, warnings.call_args)
            dataset = gdal.Open(str(output))
            np.testing.assert_array_equal(dataset.ReadAsArray(), [[2, valid, valid, 2, -9999, -9999, 9, -9999]])
            self.assertEqual(dataset.GetMetadataItem('KIGAM_LINE_FILL_METHOD'), method)
            self.assertEqual(dataset.GetMetadataItem('KIGAM_FILLED_PIXELS'), '2' if enabled else '0')
            dataset = None

    def test_all_colors_rejected_keeps_existing_result(self):
        bands = np.array([[[90, 90]], [[90, 90]], [[10, 10]]], dtype=np.uint8)
        path = self.raster('rgb.tif', bands, rgb=True)
        layer = self.project.addMapLayer(QgsRasterLayer(str(path), 'RGB'))
        iface = MagicMock()
        iface.mapCanvas().extent.return_value = layer.extent()
        iface.mapCanvas().mapSettings().destinationCrs.return_value = layer.crs()
        dialog = MainDialog(iface=iface)
        self.addCleanup(dialog.close)
        dialog.geochem_res_spin.setValue(10)
        dialog.wms_layer_combo.setCurrentIndex(dialog.wms_layer_combo.findData(layer.id()))
        dialog.geochem_preset_combo.setCurrentIndex(dialog.geochem_preset_combo.findData('pb'))
        destination = self.root / 'existing.tif'
        destination.write_bytes(b'old result')
        with patch('kigam.main.QFileDialog.getSaveFileName', return_value=(str(destination), '')), \
                patch('kigam.main.QMessageBox.critical') as errors, \
                patch('kigam.main.QMessageBox.warning') as warnings, \
                patch('kigam.main.QMessageBox.information') as done:
            dialog.run_geochem_analysis()
        self.assertFalse(warnings.called, warnings.call_args)
        self.assertIn('범례와 일치하는 유효한 픽셀', errors.call_args.args[-1])
        self.assertFalse(done.called)
        self.assertEqual(destination.read_bytes(), b'old result')

    def test_scalar_raster_is_not_offered_as_rgb(self):
        path = self.raster('scalar.tif', np.ones((2, 2)))
        layer = self.project.addMapLayer(QgsRasterLayer(str(path), 'numeric'))
        dialog = MainDialog()
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.wms_layer_combo.findData(layer.id()), -1)
        with self.assertRaisesRegex(ValueError, 'RGB'):
            geochem_utils.source_has_alpha(layer)

    def test_wms_provider_exports_rgba_and_preserves_transparent_cells(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), WmsHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        url = f'http://127.0.0.1:{server.server_port}/wms'
        uri = f'crs=EPSG:5186&format=image/png&layers=L_geochemMP_FE2O3&styles=&url={url}'
        layer = QgsRasterLayer(uri, 'Fixture WMS', 'wms')
        self.assertTrue(layer.isValid())
        self.project.addMapLayer(layer)
        dialog = MainDialog()
        self.addCleanup(dialog.close)
        index = dialog.wms_layer_combo.findData(layer.id())
        dialog.wms_layer_combo.setCurrentIndex(index)
        dialog.wms_layer_combo.activated.emit(index)
        self.assertEqual(dialog.geochem_preset_combo.currentData(), 'fe2o3')
        geochem_utils.validate_wms_preset(layer.source(), geochem_utils.PRESETS['fe2o3'])
        has_alpha = geochem_utils.source_has_alpha(layer)
        self.assertTrue(has_alpha)
        grid = raster_utils.metric_grid(layer.extent(), layer.crs(), 10)
        path = self.root / 'wms.tif'
        self.assertTrue(geochem_utils.export_geotiff(
            layer, str(path), grid.extent, grid.width, grid.height, grid.crs))
        rgb = geochem_utils.read_rgb(path, grid, has_alpha)
        self.assertFalse(rgb.opaque[0, 0])
        self.assertTrue(rgb.opaque[1:, 1:].all())
        self.assertEqual((rgb.r[1, 1], rgb.g[1, 1], rgb.b[1, 1]), (0, 255, 0))

    def test_fourth_band_is_only_used_as_alpha_if_declared(self):
        path = self.root / 'multiband.tif'
        dataset = gdal.GetDriverByName('GTiff').Create(
            str(path), 2, 2, 4, gdal.GDT_Byte, ['PHOTOMETRIC=RGB', 'ALPHA=UNSPECIFIED'])
        dataset.SetProjection(QgsCoordinateReferenceSystem('EPSG:5186').toWkt())
        dataset.SetGeoTransform((200000, 10, 0, 500100, 0, -10))
        for index, value in enumerate((0, 255, 0, 0), 1):
            dataset.GetRasterBand(index).Fill(value)
        dataset = None
        layer = QgsRasterLayer(str(path), 'RGB plus unrelated band')
        has_alpha = geochem_utils.source_has_alpha(layer)
        self.assertFalse(has_alpha)
        grid = raster_utils.reference_grid(layer)
        rendered = self.root / 'rendered.tif'
        self.assertTrue(geochem_utils.export_geotiff(
            layer, str(rendered), grid.extent, grid.width, grid.height, grid.crs))
        rgb = geochem_utils.read_rgb(rendered, grid, has_alpha)
        self.assertTrue((rgb.coverage & rgb.opaque).all())
        self.assertEqual((rgb.r[0, 0], rgb.g[0, 0], rgb.b[0, 0]), (0, 255, 0))

    def test_wms_uri_detects_original_layer_and_rejects_other_style_or_element(self):
        preset = geochem_utils.PRESETS['zn']
        uri = ('crs=EPSG:4326&format=image/png&layers=Geochemical_map%3AL_geochemMP_ZN'
               f'&styles=&url={geochem_utils.WMS_URL}')
        self.assertIs(geochem_utils.wms_preset(uri), preset)
        geochem_utils.validate_wms_preset(uri, preset)
        with self.assertRaisesRegex(ValueError, '원소'):
            geochem_utils.validate_wms_preset(uri, geochem_utils.PRESETS['pb'])
        with self.assertRaisesRegex(ValueError, '스타일'):
            geochem_utils.validate_wms_preset(uri.replace('styles=&', 'styles=other&'), preset)
        with self.assertRaisesRegex(ValueError, 'PNG'):
            geochem_utils.validate_wms_preset(uri.replace('image/png', 'image/jpeg'), preset)
        with self.assertRaisesRegex(ValueError, '원소 레이어 하나'):
            geochem_utils.validate_wms_preset(uri + '&layers=L_geochemMP_PB', preset)

    def test_reopened_class_file_exports_integer_ids_with_range_csv(self):
        template = self.raster('template.tif', np.ones((2, 2)))
        grid = raster_utils.reference_grid(QgsRasterLayer(str(template), 'Template'))
        preset = geochem_utils.PRESETS['cao']
        path = self.root / 'reopened.tif'
        values = np.array([[1, 10], [10, 1]], dtype=np.int32)
        raster_output.write_value_raster(path, values, grid, -9999, preset.metadata(),
                                         data_type=gdal.GDT_Int32, class_ids=preset.class_ids)
        layer = self.project.addMapLayer(QgsRasterLayer(str(path), 'Saved from a different project'))
        self.assertIs(geochem_utils.read_class_preset(layer), preset)
        dialog = MainDialog()
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.layer_list.count(), 1)
        dialog.res_spin.setValue(5)
        expanded = values.repeat(2, axis=0).repeat(2, axis=1)
        with patch('kigam.main.MAXENT_RESAMPLING', 1):  # Bilinear is for continuous data only.
            for file in ('classes.tif', 'classes.asc'):
                dest = self.root / file
                self.export(dialog, dest)
                result = gdal.Open(str(dest))
                np.testing.assert_array_equal(result.ReadAsArray(), expanded)
                if file.endswith('.tif'):
                    self.assertEqual(result.GetRasterBand(1).DataType, gdal.GDT_Int32)
                self.assertEqual(result.GetMetadataItem('KIGAM_VALUE_KIND'), geochem_utils.CLASS_KIND)
                result = None
                with raster_utils.codebook_path(dest).open(encoding='utf-8-sig', newline='') as fp:
                    rows = list(csv.DictReader(fp))
                self.assertEqual(rows[-1]['UPPER'], '53.07')
                self.assertEqual(rows[-1]['UNIT'], '%')

    def test_geochemical_and_geological_exports_share_grid_keep_types(self):
        reference_path = self.raster('reference.tif', np.ones((3, 3)), gt=(200005, 20, 0, 500095, 0, -20))
        numeric_path = self.raster('numeric.tif', np.full((10, 10), 0.40))
        shp = shapefile(self.root / 'data', text='Kgr', polygon=True)
        reference = self.project.addMapLayer(QgsRasterLayer(str(reference_path), '기준'))
        numeric = self.project.addMapLayer(QgsRasterLayer(str(numeric_path), 'CaO (수치화)'))
        geology = self.project.addMapLayer(QgsVectorLayer(str(shp), 'Geology', 'ogr'))
        dialog = MainDialog()
        self.addCleanup(dialog.close)
        dialog.maxent_group.setChecked(True)
        self.assertTrue(dialog.res_spin.isEnabled())
        dialog.export_reference_combo.setCurrentIndex(dialog.export_reference_combo.findData(reference.id()))
        self.assertFalse(dialog.res_spin.isEnabled())
        geo_file, chem_file, chem_tif = self.root / 'litho.tif', self.root / 'cao.asc', self.root / 'cao.tif'
        self.select_exports(dialog, geology)
        self.export(dialog, geo_file)
        self.select_exports(dialog, numeric)
        self.export(dialog, chem_file)
        self.export(dialog, chem_tif)
        geo, chem = gdal.Open(str(geo_file)), gdal.Open(str(chem_file))
        self.assertEqual(geo.GetGeoTransform(), chem.GetGeoTransform())
        self.assertEqual(chem.GetGeoTransform(), (200005, 20, 0, 500095, 0, -20))
        self.assertEqual((geo.RasterXSize, geo.RasterYSize), (3, 3))
        self.assertEqual(geo.GetRasterBand(1).DataType, gdal.GDT_Int32)
        chem_binary = gdal.Open(str(chem_tif))
        self.assertEqual(chem_binary.GetRasterBand(1).DataType, gdal.GDT_Float32)
        np.testing.assert_array_equal(chem.ReadAsArray().astype(np.float32), chem_binary.ReadAsArray())
        np.testing.assert_allclose(chem.ReadAsArray(), 0.40)
        self.assertTrue(chem_file.with_suffix('.prj').is_file())

    def test_same_stem_tiff_and_ascii_keep_distinct_codebooks(self):
        first = shapefile(self.root / 'a', text='Kgr', polygon=True)
        second = shapefile(self.root / 'b', text='Qa', polygon=True)
        first = self.project.addMapLayer(QgsVectorLayer(str(first), 'A', 'ogr'))
        second = self.project.addMapLayer(QgsVectorLayer(str(second), 'B', 'ogr'))
        dialog = MainDialog()
        self.addCleanup(dialog.close)
        tif, asc = self.root / 'geology.tif', self.root / 'geology.asc'
        self.select_exports(dialog, first)
        self.export(dialog, tif)
        self.select_exports(dialog, second)
        self.export(dialog, asc)
        for filename, expected in ((tif, 'Kgr'), (asc, 'Qa')):
            with raster_utils.codebook_path(filename).open(encoding='utf-8-sig', newline='') as fp:
                self.assertEqual(list(csv.reader(fp)), [['KIGAM_ID', 'VALUE'], ['1', expected]])

    def test_mixed_geometries_are_not_default_and_fail_before_save_prompt(self):
        point = shapefile(self.root / 'point', text='Qa')
        polygon = shapefile(self.root / 'polygon', text='Kgr', polygon=True)
        point = self.project.addMapLayer(QgsVectorLayer(str(point), 'Point', 'ogr'))
        polygon = self.project.addMapLayer(QgsVectorLayer(str(polygon), 'Polygon', 'ogr'))
        dialog = MainDialog()
        self.addCleanup(dialog.close)
        self.assertEqual(sum(dialog.layer_list.item(i).checkState() == Qt.CheckState.Checked
                             for i in range(dialog.layer_list.count())), 1)
        self.select_exports(dialog, point, polygon)
        with patch('kigam.main.QFileDialog.getSaveFileName') as save, \
                patch('kigam.main.QMessageBox.warning') as warning:
            dialog.export_maxent_raster()
        self.assertIn('지오메트리', warning.call_args.args[-1])
        self.assertFalse(save.called)

    def test_reference_crop_reports_classes_not_present_in_raster(self):
        first = shapefile(self.root / 'a', text='Kgr', polygon=True)
        second = shapefile(self.root / 'b', text='Qa', polygon=True)
        first = self.project.addMapLayer(QgsVectorLayer(str(first), 'A', 'ogr'))
        second = self.project.addMapLayer(QgsVectorLayer(str(second), 'B', 'ogr'))
        feature = next(second.getFeatures())
        geometry = QgsGeometry(feature.geometry())
        geometry.translate(200, 0)
        self.assertTrue(second.startEditing())
        self.assertTrue(second.changeGeometry(feature.id(), geometry))
        ref = self.raster('ref.tif', np.ones((3, 3)))
        reference = self.project.addMapLayer(QgsRasterLayer(str(ref), 'Reference'))
        dialog = MainDialog()
        self.addCleanup(dialog.close)
        self.select_exports(dialog, first, second)
        dialog.export_reference_combo.setCurrentIndex(dialog.export_reference_combo.findData(reference.id()))
        output = self.root / 'cropped.tif'
        with patch('kigam.main.QFileDialog.getSaveFileName', return_value=(str(output), '')), \
                patch('kigam.main.QMessageBox.critical') as errors, \
                patch('kigam.main.QMessageBox.warning') as warning:
            dialog.export_maxent_raster()
        self.assertFalse(errors.called, errors.call_args)
        self.assertIn('기록되지 않은 지질 분류 1개: Qa', warning.call_args.args[-1])
        self.assertTrue(output.is_file())

    def test_failed_pair_publication_restores_previous_pair(self):
        output = self.root / 'geology.tif'
        old_book = raster_utils.codebook_path(output)
        output.write_bytes(b'old raster')
        old_book.write_bytes(b'old table')
        real_replace = os.replace
        with raster_output.staging_directory(output) as stage:
            staged = Path(stage) / output.name
            staged.write_bytes(b'new raster')
            raster_utils.write_codebook(staged, {'Qa': 1})

            def interrupted_replace(source, target):
                if source == staged and target == output:
                    raise PermissionError('output locked')
                return real_replace(source, target)

            with patch('kigam.raster_output.os.replace', side_effect=interrupted_replace):
                with self.assertRaisesRegex(PermissionError, 'output locked'):
                    raster_output.publish_raster(staged, output, categories=True)
        self.assertEqual(output.read_bytes(), b'old raster')
        self.assertEqual(old_book.read_bytes(), b'old table')

    def test_value_writer_rejects_unreadable_output(self):
        path = self.root / 'staged.tif'
        template = self.raster('template.tif', np.ones((2, 2)))
        grid = raster_utils.reference_grid(QgsRasterLayer(str(template), 'Template'))
        with patch('kigam.raster_output.gdal.Open', return_value=None):
            with self.assertRaisesRegex(RuntimeError, '다시 열 수 없습니다'):
                raster_output.write_value_raster(path, np.ones((2, 2), np.float32), grid, -9999, {})

    def test_value_writer_checks_return_code_without_exceptions(self):
        template = self.raster('template.tif', np.ones((2, 2)))
        grid = raster_utils.reference_grid(QgsRasterLayer(str(template), 'Template'))
        band = MagicMock()
        band.SetNoDataValue.return_value = 0
        band.WriteArray.return_value = 3
        dataset = MagicMock()
        dataset.GetRasterBand.return_value = band
        for method in ('SetGeoTransform', 'SetProjection', 'SetMetadata', 'Close'):
            getattr(dataset, method).return_value = 0
        with patch('kigam.raster_output.gdal.GetDriverByName') as drivers:
            drivers.return_value.Create.return_value = dataset
            with self.assertRaisesRegex(RuntimeError, 'GDAL error 3'):
                raster_output.write_value_raster(self.root / 'stage.tif',
                                                 np.ones((2, 2), np.float32), grid, -9999, {})

    def test_qml_import_only_applies_symbology_and_labeling(self):
        shp = shapefile(self.root, polygon=True)
        source = QgsVectorLayer(str(shp), 'Source', 'ogr')
        source.renderer().symbol().setOpacity(0.37)
        source.actions().addAction(QgsAction(Qgis.AttributeActionType.Generic, 'Test only', 'echo test'))
        form = source.editFormConfig()
        form.setInitFunction('test_init')
        form.setInitCodeSource(Qgis.AttributeFormPythonInitCodeSource.Dialog)
        form.setInitCode('def test_init(*args): pass')
        source.setEditFormConfig(form)
        qml = self.root / 'fixture.qml'
        self.assertTrue(source.saveNamedStyle(str(qml))[1])

        options = QgsVectorLayer.LayerOptions()
        options.loadDefaultStyle = False
        target = QgsVectorLayer(str(shp), 'Target', 'ogr', options)
        processor = ZipProcessor(extract_root=self.root / 'extracted')
        processor.apply_sym_styling(target, None, str(qml))
        self.assertAlmostEqual(target.renderer().symbol().opacity(), 0.37)
        self.assertFalse(target.actions().actions())
        self.assertFalse(target.editFormConfig().initFunction())

    def test_qml_uses_existing_relative_image_before_same_stem_in_sym(self):
        png(self.root / 'images' / 'rock.png')
        png(self.root / 'sym' / 'rock.png', 'blue')
        qml = self.root / 'fixture.qml'
        qml.write_text('<qgis><Option name="imageFile" value="images/rock.png"/></qgis>', encoding='utf-8')
        from kigam.defusedxml import ElementTree as ET
        processor = ZipProcessor(extract_root=self.root / 'extracted')
        raw, normalized = processor._build_symbol_index(self.root / 'sym')
        style, linked, total = processor._build_relinked_qml(qml, raw, normalized)
        self.assertEqual((linked, total), (1, 1))
        path = ET.parse(style).getroot().find('Option').get('value')
        self.assertEqual(Path(path).resolve(), (self.root / 'images' / 'rock.png').resolve())

    def test_no_layers_means_no_extract_left_on_disk(self):
        extract_root = self.root / 'extracted'
        processor = ZipProcessor(extract_root=extract_root)
        for name in ('unrelated.txt', 'missing_shx.shp'):
            archive = self.root / f'{name}.zip'
            with zipfile.ZipFile(archive, 'w') as file:
                file.writestr(name, 'unused')
            self.assertEqual(processor.process_zip(archive), [])
            self.assertFalse(list(extract_root.iterdir()))
