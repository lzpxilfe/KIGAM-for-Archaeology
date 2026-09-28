"""Korean legacy ZIP names and bounded, traversal-safe nested extraction."""
import os
import re
import shutil
import stat
import struct
import tempfile
import unicodedata
import zipfile
import zlib
from pathlib import Path


class ExtractionLimitError(ValueError):
    """Shared budget exhaustion aborts the complete archive tree."""


def member_name(info):
    if info.flag_bits & 0x800:
        return unicodedata.normalize('NFC', info.filename)
    raw = info.filename.encode('cp437')
    # Info-ZIP Unicode Path extra field takes precedence if its CRC matches.
    extra = info.extra
    while len(extra) >= 4:
        tag, length = struct.unpack_from('<HH', extra)
        payload, extra = extra[4:4 + length], extra[4 + length:]
        if tag == 0x7075 and len(payload) >= 5 and payload[0] == 1:
            if struct.unpack_from('<I', payload, 1)[0] == zlib.crc32(raw):
                try:
                    return unicodedata.normalize('NFC', payload[5:].decode('utf-8'))
                except UnicodeDecodeError:
                    pass  # Ignore corrupt optional metadata and decode the real filename.
    for encoding in ('utf-8', 'cp949'):
        try:
            return unicodedata.normalize('NFC', raw.decode(encoding))
        except UnicodeDecodeError:
            pass
    return info.filename


def extract_archive(zip_path, destination, max_bytes=2 * 1024**3,
                    max_members=50000, max_depth=4):
    """Limits apply to the complete nested archive tree, not each child ZIP."""
    state = {'bytes': 0, 'members': 0, 'warnings': []}
    destination = Path(destination).resolve()

    def extract(source, target, depth):
        nested, seen = [], set()
        with zipfile.ZipFile(source) as archive:
            for info in archive.infolist():
                state['members'] += 1
                state['bytes'] += info.file_size
                if state['members'] > max_members or state['bytes'] > max_bytes:
                    raise ExtractionLimitError('ZIP extraction limit exceeded')
                name = member_name(info).replace('\\', '/')
                raw_parts = name.rstrip('/').split('/')
                parts = [p for p in raw_parts if p not in ('', '.')]
                if not parts and info.is_dir():
                    continue
                if (not parts or name.startswith('/') or '..' in raw_parts
                        or any(re.search(r'[<>:"|?*\x00-\x1f]', p) for p in parts)
                        or any(p.endswith((' ', '.')) for p in parts)
                        or any(re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', p, re.I) for p in parts)):
                    raise ValueError('Unsafe ZIP member: ' + name)
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise ValueError('ZIP symbolic links are unsupported: ' + name)
                path = target.joinpath(*parts).resolve()
                if os.path.commonpath((str(destination), str(path))) != str(destination):
                    raise ValueError('ZIP member escapes extraction directory')
                key = str(path).casefold()
                if key in seen and not info.is_dir():
                    raise ValueError('Duplicate ZIP member after filename decoding: ' + name)
                seen.add(key)
                if info.is_dir() or name.endswith('/'):
                    path.mkdir(parents=True, exist_ok=True)
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as src, open(path, 'xb') as dst:
                    shutil.copyfileobj(src, dst)
                if path.suffix.lower() == '.zip':
                    nested.append(path)
        for path in nested:
            if depth >= max_depth:
                state['warnings'].append(f'{path.relative_to(destination)}: nested ZIP depth limit exceeded; skipped')
                continue
            child = Path(tempfile.mkdtemp(prefix=path.stem + '_', dir=str(path.parent)))
            try:
                extract(path, child, depth + 1)
            except ExtractionLimitError:
                raise
            except Exception as exc:
                # This directory was created above and cannot contain a loaded layer.
                resolved_child = child.resolve()
                if resolved_child == destination or not resolved_child.is_relative_to(destination):
                    raise ValueError('Refusing cleanup outside extraction root') from exc
                shutil.rmtree(resolved_child)
                state['warnings'].append(f'{path.relative_to(destination)}: nested ZIP skipped: {exc}')

    extract(zip_path, destination, 0)
    return state
