"""Package the recolored Letter C master into local header and PWA PNG assets."""

from pathlib import Path
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "frontend/public/icons"
BACKGROUND = (230, 241, 232)


def read_rgba(path):
    data = path.read_bytes()
    width, height, depth, color, compression, filtering, interlace = struct.unpack("!2I5B", data[16:29])
    if data[:8] != b"\x89PNG\r\n\x1a\n" or (depth, color, compression, filtering, interlace) != (8, 6, 0, 0, 0):
        raise ValueError("The icon master must be a non-interlaced 8-bit RGBA PNG")
    compressed, offset = bytearray(), 8
    while offset < len(data):
        size = struct.unpack("!I", data[offset:offset + 4])[0]
        if data[offset + 4:offset + 8] == b"IDAT":
            compressed.extend(data[offset + 8:offset + 8 + size])
        offset += size + 12
    raw = zlib.decompress(compressed)
    stride, pixels = width * 4, bytearray()
    previous = bytearray(stride)
    for y in range(height):
        offset = y * (stride + 1)
        kind, row = raw[offset], bytearray(raw[offset + 1:offset + 1 + stride])
        if kind not in range(5):
            raise ValueError("Unknown PNG filter")
        for i in range(stride):
            left = row[i - 4] if i >= 4 else 0
            above, corner = previous[i], previous[i - 4] if i >= 4 else 0
            prediction = left + above - corner
            distances = (abs(prediction - left), abs(prediction - above), abs(prediction - corner))
            paeth = (left, above, corner)[distances.index(min(distances))]
            row[i] = (row[i] + (0, left, above, (left + above) // 2, paeth)[kind]) & 255
        pixels.extend(row)
        previous = row
    return width, height, pixels


def png(size, source, transparent=False):
    width, height, pixels = source
    fraction = 1 if transparent else .78
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            sx = ((x + .5) / size - .5) / fraction + .5
            sy = ((y + .5) / size - .5) / fraction + .5
            if not (0 <= sx < 1 and 0 <= sy < 1):
                rows.extend((0, 0, 0, 0) if transparent else BACKGROUND)
                continue
            # Premultiplied bilinear sampling keeps transparent edges smooth.
            px, py = max(0, sx * width - .5), max(0, sy * height - .5)
            ix, iy = int(px), int(py)
            dx, dy = px - ix, py - iy
            rgba = [0., 0., 0., 0.]
            for ox, oy, weight in ((0, 0, (1-dx)*(1-dy)), (1, 0, dx*(1-dy)),
                                   (0, 1, (1-dx)*dy), (1, 1, dx*dy)):
                index = (min(iy + oy, height - 1) * width + min(ix + ox, width - 1)) * 4
                red, green, blue, alpha = pixels[index:index + 4]
                rgba[3] += alpha * weight
                for channel, value in enumerate((red, green, blue)):
                    rgba[channel] += value * alpha / 255 * weight
            if transparent:
                rows.extend([round(value * 255 / rgba[3]) if rgba[3] else 0 for value in rgba[:3]] + [round(rgba[3])])
            else:
                rows.extend(round(value + background * (1 - rgba[3] / 255))
                            for value, background in zip(rgba[:3], BACKGROUND))
    def chunk(kind, data):
        return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data))
    header = struct.pack("!2I5B", size, size, 8, 6 if transparent else 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")


if __name__ == "__main__":
    source = read_rgba(ROOT / "data/icons/letter-c-master.png")
    ICONS.mkdir(parents=True, exist_ok=True)
    (ICONS / "brand-c.png").write_bytes(png(64, source, transparent=True))
    for size in (180, 192, 512):
        (ICONS / f"icon-{size}.png").write_bytes(png(size, source))
    # The mark occupies less than the central 80% maskable safe-zone diameter.
    (ICONS / "maskable-512.png").write_bytes((ICONS / "icon-512.png").read_bytes())
    print("Packaged Letter C: header, 180/192/512 and maskable icons")
