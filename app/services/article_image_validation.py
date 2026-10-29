"""Constrained SVG and PNG validation. Untrusted SVG is never injected as HTML."""

import math
import re
import struct
import zlib

from lxml import etree

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
XML_NS = "http://www.w3.org/XML/1998/namespace"
SVG_TAGS = set("svg g defs symbol use path rect circle ellipse line polyline polygon text tspan textPath title desc clipPath mask marker linearGradient radialGradient stop style a switch".split())
SVG_ATTRS = set("id class version width height viewBox preserveAspectRatio x y x1 y1 x2 y2 dx dy cx cy r rx ry d points transform fill fill-opacity fill-rule stroke stroke-width stroke-opacity stroke-linecap stroke-linejoin stroke-miterlimit stroke-dasharray stroke-dashoffset opacity color font-family font-size font-weight font-style font-variant text-anchor dominant-baseline alignment-baseline baseline-shift text-decoration letter-spacing word-spacing writing-mode direction unicode-bidi visibility display overflow clip-path clip-rule mask marker-start marker-mid marker-end markerWidth markerHeight markerUnits refX refY orient gradientUnits gradientTransform spreadMethod offset stop-color stop-opacity fx fy fr href startOffset textLength lengthAdjust style role aria-label aria-labelledby aria-describedby focusable requiredFeatures requiredExtensions systemLanguage".split())
CSS_PROPERTIES = set("fill fill-opacity fill-rule stroke stroke-width stroke-opacity stroke-linecap stroke-linejoin stroke-miterlimit stroke-dasharray stroke-dashoffset opacity color font font-family font-size font-weight font-style font-variant text-anchor dominant-baseline alignment-baseline baseline-shift text-decoration letter-spacing word-spacing writing-mode direction unicode-bidi visibility display overflow clip-path clip-rule mask marker-start marker-mid marker-end stop-color stop-opacity white-space".split())


def _safe_value(value: str) -> None:
    if "/*" in value or "*/" in value or re.search(r"[\\@<>\x00-\x08\x0b\x0c\x0e-\x1f]", value) or re.search(r"expression\s*\(|(?:javascript|vbscript)\s*:", value, re.I):
        raise ValueError("SVG contains unsupported or unsafe styling.")
    without_refs = re.sub(r"url\(\s*(['\"]?)#[A-Za-z_][\w:.-]*\1\s*\)", "", value, flags=re.I)
    if re.search(r"url\s*\(", without_refs, re.I):
        raise ValueError("SVG may only reference resources inside the same image.")


def _css_declarations(source: str) -> None:
    _safe_value(source)
    if any(char in source for char in "{}"):
        raise ValueError("SVG contains unsupported nested styles.")
    for declaration in source.split(";"):
        if not declaration.strip():
            continue
        name, separator, value = declaration.partition(":")
        if not separator or name.strip().lower() not in CSS_PROPERTIES or not value.strip():
            raise ValueError("SVG contains an unsupported CSS property. Export native SVG or PNG.")


def _stylesheet(source: str) -> None:
    _safe_value(source)
    cursor = 0
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", source):
        if source[cursor:match.start()].strip() or not re.fullmatch(r"[\w\s.#*,>+~-]+", match[1]):
            raise ValueError("SVG contains unsupported CSS selectors.")
        _css_declarations(match[2])
        cursor = match.end()
    if source[cursor:].strip():
        raise ValueError("SVG contains unsupported styles. Export native SVG or PNG.")


def _length(value: str | None, fallback: float) -> float:
    if value is None or value.endswith("%"):
        return fallback
    match = re.fullmatch(r"\s*([+]?(?:\d+(?:\.\d*)?|\.\d+))\s*(px|pt|mm|cm|in)?\s*", value)
    if not match:
        raise ValueError("SVG needs numeric dimensions or a valid viewBox.")
    return float(match[1]) * {None: 1, "px": 1, "pt": 96 / 72, "mm": 96 / 25.4, "cm": 96 / 2.54, "in": 96}[match[2]]


def validate_svg(data: bytes, max_pixels: int) -> bytes:
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", data, re.I) or re.search(br"<\?(?!xml\s)[\s\S]*?\?>", data, re.I):
        raise ValueError("SVG document types, entities and processing instructions are not supported.")
    try:
        root = etree.fromstring(data, parser=etree.XMLParser(
            resolve_entities=False, no_network=True, load_dtd=False,
            remove_comments=True, remove_pis=False, huge_tree=False,
        ))
    except (etree.XMLSyntaxError, ValueError) as exc:
        raise ValueError("The SVG is not valid XML.") from exc
    tree = root.getroottree()
    if tree.docinfo.doctype or tree.xpath("//processing-instruction()"):
        raise ValueError("SVG document types, entities and processing instructions are not supported.")
    if root.tag != f"{{{SVG_NS}}}svg":
        raise ValueError("SVG must have an svg root and the standard SVG namespace.")
    count = 0
    for element in root.iter():
        count += 1
        if count > 50_000 or not isinstance(element.tag, str):
            raise ValueError("SVG is too complex or contains unsupported XML.")
        tag = etree.QName(element)
        if tag.localname.lower() == "foreignobject":
            raise ValueError("SVG HTML labels (foreignObject) are unsupported. In draw.io use Convert Labels to SVG, or export PNG.")
        if tag.namespace != SVG_NS or tag.localname not in SVG_TAGS:
            raise ValueError(f"Unsupported SVG element: {tag.localname}. Export native SVG or PNG.")
        if any(namespace not in {SVG_NS, XLINK_NS, XML_NS} for namespace in element.nsmap.values()):
            raise ValueError("SVG contains an unsupported XML namespace.")
        for attribute, value in element.attrib.items():
            name = etree.QName(attribute)
            if name.localname.lower().startswith("on"):
                raise ValueError("SVG event handlers are not allowed.")
            if name.namespace == XML_NS and name.localname == "space" and value in {"default", "preserve"}:
                continue
            if name.namespace not in {None, XLINK_NS} or name.localname not in SVG_ATTRS or (name.namespace == XLINK_NS and name.localname != "href"):
                raise ValueError(f"Unsupported SVG attribute: {name.localname}.")
            if name.localname == "href" and not re.fullmatch(r"#[A-Za-z_][\w:.-]*", value):
                raise ValueError("SVG links and resources must be internal #id references.")
            _safe_value(value)
            if name.localname == "style":
                _css_declarations(value)
        if tag.localname == "style":
            _stylesheet(element.text or "")
    try:
        box = [float(value) for value in re.split(r"[\s,]+", root.get("viewBox", "0 0 300 150").strip())]
        if len(box) != 4 or not all(math.isfinite(value) for value in box) or box[2] <= 0 or box[3] <= 0:
            raise ValueError()
        width, height = _length(root.get("width"), box[2]), _length(root.get("height"), box[3])
        if not all(math.isfinite(value) and 0 < value <= 32768 for value in (width, height)) or width * height > max_pixels:
            raise ValueError()
    except (ValueError, OverflowError) as exc:
        raise ValueError("SVG dimensions exceed the allowed image size.") from exc
    return etree.tostring(root, encoding="utf-8", xml_declaration=True)


def validate_png(data: bytes, max_pixels: int) -> bytes:
    """Verify all chunk CRCs and bounded scanline decompression, including Adam7."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("The PNG signature is invalid.")
    offset, header, compressed, ended, seen_data, data_closed = 8, None, bytearray(), False, False, False
    palette = False
    while offset < len(data):
        if len(data) - offset < 12:
            raise ValueError("The PNG is truncated.")
        length, kind = struct.unpack(">I4s", data[offset:offset + 8])
        end = offset + 12 + length
        if end > len(data):
            raise ValueError("The PNG is truncated.")
        chunk = data[offset + 8:offset + 8 + length]
        checksum = struct.unpack(">I", data[offset + 8 + length:end])[0]
        if zlib.crc32(kind + chunk) & 0xffffffff != checksum:
            raise ValueError("The PNG contains a corrupt chunk.")
        if header is None and kind != b"IHDR":
            raise ValueError("The PNG header is missing.")
        if kind == b"IHDR":
            if header is not None or length != 13:
                raise ValueError("The PNG header is invalid.")
            header = struct.unpack(">IIBBBBB", chunk)
            width, height, depth, color, compression, filtering, interlace = header
            depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
            if not width or not height or width * height > max_pixels or width > 32768 or height > 32768 or depth not in depths.get(color, set()) or compression or filtering or interlace not in {0, 1}:
                raise ValueError("PNG dimensions or encoding are unsupported.")
        elif kind == b"PLTE":
            if seen_data or not length or length % 3 or length > 768:
                raise ValueError("The PNG palette is invalid.")
            palette = True
        elif kind == b"IDAT":
            if data_closed:
                raise ValueError("PNG image chunks must be contiguous.")
            seen_data = True
            compressed.extend(chunk)
        elif kind == b"IEND":
            if length or not seen_data or end != len(data):
                raise ValueError("The PNG end chunk is invalid.")
            ended = True
            break
        else:
            if seen_data:
                data_closed = True
            if kind in {b"acTL", b"fcTL", b"fdAT"} or not kind[0] & 32:
                raise ValueError("Animated PNG or unknown critical PNG chunks are unsupported.")
        offset = end
    if not ended or header is None or (header[3] == 3 and not palette):
        raise ValueError("The PNG is incomplete.")
    width, height, depth, color, _, _, interlace = header
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    passes = [(0, 0, 1, 1)] if not interlace else [(0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2)]
    scanlines = []
    for x, y, step_x, step_y in passes:
        columns = max(0, (width - x + step_x - 1) // step_x)
        rows = max(0, (height - y + step_y - 1) // step_y)
        if columns and rows:
            scanlines.append((rows, 1 + (columns * channels * depth + 7) // 8))
    expected = sum(rows * row_size for rows, row_size in scanlines)
    try:
        decoder = zlib.decompressobj()
        pixels = decoder.decompress(compressed, expected + 1)
        if len(pixels) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError("PNG pixel data has an invalid size.")
        cursor = 0
        for rows, row_size in scanlines:
            for _ in range(rows):
                if pixels[cursor] > 4:
                    raise ValueError("PNG contains an invalid scanline filter.")
                cursor += row_size
    except zlib.error as exc:
        raise ValueError("PNG pixel data is corrupt.") from exc
    return data
