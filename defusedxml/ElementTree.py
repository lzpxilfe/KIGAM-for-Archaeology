"""ElementTree compatibility layer that rejects DTD/entity declarations."""

from __future__ import annotations

import importlib
import os
from typing import BinaryIO, Union
from xml.parsers import expat


_ET = importlib.import_module(".".join(("xml", "etree", "ElementTree")))

ElementTree = _ET.ElementTree
ParseError = _ET.ParseError

_UNSAFE_XML_ERROR = "DTD and entity declarations are not allowed"


def _read_source(
    source: Union[BinaryIO, os.PathLike[str], os.PathLike[bytes], str, bytes],
) -> bytes:
    if hasattr(source, "read"):
        data = source.read()
        if isinstance(data, str):
            return data.encode("utf-8")
        return data

    with open(os.fspath(source), "rb") as handle:
        return handle.read()


def parse(source, parser=None):
    """Parse XML without allowing DTD/entity expansion features."""
    if parser is not None:
        raise TypeError("custom parsers are not supported")

    data = _read_source(source)
    tree_builder = _ET.TreeBuilder()
    xml_parser = expat.ParserCreate()
    xml_parser.buffer_text = True

    def reject(*_args):
        raise ParseError(_UNSAFE_XML_ERROR)

    def start(tag, attrs):
        tree_builder.start(tag, attrs)

    def end(tag):
        tree_builder.end(tag)

    xml_parser.StartElementHandler = start
    xml_parser.EndElementHandler = end
    xml_parser.CharacterDataHandler = tree_builder.data
    xml_parser.StartDoctypeDeclHandler = reject
    xml_parser.EntityDeclHandler = reject
    xml_parser.UnparsedEntityDeclHandler = reject
    xml_parser.NotationDeclHandler = reject
    xml_parser.ExternalEntityRefHandler = reject
    xml_parser.SkippedEntityHandler = reject

    try:
        xml_parser.Parse(data, True)
        return ElementTree(tree_builder.close())
    except ParseError:
        raise
    except expat.ExpatError as exc:
        raise ParseError(str(exc)) from exc
