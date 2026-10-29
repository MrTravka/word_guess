"""Generate the project's geometric C mark as PNGs using Python's standard library."""

from pathlib import Path
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "frontend/public/icons"
GREEN = (22, 101, 52)
WHITE = (255, 255, 255)


def png(size):
    # Four samples per axis soften the circular mark without a font or external asset.
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            white = 0
            for sy in range(4):
                for sx in range(4):
                    dx = (x + (sx + 0.5) / 4) / size - 0.5
                    dy = (y + (sy + 0.5) / 4) / size - 0.5
                    radius = dx * dx + dy * dy
                    white += 0.15**2 <= radius <= 0.28**2 and not (dx > 0 and abs(dy) < dx)
            rows.extend(round(base + (top - base) * white / 16) for base, top in zip(GREEN, WHITE))
    def chunk(kind, data):
        return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!2I5B", size, size, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")


if __name__ == "__main__":
    ICONS.mkdir(parents=True, exist_ok=True)
    for size in (180, 192, 512):
        (ICONS / f"icon-{size}.png").write_bytes(png(size))
    # The full-bleed icon keeps its entire symbol within the maskable safe zone.
    (ICONS / "maskable-512.png").write_bytes((ICONS / "icon-512.png").read_bytes())
    print("Generated 180/192/512 and maskable icons")
