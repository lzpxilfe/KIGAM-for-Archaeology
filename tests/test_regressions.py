import csv
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import zipfile

import numpy as np
from osgeo import ogr, osr, gdal
from qgis.core import (
    QgsVectorLayer, QgsProject, QgsRasterFillSymbolLayer, QgsFillSymbol,
    QgsSingleSymbolRenderer, QgsCoordinateReferenceSystem, QgsRectangle,
    QgsRasterLayer,
)
from qgis.PyQt.QtGui import QImage, QColor
from kigam.archive_utils import extract_archive
from kigam.encoding_utils import detect_dbf_encoding
from kigam.zip_processor import ZipProcessor
from kigam.defusedxml import ElementTree as ET
from kigam.plugin_config import load_plugin_config
from kigam import geochem_utils, raster_utils
from kigam.main import MainDialog


def shapefile(directory, name='Litho', encoding='CP949', text='화강암 퇴적층 똠', cpg=True,
              field='LITHONAME', polygon=False, epsg=5186):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (name + '.shp')
    previous_encoding = gdal.GetConfigOption('SHAPE_ENCODING')
    gdal.SetConfigOption('SHAPE_ENCODING', None)
    ds = ogr.GetDriverByName('ESRI Shapefile').CreateDataSource(str(path))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    layer = ds.CreateLayer(name, srs, ogr.wkbPolygon if polygon else ogr.wkbPoint, options=['ENCODING=' + encoding])
    definition = ogr.FieldDefn(field, ogr.OFTString)
    definition.SetWidth(100)
    layer.CreateField(definition)
    feature = ogr.Feature(layer.GetLayerDefn())
    feature.SetField(field, text)
    wkt = 'POLYGON ((200000 500000,200100 500000,200100 500100,200000 500100,200000 500000))' if polygon else 'POINT (200000 500000)'
    feature.SetGeometry(ogr.CreateGeometryFromWkt(wkt))
    layer.CreateFeature(feature)
    feature = layer = ds = None
    gdal.SetConfigOption('SHAPE_ENCODING', previous_encoding)
    if not cpg:
        path.with_suffix('.cpg').unlink()
    return path


def png(path, color='red'):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(16, 16, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    assert image.save(str(path))


class LegacyZipInfo(zipfile.ZipInfo):
    def _encodeFilenameFlags(self):
        return self.filename.encode('cp949'), self.flag_bits & ~0x800


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kigam_test_', ignore_cleanup_errors=True)
        self.root = Path(self.temp.name)
        self.processor = ZipProcessor(extract_root=str(self.root / 'extracted'))

    def tearDown(self):
        QgsProject.instance().removeAllMapLayers()
        self.temp.cleanup()

    def zip_tree(self, path=None, legacy=False):
        archive = self.root / 'input.zip'
        source = path or self.root / 'source'
        with zipfile.ZipFile(archive, 'w') as dest:
            for child in source.rglob('*'):
                if child.is_file():
                    name = child.relative_to(source).as_posix()
                    dest.writestr(LegacyZipInfo(name) if legacy else name, child.read_bytes())
        return archive

    def test_cp949_without_cpg_actual_provider(self):
        shp = shapefile(self.root, cpg=False)
        layer, encoding, *_ = self.processor._load_layer_with_best_encoding(str(shp), 'test')
        self.assertEqual(encoding, 'cp949')
        self.assertEqual(next(layer.getFeatures())['LITHONAME'], '화강암 퇴적층 똠')

    def test_utf8_without_cpg(self):
        shp = shapefile(self.root, encoding='UTF-8', cpg=False)
        layer, encoding, *_ = self.processor._load_layer_with_best_encoding(str(shp), 'test')
        self.assertEqual(encoding, 'utf-8')
        self.assertEqual(next(layer.getFeatures())['LITHONAME'], '화강암 퇴적층 똠')

    def test_numeric_cpg_alias_and_wrong_cpg(self):
        shp = shapefile(self.root)
        shp.with_suffix('.cpg').write_text('949')
        self.assertEqual(detect_dbf_encoding(shp)[0], 'cp949')
        shp.with_suffix('.cpg').write_text('UTF-8')
        layer, encoding, *_ = self.processor._load_layer_with_best_encoding(str(shp), 'test')
        self.assertEqual(encoding, 'cp949')
        self.assertEqual(next(layer.getFeatures())['LITHONAME'], '화강암 퇴적층 똠')

    def test_euckr_and_manual_override(self):
        shp = shapefile(self.root, encoding='EUC-KR', text='화강암')
        self.assertEqual(detect_dbf_encoding(shp)[0], 'euc_kr')
        self.assertEqual(detect_dbf_encoding(shp, 'CP949')[0], 'cp949')

    def test_cp949_archive_names_and_nested_zip(self):
        source = self.root / 'source'
        shp = shapefile(source / '한글도엽', name='지질도')
        inner = source / 'nested.zip'
        with zipfile.ZipFile(inner, 'w') as dest:
            for child in shp.parent.iterdir():
                dest.write(child, 'second/' + child.name)
        archive = self.zip_tree(legacy=True)
        layers = self.processor.process_zip(str(archive))
        self.assertEqual(len(layers), 2)
        self.assertEqual({layer.name() for layer in layers}, {'지질도'})
        self.assertEqual(self.processor.last_report['discovered'], 2)

    def test_missing_sidecar_does_not_abort_batch(self):
        source = self.root / 'source'
        broken = shapefile(source, name='a_broken')
        broken.with_suffix('.dbf').unlink()
        shapefile(source, name='z_valid')
        layers = self.processor.process_zip(str(self.zip_tree()))
        self.assertEqual([layer.name() for layer in layers], ['z_valid'])
        self.assertEqual(self.processor.last_report['failed'], ['a_broken.shp'])

    def test_zip_traversal_and_limits(self):
        for name in ('../escape.txt', 'C:/escape.txt', '/escape.txt', 'map/../../escape.txt'):
            archive = self.root / 'bad.zip'
            with zipfile.ZipFile(archive, 'w') as dest:
                dest.writestr(name, b'x')
            with self.assertRaises(ValueError):
                extract_archive(archive, self.root / 'out')
        with zipfile.ZipFile(archive, 'w') as dest:
            dest.writestr('big.txt', b'12345')
        with self.assertRaises(ValueError):
            extract_archive(archive, self.root / 'out', max_bytes=4)
        self.assertFalse((self.root / 'escape.txt').exists())

    def test_native_qml_doctype_and_entity_rejection(self):
        layer = QgsVectorLayer('Point?crs=epsg:5186', 'test', 'memory')
        path = self.root / 'native.qml'
        layer.saveNamedStyle(str(path))
        self.assertEqual(ET.parse(path).getroot().tag, 'qgis')
        for payload in (b'<!DOCTYPE qgis [<!ENTITY x "bad">]><qgis>&x;</qgis>',
                        b'<!DOCTYPE qgis [<!ENTITY x SYSTEM "file:///etc/passwd">]><qgis>&x;</qgis>'):
            with self.assertRaises(ET.ParseError):
                ET.parse(io.BytesIO(payload))

    def test_qml_without_sym_folder_is_applied(self):
        source = self.root / 'source'
        shp = shapefile(source, polygon=True)
        layer = QgsVectorLayer(str(shp), 'map', 'ogr')
        layer.renderer().symbol().setColor(QColor('#123456'))
        layer.saveNamedStyle(str(shp.with_suffix('.QML')))
        layer = None
        layers = self.processor.process_zip(str(self.zip_tree()))
        self.assertEqual(layers[0].renderer().symbol().color().name(), '#123456')

    def test_per_sheet_symbols_and_pattern_scale(self):
        source = self.root / 'source'
        for sheet in ('A', 'B'):
            shp = shapefile(source / sheet, polygon=True, text='화강암')
            image = shp.parent / 'sym' / '화강암.png'
            png(image, 'red' if sheet == 'A' else 'blue')
            layer = QgsVectorLayer(str(shp), sheet, 'ogr')
            raster = QgsRasterFillSymbolLayer()
            raster.setImageFilePath(str(image))
            raster.setWidth(5)
            symbol = QgsFillSymbol()
            symbol.changeSymbolLayer(0, raster)
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
            layer.saveNamedStyle(str(shp.with_suffix('.qml')))
            layer = None
        layers = self.processor.process_zip(str(self.zip_tree()), pattern_scale=2)
        self.assertEqual(len(layers), 2)
        for layer in layers:
            symbol_layer = layer.renderer().symbol().symbolLayer(0)
            self.assertEqual(symbol_layer.width(), 10)
            self.assertTrue(Path(symbol_layer.imageFilePath()).is_file())
            self.assertEqual(Path(symbol_layer.imageFilePath()).parent.parent, Path(layer.source()).parent)
            ZipProcessor.apply_pattern_scale(layer, 3)
            self.assertEqual(symbol_layer.width(), 15)
            ZipProcessor.apply_pattern_scale(layer, 3)
            self.assertEqual(symbol_layer.width(), 15)

    def test_qml_old_prop_mapping(self):
        image = self.root / 'sym' / '화강암.png'
        png(image)
        qml = self.root / 'old.qml'
        qml.write_text('<qgis><renderer-v2 type="categorizedSymbol" attr="TYPE"><categories>'
                       '<category symbol="0" value="Kgr"/></categories><symbols><symbol name="0">'
                       '<layer><prop k="imageFile" v="C:/old/화강암.png"/></layer></symbol></symbols>'
                       '</renderer-v2></qgis>', encoding='utf-8')
        self.assertEqual(self.processor._parse_qml_mapping(str(qml)), ('TYPE', {'Kgr': '화강암'}))
        raw, normalized = self.processor._build_symbol_index(str(image.parent))
        path, linked, total = self.processor._build_relinked_qml(str(qml), raw, normalized)
        self.assertEqual((linked, total), (1, 1))
        self.assertIn(image.as_posix(), Path(path).read_text())

    def test_config_invalid_sections_do_not_crash(self):
        (self.root / 'plugin_config.json').write_text('{"zip_processor":null,"ui":[],"raster":{"nodata":-9999}}')
        self.assertEqual(load_plugin_config(str(self.root))['zip_processor']['fill_symbol_width'], 50.0)

    def test_dialog_constructs_and_finds_lowercase_fields(self):
        dialog = MainDialog()
        layer = QgsVectorLayer('Polygon?crs=epsg:5186&field=lithoidx:string', 'map', 'memory')
        self.assertEqual(dialog._resolve_vector_export_field(layer), 'lithoidx')
        self.assertEqual(dialog.pattern_scale_spin.value(), 2)
        dialog.close()

    def test_metric_grid_geographic_and_pixel_limit(self):
        extent, crs, width, height = raster_utils.metric_grid(
            QgsRectangle(127.0, 36.0, 127.01, 36.01), QgsCoordinateReferenceSystem('EPSG:4326'), 30)
        self.assertEqual(crs.authid(), 'EPSG:5186')
        self.assertAlmostEqual(extent.width() / width, 30)
        self.assertGreater(width, 1)
        self.assertGreater(height, 1)
        with self.assertRaises(ValueError):
            raster_utils.metric_grid(QgsRectangle(0, 0, 10000, 10000), crs, 1)

    def test_nodata_is_preserved_when_filling_lines(self):
        values = np.full((5, 5), 10, dtype=np.float32)
        values[2, 2] = -9999
        mask = np.zeros((5, 5), dtype=bool)
        mask[1, 1] = True
        result = geochem_utils.fill_linework(values, mask, -9999, 3)
        self.assertEqual(result[2, 2], -9999)
        self.assertEqual(result[1, 1], 10)

    def test_legend_anchors(self):
        for preset in geochem_utils.PRESETS.values():
            rgb = np.array([p.rgb for p in preset.points], dtype=np.uint8)
            result = geochem_utils.interp_rgb_to_value(r=rgb[:, 0], g=rgb[:, 1], b=rgb[:, 2], points=preset.points)
            np.testing.assert_allclose(result, [p.value for p in preset.points], rtol=1e-5)

    def test_categorical_export_tif_and_asc(self):
        import processing
        paths = [shapefile(self.root / 'a', text='Kgr', polygon=True),
                 shapefile(self.root / 'b', text='Qa', polygon=True, field='TYPE')]
        layers = [QgsVectorLayer(str(p), 'litho', 'ogr') for p in paths]
        prepared, codes, crs = raster_utils.categorical_layers(
            layers, lambda layer: MainDialog._resolve_vector_export_field(None, layer))
        self.assertEqual(codes, {'Kgr': 1, 'Qa': 2})
        tif = self.root / 'out.tif'
        processing.run('gdal:rasterize', {'INPUT': prepared[0], 'FIELD': 'KIGAM_ID', 'UNITS': 1,
                       'WIDTH': 10, 'HEIGHT': 10, 'NODATA': -9999, 'DATA_TYPE': 4, 'OUTPUT': str(tif)})
        ds = gdal.Open(str(tif))
        self.assertIn(1, np.unique(ds.ReadAsArray()))
        self.assertTrue(set(np.unique(ds.ReadAsArray())).issubset({-9999, 1}))
        ds = None
        asc = self.root / 'out.asc'
        ds = gdal.Translate(str(asc), str(tif), format='AAIGrid')
        self.assertIsNotNone(ds)
        ds = None
        codebook = raster_utils.write_codebook(asc, codes)
        with open(codebook, encoding='utf-8-sig', newline='') as fp:
            self.assertEqual(list(csv.reader(fp)), [['KIGAM_ID', 'VALUE'], ['1', 'Kgr'], ['2', 'Qa']])

    def test_rgb_export_reprojects_to_requested_crs(self):
        path = self.root / 'rgb.tif'
        ds = gdal.GetDriverByName('GTiff').Create(str(path), 10, 10, 3, gdal.GDT_Byte)
        crs = osr.SpatialReference()
        crs.ImportFromEPSG(4326)
        ds.SetProjection(crs.ExportToWkt())
        ds.SetGeoTransform((127, .001, 0, 36.01, 0, -.001))
        for band in range(1, 4):
            ds.GetRasterBand(band).Fill(100)
        ds = None
        layer = QgsRasterLayer(str(path), 'rgb')
        extent, crs, width, height = raster_utils.metric_grid(layer.extent(), layer.crs(), 30)
        target = self.root / 'projected.tif'
        self.assertTrue(geochem_utils.export_geotiff(layer, str(target), extent, width, height, crs))
        ds = gdal.Open(str(target))
        self.assertAlmostEqual(ds.GetGeoTransform()[1], 30)
        self.assertEqual(ds.RasterXSize, width)
        self.assertIn('5186', ds.GetProjection())
        ds = None

    def test_export_dialog_full_path(self):
        shp = shapefile(self.root, text='Kgr', polygon=True)
        layer = QgsVectorLayer(str(shp), 'Litho', 'ogr')
        QgsProject.instance().addMapLayer(layer)
        dialog = MainDialog()
        output = self.root / 'dialog.asc'
        with patch('kigam.main.QFileDialog.getSaveFileName', return_value=(str(output), 'ASCII Grids (*.asc)')), \
                patch('kigam.main.QMessageBox.information'), patch('kigam.main.QMessageBox.critical') as errors:
            dialog.export_maxent_raster()
            self.assertFalse(errors.called, errors.call_args)
        ds = gdal.Open(str(output))
        self.assertIsNotNone(ds)
        self.assertIn(1, np.unique(ds.ReadAsArray()))
        self.assertTrue(output.with_suffix('.categories.csv').exists())
        ds = None
        dialog.close()

    def test_geochem_dialog_full_path_and_transparency(self):
        path = self.root / 'rgb_alpha.tif'
        ds = gdal.GetDriverByName('GTiff').Create(str(path), 10, 10, 4, gdal.GDT_Byte)
        crs = osr.SpatialReference()
        crs.ImportFromEPSG(5186)
        ds.SetProjection(crs.ExportToWkt())
        ds.SetGeoTransform((200000, 30, 0, 500300, 0, -30))
        for band, value in enumerate((0, 255, 0, 255), 1):
            array = np.full((10, 10), value, dtype=np.uint8)
            if band == 4:
                array[4, 4] = 0
                ds.GetRasterBand(band).SetColorInterpretation(gdal.GCI_AlphaBand)
            ds.GetRasterBand(band).WriteArray(array)
        ds = None
        layer = QgsRasterLayer(str(path), 'geochem')
        QgsProject.instance().addMapLayer(layer)
        iface = MagicMock()
        iface.mapCanvas().extent.return_value = layer.extent()
        iface.mapCanvas().mapSettings().destinationCrs.return_value = layer.crs()
        dialog = MainDialog(iface=iface)
        dialog.wms_layer_combo.setCurrentIndex(dialog.wms_layer_combo.findData(layer.id()))
        output = self.root / 'converted.tif'
        with patch('kigam.main.QFileDialog.getSaveFileName', return_value=(str(output), 'GeoTIFF (*.tif)')), \
                patch('kigam.main.QMessageBox.information'), patch('kigam.main.QMessageBox.critical') as errors:
            dialog.run_geochem_analysis()
            self.assertFalse(errors.called, errors.call_args)
        ds = gdal.Open(str(output))
        self.assertIsNotNone(ds)
        self.assertAlmostEqual(ds.ReadAsArray()[0, 0], 4.5)
        self.assertEqual(ds.ReadAsArray()[4, 4], -9999)
        ds = None
        self.assertTrue(dialog.geochem_btn.isEnabled())
        dialog.close()
