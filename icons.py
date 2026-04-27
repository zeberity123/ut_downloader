"""Procedural icon generator for the dark UI.

Provides:
- Checkbox indicators (PNG files referenced from QSS via image: url(...)).
- Combobox chevron (PNG file).
- Audio-player glyphs (returned as QIcon directly for use on QPushButtons).
"""
import os
import tempfile

from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF


_ICON_DIR = os.path.join(tempfile.gettempdir(), 'ut_download_icons')


def _render_unchecked(size: int = 22) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor("#7aa2f7"))
    pen.setWidthF(2.0)
    p.setPen(pen)
    p.setBrush(QBrush(QColor("#1a1b26")))
    inset = 2
    p.drawRoundedRect(inset, inset, size - 2 * inset, size - 2 * inset, 5, 5)
    p.end()
    return pix


def _render_checked(size: int = 22) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    inset = 2
    # filled body
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor("#7aa2f7")))
    p.drawRoundedRect(inset, inset, size - 2 * inset, size - 2 * inset, 5, 5)
    # checkmark
    pen = QPen(QColor("#16161e"))
    pen.setWidthF(2.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    s = size
    p.drawLine(int(s * 0.27), int(s * 0.52), int(s * 0.45), int(s * 0.70))
    p.drawLine(int(s * 0.45), int(s * 0.70), int(s * 0.74), int(s * 0.32))
    p.end()
    return pix


def _render_chevron_down(size: int = 14) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor("#a9b1d6"))
    pen.setWidthF(1.8)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    s = size
    p.drawLine(int(s * 0.25), int(s * 0.40), int(s * 0.50), int(s * 0.65))
    p.drawLine(int(s * 0.50), int(s * 0.65), int(s * 0.75), int(s * 0.40))
    p.end()
    return pix


def _render_player_glyph(kind: str, size: int, color: str) -> QPixmap:
    """Render a clean, monoline player glyph (prev / next / play / pause)."""
    pix = QPixmap(size, size)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.NoPen)
    s = float(size)
    if kind == 'prev':
        bar_w = max(2, int(s / 9))
        bar_h = int(s * 0.55)
        p.drawRoundedRect(int(s * 0.20), int((s - bar_h) / 2), bar_w, bar_h, 1, 1)
        p.drawPolygon(QPolygonF([
            QPointF(s * 0.78, s * 0.20),
            QPointF(s * 0.78, s * 0.80),
            QPointF(s * 0.34, s * 0.50),
        ]))
    elif kind == 'next':
        bar_w = max(2, int(s / 9))
        bar_h = int(s * 0.55)
        p.drawRoundedRect(int(s * 0.80) - bar_w, int((s - bar_h) / 2),
                          bar_w, bar_h, 1, 1)
        p.drawPolygon(QPolygonF([
            QPointF(s * 0.22, s * 0.20),
            QPointF(s * 0.22, s * 0.80),
            QPointF(s * 0.66, s * 0.50),
        ]))
    elif kind == 'play':
        # slightly off-center triangle, visually balanced
        p.drawPolygon(QPolygonF([
            QPointF(s * 0.32, s * 0.18),
            QPointF(s * 0.32, s * 0.82),
            QPointF(s * 0.80, s * 0.50),
        ]))
    elif kind == 'pause':
        bar_w = int(s * 0.16)
        bar_h = int(s * 0.55)
        gap   = max(2, int(s * 0.10))
        cx = s / 2
        cy = s / 2
        p.drawRoundedRect(int(cx - gap / 2 - bar_w), int(cy - bar_h / 2),
                          bar_w, bar_h, 2, 2)
        p.drawRoundedRect(int(cx + gap / 2),         int(cy - bar_h / 2),
                          bar_w, bar_h, 2, 2)
    p.end()
    return pix


def player_icon(kind: str, size: int, color: str,
                disabled_color: str = None) -> QIcon:
    """Return a QIcon with both Normal and (optionally) Disabled pixmaps."""
    icon = QIcon()
    icon.addPixmap(_render_player_glyph(kind, size, color), QIcon.Normal)
    if disabled_color:
        icon.addPixmap(_render_player_glyph(kind, size, disabled_color),
                       QIcon.Disabled)
    return icon


def _render_download_icon(size: int, color: str) -> QPixmap:
    """Crisp download glyph — round-cap shaft, V-arrowhead, base tray."""
    pix = QPixmap(size, size)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    s = float(size)
    pen = QPen(QColor(color))
    pen.setWidthF(max(2.0, s * 0.13))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    cx = s / 2
    # vertical shaft
    p.drawLine(QPointF(cx, s * 0.18), QPointF(cx, s * 0.62))
    # arrow head (chevron pointing down)
    p.drawLine(QPointF(s * 0.27, s * 0.46), QPointF(cx, s * 0.72))
    p.drawLine(QPointF(s * 0.73, s * 0.46), QPointF(cx, s * 0.72))
    # base tray
    p.drawLine(QPointF(s * 0.20, s * 0.86), QPointF(s * 0.80, s * 0.86))

    p.end()
    return pix


def download_icon(size: int = 22, color: str = "#16161e") -> QIcon:
    return QIcon(_render_download_icon(size, color))


def ensure_checkbox_icons() -> dict:
    """Write PNG icons to a temp folder and return their absolute paths.

    Returns dict {'unchecked', 'checked', 'chevron_down', 'download_green'}.
    Paths use forward slashes (safe inside QSS url(...)).
    """
    os.makedirs(_ICON_DIR, exist_ok=True)
    paths = {
        'unchecked':       os.path.join(_ICON_DIR, 'cbox_unchecked.png'),
        'checked':         os.path.join(_ICON_DIR, 'cbox_checked.png'),
        'chevron_down':    os.path.join(_ICON_DIR, 'chevron_down.png'),
        'download_green':  os.path.join(_ICON_DIR, 'download_green.png'),
    }
    if not os.path.isfile(paths['unchecked']):
        _render_unchecked().save(paths['unchecked'])
    if not os.path.isfile(paths['checked']):
        _render_checked().save(paths['checked'])
    if not os.path.isfile(paths['chevron_down']):
        _render_chevron_down().save(paths['chevron_down'])
    # Always re-render the download icon — color may change if the palette is tweaked.
    _render_download_icon(18, "#9ece6a").save(paths['download_green'])
    return {k: v.replace('\\', '/') for k, v in paths.items()}
