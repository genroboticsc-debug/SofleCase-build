from pathlib import Path
import ctypes
import struct
import json
import traceback
from ctypes import wintypes

OUT = Path("lid_gdi_svg_results")
OUT.mkdir(exist_ok=True)
CHARS = [c for c in "Logic Analyzer" if c != " "]


class FIXED(ctypes.Structure):
    _fields_ = [("fract", wintypes.WORD), ("value", ctypes.c_short)]


class MAT2(ctypes.Structure):
    _fields_ = [("eM11", FIXED), ("eM12", FIXED), ("eM21", FIXED), ("eM22", FIXED)]


class GLYPHMETRICS(ctypes.Structure):
    _fields_ = [
        ("gmBlackBoxX", wintypes.UINT),
        ("gmBlackBoxY", wintypes.UINT),
        ("gmptGlyphOrigin", wintypes.POINT),
        ("gmCellIncX", ctypes.c_short),
        ("gmCellIncY", ctypes.c_short),
    ]


def fixed_value(value, fraction):
    return float(value) + float(fraction) / 65536.0


def pointfx(data, offset):
    fract_x, value_x, fract_y, value_y = struct.unpack_from("<HhHh", data, offset)
    return fixed_value(value_x, fract_x), fixed_value(value_y, fract_y)


def fmt(value):
    return f"{value:.9f}"


def glyph_svg(face_name, char, weight, unhinted, target):
    gdi = ctypes.WinDLL("gdi32", use_last_error=True)
    create_font = gdi.CreateFontW
    create_font.restype = wintypes.HANDLE
    create_font.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPCWSTR,
    ]
    create_dc = gdi.CreateCompatibleDC
    create_dc.restype = wintypes.HDC
    create_dc.argtypes = [wintypes.HDC]
    select_object = gdi.SelectObject
    select_object.restype = wintypes.HANDLE
    select_object.argtypes = [wintypes.HDC, wintypes.HANDLE]
    delete_object = gdi.DeleteObject
    delete_object.argtypes = [wintypes.HANDLE]
    delete_dc = gdi.DeleteDC
    delete_dc.argtypes = [wintypes.HDC]
    get_outline = gdi.GetGlyphOutlineW
    get_outline.restype = wintypes.DWORD
    get_outline.argtypes = [
        wintypes.HDC,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.POINTER(GLYPHMETRICS),
        wintypes.DWORD,
        wintypes.LPVOID,
        ctypes.POINTER(MAT2),
    ]
    get_face = gdi.GetTextFaceW
    get_face.restype = ctypes.c_int
    get_face.argtypes = [wintypes.HDC, ctypes.c_int, wintypes.LPWSTR]

    hdc = create_dc(None)
    font = create_font(-2048, 0, 0, 0, weight, 0, 0, 0, 1, 7, 0, 4, 0, face_name)
    if not font:
        raise ctypes.WinError(ctypes.get_last_error())
    old = select_object(hdc, font)
    resolved_name = ctypes.create_unicode_buffer(256)
    get_face(hdc, 256, resolved_name)
    matrix = MAT2(FIXED(0, 1), FIXED(0, 0), FIXED(0, 0), FIXED(0, 1))
    metrics = GLYPHMETRICS()
    flags = 2 | (0x0100 if unhinted else 0)
    size = get_outline(hdc, ord(char), flags, ctypes.byref(metrics), 0, None, ctypes.byref(matrix))
    if size == 0xFFFFFFFF:
        raise ctypes.WinError(ctypes.get_last_error())
    buffer = (ctypes.c_ubyte * size)()
    received = get_outline(
        hdc,
        ord(char),
        flags,
        ctypes.byref(metrics),
        size,
        ctypes.byref(buffer),
        ctypes.byref(matrix),
    )
    if received == 0xFFFFFFFF:
        raise ctypes.WinError(ctypes.get_last_error())
    data = bytes(buffer)
    select_object(hdc, old)
    delete_object(font)
    delete_dc(hdc)

    commands = []
    offset = 0
    while offset < len(data):
        block_size, polygon_type = struct.unpack_from("<II", data, offset)
        if block_size <= 16 or offset + block_size > len(data):
            raise RuntimeError(f"invalid polygon block {block_size} at {offset}")
        start = pointfx(data, offset + 8)
        commands.append(f"M {fmt(start[0])} {fmt(start[1])}")
        position = offset + 16
        while position < offset + block_size:
            primitive, count = struct.unpack_from("<HH", data, position)
            position += 4
            points = [pointfx(data, position + 8 * index) for index in range(count)]
            position += 8 * count
            if primitive == 1:
                for point in points:
                    commands.append(f"L {fmt(point[0])} {fmt(point[1])}")
            elif primitive == 2:
                for index in range(count - 1):
                    control = points[index]
                    endpoint = (
                        ((points[index][0] + points[index + 1][0]) / 2, (points[index][1] + points[index + 1][1]) / 2)
                        if index < count - 2
                        else points[index + 1]
                    )
                    commands.append(
                        f"Q {fmt(control[0])} {fmt(control[1])} {fmt(endpoint[0])} {fmt(endpoint[1])}"
                    )
            elif primitive == 3:
                if count % 3:
                    raise RuntimeError("invalid cubic spline point count")
                for index in range(0, count, 3):
                    first, second, endpoint = points[index : index + 3]
                    commands.append(
                        "C "
                        + " ".join(
                            map(
                                fmt,
                                [first[0], first[1], second[0], second[1], endpoint[0], endpoint[1]],
                            )
                        )
                    )
            else:
                raise RuntimeError(f"unknown primitive {primitive}")
        commands.append("Z")
        offset += block_size

    target.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" overflow="visible"><path fill="black" fill-rule="evenodd" d="'
        + " ".join(commands)
        + '"/></svg>',
        encoding="utf-8",
    )
    return resolved_name.value, {
        "black_box": [metrics.gmBlackBoxX, metrics.gmBlackBoxY],
        "origin": [metrics.gmptGlyphOrigin.x, metrics.gmptGlyphOrigin.y],
        "advance": [metrics.gmCellIncX, metrics.gmCellIncY],
    }


rows = []
try:
    for unhinted in (False, True):
        for weight in range(350, 751, 5):
            directory = OUT / f"w{weight}_{'u' if unhinted else 'h'}"
            directory.mkdir(exist_ok=True)
            resolved_faces = set()
            metrics = []
            for index, char in enumerate(CHARS):
                face, glyph_metrics = glyph_svg(
                    "Century Gothic",
                    char,
                    weight,
                    unhinted,
                    directory / f"g{index:02d}_{ord(char):04x}.svg",
                )
                resolved_faces.add(face)
                metrics.append(glyph_metrics)
            row = {
                "weight": weight,
                "unhinted": unhinted,
                "resolved_faces": sorted(resolved_faces),
                "metrics": metrics,
            }
            rows.append(row)
            print(json.dumps(row), flush=True)
except Exception:
    (OUT / "traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
    raise

(OUT / "manifest.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
