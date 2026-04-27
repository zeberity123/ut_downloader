"""Dark theme stylesheet for ut_download. Made by Daru."""

# Tokyo Night–inspired palette
COL_BG          = "#1a1b26"
COL_BG_SOFT     = "#1f2335"
COL_BG_LIST     = "#16161e"
COL_BORDER      = "#292e42"
COL_BORDER_S    = "#414868"
COL_TEXT        = "#c0caf5"
COL_TEXT_DIM    = "#a9b1d6"
COL_TEXT_MUTE   = "#565f89"
COL_ACCENT      = "#7aa2f7"   # blue
COL_ACCENT_2    = "#bb9af7"   # purple
COL_ACCENT_3    = "#7dcfff"   # cyan
COL_DANGER      = "#f7768e"   # red / pink
COL_OK          = "#9ece6a"   # green
COL_WARN        = "#e0af68"   # amber / yellow
COL_ORANGE      = "#ff9e64"
COL_MAGENTA     = "#ad8ee6"

DARK_QSS = f"""
* {{
    font-family: "Segoe UI", "Malgun Gothic", "맑은 고딕", sans-serif;
    font-size: 11px;
}}

QMainWindow, QWidget#central, QWidget#rightPane {{
    background-color: {COL_BG};
    color: {COL_TEXT};
}}

/* Right-side widgets render at the same size as the search bar (heroInput).
   This is intentionally narrow — only the right pane and its descendants. */
QWidget#rightPane,
QWidget#rightPane QLabel,
QWidget#rightPane QCheckBox,
QWidget#rightPane QRadioButton,
QWidget#rightPane QPushButton,
QWidget#rightPane QLineEdit,
QWidget#rightPane QComboBox,
QWidget#rightPane QTextEdit,
QWidget#rightPane QListWidget,
QWidget#rightPane QListWidget::item,
QWidget#rightPane QGroupBox,
QWidget#rightPane QProgressBar {{
    font-size: 13px;
}}

QWidget#rightPane QGroupBox::title {{
    font-size: 12px;
}}

/* Bump every input/label inside the Download Options card. Higher cascade
   specificity than the generic rightPane rule (1 ID + 1 ID + 1 type vs 1 ID
   + 1 type) so this wins. Fluent widgets still get a per-widget override
   below where stronger cascade is required. */
QGroupBox#optionsBox QLabel,
QGroupBox#optionsBox QCheckBox,
QGroupBox#optionsBox QLineEdit,
QGroupBox#optionsBox QComboBox,
QGroupBox#optionsBox QPushButton {{
    font-size: 15px;
}}

QLabel {{
    color: {COL_TEXT};
    background: transparent;
}}

QLabel#headerTitle {{
    color: {COL_TEXT};
    font-size: 20px;
    font-weight: 800;
    padding: 2px 0;
}}

QLabel#headerSub {{
    color: {COL_TEXT_DIM};
    font-size: 12px;
    padding-bottom: 2px;
}}

QLabel#sectionLabel {{
    color: {COL_TEXT_DIM};
    font-weight: 600;
}}

QLabel#counterLabel {{
    color: {COL_ACCENT_3};
    font-weight: 600;
    padding: 0 4px;
}}

QLabel#footer {{
    color: {COL_TEXT_MUTE};
    font-size: 11px;
    padding: 4px 8px 0 0;
}}

/* Group boxes */
QGroupBox {{
    background-color: {COL_BG_SOFT};
    border: 1px solid {COL_BORDER};
    border-radius: 10px;
    margin-top: 10px;
    padding: 6px 8px 6px 8px;
    font-weight: 600;
    color: {COL_TEXT};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    top: -1px;
    padding: 3px 12px;
    color: {COL_ACCENT};
    background-color: {COL_BG};
    border: 1px solid {COL_BORDER};
    border-radius: 8px;
    font-weight: 800;
    font-size: 11px;
}}

/* Per-section title colors + colored top-accent border (a "ribbon" on each card) */
QGroupBox#optionsBox {{
    border-top: 3px solid {COL_ACCENT_2};
}}
QGroupBox#optionsBox::title {{
    color: {COL_ACCENT_2};   /* purple — option config */
}}

QGroupBox#queueBox {{
    border-top: 3px solid {COL_ORANGE};
}}
QGroupBox#queueBox::title {{
    color: {COL_ORANGE};     /* orange — pending queue */
}}

QGroupBox#downloadBox {{
    border-top: 3px solid {COL_OK};
}}
QGroupBox#downloadBox::title {{
    color: {COL_OK};         /* green — go */
}}

/* Inputs */
/* QTextEdit only — log view. Fluent now styles QLineEdit / QComboBox itself. */
QTextEdit {{
    background-color: {COL_BG};
    border: 1px solid {COL_BORDER};
    border-radius: 6px;
    padding: 5px 9px;
    color: {COL_TEXT};
    selection-background-color: {COL_ACCENT};
    selection-color: {COL_BG};
}}

QTextEdit:focus {{
    border: 1px solid {COL_ACCENT};
    background-color: {COL_BG_SOFT};
}}

QTextEdit#logView {{
    background-color: {COL_BG_LIST};
    color: {COL_TEXT_DIM};
    font-family: "Cascadia Mono", "Consolas", "D2Coding", monospace;
    font-size: 11px;
    border-radius: 8px;
    padding: 8px 10px;
}}

/* Buttons — generic rules removed; Fluent widgets style themselves.
   Object-name rules below still apply to our custom audio-player buttons. */

/* Primary download button */
QPushButton#downloadBtn {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {COL_ACCENT_3}, stop:0.5 {COL_ACCENT}, stop:1 {COL_ACCENT_2}
    );
    color: {COL_BG};
    border: none;
    border-radius: 12px;
    padding: 12px 20px;
    font-size: 14px;
    font-weight: 800;
}}

QPushButton#downloadBtn:hover {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #89dceb, stop:0.5 #89b4fa, stop:1 #cba6f7
    );
}}

QPushButton#downloadBtn:disabled {{
    background-color: {COL_BORDER};
    color: {COL_TEXT_MUTE};
}}

/* Primary button — search / URL add */
QPushButton#primaryBtn {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {COL_ACCENT}, stop:1 {COL_ACCENT_2}
    );
    color: {COL_BG};
    border: none;
    border-radius: 10px;
    padding: 7px 14px;
    font-size: 14px;
    font-weight: 600;
}}

QPushButton#primaryBtn:hover {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #89b4fa, stop:1 #cba6f7
    );
}}

QPushButton#primaryBtn:disabled {{
    background-color: {COL_BORDER};
    color: {COL_TEXT_MUTE};
}}

/* Accent button — "+ 대기열에 추가" */
QPushButton#accentBtn {{
    color: {COL_BG};
    background-color: {COL_ACCENT_3};
    border: none;
    border-radius: 6px;
    font-weight: 700;
    padding: 6px 12px;
}}

QPushButton#accentBtn:hover {{
    background-color: #a8e2ff;
}}

QPushButton#accentBtn:disabled {{
    background-color: {COL_BORDER};
    color: {COL_TEXT_MUTE};
}}

/* Subtle "danger" button (Clear all / Remove) */
QPushButton#dangerBtn {{
    color: {COL_DANGER};
    border: 1px solid {COL_BORDER};
}}

QPushButton#dangerBtn:hover {{
    background-color: rgba(247,118,142, 0.12);
    border-color: {COL_DANGER};
    color: {COL_DANGER};
}}

/* Lists */
QListWidget {{
    background-color: {COL_BG_LIST};
    border: 1px solid {COL_BORDER};
    border-radius: 8px;
    padding: 4px;
    color: {COL_TEXT};
    outline: 0;
    alternate-background-color: {COL_BG};
}}

QListWidget::item {{
    padding: 8px 10px;
    border-radius: 4px;
    margin: 1px 2px;
}}

QListWidget::item:hover {{
    background-color: {COL_BORDER};
}}

QListWidget::item:selected {{
    background-color: {COL_BORDER_S};
    color: {COL_TEXT};
}}

/* QListWidget item-row checkbox indicators (search results).
   Fluent styles its own QCheckBox; only QListWidget keeps our look. */
QListWidget::indicator {{
    width: 20px;
    height: 20px;
    margin-left: 6px;
    margin-right: 14px;
}}

/* Progress bar */
QProgressBar {{
    background-color: {COL_BG_LIST};
    border: 1px solid {COL_BORDER};
    border-radius: 8px;
    text-align: center;
    color: {COL_TEXT};
    font-weight: 700;
    height: 22px;
}}

QProgressBar::chunk {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0     {COL_OK},
        stop:0.33  {COL_ACCENT_3},
        stop:0.66  {COL_ACCENT},
        stop:1     {COL_DANGER}
    );
    border-radius: 7px;
    margin: 1px;
}}

/* Scrollbars */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {COL_BORDER_S};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COL_ACCENT};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {COL_BORDER_S};
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {COL_ACCENT};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
}}

/* Message boxes / file dialogs */
QMessageBox, QFileDialog {{
    background-color: {COL_BG};
    color: {COL_TEXT};
}}
QMessageBox QLabel, QFileDialog QLabel {{
    color: {COL_TEXT};
    background: transparent;
}}
QMessageBox QPushButton {{
    min-width: 84px;
}}

/* ToolTip */
QToolTip {{
    background-color: {COL_BG_SOFT};
    color: {COL_TEXT};
    border: 1px solid {COL_BORDER_S};
    padding: 6px 8px;
    border-radius: 4px;
}}

/* Accent strip — full rainbow gradient for the bottom-edge ribbon */
QFrame#accentStrip {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0    {COL_OK},
        stop:0.20 {COL_ACCENT_3},
        stop:0.40 {COL_ACCENT},
        stop:0.60 {COL_ACCENT_2},
        stop:0.80 {COL_DANGER},
        stop:1    {COL_WARN}
    );
    border: none;
    min-height: 3px;
    max-height: 3px;
    border-radius: 1px;
}}

/* Autocomplete popup (QCompleter) — match the search bar size */
QListView, QAbstractItemView {{
    background-color: {COL_BG_SOFT};
    color: {COL_TEXT};
    border: 1px solid {COL_BORDER};
    border-radius: 6px;
    selection-background-color: {COL_ACCENT};
    selection-color: {COL_BG};
    outline: 0;
    padding: 4px;
    font-size: 13px;
}}
QListView::item, QAbstractItemView::item {{
    padding: 7px 12px;
    border-radius: 4px;
    font-size: 13px;
}}

/* Loading indicator (centered text in results stack) */
QLabel#loadingLabel {{
    color: {COL_ACCENT};
    font-size: 16px;
    font-weight: 500;
    padding: 12px;
}}

/* Compact "browse" button next to the path field */
QPushButton#browseBtn {{
    background-color: {COL_BG};
    border: 1px solid {COL_BORDER_S};
    border-radius: 6px;
    padding: 4px 10px;
    color: {COL_TEXT};
}}
QPushButton#browseBtn:hover {{
    border-color: {COL_ACCENT};
    color: {COL_ACCENT};
}}

/* Player view back/info */
QLabel#playerTitle {{
    color: {COL_TEXT};
    font-size: 13px;
    font-weight: 700;
    padding: 2px 6px;
}}

QPushButton#backBtn {{
    background-color: {COL_BG};
    border: 1px solid {COL_BORDER_S};
    border-radius: 8px;
    padding: 6px 14px;
    color: {COL_TEXT};
    font-weight: 600;
}}

QPushButton#backBtn:hover {{
    border-color: {COL_ACCENT};
    color: {COL_ACCENT};
}}

/* Player slider + status/time labels — horizontal (seek bar) */
QSlider::groove:horizontal {{
    background: {COL_BORDER};
    height: 4px;
    border-radius: 2px;
    margin: 0 4px;
}}
QSlider::handle:horizontal {{
    background: {COL_ACCENT};
    width: 14px;
    height: 14px;
    margin: -6px 0;
    border-radius: 7px;
    border: 2px solid {COL_BG};
}}
QSlider::handle:horizontal:hover {{
    background: #89b4fa;
}}
QSlider::sub-page:horizontal {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {COL_ACCENT_3}, stop:1 {COL_ACCENT}
    );
    border-radius: 2px;
    margin: 0 4px;
}}
QSlider::add-page:horizontal {{
    background: {COL_BORDER};
    border-radius: 2px;
    margin: 0 4px;
}}

/* Vertical variant — same look, used by the volume slider. With
   invertedAppearance(True), sub-page is the LOWER (filled) section. */
QSlider::groove:vertical {{
    background: {COL_BORDER};
    width: 4px;
    border-radius: 2px;
    margin: 4px 0;
}}
QSlider::handle:vertical {{
    background: {COL_ACCENT};
    width: 14px;
    height: 14px;
    margin: 0 -6px;
    border-radius: 7px;
    border: 2px solid {COL_BG};
}}
QSlider::handle:vertical:hover {{
    background: #89b4fa;
}}
/* Volume slider stays uncolored — both sub/add pages render the same neutral
   track. Only the handle moves to indicate level. */
QSlider::sub-page:vertical {{
    background: {COL_BORDER};
    border-radius: 2px;
    margin: 4px 0;
}}
QSlider::add-page:vertical {{
    background: {COL_BORDER};
    border-radius: 2px;
    margin: 4px 0;
}}

QLabel#playerStatus {{
    color: {COL_TEXT_DIM};
    padding: 2px 6px;
    font-size: 12px;
}}

QLabel#playerTime {{
    color: {COL_TEXT_DIM};
    padding: 1px 2px;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 14px;
    font-weight: 600;
}}

/* === Compact audio-player bar (under the search results) === */
QWidget#audioPlayerBar {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0    #1d2336,
        stop:0.5  #25294a,
        stop:1    #221f3a
    );
    border: 1px solid {COL_BORDER};
    border-top: 2px solid {COL_ACCENT_2};
    border-radius: 12px;
}}

QPushButton#playerCtrl {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {COL_BG_SOFT}, stop:1 {COL_BG}
    );
    border: 1px solid {COL_BORDER_S};
    border-radius: 19px;
    color: {COL_TEXT};
    padding: 0;
}}
QPushButton#playerCtrl:hover {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #2a2f47, stop:1 #1f2335
    );
    border: 1px solid {COL_ACCENT};
}}
QPushButton#playerCtrl:pressed {{
    background-color: {COL_BORDER};
    border: 1px solid {COL_ACCENT};
}}
QPushButton#playerCtrl:disabled {{
    background-color: {COL_BG};
    border-color: {COL_BORDER};
}}

QPushButton#playerPlay {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 {COL_ACCENT_3},
        stop:0.5 {COL_ACCENT},
        stop:1 {COL_ACCENT_2}
    );
    border: none;
    border-radius: 25px;
    color: {COL_BG};
    font-size: 16px;
    font-weight: 800;
    padding: 0;
}}
QPushButton#playerPlay:hover {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 #89dceb,
        stop:0.5 #89b4fa,
        stop:1 #cba6f7
    );
}}
QPushButton#playerPlay:pressed {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 {COL_ACCENT}, stop:1 {COL_ACCENT_2}
    );
}}
QPushButton#playerPlay:disabled {{
    background-color: {COL_BORDER};
    color: {COL_TEXT_MUTE};
}}

/* Sentinel row at the bottom of the results list */
QListWidget::item:disabled {{
    color: {COL_TEXT_MUTE};
}}

/* Autoplay toggle inside the audio player bar */
QCheckBox#autoplayCb {{
    color: {COL_TEXT_MUTE};
    font-size: 14px;
    font-weight: 600;
    spacing: 6px;
    padding: 2px 6px;
}}
QCheckBox#autoplayCb:hover {{
    color: {COL_TEXT_DIM};
}}
QCheckBox#autoplayCb:checked {{
    color: {COL_ACCENT_3};
}}

/* Splitter handle — vertical multi-color ribbon between the panes */
QSplitter::handle {{
    background: transparent;
}}
QSplitter::handle:horizontal {{
    width: 8px;
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0    transparent,
        stop:0.15 {COL_OK},
        stop:0.35 {COL_ACCENT_3},
        stop:0.55 {COL_ACCENT_2},
        stop:0.75 {COL_DANGER},
        stop:1    transparent
    );
    margin: 30px 2px;
    border-radius: 4px;
}}
QSplitter::handle:hover {{
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0    transparent,
        stop:0.15 #b9f27c,
        stop:0.35 #89dceb,
        stop:0.55 #cba6f7,
        stop:0.75 #ff8aa1,
        stop:1    transparent
    );
}}

/* Section title above lists */
QLabel#paneTitle {{
    color: {COL_TEXT};
    font-size: 13px;
    font-weight: 700;
    padding: 2px 0;
}}

QLabel#badge {{
    color: {COL_BG};
    background-color: {COL_ACCENT_3};   /* solid cyan — no gradient */
    border-radius: 9px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 800;
    min-width: 18px;
}}

QLabel#badgeMuted {{
    color: {COL_TEXT_DIM};
    background-color: {COL_BORDER};
    border-radius: 9px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 600;
    min-width: 18px;
}}

/* Queue uses an orange badge to differentiate from cyan results badge */
QLabel#queueBadge {{
    color: {COL_BG};
    background-color: {COL_ORANGE};   /* solid orange — no gradient */
    border-radius: 9px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 800;
    min-width: 18px;
}}

/* Section title row */
QLabel#paneTitle {{
    color: {COL_TEXT};
    font-size: 13px;
    font-weight: 800;
    padding: 4px 0;
    letter-spacing: 0.2px;
}}

QLabel#titleGlyphCyan {{
    color: {COL_ACCENT_3};
    font-size: 14px;
    font-weight: 900;
    padding: 0 4px 0 2px;
}}

QLabel#titleGlyphPurple {{
    color: {COL_ACCENT_2};
    font-size: 14px;
    font-weight: 900;
    padding: 0 4px 0 2px;
}}

QLabel#titleGlyphOrange {{
    color: {COL_ORANGE};
    font-size: 14px;
    font-weight: 900;
    padding: 0 4px 0 2px;
}}

QLabel#titleGlyphGreen {{
    color: {COL_OK};
    font-size: 14px;
    font-weight: 900;
    padding: 0 4px 0 2px;
}}

QLabel#titleGlyphPink {{
    color: {COL_DANGER};
    font-size: 14px;
    font-weight: 900;
    padding: 0 4px 0 2px;
}}
"""


def build_qss(checkbox_paths: dict) -> str:
    """Return the full QSS with checkbox indicator images patched in.

    Only QListWidget item rows use our custom indicator now; QCheckBox is
    rendered by Fluent's own widget paint code (with a built-in animation),
    so we no longer try to override it via QSS image: url(...).
    """
    extra = f"""
QListWidget::indicator:unchecked {{
    image: url("{checkbox_paths['unchecked']}");
}}
QListWidget::indicator:checked {{
    image: url("{checkbox_paths['checked']}");
}}
"""
    if 'chevron_down' in checkbox_paths:
        extra += f"""
QComboBox::down-arrow {{
    image: url("{checkbox_paths['chevron_down']}");
    width: 14px;
    height: 14px;
}}
"""
    # NOTE: we previously tried to use a PNG as background-image on
    # QGroupBox#downloadBox::title — Qt's QSS engine doesn't honor
    # `background-position` reliably for the ::title sub-control, so the
    # icon ended up visually centered. We now use a Unicode glyph in the
    # title text instead (see _build_action_box).
    return DARK_QSS + extra

