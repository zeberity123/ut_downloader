"""Generate logo.ico (multi-resolution Windows icon) for ut_download.

Run once: `python generate_logo.py`. Produces logo.ico next to this file.
The file is committed to the project so build.bat can bundle it.
"""
import os
import struct
import sys

from PyQt5.QtCore import Qt, QPointF, QRectF, QBuffer, QByteArray
from PyQt5.QtGui import (
    QBrush, QColor, QImage, QLinearGradient, QPainter, QPen, QPolygonF,
)
from PyQt5.QtWidgets import QApplication


def render_logo(size: int) -> QImage:
    """Render the logo at `size` × `size` as a QImage with alpha."""
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)

    s = float(size)

    # ---- 1. rounded-square base with the app's signature gradient ---------
    grad = QLinearGradient(0, 0, s, s)
    grad.setColorAt(0.00, QColor("#7dcfff"))   # cyan
    grad.setColorAt(0.50, QColor("#7aa2f7"))   # blue
    grad.setColorAt(1.00, QColor("#bb9af7"))   # purple
    p.setBrush(QBrush(grad))
    p.setPen(Qt.NoPen)
    radius = s * 0.22
    p.drawRoundedRect(QRectF(0, 0, s, s), radius, radius)

    # subtle inner highlight at the top — gives a glassy feel
    sheen = QLinearGradient(0, 0, 0, s * 0.50)
    sheen.setColorAt(0.0, QColor(255, 255, 255, 60))
    sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(QBrush(sheen))
    p.drawRoundedRect(QRectF(0, 0, s, s * 0.55), radius, radius)

    # ---- 2. white play disk -------------------------------------------------
    disk_d = s * 0.58
    disk_x = (s - disk_d) / 2
    disk_y = (s - disk_d) / 2
    # soft outer ring
    p.setBrush(QBrush(QColor(255, 255, 255, 60)))
    p.drawEllipse(QRectF(disk_x - s * 0.04, disk_y - s * 0.04,
                         disk_d + s * 0.08, disk_d + s * 0.08))
    # solid disk
    p.setBrush(QBrush(QColor(255, 255, 255, 240)))
    p.drawEllipse(QRectF(disk_x, disk_y, disk_d, disk_d))

    # ---- 3. play triangle inside the disk ----------------------------------
    cx, cy = s / 2, s / 2
    tri_w = s * 0.18
    tri_h = s * 0.22
    poly = QPolygonF([
        QPointF(cx - tri_w * 0.42, cy - tri_h * 0.55),
        QPointF(cx - tri_w * 0.42, cy + tri_h * 0.55),
        QPointF(cx + tri_w * 0.78, cy),
    ])
    p.setBrush(QBrush(QColor("#1a1b26")))
    p.drawPolygon(poly)

    # ---- 4. download badge in the bottom-right corner ----------------------
    # Small dark circle with a white down-arrow — hints at "download".
    if s >= 32:
        badge_d = s * 0.30
        badge_x = s - badge_d - s * 0.06
        badge_y = s - badge_d - s * 0.06
        # outer ring for separation against the gradient
        p.setBrush(QBrush(QColor(255, 255, 255, 140)))
        p.drawEllipse(QRectF(badge_x - s * 0.012, badge_y - s * 0.012,
                             badge_d + s * 0.024, badge_d + s * 0.024))
        # dark fill
        p.setBrush(QBrush(QColor("#1a1b26")))
        p.drawEllipse(QRectF(badge_x, badge_y, badge_d, badge_d))
        # arrow shaft + head
        bcx = badge_x + badge_d / 2
        bcy = badge_y + badge_d / 2
        shaft_w = max(2.0, badge_d * 0.16)
        shaft_top = bcy - badge_d * 0.27
        shaft_bot = bcy + badge_d * 0.05
        pen = QPen(QColor("#c0caf5"))
        pen.setWidthF(shaft_w)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(bcx, shaft_top), QPointF(bcx, shaft_bot))
        # arrowhead (down)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#c0caf5")))
        head_w = badge_d * 0.34
        head_h = badge_d * 0.24
        p.drawPolygon(QPolygonF([
            QPointF(bcx - head_w / 2, bcy + badge_d * 0.04),
            QPointF(bcx + head_w / 2, bcy + badge_d * 0.04),
            QPointF(bcx,               bcy + badge_d * 0.04 + head_h),
        ]))

    p.end()
    return img


def _bmp_dib_entry(img: QImage) -> bytes:
    """Encode `img` as a BMP/DIB icon entry (BITMAPINFOHEADER + XOR + AND).

    This is the format PyInstaller's icon embedder + Windows Explorer
    handle most reliably for EXE icons; PNG-in-ICO entries can fall
    through to the default icon on some shell-renderer paths.
    """
    img = img.convertToFormat(QImage.Format_ARGB32)
    w = img.width()
    h = img.height()

    # XOR mask: 32-bit BGRA, bottom-up rows.
    xor_rows = []
    for y in range(h - 1, -1, -1):
        ptr = img.constScanLine(y)
        # Qt scanlines on ARGB32 are 0xAARRGGBB (little-endian → BGRA bytes).
        # Casting to bytes via sip gives us the raw 4-bytes-per-pixel BGRA row.
        ptr.setsize(w * 4)
        xor_rows.append(bytes(ptr))
    xor_data = b''.join(xor_rows)

    # AND mask: 1-bit-per-pixel transparency, bottom-up, rows padded to 4 bytes.
    row_bytes = ((w + 31) // 32) * 4
    and_rows = []
    for y in range(h - 1, -1, -1):
        row = bytearray(row_bytes)
        for x in range(w):
            alpha = (img.pixel(x, y) >> 24) & 0xFF
            if alpha < 128:                      # treat near-transparent as masked
                row[x // 8] |= 0x80 >> (x % 8)
        and_rows.append(bytes(row))
    and_data = b''.join(and_rows)

    header = struct.pack(
        '<IiiHHIIiiII',
        40,       # biSize
        w,        # biWidth
        h * 2,    # biHeight (doubled — XOR mask + AND mask)
        1,        # biPlanes
        32,       # biBitCount
        0,        # biCompression (BI_RGB)
        0,        # biSizeImage
        0, 0,     # biXPelsPerMeter, biYPelsPerMeter
        0, 0,     # biClrUsed, biClrImportant
    )
    return header + xor_data + and_data


def _png_entry(img: QImage) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def write_ico(out_path: str, sizes=(16, 24, 32, 48, 64, 128, 256)) -> None:
    """Write a multi-resolution ICO. BMP/DIB for ≤128 px (max compatibility
    with the Windows shell + PyInstaller's resource embedder), PNG for the
    256 px entry (where BMP would balloon to ~256 KB)."""
    entries = []
    for sz in sizes:
        img = render_logo(sz)
        if sz >= 256:
            entries.append((sz, _png_entry(img)))
        else:
            entries.append((sz, _bmp_dib_entry(img)))

    # ICONDIR: reserved, type=1 (icon), count
    out = bytearray()
    out += struct.pack('<HHH', 0, 1, len(entries))

    offset = 6 + 16 * len(entries)
    for sz, data in entries:
        # 256 → 0 in the 8-bit width/height fields
        w = 0 if sz >= 256 else sz
        h = 0 if sz >= 256 else sz
        out += struct.pack(
            '<BBBBHHII',
            w, h,
            0,           # color count
            0,           # reserved
            1,           # color planes
            32,          # bpp
            len(data),
            offset,
        )
        offset += len(data)

    for _, data in entries:
        out += data

    with open(out_path, 'wb') as f:
        f.write(out)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, 'logo.ico')
    write_ico(out)
    size = os.path.getsize(out)
    print(f"Wrote: {out}  ({size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
