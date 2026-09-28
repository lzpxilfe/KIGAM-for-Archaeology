"""Run with QGIS's Python (QT_QPA_PLATFORM=offscreen). No user data required."""
import importlib.util
import os
from pathlib import Path
import sys
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from qgis.core import QgsApplication, Qgis

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = Path(os.environ.get('KIGAM_PLUGIN_ROOT', ROOT))
spec = importlib.util.spec_from_file_location('kigam', PLUGIN_ROOT / '__init__.py', submodule_search_locations=[str(PLUGIN_ROOT)])
package = importlib.util.module_from_spec(spec)
sys.modules['kigam'] = package
spec.loader.exec_module(package)
app = QgsApplication([], False)
app.initQgis()
sys.path.insert(0, str(Path(QgsApplication.pkgDataPath()) / 'python' / 'plugins'))
# OSGeo4W keeps processing under the QGIS prefix, alongside python/qgis.
sys.path.insert(0, str(Path(QgsApplication.prefixPath()) / 'python' / 'plugins'))
from processing.core.Processing import Processing  # noqa: E402 -- requires QGIS bootstrap
Processing.initialize()
print('Runtime:', Qgis.QGIS_VERSION, flush=True)
expected_major = os.environ.get('EXPECTED_QGIS_MAJOR')
if expected_major and Qgis.QGIS_VERSION_INT // 10000 != int(expected_major):
    raise RuntimeError('CI container has an unexpected QGIS major version')
suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern='test_*.py')
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
