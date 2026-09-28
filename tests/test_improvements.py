import io
import struct
import tempfile
import unittest
from pathlib import Path
import zipfile
import zlib

from qgis.core import (
    Qgis, QgsProject, QgsVectorLayer, QgsRasterFillSymbolLayer, QgsRasterMarkerSymbolLayer,
    QgsFillSymbol, QgsMarkerSymbol, QgsSingleSymbolRenderer, QgsCategorizedSymbolRenderer,
    QgsRendererCategory, QgsProperty, QgsSymbolLayer, QgsRectangle, QgsCoordinateReferenceSystem,
    QgsMapSettings, QgsMapRendererParallelJob,
)
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QImage, QColor, QPainter, QPen
from qgis.PyQt.QtWidgets import QApplication
from kigam.archive_utils import extract_archive, member_name, ExtractionLimitError
from kigam.zip_processor import ZipProcessor
from kigam.pattern_utils import scale_patterns
from kigam.pattern_preview import PatternPreviewDialog
from test_regressions import shapefile, png


class ImprovementsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kigam_improved_', ignore_cleanup_errors=True)
        self.root = Path(self.temp.name)
        self.processor = ZipProcessor(extract_root=str(self.root / 'extracted'))

    def tearDown(self):
        QgsProject.instance().removeAllMapLayers()
        QApplication.processEvents()
        self.temp.cleanup()

    def raster_symbol(self, image, width=5, height=0):
        raster = QgsRasterFillSymbolLayer()
        raster.setImageFilePath(str(image))
        raster.setWidth(width)
        raster.setHeight(height)
        symbol = QgsFillSymbol()
        symbol.changeSymbolLayer(0, raster)
        return symbol

    def pattern_layer(self, width=5, height=0):
        image = self.root / 'tile.png'
        png(image)
        shp = shapefile(self.root, polygon=True)
        layer = QgsVectorLayer(str(shp), 'Litho', 'ogr')
        layer.setRenderer(QgsSingleSymbolRenderer(self.raster_symbol(image, width, height)))
        return layer

    def test_partial_qml_preserves_categories_and_valid_symbols(self):
        shp = shapefile(self.root, polygon=True)
        image = self.root / 'sym' / 'Kgr.png'
        png(image)
        layer = QgsVectorLayer(str(shp), 'Litho', 'ogr')
        layer.setRenderer(QgsCategorizedSymbolRenderer('LITHONAME', [
            QgsRendererCategory('Kgr', self.raster_symbol(image), '원래 범례 A'),
            QgsRendererCategory('Qa', self.raster_symbol(self.root / 'missing.png'), '원래 범례 B'),
        ]))
        qml = shp.with_suffix('.qml')
        layer.saveNamedStyle(str(qml))
        self.processor.apply_sym_styling(layer, str(image.parent), str(qml))
        renderer = layer.renderer()
        self.assertIsInstance(renderer, QgsCategorizedSymbolRenderer)
        categories = renderer.categories()
        self.assertEqual([c.label() for c in categories], ['원래 범례 A', '원래 범례 B'])
        self.assertIsInstance(categories[0].symbol().symbolLayer(0), QgsRasterFillSymbolLayer)
        self.assertEqual(categories[1].symbol().symbolLayer(0).layerType(), 'SimpleFill')
        self.assertTrue(self.processor.last_report['warnings'])

    def test_relative_qml_image_without_sym_directory(self):
        shp = shapefile(self.root, polygon=True)
        image = self.root / 'textures' / 'tile.png'
        png(image)
        layer = QgsVectorLayer(str(shp), 'Litho', 'ogr')
        layer.setRenderer(QgsSingleSymbolRenderer(self.raster_symbol(image)))
        qml = shp.with_suffix('.qml')
        layer.saveNamedStyle(str(qml))
        from kigam.defusedxml import ElementTree as ET
        tree = ET.parse(qml)
        for prop, key in self.processor._image_properties(tree.getroot()):
            prop.set(key, './textures/tile.png')
        tree.write(str(qml), encoding='utf-8')
        self.processor.apply_sym_styling(layer, None, str(qml))
        symbol_layer = layer.renderer().symbol().symbolLayer(0)
        self.assertIsInstance(symbol_layer, QgsRasterFillSymbolLayer)
        self.assertEqual(Path(symbol_layer.imageFilePath()).resolve(), image.resolve())

    def test_broken_marker_is_replaced(self):
        shp = shapefile(self.root)
        layer = QgsVectorLayer(str(shp), 'Point', 'ogr')
        symbol = QgsMarkerSymbol()
        symbol.changeSymbolLayer(0, QgsRasterMarkerSymbolLayer(str(self.root / 'missing.png')))
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        self.assertEqual(self.processor._repair_missing_images(layer), 1)
        self.assertEqual(layer.renderer().symbol().symbolLayer(0).layerType(), 'SimpleMarker')

    def test_style_replacement_rebases_pattern_scale(self):
        layer = self.pattern_layer()
        scale_patterns(layer, 2)
        layer.renderer().symbol().symbolLayer(0).setWidth(7)
        scale_patterns(layer, 3)
        self.assertEqual(layer.renderer().symbol().symbolLayer(0).width(), 21)
        scale_patterns(layer, 1)
        self.assertEqual(layer.renderer().symbol().symbolLayer(0).width(), 7)

    def test_intrinsic_size_and_original_units_are_restored(self):
        layer = self.pattern_layer(0, 0)
        symbol_layer = layer.renderer().symbol().symbolLayer(0)
        original_unit = symbol_layer.sizeUnit()
        scale_patterns(layer, 2)
        self.assertEqual(symbol_layer.width(), 32)
        self.assertEqual(symbol_layer.sizeUnit(), Qgis.RenderUnit.Pixels)
        scale_patterns(layer, 3)
        self.assertEqual(symbol_layer.width(), 48)
        scale_patterns(layer, 1)
        self.assertEqual((symbol_layer.width(), symbol_layer.height()), (0, 0))
        self.assertEqual(symbol_layer.sizeUnit(), original_unit)

    def test_non_square_and_cloned_pattern_baselines(self):
        layer = self.pattern_layer(5, 3)
        scale_patterns(layer, 2)
        clone = layer.clone()
        scale_patterns(clone, 3)
        clone_symbol = clone.renderer().symbol().symbolLayer(0)
        self.assertEqual((clone_symbol.width(), clone_symbol.height()), (15, 9))
        self.assertEqual(layer.renderer().symbol().symbolLayer(0).width(), 10)

    def test_data_defined_size_is_preserved_and_reported(self):
        layer = self.pattern_layer()
        raster = layer.renderer().symbol().symbolLayer(0)
        raster.setDataDefinedProperty(QgsSymbolLayer.Property.Width, QgsProperty.fromExpression('10 + 2'))
        report = scale_patterns(layer, 2)
        self.assertEqual(report, {'changed': 0, 'skipped': 1})
        self.assertEqual(raster.width(), 5)

    def test_invalid_pattern_multiplier_changes_nothing(self):
        layer = self.pattern_layer()
        for value in (float('nan'), float('inf'), 0, 7):
            with self.assertRaises(ValueError):
                scale_patterns(layer, value)
        self.assertEqual(layer.renderer().symbol().symbolLayer(0).width(), 5)

    def test_damaged_saved_pattern_metadata_is_ignored(self):
        from kigam.pattern_utils import STATE_KEY
        layer = self.pattern_layer()
        layer.setCustomProperty(STATE_KEY, '{"0/0": "damaged"}')
        self.assertEqual(scale_patterns(layer, 2)['changed'], 1)
        self.assertEqual(layer.renderer().symbol().symbolLayer(0).width(), 10)

    def test_preview_cancel_and_accept_leave_original_untouched(self):
        layer = self.pattern_layer()
        canvas = QgsMapCanvas()
        canvas.setDestinationCrs(layer.crs())
        canvas.setExtent(layer.extent())
        canvas.setLayers([layer])
        for accepted in (False, True):
            dialog = PatternPreviewDialog(canvas, [layer], 2)
            dialog.multiplier_spin.setValue(3)
            self.assertEqual(dialog._clones[layer.id()].renderer().symbol().symbolLayer(0).width(), 15)
            self.assertEqual(layer.renderer().symbol().symbolLayer(0).width(), 5)
            dialog.accept() if accepted else dialog.reject()
            self.assertEqual(layer.renderer().symbol().symbolLayer(0).width(), 5)
            dialog.deleteLater()
        canvas.stopRendering()
        canvas.setLayers([])
        canvas.close()

    def test_rendered_pattern_changes_and_restores(self):
        layer = self.pattern_layer(4)
        tile = QImage(16, 16, QImage.Format.Format_ARGB32)
        tile.fill(QColor('#f4dae5'))
        painter = QPainter(tile)
        painter.setPen(QPen(QColor('#b62c77'), 2))
        painter.drawLine(2, 2, 10, 10)
        painter.end()
        image = self.root / 'striped.png'
        tile.save(str(image))
        layer.renderer().symbol().symbolLayer(0).setImageFilePath(str(image))
        settings = QgsMapSettings()
        settings.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:5186'))
        settings.setExtent(QgsRectangle(layer.extent()))
        settings.setOutputSize(QSize(256, 256))
        settings.setLayers([layer])

        def render():
            job = QgsMapRendererParallelJob(settings)
            job.start()
            job.waitForFinished()
            return job.renderedImage().copy()

        before = render()
        scale_patterns(layer, 2)
        after = render()
        self.assertNotEqual(before, after)
        scale_patterns(layer, 1)
        self.assertEqual(before, render())

    def test_corrupt_nested_zip_keeps_healthy_shapefile(self):
        source = self.root / 'source'
        shapefile(source)
        archive = self.root / 'mixed.zip'
        with zipfile.ZipFile(archive, 'w') as dest:
            for path in source.iterdir():
                dest.write(path, path.name)
            dest.writestr('broken.zip', b'not a zip')
        layers = self.processor.process_zip(str(archive))
        self.assertEqual(len(layers), 1)
        self.assertTrue(any('broken.zip' in msg for msg in self.processor.last_report['warnings']))

    def test_nested_traversal_isolated_and_global_budget_enforced(self):
        child = io.BytesIO()
        with zipfile.ZipFile(child, 'w') as archive:
            archive.writestr('../escape.txt', 'bad')
        outer = self.root / 'outer.zip'
        with zipfile.ZipFile(outer, 'w') as archive:
            archive.writestr('safe.txt', 'safe')
            archive.writestr('child.zip', child.getvalue())
        out = self.root / 'out'
        report = extract_archive(outer, out)
        self.assertEqual((out / 'safe.txt').read_text(), 'safe')
        self.assertTrue(report['warnings'])
        self.assertFalse((self.root / 'escape.txt').exists())
        with self.assertRaises(ExtractionLimitError):
            extract_archive(outer, self.root / 'limited', max_bytes=1)

    def test_dot_prefixed_zip_paths_and_reserved_names(self):
        archive = self.root / 'dots.zip'
        with zipfile.ZipFile(archive, 'w') as dest:
            dest.writestr('./maps/map.txt', 'valid')
        out = self.root / 'out'
        extract_archive(archive, out)
        self.assertEqual((out / 'maps' / 'map.txt').read_text(), 'valid')
        with zipfile.ZipFile(archive, 'w') as dest:
            dest.writestr('AUX.txt', 'invalid')
        with self.assertRaises(ValueError):
            extract_archive(archive, self.root / 'other')

    def test_invalid_unicode_extra_field_falls_back(self):
        info = zipfile.ZipInfo('test.txt')
        payload = b'\x01' + struct.pack('<I', zlib.crc32(b'test.txt')) + b'\xff'
        info.extra = struct.pack('<HH', 0x7075, len(payload)) + payload
        self.assertEqual(member_name(info), 'test.txt')
