"""Build a QGIS-installable ZIP with one plugin directory and no development debris."""
import argparse
import configparser
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    '__init__.py', 'main.py', 'zip_processor.py', 'encoding_utils.py', 'archive_utils.py',
    'raster_utils.py', 'geochem_utils.py', 'pattern_utils.py', 'pattern_preview.py', 'plugin_config.py', 'plugin_config.json',
    'metadata.txt', 'icon.png', 'LICENSE', 'README.md', 'CHANGELOG.md', 'CITATION.cff',
    'defusedxml/__init__.py', 'defusedxml/ElementTree.py', 'RELEASE_CHECKLIST.md',
)


def build(output_dir):
    metadata = configparser.ConfigParser()
    metadata.read(ROOT / 'metadata.txt', encoding='utf-8')
    version = metadata['general']['version']
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f'KIGAM_for_Archaeology_v{version}.zip'
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(ROOT / name, 'KigamGeoDownloader/' + name)
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('Invalid release ZIP')
    print(destination)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default=str(ROOT / 'dist'))
    build(parser.parse_args().output_dir)
