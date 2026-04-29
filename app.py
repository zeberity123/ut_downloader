"""ut_download — 유튜브 다운로더 GUI. Made by Daru."""
import os
import shutil
import sys
import tempfile
import webbrowser
from pathlib import Path

from PyQt5.QtCore import (
    Qt, QSize, QTimer, QStringListModel, QUrl, QPoint, QPointF, QRectF, QEvent,
    QObject, QPropertyAnimation, QEasingCurve, QVariantAnimation, pyqtSignal,
)
from PyQt5.QtGui import (
    QBrush, QColor, QFont, QIcon, QPainter, QPen, QPixmap, QPolygonF,
)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QListWidget, QListWidgetItem, QLabel,
    QFileDialog, QInputDialog, QTextEdit, QSplitter,
    QMessageBox, QGroupBox, QProgressBar, QStackedWidget,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QSlider,
    QGraphicsDropShadowEffect,
)

# Fluent widgets — drop-in replacements for the most visible inputs/buttons.
# QPushButton stays for the heavily-styled audio-player buttons; everything else
# migrates so we get Fluent's hover/press animations and toast notifications.
from qfluentwidgets import (
    PushButton, PrimaryPushButton, LineEdit,
    ComboBox, CheckBox, InfoBar, InfoBarPosition,
    IndeterminateProgressRing, ProgressBar,
    setTheme, setThemeColor, Theme,
)

try:
    from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
    _MEDIA_OK = True
except Exception:
    QMediaPlayer = None
    QMediaContent = None
    _MEDIA_OK = False

from downloader import (
    SearchWorker, LoadMoreWorker, FetchInfoWorker, DownloadWorker,
    ThumbnailWorker, SuggestWorker, AudioDownloadWorker,
    UpdateCheckWorker,
)
from icons import player_icon, download_icon, folder_icon
from theme import build_qss
from icons import ensure_checkbox_icons

__version__ = "1.4.8"
APP_TITLE = f"유튜브 다운로더 by Daru  v{__version__}"
DEFAULT_DEST = str(Path.home() / "Downloads")

ICON_RESULTS = QSize(120, 68)   # search-results thumbnail
ICON_QUEUE   = QSize(80, 45)    # queue thumbnail


def _format_dur(seconds: int) -> str:
    if not seconds:
        return "--:--"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _format_ms(ms: int) -> str:
    sec = max(0, int(ms)) // 1000
    m, s = divmod(sec, 60)
    return f"{m:02d}:{s:02d}"


# Sentinel row at the end of search results — shows scroll/loading hints.
SENTINEL_ROLE = Qt.UserRole + 3
SENTINEL_TEXT = {
    'idle':       "↓   스크롤 다운하여 결과 더 보기",
    'loading':    "결과 불러오는 중…",
    'exhausted':  "더 이상 결과가 없습니다",
}


class QueueRenameHintDelegate(QStyledItemDelegate):
    """Paints a clickable '✎ 이름변경' pill at the bottom-right of every queue
    item. The owning list (QueueListWidget) detects clicks on the same hit
    rectangle and triggers inline rename. Item geometry is unchanged."""

    HINT_TEXT     = "✎ 이름변경"
    HINT_FONT_PT  = 9
    HINT_PAD_X    = 8       # gap from item right edge
    HINT_PAD_Y    = 6       # gap from item bottom edge
    HINT_W        = 92      # hit-zone width (must match QueueListWidget HINT_W)
    HINT_H        = 22

    HINT_TEXT_COLOR    = QColor(200, 140, 220)
    HINT_BG_COLOR      = QColor(200, 140, 220, 35)
    HINT_BORDER_COLOR  = QColor(200, 140, 220, 130)

    @classmethod
    def hit_rect_for(cls, item_rect):
        x = item_rect.right() - cls.HINT_W - cls.HINT_PAD_X
        y = item_rect.bottom() - cls.HINT_H - cls.HINT_PAD_Y
        return QRectF(x, y, cls.HINT_W, cls.HINT_H)

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        rect = option.rect
        hit = self.hit_rect_for(rect)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        # filled pill background + border so it reads as a clickable button
        painter.setBrush(QBrush(self.HINT_BG_COLOR))
        painter.setPen(QPen(self.HINT_BORDER_COLOR, 1))
        painter.drawRoundedRect(hit, 6, 6)
        # label
        font = painter.font()
        font.setPointSize(self.HINT_FONT_PT)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(self.HINT_TEXT_COLOR)
        painter.drawText(hit, Qt.AlignCenter, self.HINT_TEXT)
        painter.restore()


class SmoothListWidget(QListWidget):
    """QListWidget with pixel-precise + animated wheel scrolling.

    The default QListWidget jumps by full items on each wheel notch, which
    feels chunky on a long search-results list. We swap to per-pixel scroll
    mode and animate the scrollbar value with an OutCubic easing curve so
    the list glides instead of stepping.
    """
    SCROLL_DURATION = 220   # ms — feels responsive without being jittery
    WHEEL_PIXELS_PER_NOTCH = 0.6   # multiplier on event.angleDelta().y()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollMode(self.ScrollPerPixel)
        self.setHorizontalScrollMode(self.ScrollPerPixel)
        self._scroll_anim = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._scroll_anim.setDuration(self.SCROLL_DURATION)
        self._scroll_anim.setEasingCurve(QEasingCurve.OutCubic)

    def wheelEvent(self, event):
        if event.modifiers():           # let Ctrl/Shift+wheel fall through
            super().wheelEvent(event)
            return
        bar = self.verticalScrollBar()
        # If an animation is in flight, chain off its target so rapid scrolls
        # accumulate rather than fighting each other.
        if self._scroll_anim.state() == QPropertyAnimation.Running:
            cur = self._scroll_anim.endValue()
        else:
            cur = bar.value()
        delta = event.angleDelta().y()
        target = max(bar.minimum(),
                     min(bar.maximum(), cur - int(delta * self.WHEEL_PIXELS_PER_NOTCH)))
        self._scroll_anim.stop()
        self._scroll_anim.setStartValue(bar.value())
        self._scroll_anim.setEndValue(target)
        self._scroll_anim.start()
        event.accept()


class SuggestPopup(QListWidget):
    """Autocomplete dropdown that floats *inside* its parent window.

    Implementation notes — why not Qt.Popup:

    `Qt.Popup` (the natural choice for a dropdown) makes Qt grab mouse and
    keyboard input globally so clicks outside dismiss the popup. That grab
    also blackholes keystrokes from reaching the search input behind it,
    so the user can't type or delete while suggestions are visible.

    Instead we make the popup a regular child widget of the main window
    and `raise_()` it above siblings. Keystrokes flow normally to the
    search input. The owning MainWindow handles click-outside dismissal
    via an application-level event filter.
    """
    item_picked = pyqtSignal(str)

    ROW_HEIGHT = 38       # matches the search bar's 16-px font with comfy padding
    MAX_VISIBLE = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.NoFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setObjectName("suggestPopup")
        self.setStyleSheet("""
            QListWidget#suggestPopup {
                background-color: #1f2335;
                color: #c0caf5;
                border: 1px solid #414868;
                border-radius: 8px;
                padding: 4px;
                font-size: 16px;
                outline: 0;
            }
            QListWidget#suggestPopup::item {
                padding: 8px 14px;
                border-radius: 4px;
                margin: 1px 2px;
                font-size: 16px;
            }
            QListWidget#suggestPopup::item:selected,
            QListWidget#suggestPopup::item:hover {
                background-color: #364a82;
                color: #c0caf5;
            }
        """)
        self.itemClicked.connect(self._pick)
        # subtle drop shadow so the popup reads as floating above the panel
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)
        self.hide()

    def show_below(self, anchor: QWidget, items: list) -> None:
        if not items:
            self.hide()
            return
        if self.parent() is None:
            return
        self.clear()
        self.addItems(items[: self.MAX_VISIBLE * 2])
        rows = min(self.MAX_VISIBLE, self.count())
        h = rows * self.ROW_HEIGHT + 12
        # Position below the anchor in *parent* (window) coordinates.
        anchor_bl = anchor.mapTo(self.parent(), QPoint(0, anchor.height() + 2))
        self.setGeometry(anchor_bl.x(), anchor_bl.y(), anchor.width(), h)
        self.show()
        self.raise_()

    def _pick(self, item: QListWidgetItem) -> None:
        self.item_picked.emit(item.text())
        self.hide()


class JumpSlider(QSlider):
    """QSlider where clicking *anywhere* on the groove jumps directly to that
    position (instead of doing a page-step). Dragging continues to work after
    a click without releasing — feels exactly like a typical media seek bar.
    """
    def _value_for_pos(self, pos) -> int:
        if self.orientation() == Qt.Horizontal:
            length = max(1, self.width())
            coord = max(0, min(length, int(pos.x())))
        else:
            length = max(1, self.height())
            coord = max(0, min(length, int(pos.y())))
        return QStyle.sliderValueFromPosition(
            self.minimum(), self.maximum(), coord, length, False,
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.isEnabled():
            value = self._value_for_pos(event.pos())
            self.setValue(value)
            self.sliderMoved.emit(value)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.LeftButton) and self.isEnabled():
            value = self._value_for_pos(event.pos())
            self.setValue(value)
            self.sliderMoved.emit(value)
            event.accept()
            return
        super().mouseMoveEvent(event)


class AudioPlayerBar(QWidget):
    """Compact audio player bar — prev / play-pause / next + seek + time.

    Drives MainWindow via signals; doesn't own the QMediaPlayer itself.
    """
    prev_clicked = pyqtSignal()
    play_pause_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    seek_requested = pyqtSignal(int)        # ms position
    volume_changed = pyqtSignal(int)        # 0..100

    # Glyph palette
    _CTRL_COLOR     = "#c0caf5"
    _CTRL_DISABLED  = "#565f89"
    _PLAY_COLOR     = "#16161e"
    _PLAY_DISABLED  = "#565f89"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("audioPlayerBar")
        self.setFixedHeight(76)

        h = QHBoxLayout(self)
        h.setContentsMargins(12, 8, 14, 8)
        h.setSpacing(10)

        # ---- prev / next: 38×38, custom-painted glyph ---------------------
        self.prev_btn = QPushButton()
        self.prev_btn.setObjectName("playerCtrl")
        self.prev_btn.setFixedSize(38, 38)
        self.prev_btn.setIcon(player_icon('prev', 22, self._CTRL_COLOR,
                                          self._CTRL_DISABLED))
        self.prev_btn.setIconSize(QSize(22, 22))
        self.prev_btn.setToolTip("이전 결과")
        self.prev_btn.clicked.connect(self.prev_clicked.emit)

        # ---- play: 50×50, gradient + soft glow ---------------------------
        self._play_icon  = player_icon('play',  20, self._PLAY_COLOR,
                                       self._PLAY_DISABLED)
        self._pause_icon = player_icon('pause', 20, self._PLAY_COLOR,
                                       self._PLAY_DISABLED)
        self.play_btn = QPushButton()
        self.play_btn.setObjectName("playerPlay")
        self.play_btn.setFixedSize(50, 50)
        self.play_btn.setIcon(self._play_icon)
        self.play_btn.setIconSize(QSize(20, 20))
        self.play_btn.clicked.connect(self.play_pause_clicked.emit)
        # subtle outer glow — fancier than a flat circle
        glow = QGraphicsDropShadowEffect(self.play_btn)
        glow.setBlurRadius(22)
        glow.setColor(QColor(122, 162, 247, 110))
        glow.setOffset(0, 0)
        self.play_btn.setGraphicsEffect(glow)

        self.next_btn = QPushButton()
        self.next_btn.setObjectName("playerCtrl")
        self.next_btn.setFixedSize(38, 38)
        self.next_btn.setIcon(player_icon('next', 22, self._CTRL_COLOR,
                                          self._CTRL_DISABLED))
        self.next_btn.setIconSize(QSize(22, 22))
        self.next_btn.setToolTip("다음 결과")
        self.next_btn.clicked.connect(self.next_clicked.emit)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("playerTime")
        self.time_label.setFixedWidth(132)   # widened so 14 px monospace fits
        self.time_label.setAlignment(Qt.AlignCenter)

        self.seek_bar = JumpSlider(Qt.Horizontal)
        self.seek_bar.setEnabled(False)
        self.seek_bar.setRange(0, 0)
        self.seek_bar.sliderMoved.connect(self.seek_requested.emit)

        # Autoplay toggle — off by default. When OFF, playback simply stops
        # at end-of-media; when ON, MainWindow auto-advances to the next row.
        self.autoplay_cb = CheckBox("자동재생")
        self.autoplay_cb.setObjectName("autoplayCb")
        self.autoplay_cb.setChecked(False)
        self.autoplay_cb.setToolTip("재생이 끝나면 다음 영상 이어서 재생")
        # Bump the label past Fluent's class-level font rule by appending
        # a higher-cascade widget-instance stylesheet.
        prev = self.autoplay_cb.styleSheet() or ""
        self.autoplay_cb.setStyleSheet(
            prev + "\nCheckBox, QCheckBox { font-size: 14px; font-weight: 600; }"
        )

        # Vertical volume slider next to autoplay — picks up the same paint
        # as the horizontal seek bar from the global QSS (vertical variant).
        self.volume_slider = QSlider(Qt.Vertical)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(75)
        # Qt vertical default: top = min, bottom = max.
        self.volume_slider.setInvertedAppearance(False)
        self.volume_slider.setFixedSize(22, 56)
        self.volume_slider.setToolTip("볼륨")
        self.volume_slider.setCursor(Qt.PointingHandCursor)
        self.volume_slider.valueChanged.connect(self.volume_changed.emit)

        # Small speaker glyph above the slider (replaces the "VOL" caption).
        self._vol_glyph = QLabel("🔊")
        self._vol_glyph.setAlignment(Qt.AlignCenter)
        self._vol_glyph.setStyleSheet("color:#a9b1d6;font-size:13px;padding:0;")

        # Speaker glyph on the LEFT of the slider, vertically centered.
        vol_row = QHBoxLayout()
        vol_row.setContentsMargins(0, 0, 0, 0)
        vol_row.setSpacing(4)
        vol_row.addWidget(self._vol_glyph, 0, Qt.AlignVCenter)
        vol_row.addWidget(self.volume_slider, 0, Qt.AlignVCenter)

        h.addWidget(self.prev_btn)
        h.addWidget(self.play_btn)
        h.addWidget(self.next_btn)
        h.addSpacing(4)
        h.addWidget(self.time_label)
        h.addWidget(self.seek_bar, 1)
        h.addSpacing(4)
        h.addWidget(self.autoplay_cb)
        h.addSpacing(6)
        h.addLayout(vol_row)

        self.set_idle()

    def is_autoplay_enabled(self) -> bool:
        return self.autoplay_cb.isChecked()

    # ------------- visual states ------------------------------------------
    def _show_play_glyph(self):
        self.play_btn.setText("")
        self.play_btn.setIcon(self._play_icon)

    def _show_pause_glyph(self):
        self.play_btn.setText("")
        self.play_btn.setIcon(self._pause_icon)

    def _show_loading_glyph(self, ch: str):
        # text spinner — clear icon so the button shows just the glyph char
        self.play_btn.setIcon(QIcon())
        self.play_btn.setText(ch)

    def set_idle(self):
        self._show_play_glyph()
        self.play_btn.setEnabled(False)
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.seek_bar.setEnabled(False)
        self.seek_bar.blockSignals(True)
        self.seek_bar.setRange(0, 0)
        self.seek_bar.setValue(0)
        self.seek_bar.blockSignals(False)
        self.time_label.setText("00:00 / 00:00")

    def set_loading(self, spinner_char: str = "⠋"):
        self._show_loading_glyph(spinner_char)
        self.play_btn.setEnabled(False)
        self.prev_btn.setEnabled(True)
        self.next_btn.setEnabled(True)
        self.seek_bar.setEnabled(False)
        self.time_label.setText("00:00 / 00:00")

    def set_playing(self):
        self._show_pause_glyph()
        self.play_btn.setEnabled(True)
        self.prev_btn.setEnabled(True)
        self.next_btn.setEnabled(True)

    def set_paused(self):
        self._show_play_glyph()
        self.play_btn.setEnabled(True)
        self.prev_btn.setEnabled(True)
        self.next_btn.setEnabled(True)

    # ------------- live updates from QMediaPlayer -------------------------
    def update_position(self, pos_ms: int):
        self.seek_bar.blockSignals(True)
        self.seek_bar.setValue(pos_ms)
        self.seek_bar.blockSignals(False)
        self._refresh_time()

    def update_duration(self, dur_ms: int):
        self.seek_bar.setRange(0, dur_ms)
        self.seek_bar.setEnabled(dur_ms > 0)
        self._refresh_time()

    def _refresh_time(self):
        self.time_label.setText(
            f"{_format_ms(self.seek_bar.value())} / {_format_ms(self.seek_bar.maximum())}"
        )


# ---- play button drawn on the right side of each search-results row -------
class PlayButtonDelegate(QStyledItemDelegate):
    """Paints a small circular play / pause button on the right edge of each
    QListWidgetItem in the search-results list. The list widget itself
    handles click hit-tests in the same x range and emits `play_clicked`.
    """
    BTN_SIZE   = 28
    BTN_MARGIN = 10
    COL_BG_IDLE   = "#414868"
    COL_BG_ACTIVE = "#7aa2f7"
    COL_GLYPH     = "#c0caf5"
    COL_GLYPH_ON_ACTIVE = "#16161e"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_id = None
        self._is_paused = False
        self._is_loading = False

    def set_state(self, video_id, is_paused: bool = False, is_loading: bool = False):
        self._active_id = video_id
        self._is_paused = is_paused
        self._is_loading = is_loading

    @classmethod
    def reserved_width(cls) -> int:
        return cls.BTN_SIZE + cls.BTN_MARGIN * 2

    def paint(self, painter, option, index):
        # Sentinel rows (scroll-prompt / loading-more / exhausted) get the
        # default paint and no play button.
        if index.data(SENTINEL_ROLE):
            super().paint(painter, option, index)
            return

        # Reserve space on the right so item text doesn't run under the button.
        adjusted = QStyleOptionViewItem(option)
        adjusted.rect = option.rect.adjusted(0, 0, -self.reserved_width(), 0)
        super().paint(painter, adjusted, index)

        rect = option.rect
        cx = rect.right() - self.BTN_MARGIN - self.BTN_SIZE / 2
        cy = rect.top() + rect.height() / 2
        vid = index.data(Qt.UserRole + 2)
        is_active = vid is not None and vid == self._active_id

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(
            self.COL_BG_ACTIVE if is_active else self.COL_BG_IDLE
        )))
        painter.drawEllipse(QPointF(cx, cy), self.BTN_SIZE / 2, self.BTN_SIZE / 2)

        # Glyph: ▶ idle, ⏸ active+playing, ▶ active+paused, ⠋ active+loading
        glyph_color = QColor(
            self.COL_GLYPH_ON_ACTIVE if is_active else self.COL_GLYPH
        )
        painter.setBrush(QBrush(glyph_color))
        if is_active and self._is_loading:
            # spinning hint — small ring sector
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(cx, cy), 3, 3)
        elif is_active and not self._is_paused:
            # pause icon: two vertical bars
            bar_w = 3
            bar_h = 11
            painter.drawRect(int(cx - bar_w - 1), int(cy - bar_h / 2), bar_w, bar_h)
            painter.drawRect(int(cx + 1),         int(cy - bar_h / 2), bar_w, bar_h)
        else:
            # play triangle
            poly = QPolygonF([
                QPointF(cx - 4, cy - 6),
                QPointF(cx - 4, cy + 6),
                QPointF(cx + 6, cy),
            ])
            painter.drawPolygon(poly)
        painter.restore()


class QueueListWidget(SmoothListWidget):
    """Smooth-scroll list whose rows expose a clickable rename pill at the
    bottom-right (painted by QueueRenameHintDelegate). Clicks on that hit
    zone emit `rename_clicked` and don't bubble to selection."""
    rename_clicked = pyqtSignal(object)   # QListWidgetItem

    def _on_rename_zone(self, x: int, y: int, item) -> bool:
        rect = self.visualItemRect(item)
        hit = QueueRenameHintDelegate.hit_rect_for(rect)
        return (hit.left() <= x <= hit.right() and
                hit.top()  <= y <= hit.bottom())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            if item and self._on_rename_zone(event.pos().x(),
                                              event.pos().y(), item):
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            if item and self._on_rename_zone(event.pos().x(),
                                              event.pos().y(), item):
                self.rename_clicked.emit(item)
                event.accept()
                return
        super().mouseReleaseEvent(event)


class ResultsListWidget(SmoothListWidget):
    """Custom list widget. Clicks on the right-edge play-button area emit
    `play_clicked` and don't bubble through to selection. Everywhere else,
    standard Qt selection / checkbox-toggle behavior applies.

    Inherits SmoothListWidget for pixel-precise + animated wheel scrolling.
    """
    play_clicked = pyqtSignal(object)  # QListWidgetItem

    def _is_play_zone(self, x: int, item_rect) -> bool:
        zone = PlayButtonDelegate.reserved_width()
        return x >= item_rect.right() - zone

    @staticmethod
    def _is_sentinel(item) -> bool:
        return bool(item and item.data(SENTINEL_ROLE))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            if item and not self._is_sentinel(item) \
                    and self._is_play_zone(event.pos().x(), self.visualItemRect(item)):
                event.accept()
                return  # don't change selection on play-button press
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            if item and not self._is_sentinel(item) \
                    and self._is_play_zone(event.pos().x(), self.visualItemRect(item)):
                self.play_clicked.emit(item)
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            if item and (self._is_sentinel(item)
                         or self._is_play_zone(event.pos().x(),
                                               self.visualItemRect(item))):
                event.accept()
                return  # don't fire add-to-queue on sentinel / play-button
        super().mouseDoubleClickEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1440, 810)  # 16:9
        self.setMinimumSize(1100, 680)

        self._results = []           # left list backing data
        self._queue = []             # right (download) list backing data
        self._thumb_cache = {}       # video_id -> QPixmap

        self._search_worker = None
        self._fetch_worker = None
        self._download_worker = None
        self._thumb_workers = []
        self._suggest_worker = None
        self._load_more_worker = None
        self._audio_worker = None
        self._update_check_worker = None

        # paginated search state
        self._search_obj = None
        self._search_offset = 0
        self._loading_more = False
        self._search_exhausted = False
        self._search_query = ""              # for cache_extend on load-more
        self._stream_thumb_buffer: list = []  # batch streaming thumb requests

        # audio preview state
        self._audio_cache_dir = os.path.join(tempfile.gettempdir(), 'ut_download_audio')
        self._playing_video_id = None
        self._audio_loading = False
        if _MEDIA_OK:
            self._audio_player = QMediaPlayer(self)
            self._audio_player.error.connect(self._on_audio_error)
            self._audio_player.stateChanged.connect(self._on_audio_state)
            self._audio_player.mediaStatusChanged.connect(self._on_audio_status)
            self._audio_player.positionChanged.connect(self._on_audio_position)
            self._audio_player.durationChanged.connect(self._on_audio_duration)
            # Volume is set later via the slider; calling setVolume here on
            # some Windows builds (no audio device yet) was access-violating.
        else:
            self._audio_player = None

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 14, 18, 10)
        root.setSpacing(8)

        # main horizontal split — 69% left / 31% right
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([69, 31])
        splitter.setStretchFactor(0, 69)
        splitter.setStretchFactor(1, 31)
        root.addWidget(splitter, 1)
        self._install_splitter_glow(splitter)
        # Re-apply once the layout has settled — initial setSizes can be
        # overridden by Qt's first layout pass on some Fluent builds.
        self._splitter_ref = splitter
        self._split_left_ratio = 0.69
        QTimer.singleShot(0, self._apply_split_ratio)
        # Fire the update check a couple of seconds after launch — far enough
        # out that the GitHub round-trip can't slow the cold-start, but soon
        # enough that the user sees the toast before they get into a flow.
        QTimer.singleShot(2500, self._check_for_update)

    def _apply_split_ratio(self):
        if not getattr(self, '_splitter_ref', None):
            return
        total = max(self._splitter_ref.width(), self.width())
        if total <= 0:
            return
        left = int(total * getattr(self, '_split_left_ratio', 0.68))
        right = total - left
        self._splitter_ref.setSizes([left, right])

        self._setup_autocomplete()
        self._update_format()
        self._refresh_counters()
        self._update_download_btn()

    # -------------------------------------------------------- LEFT PANEL
    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("central")
        v = QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 6, 0)
        v.setSpacing(8)

        # search row — plain Fluent LineEdit + PrimaryPushButton (avoid
        # SearchLineEdit because its searchSignal fires alongside
        # returnPressed and confuses our QCompleter wiring).
        row = QHBoxLayout()
        row.setSpacing(8)
        self.search_input = LineEdit()
        self.search_input.setPlaceholderText("🔍   유튜브에서 검색…")
        self.search_input.setMinimumHeight(38)
        self._stack_qss(self.search_input,
                        "LineEdit, QLineEdit { font-size: 16px; }")
        self.search_input.returnPressed.connect(self.do_search)
        self.search_btn = PrimaryPushButton("검색")
        self.search_btn.setFixedWidth(110)
        self.search_btn.setMinimumHeight(38)
        self.search_btn.setCursor(Qt.PointingHandCursor)
        # Solid tinted style (same scheme as the secondary buttons).
        self._tint_button(self.search_btn, 122, 162, 247, font_size=16, weight=700)
        self.search_btn.clicked.connect(self.do_search)
        row.addWidget(self.search_input, 1)
        row.addWidget(self.search_btn)
        v.addLayout(row)

        # title bar above results
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        ttl_glyph = QLabel("✦")
        ttl_glyph.setObjectName("titleGlyphCyan")
        ttl = QLabel("검색 결과")
        ttl.setObjectName("paneTitle")
        self.results_count_badge = QLabel("0")
        self.results_count_badge.setObjectName("badge")
        self.results_count_badge.setAlignment(Qt.AlignCenter)
        self.results_check_badge = QLabel("선택 0")
        self.results_check_badge.setObjectName("badgeMuted")
        self.results_check_badge.setAlignment(Qt.AlignCenter)
        hint = QLabel("더블클릭으로 대기열에 추가 · 체크 후 [+ 대기열에 추가]")
        hint.setObjectName("sectionLabel")
        hint.setStyleSheet("font-size: 13px; color: #a9b1d6; font-weight: 600;")
        title_row.addWidget(ttl_glyph)
        title_row.addWidget(ttl)
        title_row.addSpacing(8)
        title_row.addWidget(self.results_count_badge)
        title_row.addSpacing(4)
        title_row.addWidget(self.results_check_badge)
        title_row.addStretch()
        title_row.addWidget(hint)
        v.addLayout(title_row)

        # results list (custom — checkbox on the left, play button on the right)
        self.results_list = ResultsListWidget()
        self.results_list.setIconSize(ICON_RESULTS)
        self.results_list.setSpacing(2)
        self.results_list.setAlternatingRowColors(True)
        self._play_delegate = PlayButtonDelegate(self.results_list)
        self.results_list.setItemDelegate(self._play_delegate)
        self.results_list.itemDoubleClicked.connect(self._on_results_double_clicked)
        self.results_list.play_clicked.connect(self._on_play_clicked)
        self.results_list.itemChanged.connect(lambda _i: self._refresh_counters())

        # action row — Fluent buttons; "+ 대기열에 추가" is the primary action of the row
        btns = QHBoxLayout()
        self.play_results_btn = PushButton("▶ 브라우저")
        self.play_results_btn.clicked.connect(self.play_results_selected)
        self.check_all_btn = PushButton("☑ 전체 선택")
        self.check_all_btn.clicked.connect(lambda: self._set_all_checked(True))
        self.uncheck_all_btn = PushButton("☐ 전체 해제")
        self.uncheck_all_btn.clicked.connect(lambda: self._set_all_checked(False))
        self.add_to_queue_btn = PrimaryPushButton("✚ 대기열에 추가")
        self.add_to_queue_btn.clicked.connect(self.add_checked_to_queue)
        self.clear_results_btn = PushButton("✕ 결과 지우기")
        self.clear_results_btn.setObjectName("dangerBtn")
        self.clear_results_btn.clicked.connect(self.clear_results)
        # Per-button colored tints. Each uses a different accent so the row
        # reads as a colorful palette instead of five identical gray buttons.
        self.play_results_btn.setMinimumHeight(34)
        self._tint_button(self.play_results_btn, 125, 207, 255)   # cyan — "play"
        self.check_all_btn.setMinimumHeight(34)
        self._tint_button(self.check_all_btn, 158, 206, 106)      # green — select
        self.uncheck_all_btn.setMinimumHeight(34)
        self._tint_button(self.uncheck_all_btn, 137, 162, 200)    # muted blue — neutral
        self.clear_results_btn.setMinimumHeight(34)
        self._tint_button(self.clear_results_btn, 247, 118, 142)  # pink — danger
        self.add_to_queue_btn.setMinimumHeight(34)
        self.add_to_queue_btn.setCursor(Qt.PointingHandCursor)
        self._tint_button(self.add_to_queue_btn, 158, 206, 106, font_size=15, weight=700)
        btns.addWidget(self.play_results_btn)
        btns.addWidget(self.check_all_btn)
        btns.addWidget(self.uncheck_all_btn)
        btns.addStretch()
        btns.addWidget(self.add_to_queue_btn)
        btns.addWidget(self.clear_results_btn)

        # list view = results + buttons
        list_view = QWidget()
        lv = QVBoxLayout(list_view)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(8)
        lv.addWidget(self.results_list, 1)
        lv.addLayout(btns)

        # loading view — Fluent ProgressRing + caption
        loading_view = QWidget()
        ll = QVBoxLayout(loading_view)
        ll.setAlignment(Qt.AlignCenter)
        ll.setSpacing(16)
        self.loading_ring = IndeterminateProgressRing()
        self.loading_ring.setFixedSize(64, 64)
        self.loading_label = QLabel("검색 중…")
        self.loading_label.setObjectName("loadingLabel")
        self.loading_label.setAlignment(Qt.AlignCenter)
        ring_holder = QHBoxLayout()
        ring_holder.addStretch()
        ring_holder.addWidget(self.loading_ring)
        ring_holder.addStretch()
        ll.addLayout(ring_holder)
        ll.addWidget(self.loading_label)

        # stack: 0 = list, 1 = loading
        self.results_stack = QStackedWidget()
        self.results_stack.addWidget(list_view)     # 0
        self.results_stack.addWidget(loading_view)  # 1
        v.addWidget(self.results_stack, 1)

        # audio player bar — always visible, sits below the list
        self.player_bar = AudioPlayerBar()
        self.player_bar.play_pause_clicked.connect(self._player_toggle)
        self.player_bar.prev_clicked.connect(lambda: self._player_jump(-1))
        self.player_bar.next_clicked.connect(lambda: self._player_jump(1))
        self.player_bar.seek_requested.connect(self._player_seek)
        self.player_bar.volume_changed.connect(self._on_volume_changed)
        v.addWidget(self.player_bar)

        # spinner animation
        self._spinner_chars = list("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
        self._spinner_idx = 0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(90)
        self._spinner_timer.timeout.connect(self._tick_spinner)

        # infinite scroll: fire when scrollbar nears the bottom
        self.results_list.verticalScrollBar().valueChanged.connect(self._on_results_scroll)

        return panel

    # ------------------------------------------------------- RIGHT PANEL
    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("rightPane")
        v = QVBoxLayout(panel)
        v.setContentsMargins(6, 0, 0, 0)
        v.setSpacing(10)

        # URL row — Fluent LineEdit + PrimaryPushButton
        url_row = QHBoxLayout()
        url_row.setSpacing(8)
        self.url_input = LineEdit()
        self.url_input.setPlaceholderText("🔗   유튜브 URL 직접 입력…")
        self.url_input.setMinimumHeight(38)
        self._stack_qss(self.url_input,
                        "LineEdit, QLineEdit { font-size: 16px; }")
        self.url_input.returnPressed.connect(self.add_url)
        self.add_url_btn = PrimaryPushButton("URL 추가")
        self.add_url_btn.setFixedWidth(96)
        self.add_url_btn.setMinimumHeight(38)
        self.add_url_btn.setCursor(Qt.PointingHandCursor)
        # Coral-pink — distinct from the purple 폴더위치 button on the same panel.
        self._tint_button(self.add_url_btn, 255, 142, 165, font_size=15, weight=700)
        self.add_url_btn.clicked.connect(self.add_url)
        url_row.addWidget(self.url_input, 1)
        url_row.addWidget(self.add_url_btn)
        v.addLayout(url_row)

        # options
        v.addWidget(self._build_options_box())

        # queue
        v.addWidget(self._build_queue_box(), 1)

        # download button + progress + log
        v.addWidget(self._build_action_box())

        return panel

    def _build_options_box(self) -> QGroupBox:
        box = QGroupBox("◆   다운로드 옵션")
        box.setObjectName("optionsBox")
        v = QVBoxLayout(box)
        # Slightly roomier than before — the deleted "파일명 변경" row freed
        # vertical space; using it for breathing room between the remaining rows.
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(10)

        # row 1: 저장형식  ☑비디오 ☑오디오
        self.fmt_video = CheckBox("비디오")
        self.fmt_audio = CheckBox("오디오")
        self.fmt_video.setChecked(True)
        self.fmt_audio.setChecked(True)
        self.fmt_video.toggled.connect(self._update_format)
        self.fmt_audio.toggled.connect(self._update_format)
        # Fluent's class stylesheet pins font: 14px on CheckBox; bump per instance.
        for cb in (self.fmt_video, self.fmt_audio):
            self._stack_qss(cb, "CheckBox, QCheckBox { font-size: 15px; }")
        fmt_widget = QWidget()
        fmt_h = QHBoxLayout(fmt_widget)
        fmt_h.setContentsMargins(0, 0, 0, 0)
        fmt_h.setSpacing(14)
        fmt_h.addWidget(self.fmt_video)
        fmt_h.addWidget(self.fmt_audio)
        fmt_h.addStretch()
        v.addLayout(self._row("저장형식", fmt_widget))

        # row 2: 경로  [path] [폴더위치]
        self.dest_input = LineEdit()
        self.dest_input.setText(DEFAULT_DEST)
        self.browse_btn = PushButton("폴더위치")
        self.browse_btn.setFixedWidth(92)
        self._tint_button(self.browse_btn, 187, 154, 247, font_size=15)  # purple — file picker
        self.browse_btn.clicked.connect(self.browse_dest)
        v.addLayout(self._row("경로", self.dest_input, self.browse_btn,
                              label_width=32, spacing=3))

        # row 3: 해상도  [combo]
        self.res_combo = ComboBox()
        self.res_combo.addItems(["최고 화질", "1080p", "720p", "480p", "360p", "240p", "최저 화질"])
        v.addLayout(self._row("해상도", self.res_combo))

        # row 4: 일괄 파일명 추가  [input]
        # (single-item rename is handled per-row in the download queue —
        # double-click an item or press the 이름변경 button there.)
        self.prefix_input = LineEdit()
        self.prefix_input.setPlaceholderText("다중 다운로드 시 각 파일 앞에 추가")
        v.addLayout(self._row("일괄 파일명 추가", self.prefix_input))

        # Bump every Fluent input in this card past their class-level font rule.
        for w in (self.dest_input, self.prefix_input):
            self._stack_qss(w, "LineEdit, QLineEdit { font-size: 15px; }")
        self._stack_qss(self.res_combo, "ComboBox, QComboBox { font-size: 15px; }")

        return box

    @staticmethod
    def _stack_qss(widget, addition: str) -> None:
        """Append a stylesheet snippet to the widget's existing one.

        Fluent applies its dark-theme paint via per-widget stylesheets.
        Calling `widget.setStyleSheet(short_rule)` REPLACES that, which
        falls back to vanilla Qt (white bg + black text). This helper
        layers our overrides on top of whatever Fluent already set.
        """
        prev = widget.styleSheet() or ""
        widget.setStyleSheet(prev + "\n" + addition)

    def _tint_button(self, btn, r: int, g: int, b: int,
                     font_size: int = 15, weight: int = 600) -> None:
        """Apply a 'ghost-button' tint based on (r,g,b).

        Idle: subtle tinted bg + colored text + matching border.
        Hover: stronger fill + white text.
        Pressed: solid color + dark text.
        Layers on top of Fluent's stylesheet via `_stack_qss`.
        """
        self._stack_qss(btn, f"""
            PushButton, PrimaryPushButton, QPushButton {{
                background: rgba({r}, {g}, {b}, 55);
                color: rgb({r}, {g}, {b});
                border: 1px solid rgba({r}, {g}, {b}, 140);
                border-radius: 6px;
                padding: 4px 12px;
                font-size: {font_size}px;
                font-weight: {weight};
            }}
            PushButton:hover, PrimaryPushButton:hover, QPushButton:hover {{
                background: rgba({r}, {g}, {b}, 130);
                color: #c0caf5;
                border: 1px solid rgb({r}, {g}, {b});
            }}
            PushButton:pressed, PrimaryPushButton:pressed, QPushButton:pressed {{
                background: rgb({r}, {g}, {b});
                color: #16161e;
            }}
            PushButton:disabled, QPushButton:disabled {{
                background: rgba({r}, {g}, {b}, 18);
                color: rgba({r}, {g}, {b}, 100);
                border: 1px solid rgba({r}, {g}, {b}, 60);
            }}
        """)

    @staticmethod
    def _row(label_text: str, *widgets, label_width: int = None,
             spacing: int = 6) -> QHBoxLayout:
        """Build a label + content row that hugs its label width naturally."""
        row = QHBoxLayout()
        row.setSpacing(spacing)
        lbl = QLabel(label_text)
        lbl.setObjectName("sectionLabel")
        if label_width is not None:
            lbl.setFixedWidth(label_width)
        row.addWidget(lbl)
        if widgets:
            row.addWidget(widgets[0], 1)
            for w in widgets[1:]:
                row.addWidget(w)
        return row

    def _build_queue_box(self) -> QGroupBox:
        box = QGroupBox("≡   다운로드 대기열")
        box.setObjectName("queueBox")
        v = QVBoxLayout(box)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(6)

        self.queue_list = SmoothListWidget()
        # Per-item rename pill removed by design — rename now happens via the
        # action-row 이름변경 button or by double-clicking the queue row.
        self.queue_list.setIconSize(ICON_QUEUE)
        self.queue_list.setSpacing(2)
        self.queue_list.setAlternatingRowColors(True)
        self.queue_list.itemDoubleClicked.connect(self._on_queue_double_clicked)
        v.addWidget(self.queue_list, 1)

        btns = QHBoxLayout()
        # Item count now lives at the bottom-left where the play button used to be.
        self.queue_count_badge = QLabel("0개")
        self.queue_count_badge.setObjectName("queueBadge")  # orange — distinct from results' cyan badge
        self.queue_count_badge.setAlignment(Qt.AlignCenter)
        btns.addWidget(self.queue_count_badge)
        btns.addStretch()
        self.remove_queue_btn = PushButton("✕ 삭제")
        self._tint_button(self.remove_queue_btn, 224, 175, 104, font_size=14)  # amber — queue
        self.remove_queue_btn.clicked.connect(self.remove_queue_selected)
        self.clear_queue_btn = PushButton("✕ 비우기")
        self.clear_queue_btn.setObjectName("dangerBtn")
        self._tint_button(self.clear_queue_btn, 247, 118, 142, font_size=14)   # red — danger
        self.clear_queue_btn.clicked.connect(self.clear_queue)
        self.rename_queue_btn = PushButton("✎ 이름변경")
        self._tint_button(self.rename_queue_btn, 200, 140, 220, font_size=14)  # magenta — edit
        self.rename_queue_btn.setToolTip("더블클릭으로도 이름을 바꿀 수 있어요")
        self.rename_queue_btn.clicked.connect(self.rename_queue_item)
        # Order: 삭제  비우기  이름변경 (rightmost — least frequent action lives at the edge).
        btns.addWidget(self.remove_queue_btn)
        btns.addWidget(self.clear_queue_btn)
        btns.addWidget(self.rename_queue_btn)
        v.addLayout(btns)

        return box

    def _build_action_box(self) -> QGroupBox:
        # Plain ↓ — simpler than the chevron/tray glyph; the box title is small
        # and the simple arrow reads clearly at this size.
        box = QGroupBox("↓   다운로드")
        box.setObjectName("downloadBox")
        v = QVBoxLayout(box)
        v.setSpacing(6)

        self.download_btn = PrimaryPushButton("다운로드 시작")
        self.download_btn.setIcon(download_icon(20, "#9ece6a"))
        self.download_btn.setIconSize(QSize(20, 20))
        self.download_btn.setMinimumHeight(42)
        self.download_btn.setCursor(Qt.PointingHandCursor)
        # Green tint — matches the section accent. Same flat style as 결과지우기.
        self._tint_button(self.download_btn, 158, 206, 106, font_size=17, weight=800)
        self.download_btn.clicked.connect(self.download_all)

        # Open destination folder — sits to the right of 다운로드 시작 at ~20% of the row width.
        self.open_folder_btn = PushButton("폴더열기")
        self.open_folder_btn.setIcon(folder_icon(18, "#bb9af7"))
        self.open_folder_btn.setIconSize(QSize(18, 18))
        self.open_folder_btn.setMinimumHeight(42)
        self.open_folder_btn.setCursor(Qt.PointingHandCursor)
        self.open_folder_btn.setToolTip("저장 폴더 열기")
        self._tint_button(self.open_folder_btn, 187, 154, 247, font_size=14)  # purple
        self.open_folder_btn.clicked.connect(self.open_dest_folder)

        # 80% / 20% row — download is the headliner, folder open is secondary.
        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        action_row.addWidget(self.download_btn, 4)
        action_row.addWidget(self.open_folder_btn, 1)
        v.addLayout(action_row)

        # Fluent ProgressBar — smoother animated chunk than QProgressBar.
        self.progress_bar = ProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        v.addWidget(self.progress_bar)
        # Caption under it (Fluent ProgressBar has no built-in label).
        self.progress_caption = QLabel("0 / 0")
        self.progress_caption.setAlignment(Qt.AlignCenter)
        self.progress_caption.setStyleSheet("color: #a9b1d6; font-size: 11px;")
        v.addWidget(self.progress_caption)

        self.log_view = QTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        self.log_view.setFixedHeight(80)
        v.addWidget(self.log_view)

        return box

    # ------------------------------------------------------------ HELPERS
    def log(self, msg: str):
        self.log_view.append(msg)

    # ---- Fluent toast helpers (replace blocking QMessageBox calls) ----------
    def _toast_warn(self, title: str, content: str):
        InfoBar.warning(title=title, content=content, isClosable=True,
                        position=InfoBarPosition.TOP, duration=3500, parent=self)

    def _toast_info(self, title: str, content: str):
        InfoBar.info(title=title, content=content, isClosable=True,
                     position=InfoBarPosition.TOP, duration=2500, parent=self)

    def _toast_success(self, title: str, content: str):
        InfoBar.success(title=title, content=content, isClosable=True,
                        position=InfoBarPosition.TOP, duration=2500, parent=self)

    # ------------------------------------------------------ update check
    def _check_for_update(self):
        """Hit GitHub `releases/latest` and surface a sticky toast if a
        newer tag than `__version__` is available. Failures (offline,
        rate-limit, GitHub down) are intentionally silent."""
        if self._update_check_worker and self._update_check_worker.isRunning():
            return
        self._update_check_worker = UpdateCheckWorker(__version__)
        self._update_check_worker.update_available.connect(self._on_update_available)
        # no_update / error left unconnected — silence on the happy path.
        self._update_check_worker.start()

    def _on_update_available(self, tag: str, html_url: str):
        bar = InfoBar.success(
            title=f"새 버전 v{tag} 사용 가능",
            content=f"현재 v{__version__} → v{tag}",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=-1,                  # sticky until user dismisses
            parent=self,
        )
        btn = PushButton("GitHub에서 받기")
        btn.clicked.connect(lambda: webbrowser.open(html_url))
        bar.addWidget(btn)

    def _update_format(self):
        video = self.fmt_video.isChecked()
        self.res_combo.setEnabled(video)
        self._update_download_btn()

    def _update_download_btn(self):
        ok = (self.fmt_video.isChecked() or self.fmt_audio.isChecked()) \
             and self.queue_list.count() > 0 \
             and not (self._download_worker and self._download_worker.isRunning())
        self.download_btn.setEnabled(ok)

    def _refresh_counters(self):
        total = 0
        checked = 0
        for i in range(self.results_list.count()):
            it = self.results_list.item(i)
            if it.data(SENTINEL_ROLE):
                continue  # don't count the scroll-prompt row
            total += 1
            if it.checkState() == Qt.Checked:
                checked += 1
        self.results_count_badge.setText(str(total))
        self.results_check_badge.setText(f"선택 {checked}")

        qtotal = self.queue_list.count()
        self.queue_count_badge.setText(f"{qtotal}개")
        self._update_download_btn()

    def _set_all_checked(self, checked: bool):
        state = Qt.Checked if checked else Qt.Unchecked
        self.results_list.blockSignals(True)
        for i in range(self.results_list.count()):
            it = self.results_list.item(i)
            if it.data(SENTINEL_ROLE):
                continue
            it.setCheckState(state)
        self.results_list.blockSignals(False)
        self._refresh_counters()

    # ----------------------------------------------- thumbnail handling
    def _request_thumbnails(self, video_ids):
        needed = [v for v in video_ids if v and v not in self._thumb_cache]
        if not needed:
            return
        w = ThumbnailWorker(needed)
        w.loaded.connect(self._on_thumbnail_loaded)
        w.finished_all.connect(lambda: self._thumb_workers.remove(w)
                               if w in self._thumb_workers else None)
        self._thumb_workers.append(w)
        w.start()

    def _on_thumbnail_loaded(self, video_id: str, data: bytes):
        pix = QPixmap()
        if not pix.loadFromData(data):
            return
        self._thumb_cache[video_id] = pix
        self._apply_thumb_to_list(self.results_list, self._results, video_id, pix, ICON_RESULTS)
        self._apply_thumb_to_list(self.queue_list, self._queue, video_id, pix, ICON_QUEUE)

    @staticmethod
    def _apply_thumb_to_list(list_widget: QListWidget, backing: list,
                             video_id: str, pix: QPixmap, size: QSize):
        scaled = pix.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        icon = QIcon(scaled)
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            idx = item.data(Qt.UserRole)
            if idx is None or idx >= len(backing):
                continue
            if backing[idx].get('video_id') == video_id:
                item.setIcon(icon)

    def _icon_for(self, video_id: str, size: QSize) -> QIcon:
        pix = self._thumb_cache.get(video_id)
        if not pix:
            return QIcon()
        return QIcon(pix.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    # ------------------------------------------------- autocomplete
    def _setup_autocomplete(self):
        # Custom popup — replaces QCompleter (which crashes on Fluent inputs).
        self._suggest_popup = SuggestPopup(self)
        self._suggest_popup.item_picked.connect(self._on_suggest_picked)

        self._suggest_timer = QTimer(self)
        self._suggest_timer.setSingleShot(True)
        self._suggest_timer.setInterval(180)
        self._suggest_timer.timeout.connect(self._fetch_suggestions)
        self.search_input.textEdited.connect(self._on_search_text_edited)

        # Click-outside dismissal — install an event filter only on widgets
        # whose interaction should hide the popup. Filtering on QApplication
        # has triggered access violations on this Fluent build, so we keep
        # the filter narrow.
        for w in (self.results_list, self.queue_list, self.url_input,
                  self.dest_input, self.prefix_input):
            try:
                w.installEventFilter(self)
            except Exception:
                pass

    def eventFilter(self, obj, event):
        # Any click on another input/list → hide the suggest popup.
        if event.type() == QEvent.MouseButtonPress \
                and self._suggest_popup is not None \
                and self._suggest_popup.isVisible():
            self._suggest_popup.hide()
        return super().eventFilter(obj, event)

    def _on_search_text_edited(self, text: str):
        if not text.strip():
            self._suggest_popup.hide()
            return
        self._suggest_timer.start()

    def _fetch_suggestions(self):
        text = self.search_input.text().strip()
        if not text:
            return
        if self._suggest_worker and self._suggest_worker.isRunning():
            return
        self._suggest_worker = SuggestWorker(text)
        self._suggest_worker.suggestions.connect(self._on_suggestions)
        self._suggest_worker.start()

    def _on_suggestions(self, items: list):
        if not items:
            return
        # Only show if the input still has focus and still has text — by the
        # time suggestions arrive, the user may have already submitted.
        if self.search_input.hasFocus() and self.search_input.text().strip():
            self._suggest_popup.show_below(self.search_input, items)

    def _on_suggest_picked(self, text: str):
        self.search_input.setText(text)
        self.do_search()

    PAGE_LIST = 0
    PAGE_LOADING = 1

    # ------------------------------------------------- audio preview
    def _on_play_clicked(self, item: QListWidgetItem):
        idx = item.data(Qt.UserRole)
        if idx is None or idx >= len(self._results):
            return
        self._play_video(self._results[idx])

    def _play_video(self, info: dict):
        vid = info.get('video_id')
        if not vid or self._audio_player is None:
            self._toast_warn("재생", "오디오 모듈을 사용할 수 없습니다.")
            return

        # Toggle play/pause on the current item
        if vid == self._playing_video_id:
            if self._audio_player.state() == QMediaPlayer.PlayingState:
                self._audio_player.pause()
                self._set_play_state(vid, is_paused=True)
            else:
                self._audio_player.play()
                self._set_play_state(vid, is_paused=False)
            return

        # Switching to a new item — stop current, kick off download for new one
        self._audio_player.stop()
        self._playing_video_id = vid
        self._audio_loading = True
        self._set_play_state(vid, is_loading=True)
        self._refresh_spinner()

        cached = os.path.join(self._audio_cache_dir, f"{vid}.mp3")
        if os.path.isfile(cached) and os.path.getsize(cached) > 0:
            self._play_local_file(cached, vid)
            return

        if self._audio_worker and self._audio_worker.isRunning():
            self._audio_worker.requestInterruption()
            self._audio_worker.quit()
            self._audio_worker.wait(500)
        self._audio_worker = AudioDownloadWorker(info['url'], vid, self._audio_cache_dir)
        self._audio_worker.file_ready.connect(self._on_audio_ready)
        self._audio_worker.error.connect(self._on_audio_dl_error)
        self._audio_worker.start()

    def _play_local_file(self, path: str, vid: str):
        if self._audio_player is None:
            return
        self._audio_loading = False
        self._refresh_spinner()
        self._audio_player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
        self._audio_player.play()
        self._set_play_state(vid, is_paused=False)

    def _on_audio_ready(self, video_id: str, file_path: str):
        # User might have clicked another item while we were downloading
        if video_id != self._playing_video_id:
            return
        self._play_local_file(file_path, video_id)

    def _on_audio_dl_error(self, video_id: str, msg: str):
        if video_id == self._playing_video_id:
            self._playing_video_id = None
            self._audio_loading = False
            self._set_play_state(None)
            self._refresh_spinner()
        self.log(f"오디오 미리듣기 오류: {msg}")

    def _on_audio_error(self, err):
        if self._audio_player is None or err == QMediaPlayer.NoError:
            return
        self.log(f"재생 오류: {self._audio_player.errorString()}")
        self._playing_video_id = None
        self._audio_loading = False
        self._set_play_state(None)
        self._refresh_spinner()

    def _on_audio_state(self, state):
        if self._playing_video_id is None:
            return
        if state == QMediaPlayer.PausedState:
            self._set_play_state(self._playing_video_id, is_paused=True)
        elif state == QMediaPlayer.PlayingState:
            self._set_play_state(self._playing_video_id, is_paused=False)

    def _on_audio_status(self, status):
        if status == QMediaPlayer.EndOfMedia:
            prev_id = self._playing_video_id
            self._playing_video_id = None
            self._set_play_state(None)
            # Auto-advance only when the user has opted in via the toggle.
            if (prev_id is not None
                    and self.player_bar.is_autoplay_enabled()
                    and self._jump_relative_to(prev_id, +1)):
                return
            # Otherwise stop cleanly at the end of the current track.
            self.player_bar.set_idle()

    def _on_audio_position(self, pos_ms: int):
        self.player_bar.update_position(pos_ms)

    def _on_audio_duration(self, dur_ms: int):
        self.player_bar.update_duration(dur_ms)

    def _on_volume_changed(self, value: int):
        if self._audio_player is not None:
            self._audio_player.setVolume(int(value))

    # ------------------------------------------------- splitter hover glow
    def _install_splitter_glow(self, splitter):
        """Wrap the splitter's divider handle with a drop-shadow effect that
        fades in/out on hover. Pure visual feedback — no behavior change."""
        try:
            handle = splitter.handle(1)   # the divider between widget 0 and 1
        except Exception:
            return
        if handle is None:
            return

        glow = QGraphicsDropShadowEffect(handle)
        glow.setBlurRadius(22)
        glow.setOffset(0, 0)
        # Start invisible — alpha is animated up/down by the hover filter.
        glow.setColor(QColor(122, 162, 247, 0))
        handle.setGraphicsEffect(glow)

        anim = QVariantAnimation(self)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def on_value(val):
            glow.setColor(QColor(122, 162, 247, int(val)))
        anim.valueChanged.connect(on_value)

        FULL_ALPHA = 220
        FADE_OUT_MS = 320  # gentle decay even for brief mouse passes

        class _HoverFilter(QObject):
            def __init__(self, parent=None):
                super().__init__(parent)
            def eventFilter(self, obj, event):
                if event.type() == QEvent.Enter:
                    # Instant max brightness — even a quick mouse-pass lights
                    # the ribbon to full alpha. Fade-out handles the decay.
                    anim.stop()
                    glow.setColor(QColor(122, 162, 247, FULL_ALPHA))
                elif event.type() == QEvent.Leave:
                    anim.stop()
                    anim.setDuration(FADE_OUT_MS)
                    anim.setStartValue(int(glow.color().alpha()))
                    anim.setEndValue(0)
                    anim.start()
                return False

        # Keep references alive so the effect/anim/filter aren't GC'd.
        self._splitter_glow_effect = glow
        self._splitter_glow_anim = anim
        self._splitter_hover_filter = _HoverFilter(self)
        handle.setAttribute(Qt.WA_Hover, True)
        handle.installEventFilter(self._splitter_hover_filter)

    def _set_play_state(self, video_id, is_paused: bool = False, is_loading: bool = False):
        self._play_delegate.set_state(video_id, is_paused=is_paused, is_loading=is_loading)
        self.results_list.viewport().update()
        # Mirror state into the player bar.
        if video_id is None:
            self.player_bar.set_idle()
        elif is_loading:
            self.player_bar.set_loading()
        elif is_paused:
            self.player_bar.set_paused()
        else:
            self.player_bar.set_playing()

    # ------------------------------------------------- player-bar wiring
    def _player_toggle(self):
        if not self._playing_video_id or self._audio_player is None:
            return
        if self._audio_player.state() == QMediaPlayer.PlayingState:
            self._audio_player.pause()
        else:
            self._audio_player.play()

    def _player_seek(self, pos_ms: int):
        if self._audio_player is not None:
            self._audio_player.setPosition(pos_ms)

    def _player_jump(self, delta: int):
        target_id = self._playing_video_id
        if target_id is None:
            # nothing playing — start from the first/last result
            if not self._results:
                return
            target = self._results[0 if delta >= 0 else -1]
            self._play_video(target)
            return
        self._jump_relative_to(target_id, delta)

    def _jump_relative_to(self, video_id: str, delta: int) -> bool:
        for i, info in enumerate(self._results):
            if info.get('video_id') == video_id:
                target = i + delta
                if 0 <= target < len(self._results):
                    self._play_video(self._results[target])
                    return True
                return False
        return False

    # ------------------------------------------------- loading spinner
    def _tick_spinner(self):
        self._spinner_idx = (self._spinner_idx + 1) % len(self._spinner_chars)
        ch = self._spinner_chars[self._spinner_idx]
        # main loading view uses the Fluent ProgressRing — only the sentinel
        # row + player bar still need the text-spinner animation.
        sentinel = self._sentinel_item()
        if sentinel is not None and sentinel.data(SENTINEL_ROLE) == 'loading':
            sentinel.setText(f"{ch}  결과를 더 불러오는 중…")
        if self._audio_loading:
            self.player_bar.set_loading(ch)

    def _is_anything_loading(self) -> bool:
        return (self.results_stack.currentIndex() == self.PAGE_LOADING
                or self._loading_more
                or self._audio_loading)

    def _refresh_spinner(self):
        if self._is_anything_loading():
            if not self._spinner_timer.isActive():
                self._spinner_timer.start()
        else:
            self._spinner_timer.stop()

    def _show_loading(self):
        self.results_stack.setCurrentIndex(self.PAGE_LOADING)
        self._spinner_idx = 0
        self._refresh_spinner()

    def _hide_loading(self):
        if self.results_stack.currentIndex() == self.PAGE_LOADING:
            self.results_stack.setCurrentIndex(self.PAGE_LIST)
        self._refresh_spinner()

    # ------------------------------------------------- sentinel helpers
    def _sentinel_item(self):
        """Return the sentinel QListWidgetItem at the bottom, or None."""
        last = self.results_list.count() - 1
        if last < 0:
            return None
        item = self.results_list.item(last)
        if item and item.data(SENTINEL_ROLE):
            return item
        return None

    SENTINEL_COLOR = {
        'idle':       "#7dcfff",   # cyan — invitation
        'loading':    "#e0af68",   # amber — working
        'exhausted':  "#f7768e",   # soft red — end of road
    }

    def _set_sentinel(self, state: str):
        text = SENTINEL_TEXT.get(state, SENTINEL_TEXT['idle'])
        item = self._sentinel_item()
        if item is None:
            item = QListWidgetItem(text)
            item.setFlags(Qt.ItemIsEnabled)  # visible, but not selectable / checkable
            item.setTextAlignment(Qt.AlignCenter)
            item.setSizeHint(QSize(0, 38))
            self.results_list.addItem(item)
        else:
            item.setText(text)
        item.setData(SENTINEL_ROLE, state)
        # Color the sentinel by state — gives a glanceable visual cue.
        from PyQt5.QtGui import QBrush
        item.setForeground(QBrush(QColor(self.SENTINEL_COLOR.get(state, "#a9b1d6"))))
        f = item.font()
        f.setBold(True)
        item.setFont(f)

    def _remove_sentinel(self):
        last = self.results_list.count() - 1
        if last < 0:
            return
        item = self.results_list.item(last)
        if item and item.data(SENTINEL_ROLE):
            self.results_list.takeItem(last)

    # ------------------------------------------------- infinite scroll
    def _on_results_scroll(self, value: int):
        if not self._search_obj or self._loading_more or self._search_exhausted:
            return
        bar = self.results_list.verticalScrollBar()
        if bar.maximum() <= 0:
            return  # not scrollable yet
        if value >= bar.maximum() - 30:
            self._load_more_results()

    def _load_more_results(self):
        if self._loading_more or not self._search_obj:
            return
        if self._load_more_worker and self._load_more_worker.isRunning():
            return
        self._loading_more = True
        self._set_sentinel('loading')
        self._refresh_spinner()
        self._load_more_worker = LoadMoreWorker(
            self._search_obj, self._search_offset, batch_size=5,
            query=self._search_query,
        )
        self._load_more_worker.new_results.connect(self._on_more_results)
        self._load_more_worker.finished.connect(self._on_more_finished)
        self._load_more_worker.start()

    def _on_more_results(self, results: list):
        if not results:
            self._search_exhausted = True
            self._set_sentinel('exhausted')
            self.log("더 이상 결과가 없습니다.")
            return
        # Drop the sentinel, append the new rows, then put a fresh sentinel back.
        self._remove_sentinel()
        self._search_offset += len(results)
        for r in results:
            self._add_result_item(r)
        self._request_thumbnails([r['video_id'] for r in results])
        self._set_sentinel('idle')

    def _on_more_finished(self):
        self._loading_more = False
        self._refresh_spinner()

    # -------------------------------------------------- search & results
    def do_search(self):
        # Close the autocomplete dropdown the moment the user commits.
        if getattr(self, '_suggest_popup', None) is not None:
            self._suggest_popup.hide()
        if hasattr(self, '_suggest_timer'):
            self._suggest_timer.stop()
        # If a suggestion fetch is still in flight, disconnect its callback so
        # its late-arriving result can't re-open the popup over the loading view.
        sw = getattr(self, '_suggest_worker', None)
        if sw is not None:
            try:
                sw.suggestions.disconnect()
            except (TypeError, RuntimeError):
                pass
            if sw.isRunning():
                sw.requestInterruption()

        q = self.search_input.text().strip()
        if not q:
            return
        if self._search_worker and self._search_worker.isRunning():
            self.log("이미 검색이 진행 중입니다…")
            return
        # cancel in-flight thumbnail fetches for the previous results
        for w in list(self._thumb_workers):
            if w.isRunning():
                w.cancel()
        # wipe previous results + pagination state before starting a new search
        self.clear_results()
        self._search_obj = None
        self._search_offset = 0
        self._loading_more = False
        self._search_exhausted = False
        self._search_query = q
        self._stream_thumb_buffer = []

        self._show_loading()
        self.log(f"검색 중: {q!r} …")
        self.search_btn.setEnabled(False)
        self._search_worker = SearchWorker(q, initial_count=10)
        self._search_worker.cache_hit.connect(self._on_search_cache_hit)
        self._search_worker.started_search.connect(self._on_search_started)
        self._search_worker.one_result.connect(self._on_search_one_result)
        self._search_worker.finished_loading.connect(self._on_search_finished_loading)
        self._search_worker.error.connect(self._on_search_error)
        self._search_worker.finished.connect(lambda: self.search_btn.setEnabled(True))
        self._search_worker.start()

    def _on_search_cache_hit(self, results, search_obj):
        """Repeat-query path. Cached results are already parsed — repaint
        in one shot, restoring whatever scroll-depth the user reached
        previously in this session."""
        self._hide_loading()
        self._search_obj = search_obj
        self._search_offset = len(results)
        self._search_exhausted = False
        self.log(f"  {len(results)}개의 결과 (캐시됨)")
        for r in results:
            self._add_result_item(r)
        if results:
            self._set_sentinel('idle')
        self._request_thumbnails([r['video_id'] for r in results])
        QTimer.singleShot(150, self._maybe_auto_load_more)

    def _on_search_started(self, search_obj):
        """First signal of a fresh streaming search — Search() has resolved.
        Hide the spinner so the user sees rows pop in instead of a blank
        loading view."""
        self._hide_loading()
        self._search_obj = search_obj
        self._search_offset = 0
        self._search_exhausted = False

    def _on_search_one_result(self, info: dict):
        """Per-video append. Skip the sentinel here — `_add_result_item`
        always appends to the end of the list, so creating the sentinel
        before streaming finishes would push subsequent rows below it.
        Buffer thumbnail fetches in groups of ~4 so we don't spawn one
        ThumbnailWorker per row."""
        self._add_result_item(info)
        self._search_offset += 1
        vid = info.get('video_id')
        if vid:
            self._stream_thumb_buffer.append(vid)
        if len(self._stream_thumb_buffer) >= 4:
            self._request_thumbnails(list(self._stream_thumb_buffer))
            self._stream_thumb_buffer.clear()

    def _on_search_finished_loading(self, count: int):
        """Stream complete — flush leftover thumbnails, place sentinel."""
        if self._stream_thumb_buffer:
            self._request_thumbnails(list(self._stream_thumb_buffer))
            self._stream_thumb_buffer.clear()
        if count > 0:
            self._set_sentinel('idle')
        self.log(f"  {count}개의 결과를 찾았습니다.")
        # if the initial batch didn't fill the viewport, eagerly fetch one more page
        QTimer.singleShot(150, self._maybe_auto_load_more)

    def _maybe_auto_load_more(self):
        bar = self.results_list.verticalScrollBar()
        if bar.maximum() <= 0 and self._search_obj and not self._loading_more:
            self._load_more_results()

    def _on_search_error(self, err: str):
        self._hide_loading()
        self.log(f"검색 오류: {err}")
        self._toast_warn("검색 오류", err)

    def _add_result_item(self, info: dict):
        self._results.append(info)
        idx = len(self._results) - 1
        author = info.get('author') or '?'
        dur = _format_dur(info.get('length') or 0)
        text = f"  {info['title']}\n  {author}  ·  {dur}"
        item = QListWidgetItem(text)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Unchecked)
        item.setData(Qt.UserRole, idx)
        # Stash video_id directly so the delegate can compare without poking
        # back at self._results (the delegate has no list-widget reference).
        item.setData(Qt.UserRole + 2, info.get('video_id'))
        item.setToolTip(f"{info['title']}\n{info.get('author','')}\n{info['url']}")
        item.setIcon(self._icon_for(info.get('video_id', ''), ICON_RESULTS))
        item.setSizeHint(QSize(0, ICON_RESULTS.height() + 12))
        self.results_list.addItem(item)
        self._refresh_counters()

    def _on_results_double_clicked(self, item: QListWidgetItem):
        idx = item.data(Qt.UserRole)
        if idx is None or idx >= len(self._results):
            return
        self._push_to_queue(self._results[idx])

    def play_results_selected(self):
        item = self.results_list.currentItem()
        if not item:
            self._toast_info("재생", "먼저 항목을 선택해주세요.")
            return
        idx = item.data(Qt.UserRole)
        webbrowser.open(self._results[idx]['url'])

    def add_checked_to_queue(self):
        added = 0
        for i in range(self.results_list.count()):
            it = self.results_list.item(i)
            if it.data(SENTINEL_ROLE):
                continue
            if it.checkState() == Qt.Checked:
                idx = it.data(Qt.UserRole)
                if self._push_to_queue(self._results[idx], silent=True):
                    added += 1
        self.log(f"대기열에 {added}개 추가됨.")
        if added == 0:
            self._toast_info("대기열", "체크된 항목이 없거나 모두 이미 추가되었습니다.")

    def clear_results(self):
        self.results_list.clear()
        self._results = []
        self._refresh_counters()

    # --------------------------------------------------------- URL / queue
    def add_url(self):
        url = self.url_input.text().strip()
        if not url:
            return
        if 'youtube.com' not in url and 'youtu.be' not in url:
            self._toast_warn("잘못된 URL", "유튜브 URL을 입력해주세요.")
            return
        if self._fetch_worker and self._fetch_worker.isRunning():
            self.log("URL 처리가 이미 진행 중입니다…")
            return
        self.log(f"URL 정보 가져오는 중: {url}")
        self.add_url_btn.setEnabled(False)
        self._fetch_worker = FetchInfoWorker(url)
        self._fetch_worker.finished_info.connect(self._on_url_fetched)
        self._fetch_worker.error.connect(self._on_url_error)
        self._fetch_worker.finished.connect(lambda: self.add_url_btn.setEnabled(True))
        self._fetch_worker.start()

    def _on_url_fetched(self, info: dict):
        self._push_to_queue(info)
        self._request_thumbnails([info['video_id']])
        self.url_input.clear()

    def _on_url_error(self, err: str):
        self.log(f"URL 오류: {err}")
        self._toast_warn("URL 오류", err)

    def _push_to_queue(self, info: dict, silent: bool = False) -> bool:
        # de-dupe by video_id
        vid = info.get('video_id')
        if vid:
            for q in self._queue:
                if q.get('video_id') == vid:
                    return False
        self._queue.append(dict(info))
        idx = len(self._queue) - 1
        author = info.get('author') or '?'
        dur = _format_dur(info.get('length') or 0)
        text = f"  {info['title']}\n  {author}  ·  {dur}"
        item = QListWidgetItem(text)
        item.setData(Qt.UserRole, idx)
        item.setToolTip(f"{info['title']}\n{info.get('author','')}\n{info['url']}")
        item.setIcon(self._icon_for(vid or '', ICON_QUEUE))
        item.setSizeHint(QSize(0, ICON_QUEUE.height() + 12))
        self.queue_list.addItem(item)
        self._refresh_counters()
        if not silent:
            self.log(f"대기열에 추가: {info['title']}")
        return True

    def _on_queue_double_clicked(self, item: QListWidgetItem):
        # Double-click renames inline — same path as the badge / button.
        self._start_inline_rename(item)

    def rename_queue_item(self):
        """Rename whatever queue item is currently selected (button entry-point)."""
        item = self.queue_list.currentItem()
        if item is None:
            self._toast_info("이름 변경", "먼저 대기열에서 항목을 선택해주세요.")
            return
        self._start_inline_rename(item)

    def _start_inline_rename(self, item: QListWidgetItem):
        """Show a QLineEdit overlay positioned over the item's title area.
        Commits on Enter or focus loss; Esc cancels."""
        idx = item.data(Qt.UserRole)
        if idx is None or idx >= len(self._queue):
            return
        info = self._queue[idx]
        rect = self.queue_list.visualItemRect(item)
        if rect.height() <= 0:
            return  # item not currently visible

        editor = QLineEdit(self.queue_list.viewport())
        editor.setText(info.get('custom_name') or info.get('title') or '')
        editor.selectAll()
        editor.setStyleSheet("""
            QLineEdit {
                background: #1a1b26;
                color: #c0caf5;
                border: 2px solid #c88cdc;
                border-radius: 5px;
                padding: 3px 8px;
                font-size: 14px;
                selection-background-color: #c88cdc;
                selection-color: #1a1b26;
            }
        """)
        # Sit over the title area — past the thumbnail (~88 px), comfortable height.
        thumb = ICON_QUEUE.width()
        editor.setGeometry(rect.x() + thumb + 8, rect.y() + 6,
                           rect.width() - thumb - 16, 28)
        editor.show()
        editor.setFocus(Qt.OtherFocusReason)

        committed = {'done': False}

        def commit():
            if committed['done']:
                return
            committed['done'] = True
            new_name = editor.text().strip()
            editor.deleteLater()
            if not new_name:
                return
            info['custom_name'] = new_name
            author = info.get('author') or '?'
            dur = _format_dur(info.get('length') or 0)
            item.setText(f"  {new_name}\n  {author}  ·  {dur}")
            item.setToolTip(f"{new_name}\n원본: {info.get('title','')}\n{info['url']}")

        def cancel():
            if committed['done']:
                return
            committed['done'] = True
            editor.deleteLater()

        # Enter / focus-loss commit; Esc cancels.
        editor.returnPressed.connect(commit)
        editor.editingFinished.connect(commit)
        # keyPressEvent override for Esc — install via subclass-on-fly
        original_keypress = editor.keyPressEvent
        def keypress(ev):
            if ev.key() == Qt.Key_Escape:
                cancel()
                return
            original_keypress(ev)
        editor.keyPressEvent = keypress

    def remove_queue_selected(self):
        rows = sorted(
            {self.queue_list.row(self.queue_list.item(i))
             for i in range(self.queue_list.count())
             if self.queue_list.item(i).isSelected()},
            reverse=True
        )
        for r in rows:
            self.queue_list.takeItem(r)
        self._rebuild_queue_indices()

    def clear_queue(self):
        self.queue_list.clear()
        self._queue = []
        self._refresh_counters()

    def _rebuild_queue_indices(self):
        new_q = []
        for i in range(self.queue_list.count()):
            item = self.queue_list.item(i)
            old_idx = item.data(Qt.UserRole)
            new_idx = len(new_q)
            new_q.append(self._queue[old_idx])
            item.setData(Qt.UserRole, new_idx)
        self._queue = new_q
        self._refresh_counters()

    # -------------------------------------------------------------- misc
    def browse_dest(self):
        d = QFileDialog.getExistingDirectory(
            self, "저장 폴더 선택",
            self.dest_input.text() or str(Path.home())
        )
        if d:
            self.dest_input.setText(d)

    def open_dest_folder(self):
        """Open the configured destination folder in Windows Explorer."""
        path = (self.dest_input.text() or str(Path.home())).strip()
        if not os.path.isdir(path):
            self._toast_warn("폴더 열기", f"폴더가 존재하지 않습니다:\n{path}")
            return
        try:
            os.startfile(path)   # Windows-native; opens folder in Explorer
        except OSError as e:
            self._toast_warn("폴더 열기", str(e))

    # ---------------------------------------------------------- DOWNLOAD
    def download_all(self):
        items = [dict(q) for q in self._queue]
        if not items:
            self._toast_info("다운로드", "대기열이 비어있습니다.")
            return

        video = self.fmt_video.isChecked()
        audio = self.fmt_audio.isChecked()
        if not video and not audio:
            self._toast_warn("형식 선택", "비디오 또는 오디오 중 하나 이상을 선택해주세요.")
            return

        dest = self.dest_input.text().strip()
        if not dest:
            self._toast_warn("다운로드", "저장 경로를 설정해주세요.")
            return

        if self._download_worker and self._download_worker.isRunning():
            self._toast_info("다운로드", "이미 다운로드가 진행 중입니다.")
            return

        # Per-item filenames already get applied via the queue's inline rename
        # (✎ button / double-click), which writes into info['custom_name'].
        if video and audio:
            mode, include_audio = 'video', True
        elif video:
            mode, include_audio = 'video', False
        else:  # audio only
            mode, include_audio = 'mp3', True

        opts = {
            'mode': mode,
            'resolution': self._resolution_value(),
            'include_audio': include_audio,
            'dest': dest,
            'prefix': self.prefix_input.text().strip(),
        }

        self.log(f"=== {len(items)}개 다운로드 시작 → {dest} ===")
        # Each item contributes a 100-unit slot to the bar — gives us
        # smooth per-item progress (0–90 % download, 90–100 % post-process)
        # AND a "completed/total" counter that only ticks when an item is
        # fully done.
        self._dl_total = len(items)
        self.progress_bar.setRange(0, len(items) * 100)
        self.progress_bar.setValue(0)
        self.progress_caption.setText(f"0 / {len(items)}")

        self._download_worker = DownloadWorker(items, opts)
        self._download_worker.log.connect(self.log)
        self._download_worker.progress.connect(self._on_dl_progress)
        self._download_worker.finished_all.connect(self._on_dl_finished)
        self._download_worker.start()
        self._update_download_btn()

    def _resolution_value(self) -> str:
        mapping = {"최고 화질": "Highest", "최저 화질": "Lowest"}
        return mapping.get(self.res_combo.currentText(), self.res_combo.currentText())

    def _on_dl_progress(self, items_completed: int, pct_in_current: int):
        """Maps DownloadWorker's `(items_completed, pct_in_current 0-100)`
        signal onto the progress bar. The bar's range was set to
        `total * 100` at start, so we read `items_completed * 100 +
        pct_in_current` directly. Counter shows completed-vs-total."""
        total = getattr(self, '_dl_total', 0) or 1
        self.progress_bar.setValue(items_completed * 100 + pct_in_current)
        self.progress_caption.setText(f"{items_completed} / {total}")

    def _on_dl_finished(self):
        self.log("=== 모든 다운로드 완료 ===")
        self._update_download_btn()
        self._toast_success("완료", "모든 다운로드가 완료되었습니다.")

    def closeEvent(self, e):
        if self._audio_player is not None:
            try:
                self._audio_player.stop()
                # Drop the current media so the file isn't held when we delete it.
                self._audio_player.setMedia(QMediaContent())
            except Exception:
                pass
        for w in [self._search_worker, self._fetch_worker, self._download_worker,
                  self._suggest_worker, self._load_more_worker,
                  self._audio_worker, self._update_check_worker,
                  *self._thumb_workers]:
            if w and w.isRunning():
                if hasattr(w, 'cancel'):
                    w.cancel()
                w.requestInterruption()
                w.quit()
                w.wait(2000)
        # Clean up the temp audio cache.
        try:
            shutil.rmtree(self._audio_cache_dir, ignore_errors=True)
        except Exception:
            pass
        super().closeEvent(e)


def _resource_path(name: str) -> str:
    """Resolve a bundled resource path — works both when running from source
    and when running inside a PyInstaller --onefile build."""
    base = getattr(sys, '_MEIPASS', None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, name)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ut_download")
    base_font = QFont("Segoe UI", 9)
    base_font.setHintingPreference(QFont.PreferDefaultHinting)
    app.setFont(base_font)

    # Fluent theme — must be set BEFORE any Fluent widget is constructed.
    setTheme(Theme.DARK)
    setThemeColor("#7aa2f7")  # Tokyo-Night accent — keeps our brand color

    # App / window icon — same logo for taskbar, title bar, and Alt-Tab.
    logo_path = _resource_path('logo.ico')
    if os.path.isfile(logo_path):
        app.setWindowIcon(QIcon(logo_path))

    # Layer our custom QSS on top of Fluent's so our bespoke widgets
    # (audio player bar, sentinel row, badges, etc.) keep their look.
    icon_paths = ensure_checkbox_icons()
    app.setStyleSheet(build_qss(icon_paths))

    w = MainWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
