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

from kigam import geochem_utils, raster_output, raster_utils
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
    <Layer><Name>geochem</Name><Title>GeoChem</Title><SRS>EPSG:5186</SRS>
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

    def test_off_legend_and_lowest_real_color(self):
        rgb = np.array([[(90, 90, 10), (1, 39, 116), (204, 204, 204), (0, 255, 0)]], dtype=np.uint8)
        preset = geochem_utils.PRESETS['pb']
        values, stats = geochem_utils.convert_rgb(*np.moveaxis(rgb, -1, 0), preset.points,
                                                 np.ones(rgb.shape[:2], bool), -9999)
        self.assertEqual(values[0, 0], -9999)
        self.assertAlmostEqual(values[0, 1], 18.017, places=3)
        self.assertEqual(values[0, 2], -9999)
        self.assertEqual(values[0, 3], 24)
        self.assertEqual(stats['off_legend_pixels'], 1)

    def test_linework_and_halo_get_neighbor_values_only_on_request(self):
        pixels = [(255, 255, 255), (230, 0, 0), (115, 0, 0), (0, 0, 0),
                  (255, 255, 0), (115, 12, 12)]
        rgb = np.array([pixels] * 3, dtype=np.uint8)
        args = (*np.moveaxis(rgb, -1, 0), geochem_utils.FE2O3_POINTS,
                np.ones(rgb.shape[:2], bool), -9999)
        values, stats = geochem_utils.convert_rgb(*args)
        self.assertTrue(np.all(values[:, 2:4] == -9999))
        self.assertEqual(stats['filled_pixels'], 0)
        filled, stats = geochem_utils.convert_rgb(*args, fill_distance=3)
        self.assertTrue(np.all(filled[:, 0] == -9999))
        self.assertTrue(np.all(filled[:, 2] == 12))
        np.testing.assert_allclose(filled[:, 3], 7.1)
        self.assertTrue(np.all(filled[:, 5] == 51))
        self.assertEqual(stats['filled_pixels'], 6)

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
        uri = f'crs=EPSG:5186&format=image/png&layers=geochem&styles=&url={url}'
        layer = QgsRasterLayer(uri, 'Fixture WMS', 'wms')
        self.assertTrue(layer.isValid())
        has_alpha = geochem_utils.source_has_alpha(layer)
        self.assertTrue(has_alpha)
        grid = raster_utils.metric_grid(layer.extent(), layer.crs(), 10)
        path = self.root / 'wms.tif'
        self.assertTrue(geochem_utils.export_geotiff(
            layer, str(path), grid.extent, grid.width, grid.height, grid.crs))
        r, g, b, available = geochem_utils.read_rgb(path, grid, has_alpha)
        self.assertFalse(available[0, 0])
        self.assertTrue(available[1:, 1:].all())
        self.assertEqual((r[1, 1], g[1, 1], b[1, 1]), (0, 255, 0))

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
        r, g, b, available = geochem_utils.read_rgb(rendered, grid, has_alpha)
        self.assertTrue(available.all())
        self.assertEqual((r[0, 0], g[0, 0], b[0, 0]), (0, 255, 0))

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
