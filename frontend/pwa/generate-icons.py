"""Rasterize the existing favicon's circles into dependency-free PWA PNG icons.

Run from any directory: python3 frontend/pwa/generate-icons.py
The maskable icon uses a solid background and keeps the mark inside its safe area.
"""

from pathlib import Path
import struct
import zlib


def png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def write_icon(size, dest):
    background = (11, 14, 17)
    green = (63, 185, 80)
    rows = bytearray()
    # Four samples per axis smooth the same ring/dot geometry as favicon.svg.
    for y in range(size):
        rows.append(0)
        for x in range(size):
            covered = 0
            for sy in range(4):
                for sx in range(4):
                    dx = (x + (sx + 0.5) / 4) * 32 / size - 16
                    dy = (y + (sy + 0.5) / 4) * 32 / size - 16
                    radius_sq = dx * dx + dy * dy
                    covered += radius_sq <= 1.6**2 or 4.75**2 <= radius_sq <= 7.25**2
            rows.extend(round(b + (g - b) * covered / 16) for b, g in zip(background, green))
    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    dest.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", header)
        + png_chunk(b"IDAT", zlib.compress(rows, 9))
        + png_chunk(b"IEND", b"")
    )


if __name__ == "__main__":
    output = Path(__file__).resolve().parent.parent / "public" / "icons"
    output.mkdir(parents=True, exist_ok=True)
    write_icon(192, output / "icon-192.png")
    write_icon(512, output / "icon-512.png")
    (output / "maskable-512.png").write_bytes((output / "icon-512.png").read_bytes())
