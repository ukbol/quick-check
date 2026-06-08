#!/usr/bin/env python3
"""Generate the PWA app icons (no external image libraries required).

Draws a simple DNA-barcode motif (vertical bars) in the UKBOL palette and
writes assets/icons/icon-192.png and icon-512.png. Re-run only if you want to
regenerate the icons; the PNGs are committed so this isn't part of the normal
data-update flow.
"""

import os
import struct
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(HERE, "assets", "icons")

TEAL = (26, 77, 90)        # #1a4d5a background
LIGHT = (232, 244, 248)    # #e8f4f8 bars
GOLD = (212, 160, 23)      # #d4a017 accent bars

# A fixed "barcode" pattern: (relative_width, kind) where kind 0=gap,1=light,2=gold
PATTERN = [
    (2, 1), (1, 0), (1, 1), (2, 0), (3, 2), (1, 0), (1, 1), (2, 0),
    (1, 1), (1, 0), (2, 2), (1, 0), (3, 1), (1, 0), (1, 1), (2, 0),
    (2, 2), (1, 0), (1, 1), (2, 0), (1, 1),
]


def render(size):
    margin = int(size * 0.16)
    inner = size - 2 * margin
    total_units = sum(w for w, _ in PATTERN)
    unit = inner / total_units

    # Precompute bar colour for each x in the inner region.
    xcolour = [None] * size
    x = margin
    for w, kind in PATTERN:
        x0, x1 = int(round(x)), int(round(x + w * unit))
        col = {0: None, 1: LIGHT, 2: GOLD}[kind]
        for px in range(x0, min(x1, size)):
            xcolour[px] = col
        x += w * unit

    bar_top = margin
    bar_bot = size - margin
    raw = bytearray()
    for y in range(size):
        raw.append(0)  # filter type 0
        in_band = bar_top <= y < bar_bot
        for px in range(size):
            col = xcolour[px] if in_band else None
            r, g, b = col if col else TEAL
            raw += bytes((r, g, b, 255))
    return raw


def png_chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data +
            struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def write_png(path, size):
    raw = render(size)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    png = (b"\x89PNG\r\n\x1a\n" +
           png_chunk(b"IHDR", ihdr) +
           png_chunk(b"IDAT", zlib.compress(bytes(raw), 9)) +
           png_chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    print(f"wrote {os.path.relpath(path, HERE)} ({size}x{size}, {len(png)} bytes)")


def main():
    os.makedirs(ICON_DIR, exist_ok=True)
    for sz in (192, 512):
        write_png(os.path.join(ICON_DIR, f"icon-{sz}.png"), sz)


if __name__ == "__main__":
    main()
