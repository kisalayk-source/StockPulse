"""Faceless voiceover script and a chart PNG for one digest story."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Any

# 5x7 glyphs. Each glyph is seven rows, five bits, most significant bit on the left.
_GLYPHS = {
    " ": "00000,00000,00000,00000,00000,00000,00000",
    "$": "00100,01111,10100,01110,00101,11110,00100",
    ".": "00000,00000,00000,00000,00000,01100,01100",
    "-": "00000,00000,00000,11111,00000,00000,00000",
    "0": "01110,10001,10011,10101,11001,10001,01110",
    "1": "00100,01100,00100,00100,00100,00100,01110",
    "2": "01110,10001,00001,00010,00100,01000,11111",
    "3": "11110,00001,00001,01110,00001,00001,11110",
    "4": "00010,00110,01010,10010,11111,00010,00010",
    "5": "11111,10000,10000,11110,00001,00001,11110",
    "6": "01110,10000,10000,11110,10001,10001,01110",
    "7": "11111,00001,00010,00100,01000,01000,01000",
    "8": "01110,10001,10001,01110,10001,10001,01110",
    "9": "01110,10001,10001,01111,00001,00001,01110",
    "A": "01110,10001,10001,11111,10001,10001,10001",
    "B": "11110,10001,10001,11110,10001,10001,11110",
    "C": "01110,10001,10000,10000,10000,10001,01110",
    "D": "11110,10001,10001,10001,10001,10001,11110",
    "E": "11111,10000,10000,11110,10000,10000,11111",
    "F": "11111,10000,10000,11110,10000,10000,10000",
    "G": "01110,10001,10000,10111,10001,10001,01110",
    "H": "10001,10001,10001,11111,10001,10001,10001",
    "I": "01110,00100,00100,00100,00100,00100,01110",
    "J": "00111,00010,00010,00010,10010,10010,01100",
    "K": "10001,10010,10100,11000,10100,10010,10001",
    "L": "10000,10000,10000,10000,10000,10000,11111",
    "M": "10001,11011,10101,10101,10001,10001,10001",
    "N": "10001,11001,10101,10011,10001,10001,10001",
    "O": "01110,10001,10001,10001,10001,10001,01110",
    "P": "11110,10001,10001,11110,10000,10000,10000",
    "Q": "01110,10001,10001,10001,10101,10010,01101",
    "R": "11110,10001,10001,11110,10100,10010,10001",
    "S": "01111,10000,10000,01110,00001,00001,11110",
    "T": "11111,00100,00100,00100,00100,00100,00100",
    "U": "10001,10001,10001,10001,10001,10001,01110",
    "V": "10001,10001,10001,10001,10001,01010,00100",
    "W": "10001,10001,10001,10101,10101,10101,01010",
    "X": "10001,10001,01010,00100,01010,10001,10001",
    "Y": "10001,10001,01010,00100,00100,00100,00100",
    "Z": "11111,00001,00010,00100,01000,10000,11111",
}


def voiceover_script(story: dict[str, Any]) -> str:
    """Narration only. No host, no camera, no first person."""
    ticker = story.get("ticker") or "the company"
    title = story["title"]
    summary = story["summary"]
    value = float(story.get("value") or 0)
    amount_reason = str(story.get("amount_reason") or "").strip()
    if value <= 0 and amount_reason:
        scale = f"{amount_reason}."
    else:
        scale = f"The reported amount is {_spoken_money(value)}."
    label = _compact_label(story)
    kind = "insider filing" if story.get("kind") == "insider" else "government contract"
    return (
        f"HOOK\n"
        f"{ticker}. {title}.\n\n"
        f"ON SCREEN\n"
        f"{label}\n\n"
        f"FACT\n"
        f"{summary}\n\n"
        f"SCALE\n"
        f"{scale} This is one {kind} from the day.\n\n"
        f"CLOSE\n"
        f"That is the record. This is not investment advice.\n"
    )


def write_story_assets(story: dict[str, Any], directory: Path) -> dict[str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    script_path = directory / "script.txt"
    chart_path = directory / "chart.png"
    script_path.write_text(voiceover_script(story), encoding="utf-8")
    chart_path.write_bytes(chart_png(story))
    return {"script": str(script_path), "chart": str(chart_path)}


def chart_png(story: dict[str, Any], *, width: int = 960, height: int = 540) -> bytes:
    label = _compact_label(story)
    pixels = bytearray(width * height * 3)
    _fill(pixels, width, 0, 0, width, height, (11, 16, 24))
    bar_left, bar_top, bar_width, bar_height = 80, 180, 800, 160
    _fill(pixels, width, bar_left, bar_top, bar_width, bar_height, (24, 36, 52))
    value = float(story.get("value") or 0)
    filled = bar_width if value > 0 else 24
    color = (33, 132, 100) if story.get("kind") == "contract" else (80, 140, 220)
    _fill(pixels, width, bar_left, bar_top, filled, bar_height, color)
    _draw_text(pixels, width, label, 80, 80, scale=4, color=(236, 240, 244))
    _draw_text(pixels, width, (story.get("kind") or "story").upper(), 80, 380, scale=3, color=(160, 174, 192))
    return _encode_png(width, height, pixels)


def _compact_label(story: dict[str, Any]) -> str:
    ticker = (story.get("ticker") or "STORY").upper()
    amount = abs(float(story.get("value") or 0))
    if amount <= 0:
        return f"{ticker} NO $"
    if amount >= 1_000_000_000:
        money = f"${amount / 1_000_000_000:.1f}B"
    elif amount >= 1_000_000:
        money = f"${amount / 1_000_000:.1f}M"
    elif amount >= 1_000:
        money = f"${amount / 1_000:.1f}K"
    else:
        money = f"${amount:.0f}"
    return f"{ticker} {money}"


def _spoken_money(value: float) -> str:
    amount = abs(value)
    if amount >= 1_000_000_000:
        return f"{amount / 1_000_000_000:.1f} billion dollars"
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f} million dollars"
    if amount >= 1_000:
        return f"{amount / 1_000:.1f} thousand dollars"
    return f"{amount:.0f} dollars"


def _fill(pixels: bytearray, width: int, x: int, y: int, w: int, h: int, color: tuple[int, int, int]) -> None:
    height = len(pixels) // (width * 3)
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(width, x + w), min(height, y + h)
    red, green, blue = color
    for row in range(y0, y1):
        start = (row * width + x0) * 3
        for _col in range(x0, x1):
            pixels[start] = red
            pixels[start + 1] = green
            pixels[start + 2] = blue
            start += 3


def _draw_text(
    pixels: bytearray,
    width: int,
    text: str,
    x: int,
    y: int,
    *,
    scale: int,
    color: tuple[int, int, int],
) -> None:
    cursor = x
    for char in text.upper():
        glyph = _GLYPHS.get(char, _GLYPHS[" "])
        rows = glyph.split(",")
        for row_index, bits in enumerate(rows):
            for col_index, bit in enumerate(bits):
                if bit == "1":
                    _fill(pixels, width, cursor + col_index * scale, y + row_index * scale, scale, scale, color)
        cursor += 6 * scale


def _encode_png(width: int, height: int, pixels: bytearray) -> bytes:
    raw = bytearray()
    stride = width * 3
    for row in range(height):
        raw.append(0)
        raw.extend(pixels[row * stride : (row + 1) * stride])

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
