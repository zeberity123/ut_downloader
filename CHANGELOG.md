# Changelog

All notable changes to **ut_download (유튜브 다운로더 by Daru)** are recorded here.
This project follows a loose form of [Keep a Changelog][keep-a-changelog]; date
format is `YYYY-MM-DD`.

## v1.4 — 2026-04-28

A search-speed pass. Cold search now returns in ~1.2 s instead of 3–8 s
on Korean queries; repeat searches are instant. The backend swap also
ends the cat-and-mouse with YouTube's bot detection that prompted the
v1.3 client-fallback code.

### Added
- **In-memory result cache** keyed by lowercased query. LRU-trimmed at
  32 entries. Repeat searches restore the full scrolled-through list
  (initial 10 + every "load more" batch the user pulled this session)
  without hitting the network. Log shows `(캐시됨)` on a hit.
- **Streaming search results** — rows now appear as they parse instead of
  all-at-once after the full list resolves. Sentinel placement deferred
  to end-of-stream so it stays at the bottom.

### Changed
- **Backend: yt-dlp** (was `pytubefix`).
  - Search uses yt-dlp's flat extractor (`extract_flat='in_playlist'`),
    which returns just IDs / titles / durations / channels in a single
    InnerTube round-trip — no per-video page fetches.
  - Single-URL info via `extract_info(url, download=False)`.
  - Downloads go through `yt_dlp.YoutubeDL` with format selectors
    mapped from the resolution combo (`bestvideo[ext=mp4][height<=N]`
    + itag 140 audio); video+audio merging handled inline by yt-dlp
    when ffmpeg is supplied.
  - `_make_yt` / `_make_search` clients fallback retired — yt-dlp's own
    extractor handles bot evasion + format selection robustly.
- **`_make_search` returns `(search_obj, videos)`** instead of just the
  search object. `SearchWorker` no longer triggers a redundant
  `list(s.videos)` round-trip after verification.
- **`SearchWorker` signal contract**: `cache_hit / started_search /
  one_result / finished_loading / error` — replaces the all-at-once
  `finished_results(list, search_obj)`.

### Build
- `requirements.txt`: `yt-dlp>=2025.1.0` (was `pytubefix>=10.4.0`).
- `build.bat`: `--collect-all yt_dlp` (was `--collect-submodules pytubefix`).
- ffmpeg.exe still bundled inside the onefile build.

## v1.3 — 2026-04-28

### Added
- **Multi-client fallback** for both video info fetch and search.
  YouTube's bot-detection scores requests using the query string and
  the InnerTube client; some Korean queries (e.g. `인기동요 모음`)
  triggered the WEB client's bot heuristic in v1.2 and silently
  returned zero results. v1.3 cycles through `WEB → WEB_EMBED →
  ANDROID_VR → IOS → TV_EMBED` automatically — both on bot-detection
  exceptions and on empty-result responses — until one client passes.
  - `_make_yt(url, on_progress_callback=...)` for `YouTube(...)` calls.
  - `_make_search(query, max_results=N)` for `Search(...)` calls.

### Changed
- **pytubefix `>=10.4.0`** required (was `>=8.0.0`).
- All five `YouTube(...)` / `Search(...)` call-sites in
  `downloader.py` (`SearchWorker`, `LoadMoreWorker`,
  `FetchInfoWorker`, `DownloadWorker`, `AudioDownloadWorker`) routed
  through the helpers.

### Build
- ffmpeg.exe still bundled inside the onefile build.

## v1.2 — 2026-04-28

### Added
- **`폴더열기` button** next to `다운로드 시작` — opens the configured
  destination folder in Windows Explorer (`os.startfile`) without
  leaving the app. Falls back to a warning toast if the path doesn't
  exist.
- New custom-painted **folder icon** (`icons._render_folder_icon`),
  rendered in the same outlined-polyline style as the existing
  download / player glyphs.

### Changed
- `다운로드 시작` button shrunk to ~80 % of the action-row width
  (4:1 stretch ratio); the new `폴더열기` button takes the remaining
  20 %. Both share the same 42 px minimum height.

### Build
- `ffmpeg.exe` continues to be bundled inside the onefile build (no
  external ffmpeg install required on target PCs).

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
