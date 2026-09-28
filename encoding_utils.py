"""Detect DBF encodings from bytes, independently of QGIS/provider defaults."""
import codecs
import struct
from pathlib import Path


def sidecar(path, suffix):
    path = Path(path)
    expected = (path.stem + suffix).casefold()
    return next((p for p in sorted(path.parent.iterdir())
                 if p.is_file() and p.name.casefold() == expected), None)


def canonical_encoding(value):
    value = str(value).strip().lstrip('\ufeff')
    aliases = {'949': 'cp949', '65001': 'utf-8', '51949': 'euc-kr',
               'windows-949': 'cp949', 'ansi 949': 'cp949'}
    try:
        return codecs.lookup(aliases.get(value.casefold(), value)).name
    except LookupError:
        return None


def dbf_samples(path, limit=256):
    """Sample complete character fields across the table, including field names."""
    with open(path, 'rb') as fp:
        header = fp.read(32)
        if len(header) != 32:
            raise ValueError('Truncated DBF header')
        count, header_size, record_size = struct.unpack_from('<IHH', header, 4)
        if header_size < 33 or record_size < 1:
            raise ValueError('Invalid DBF record layout')
        fields, samples, offset = [], [], 1
        while fp.tell() + 32 <= header_size:
            field = fp.read(32)
            if len(field) != 32:
                raise ValueError('Truncated DBF field descriptor')
            name = field[:11].split(b'\0', 1)[0]
            if name:
                samples.append(name)
            length = field[16]
            if field[11:12] == b'C':
                fields.append((offset, length))
            offset += length
        if offset > record_size:
            raise ValueError('DBF fields exceed record size')
        positions = sorted({int(i * (count - 1) / max(1, min(count, limit) - 1))
                            for i in range(min(count, limit))})
        for index in positions:
            fp.seek(header_size + index * record_size)
            record = fp.read(record_size)
            if len(record) != record_size:
                raise ValueError('Truncated DBF record')
            if record[:1] == b'*':
                continue
            for offset, length in fields:
                value = record[offset:offset + length].rstrip(b' \0')
                if value:
                    samples.append(value)
        return samples


def detect_dbf_encoding(shp_path, override=None, candidates=None):
    """Return (encoding, reason). A manual override resolves ambiguous legacy data."""
    if override:
        encoding = canonical_encoding(override)
        if not encoding:
            raise ValueError('Unknown encoding: ' + str(override))
        return encoding, 'manual override'
    dbf = sidecar(shp_path, '.dbf')
    if not dbf:
        raise ValueError('Missing DBF sidecar')
    samples = dbf_samples(dbf)
    cpg = sidecar(shp_path, '.cpg')
    declared = None
    if cpg:
        raw_cpg = cpg.read_bytes()
        try:
            text = raw_cpg.decode('utf-16' if raw_cpg.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
            declared = canonical_encoding(text)
        except UnicodeError:
            pass

    def valid(encoding):
        if not encoding:
            return False
        try:
            for value in samples:
                value.decode(encoding, errors='strict')
            return True
        except UnicodeError:
            return False

    if valid(declared):
        return declared, 'CPG declaration validated against sampled DBF bytes'
    warning = ' (invalid/contradictory CPG ignored)' if cpg else ''
    if valid('utf-8'):
        return 'utf-8', 'strict UTF-8 DBF sample' + warning
    if valid('cp949'):
        return 'cp949', 'strict CP949 DBF sample (includes EUC-KR)' + warning
    for candidate in candidates or []:
        encoding = canonical_encoding(candidate) if candidate else None
        if encoding not in ('utf-8', 'cp949', 'euc_kr') and valid(encoding):
            return encoding, 'configured encoding validated against DBF sample' + warning
    raise ValueError('DBF is not valid UTF-8/CP949; select its encoding explicitly or inspect the source')
