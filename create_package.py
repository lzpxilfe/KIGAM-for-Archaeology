import sys
import zipfile
from pathlib import Path


PLUGIN_DIR_NAME = "KigamGeoDownloader"
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
EXCLUDED_DIR_NAMES = {"__pycache__", ".git"}


def _iter_plugin_files(source_dir: Path):
    for path in sorted(source_dir.rglob("*")):
        if path.is_dir():
            continue
        if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        if path.name.endswith("~"):
            continue
        yield path


def _read_plugin_version(source_dir: Path) -> str:
    metadata_path = source_dir / "metadata.txt"
    if not metadata_path.exists():
        return "dev"

    try:
        for line in metadata_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("version="):
                version = line.split("=", 1)[1].strip()
                if version:
                    return version
    except Exception:
        pass

    return "dev"


def create_plugin_zip(output_path):
    base_dir = Path(__file__).resolve().parent
    source_dir = base_dir / PLUGIN_DIR_NAME
    if not source_dir.exists():
        raise FileNotFoundError(f"Plugin directory not found: {source_dir}")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Creating ZIP package: {output_path}")

    added_count = 0
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for src_path in _iter_plugin_files(source_dir):
            rel_path = src_path.relative_to(source_dir).as_posix()
            arcname = f"{PLUGIN_DIR_NAME}/{rel_path}"
            archive.write(src_path, arcname)
            print(f"  Added: {rel_path}")
            added_count += 1

        license_path = base_dir / "LICENSE"
        if license_path.exists():
            archive.write(license_path, f"{PLUGIN_DIR_NAME}/LICENSE")
            print("  Added: LICENSE")
            added_count += 1

    print(f"ZIP package created successfully ({added_count} file(s)).")


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent
    plugin_version = _read_plugin_version(repo_root / PLUGIN_DIR_NAME)

    if len(sys.argv) > 1:
        output_path = Path(sys.argv[1])
    else:
        output_path = Path.home() / "Desktop" / f"KIGAM_for_Archaeology_v{plugin_version}.zip"

    create_plugin_zip(output_path)
