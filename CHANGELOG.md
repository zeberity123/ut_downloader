# Changelog

All notable changes to **ut_download (유튜브 다운로더 by Daru)** are recorded here.
This project follows a loose form of [Keep a Changelog][keep-a-changelog]; date
format is `YYYY-MM-DD`.

## v1.1 — 2026-04-28

A large iteration on the v1.0 baseline: Fluent UI for the inputs and
buttons, in-app audio preview, colored buttons and dividers, inline
queue rename, and a meaningfully more polished overall feel.

### Added
- **Fluent UI** for primary widgets — `PushButton`, `PrimaryPushButton`,
  `LineEdit`, `ComboBox`, `CheckBox`, plus `InfoBar` toast notifications
  replacing every blocking `QMessageBox.warning/information/critical`.
- **Custom-painted icons** generated procedurally via `QPainter` at
  startup and saved under `%TEMP%`: download glyph, prev / play / pause /
  next, custom checkbox, dropdown chevron.
- **Per-card color identity** — each major card now has its own accent
  ribbon and title color: 다운로드 옵션 (purple), 다운로드 대기열
  (orange), 다운로드 (green).
- **Tinted secondary buttons** — every secondary action carries its own
  ghost-tint color (cyan / green / blue / pink / purple / amber / red /
  magenta) with hover-fill and pressed-saturated states.
- **Multi-color rainbow ribbon** between the left and right panes, with
  a drop-shadow glow that snaps to full brightness on hover and eases
  out over ~320 ms.
- **Audio preview** of any search result: itag-140 m4a is downloaded to
  a temporary cache, transcoded to mp3 with `ffmpeg` (sidesteps
  YouTube's iframe-embed restrictions), then played in-process via
  `QMediaPlayer`.
- **Audio player bar** under the search results: prev / gradient play /
  next buttons, click-to-jump seek bar, monospaced time label, autoplay
  toggle, vertical volume slider with a speaker glyph on the left.
- **Inline rename** for queued downloads — double-click a row or press
  the per-row pencil button to edit the filename in place; the custom
  name flows through to the file written by the download worker.
- **YouTube search suggestions** (autocomplete) via a custom dropdown
  widget. Replaces `QCompleter`, which crashes on Fluent's `LineEdit`.
- **Smooth pixel-precise wheel scrolling** with `OutCubic` easing on
  both the search-results list and the download queue.
- **Sentinel row** at the end of the search results that flips between
  three state-colored hints: scroll-down prompt (cyan), loading more
  (amber), and exhausted (soft red).
- **Configurable splitter** with deferred re-apply so the layout's
  initial pass can't silently override the requested ratio.
- Splitter now defaults to **69 % left / 31 % right**.

### Changed
- Default search batch is **10 results**; **5 more per scroll-end**.
- "찾아보기" → **"폴더위치"** (more descriptive Korean label).
- Download progress bar styling matches the player slider (cyan→blue
  gradient on the filled side).
- Download box title icon swapped from `⤓` to a simpler `↓` glyph.
- Volume slider visual track is uncolored — only the handle moves to
  indicate level (matches typical media-player conventions).

### Removed
- Inline video player (it was hitting YouTube error 152/153 on a
  significant share of videos and the watch-page workaround was too
  cluttered). Audio-only preview is the new default.
- The 단일 항목 `파일명 변경` row in the options card — replaced by the
  per-row inline rename in the queue.
- Unused `QCompleter` plumbing.

### Build
- Switched from `PyQt-Fluent-Widgets` ↔ `PyQt5` only; `PyQtWebEngine` is
  no longer a dependency.
- `PyInstaller` excludes ~40 unused `PyQt5` sub-modules (kept `QtXml`
  because qfluentwidgets needs it). Onefile build: ~46 MB.
- `build.bat` now `--collect-all qfluentwidgets qframelesswindow
  darkdetect` so all Fluent dependencies bundle correctly.

## v1.0 — 2026-04-27

Initial release.

### Added
- PyQt5 GUI (Tokyo Night dark theme), Korean locale.
- Search via `pytubefix`; paste-URL flow on the right pane.
- Download queue with checkbox-driven multi-select, video / audio
  format toggle, resolution picker, configurable destination, rename
  and bulk-prefix fields, animated progress bar.
- Custom-rendered logo (`logo.ico`, 7 resolutions, multi-res ICO).
- Single-file Windows exe via `PyInstaller`, ~39 MB.

[keep-a-changelog]: https://keepachangelog.com/en/1.1.0/
