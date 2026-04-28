"""Download workers for ut_download. Made by Daru.

Backend: yt-dlp. Switched from pytubefix in v1.4 — yt-dlp is faster
(flat ytsearch returns just IDs/titles/durations in one round-trip,
no per-video page fetches), more bot-resistant, and tracks the
YouTube API quickly when it changes.
"""
import os
import re
import sys
import shutil
import subprocess
import threading
from collections import OrderedDict

from PyQt5.QtCore import QThread, pyqtSignal

import yt_dlp


# itag 140 = m4a/AAC 128 kbps. Same audio spec as v1.0–v1.3 builds — keeps
# the audio-preview cache key stable, and the MP3 transcode chain unchanged.
# Fallback chain on itag 140 → bestaudio[ext=m4a] → bestaudio handles
# Music-Premium-locked tracks where 140 isn't published to non-auth clients.
AUDIO_FORMAT = "140/bestaudio[ext=m4a]/bestaudio"

# yt-dlp tries clients in order; the first one that successfully extracts
# wins, so `default` stays first to keep the common-case fast. The rest
# are fallbacks for: bot detection (`ios`), age gate (`tv_embedded`), embed
# restrictions (`web_embedded`), and Music-Premium / DRM-style locks where
# the `web` client is blocked but `android` still extracts (`android`).
# Mirrors the role of v1.3's pytubefix client cycle.
_YT_PLAYER_CLIENTS = [
    'default', 'android', 'ios', 'tv_embedded', 'web_embedded', 'mweb',
]


def _yt_extractor_args() -> dict:
    return {'youtube': {'player_client': list(_YT_PLAYER_CLIENTS)}}


# ----------------------------------------------------------------- yt-dlp opts
def _ydl_search_opts() -> dict:
    """Flat search — only IDs/titles/durations/channels. ~1 round-trip."""
    return {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': 'in_playlist',
        'skip_download': True,
        'noplaylist': True,
        'socket_timeout': 12,
        'extractor_args': _yt_extractor_args(),
    }


def _ydl_info_opts() -> dict:
    """Single-URL metadata. Slower than flat but full title/length/etc."""
    return {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
        'socket_timeout': 15,
        'extractor_args': _yt_extractor_args(),
    }


def _entry_to_dict(entry: dict) -> dict:
    """Normalize a yt-dlp entry to our internal video dict shape."""
    vid = (entry.get('id') or '').strip()
    title = entry.get('title') or '?'
    # `channel` is populated by ytsearch; `uploader` by direct video pages.
    author = entry.get('channel') or entry.get('uploader') or ''
    duration = entry.get('duration')
    length = int(duration) if duration else 0
    if vid:
        url = f"https://www.youtube.com/watch?v={vid}"
    else:
        url = entry.get('webpage_url') or entry.get('url') or ''
    return {
        'title': title,
        'author': author,
        'length': length,
        'url': url,
        'video_id': vid,
    }


# ------------------------------------------------------------------- search
class _YdlSearch:
    """Adapter that holds query + accumulated entries. Mirrors the role
    that pytubefix's `Search` object played for us — SearchWorker stashes
    it so LoadMoreWorker can ask for `fetch_more` later. yt-dlp has no
    cursor for ytsearch, so "more" widens N and slices what's new — the
    extra cost is minor since the InnerTube round-trip dominates anyway.
    """

    def __init__(self, query: str):
        self.query = query
        self._fetched = 0
        self._entries: list = []
        self._exhausted = False

    @property
    def entries(self) -> list:
        return list(self._entries)

    def fetch_initial(self, n: int) -> list:
        with yt_dlp.YoutubeDL(_ydl_search_opts()) as ydl:
            info = ydl.extract_info(f"ytsearch{n}:{self.query}", download=False)
        raw = (info or {}).get('entries') or []
        out = [_entry_to_dict(e) for e in raw if e]
        self._entries = out
        self._fetched = n
        return out

    def fetch_more(self, batch: int = 5) -> list:
        if self._exhausted:
            return []
        target = max(self._fetched + batch, len(self._entries) + batch)
        with yt_dlp.YoutubeDL(_ydl_search_opts()) as ydl:
            info = ydl.extract_info(f"ytsearch{target}:{self.query}",
                                    download=False)
        raw = (info or {}).get('entries') or []
        all_out = [_entry_to_dict(e) for e in raw if e]
        if len(all_out) <= len(self._entries):
            self._exhausted = True
            return []
        new = all_out[len(self._entries):]
        self._entries = all_out
        self._fetched = target
        return new


def _make_search(query: str, *, max_results: int = 25):
    """Returns (search_obj, videos)."""
    s = _YdlSearch(query)
    videos = s.fetch_initial(max_results)
    if not videos:
        raise RuntimeError("검색 결과가 없습니다")
    return s, videos


def _yt_info(url: str) -> dict:
    """Fetch single-video metadata (for the URL-paste flow)."""
    with yt_dlp.YoutubeDL(_ydl_info_opts()) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise RuntimeError("영상 정보를 찾을 수 없습니다")
    return _entry_to_dict(info)


# -------------------------------------------------------------------- cache
# In-memory result cache. Keyed by lowercased+stripped query. LRU-ish:
# new entries push the oldest out once we hit `_CACHE_MAX`. Repeat searches
# (even after the user clicked "load more") get an instant repaint from the
# cache before any network call. Process-lifetime only — no disk persist.
_CACHE_MAX = 32
_QUERY_CACHE: "OrderedDict[str, dict]" = OrderedDict()
_CACHE_LOCK = threading.Lock()


def _cache_key(q: str) -> str:
    return q.strip().lower()


def cache_get(query: str):
    """Return entry {'results', 'search_obj', 'offset', 'exhausted'} or None.
    Touching an entry promotes it (LRU)."""
    with _CACHE_LOCK:
        key = _cache_key(query)
        entry = _QUERY_CACHE.get(key)
        if entry is not None:
            _QUERY_CACHE.move_to_end(key)
        return entry


def cache_put(query: str, results, search_obj, *, offset: int = None,
              exhausted: bool = False):
    with _CACHE_LOCK:
        key = _cache_key(query)
        if key in _QUERY_CACHE:
            _QUERY_CACHE.move_to_end(key)
        elif len(_QUERY_CACHE) >= _CACHE_MAX:
            _QUERY_CACHE.popitem(last=False)        # drop oldest
        _QUERY_CACHE[key] = {
            'results': list(results),
            'search_obj': search_obj,
            'offset': offset if offset is not None else len(results),
            'exhausted': exhausted,
        }


def cache_extend(query: str, more_results, *, exhausted: bool = False):
    """Append additional batch (from LoadMoreWorker) to an existing entry."""
    with _CACHE_LOCK:
        entry = _QUERY_CACHE.get(_cache_key(query))
        if entry is None:
            return
        entry['results'].extend(more_results)
        entry['offset'] = len(entry['results'])
        entry['exhausted'] = exhausted


# --------------------------------------------------------------- file utils
def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', '_', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:180] if len(name) > 180 else name


def find_ffmpeg() -> str:
    """Return path to ffmpeg.exe — bundled, alongside exe, then PATH."""
    candidates = []
    if hasattr(sys, '_MEIPASS'):
        candidates.append(os.path.join(sys._MEIPASS, 'ffmpeg.exe'))
    exe_dir = os.path.dirname(os.path.abspath(sys.argv[0])) if sys.argv else os.getcwd()
    candidates.append(os.path.join(exe_dir, 'ffmpeg.exe'))
    candidates.append(os.path.join(exe_dir, 'ffmpeg', 'bin', 'ffmpeg.exe'))
    candidates.append(r'C:\ffmpeg\bin\ffmpeg.exe')
    for c in candidates:
        if os.path.isfile(c):
            return c
    found = shutil.which('ffmpeg')
    if found:
        return found
    return 'ffmpeg'


def _no_window_kwargs():
    """Hide ffmpeg console window on Windows."""
    if os.name == 'nt':
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {'startupinfo': si, 'creationflags': subprocess.CREATE_NO_WINDOW}
    return {}


# --------------------------------------------------------------- yt-dlp dl
def _ydl_download(url: str, *, fmt: str, outtmpl: str, ffmpeg_loc: str = None,
                  progress_hook=None, merge_format: str = None) -> str:
    """Run yt-dlp on a single URL, return the saved filepath.
    `outtmpl` should include `%(ext)s` so yt-dlp picks the actual extension."""
    saved = []

    def hook_collect(d):
        if d.get('status') == 'finished' and d.get('filename'):
            saved.append(d['filename'])

    hooks = [hook_collect]
    if progress_hook:
        hooks.append(progress_hook)

    opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'format': fmt,
        'outtmpl': outtmpl,
        'overwrites': True,
        'continuedl': False,
        'progress_hooks': hooks,
        'extractor_args': _yt_extractor_args(),
    }
    if ffmpeg_loc:
        opts['ffmpeg_location'] = ffmpeg_loc
    if merge_format:
        opts['merge_output_format'] = merge_format

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # Most reliable post-merge path is in info['requested_downloads'].
    if info:
        rd = info.get('requested_downloads')
        if rd and isinstance(rd, list):
            fp = rd[0].get('filepath')
            if fp and os.path.isfile(fp):
                return fp
        for k in ('filepath', '_filename'):
            fp = info.get(k)
            if fp and os.path.isfile(fp):
                return fp
    if saved and os.path.isfile(saved[-1]):
        return saved[-1]
    raise RuntimeError("yt-dlp 다운로드 실패: 출력 파일을 찾을 수 없습니다")


# -------------------------------------------------------------------- workers
class SearchWorker(QThread):
    """Initial search. Streams results to the UI as they parse instead of
    waiting for the whole list, so the first row paints almost as soon as
    the Search() round-trip returns. On a cache hit, dumps everything that
    was previously loaded for the query in one go (still feels instant).

    Signal contract:
      cache_hit(list, search_obj)   — instant batch on repeat queries
      started_search(search_obj)    — Search resolved; UI hides spinner
      one_result(dict)              — per-video append
      finished_loading(int)         — done; count of videos delivered
      error(str)                    — failure path
    """
    cache_hit        = pyqtSignal(list, object)
    started_search   = pyqtSignal(object)
    one_result       = pyqtSignal(dict)
    finished_loading = pyqtSignal(int)
    error            = pyqtSignal(str)

    def __init__(self, query: str, initial_count: int = 10):
        super().__init__()
        self.query = query
        self.initial_count = initial_count
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        cached = cache_get(self.query)
        if cached:
            self.cache_hit.emit(list(cached['results']), cached['search_obj'])
            return
        try:
            s, videos = _make_search(self.query, max_results=self.initial_count)
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")
            return
        if self._cancelled:
            return
        self.started_search.emit(s)
        for info in videos:
            if self._cancelled:
                return
            self.one_result.emit(info)
        cache_put(self.query, videos, s, offset=len(videos), exhausted=False)
        self.finished_loading.emit(len(videos))


class LoadMoreWorker(QThread):
    """Fetch the next batch from the cached _YdlSearch. `query` is optional
    — when supplied, the new batch is appended to the cached entry so a
    subsequent repeat search restores the full scrolled-through list."""
    new_results = pyqtSignal(list)

    def __init__(self, search_obj, current_offset: int, batch_size: int = 5,
                 query: str = ""):
        super().__init__()
        self.search_obj = search_obj
        self.current_offset = current_offset
        self.batch_size = batch_size
        self.query = query

    def run(self):
        try:
            new = self.search_obj.fetch_more(self.batch_size)
            if self.query:
                cache_extend(self.query, new, exhausted=(not new))
            self.new_results.emit(new)
        except Exception:
            self.new_results.emit([])


class FetchInfoWorker(QThread):
    """Fetch info for a pasted URL without blocking the UI."""
    finished_info = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            info = _yt_info(self.url)
            self.finished_info.emit(info)
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")


class SuggestWorker(QThread):
    """YouTube search suggestions for the autocomplete dropdown.
    Hits Google's suggestqueries endpoint directly — no yt-dlp involved."""
    suggestions = pyqtSignal(list)

    def __init__(self, query: str):
        super().__init__()
        self.query = query

    def run(self):
        try:
            import json
            import urllib.parse
            import urllib.request
            url = (
                "https://suggestqueries.google.com/complete/search"
                f"?client=firefox&ds=yt&q={urllib.parse.quote(self.query)}"
            )
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=4) as resp:
                raw = resp.read().decode('utf-8', errors='ignore')
            data = json.loads(raw)
            if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
                items = [s for s in data[1] if isinstance(s, str)][:10]
                self.suggestions.emit(items)
        except Exception:
            # silent on suggest errors — autocomplete must never block UX
            pass


class ThumbnailWorker(QThread):
    """Fetch YouTube thumbnails in parallel (i.ytimg.com directly, not yt-dlp)."""
    loaded = pyqtSignal(str, bytes)
    finished_all = pyqtSignal()

    def __init__(self, video_ids, max_workers: int = 6):
        super().__init__()
        self.video_ids = [v for v in video_ids if v]
        self.max_workers = max_workers
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        import urllib.request
        from concurrent.futures import ThreadPoolExecutor

        def fetch(vid: str):
            if self._cancelled:
                return vid, None
            for sub in ('mqdefault.jpg', 'hqdefault.jpg', 'default.jpg'):
                try:
                    url = f"https://i.ytimg.com/vi/{vid}/{sub}"
                    req = urllib.request.Request(
                        url, headers={'User-Agent': 'Mozilla/5.0'}
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        return vid, resp.read()
                except Exception:
                    continue
            return vid, None

        try:
            with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
                for vid, data in ex.map(fetch, self.video_ids):
                    if self._cancelled:
                        break
                    if data:
                        self.loaded.emit(vid, data)
        finally:
            self.finished_all.emit()


class AudioDownloadWorker(QThread):
    """Download itag 140 (m4a/AAC) via yt-dlp, then transcode to MP3.

    Why MP3? Qt's Windows backend (DirectShow) can't decode raw AAC/m4a on
    every Windows install — playing the .m4a directly throws DirectShow
    error 0x80040266 (no decoder for format). MP3 is decoded natively.
    Once cached on disk subsequent plays of the same video are instant.
    """
    file_ready = pyqtSignal(str, str)
    error = pyqtSignal(str, str)

    def __init__(self, video_url: str, video_id: str, dest_dir: str):
        super().__init__()
        self.video_url = video_url
        self.video_id = video_id
        self.dest_dir = dest_dir

    def run(self):
        try:
            os.makedirs(self.dest_dir, exist_ok=True)
            cached = os.path.join(self.dest_dir, f"{self.video_id}.mp3")
            if os.path.isfile(cached) and os.path.getsize(cached) > 0:
                self.file_ready.emit(self.video_id, cached)
                return

            ff = find_ffmpeg()
            ff_dir = os.path.dirname(ff) if os.path.isfile(ff) else None
            tmpl = os.path.join(self.dest_dir, f"_tmp_{self.video_id}.%(ext)s")
            try:
                m4a_path = _ydl_download(
                    self.video_url, fmt=AUDIO_FORMAT, outtmpl=tmpl,
                    ffmpeg_loc=ff_dir,
                )
            except Exception as e:
                self.error.emit(self.video_id, f"오디오 다운로드 실패: {e}")
                return

            cmd = [ff, '-y', '-loglevel', 'error',
                   '-i', m4a_path,
                   '-vn', '-acodec', 'libmp3lame', '-b:a', '128k',
                   cached]
            try:
                r = subprocess.run(cmd, capture_output=True, **_no_window_kwargs())
            finally:
                try:
                    os.remove(m4a_path)
                except OSError:
                    pass
            if r.returncode != 0:
                err = r.stderr.decode('utf-8', errors='ignore')[:300]
                self.error.emit(self.video_id, f"ffmpeg 변환 실패: {err}")
                return
            self.file_ready.emit(self.video_id, cached)
        except Exception as e:
            self.error.emit(self.video_id, f"{type(e).__name__}: {e}")


class DownloadWorker(QThread):
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)        # current_index, total_items
    item_done = pyqtSignal(int, bool, str)  # index_in_batch, ok, message
    finished_all = pyqtSignal()

    def __init__(self, items, options):
        super().__init__()
        self.items = items
        self.options = options
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        ff = find_ffmpeg()
        ff_dir = os.path.dirname(ff) if os.path.isfile(ff) else None
        total = len(self.items)
        for i, item in enumerate(self.items):
            if self._cancelled:
                self.log.emit("취소되었습니다.")
                break
            self.progress.emit(i + 1, total)
            title = item.get('title', item['url'])
            self.log.emit(f"[{i+1}/{total}] {title}")
            try:
                if self.options['mode'] == 'mp3':
                    out = self._download_mp3(item, ff, ff_dir, batch_index=i)
                else:
                    out = self._download_video(item, ff, ff_dir, batch_index=i)
                self.log.emit(f"  ✔ 저장됨: {out}")
                self.item_done.emit(i, True, out)
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                self.log.emit(f"  ✘ 오류: {msg}")
                self.item_done.emit(i, False, msg)
        self.finished_all.emit()

    # ------------------------------------------------------------------
    def _make_progress_hook(self, label: str):
        last = [-10]

        def hook(d):
            if d.get('status') != 'downloading':
                return
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            if not total:
                return
            done = d.get('downloaded_bytes') or 0
            pct = int(done * 100 / total)
            if pct >= last[0] + 10:
                last[0] = pct
                self.log.emit(f"    {label} {pct}%")
        return hook

    def _output_basename(self, item, batch_index: int) -> str:
        title = item.get('title') or 'video'
        custom = (item.get('custom_name') or '').strip()
        if custom:
            return sanitize_filename(custom)
        prefix = (self.options.get('prefix') or '').strip()
        if prefix:
            return sanitize_filename(f"{prefix}_{title}")
        return sanitize_filename(title)

    def _unique_path(self, dest_dir: str, basename: str, ext: str) -> str:
        candidate = os.path.join(dest_dir, f"{basename}.{ext}")
        if not os.path.exists(candidate):
            return candidate
        n = 2
        while True:
            candidate = os.path.join(dest_dir, f"{basename} ({n}).{ext}")
            if not os.path.exists(candidate):
                return candidate
            n += 1

    @staticmethod
    def _video_format(target: str) -> str:
        """Map the UI's resolution selector to a yt-dlp format string."""
        if target == 'Highest':
            return "bestvideo[ext=mp4]/bestvideo"
        if target == 'Lowest':
            return "worstvideo[ext=mp4]/worstvideo"
        m = re.search(r'(\d+)', target)
        h = int(m.group(1)) if m else 720
        return (f"bestvideo[ext=mp4][height<={h}]/"
                f"bestvideo[height<={h}]/bestvideo")

    @staticmethod
    def _video_only_format(target: str) -> str:
        """Same as `_video_format` but with combined-stream fallbacks for
        locked content (Music Premium, DRM, age-gated, etc.) where a pure
        video-only stream isn't published."""
        base = DownloadWorker._video_format(target)
        # Fall through to single-file combined formats if no DASH video.
        return f"{base}/best[ext=mp4]/best"

    # ------------------------------------------------------------------
    def _download_mp3(self, item, ff: str, ff_dir, batch_index: int) -> str:
        dest = self.options['dest']
        os.makedirs(dest, exist_ok=True)
        base = self._output_basename(item, batch_index)
        out_path = self._unique_path(dest, base, 'mp3')

        tmpl = os.path.join(dest, f"_tmp_audio_{batch_index}_{os.getpid()}.%(ext)s")
        self.log.emit("    오디오 다운로드 중…")
        m4a_path = _ydl_download(
            item['url'], fmt=AUDIO_FORMAT, outtmpl=tmpl,
            ffmpeg_loc=ff_dir,
            progress_hook=self._make_progress_hook("오디오"),
        )

        self.log.emit("    MP3로 인코딩 중…")
        cmd = [ff, '-y', '-loglevel', 'error',
               '-i', m4a_path,
               '-vn', '-acodec', 'libmp3lame', '-b:a', '192k',
               out_path]
        try:
            r = subprocess.run(cmd, capture_output=True, **_no_window_kwargs())
        finally:
            try:
                os.remove(m4a_path)
            except OSError:
                pass
        if r.returncode != 0:
            err = r.stderr.decode('utf-8', errors='ignore')[:400]
            raise RuntimeError(f"ffmpeg 실패: {err}")
        return out_path

    def _download_video(self, item, ff: str, ff_dir, batch_index: int) -> str:
        dest = self.options['dest']
        os.makedirs(dest, exist_ok=True)
        base = self._output_basename(item, batch_index)
        v_filter = self._video_format(self.options.get('resolution', 'Highest'))

        if not self.options.get('include_audio', True):
            # video-only (with combined-stream fallback for locked content)
            out_path = self._unique_path(dest, base + ' (영상만)', 'mp4')
            tmpl = os.path.join(dest, f"_tmp_v_{batch_index}_{os.getpid()}.%(ext)s")
            self.log.emit("    비디오 다운로드 중…")
            v_path = _ydl_download(
                item['url'],
                fmt=self._video_only_format(self.options.get('resolution', 'Highest')),
                outtmpl=tmpl,
                ffmpeg_loc=ff_dir,
                progress_hook=self._make_progress_hook("비디오"),
            )
            try:
                if os.path.exists(out_path):
                    os.remove(out_path)
                os.rename(v_path, out_path)
            except OSError as e:
                raise RuntimeError(f"파일명 변경 실패: {e}")
            return out_path

        # video + audio merge — yt-dlp does it inline when given ffmpeg.
        out_path = self._unique_path(dest, base, 'mp4')
        tmpl = os.path.join(dest, f"_tmp_va_{batch_index}_{os.getpid()}.%(ext)s")
        fmt = f"{v_filter}+{AUDIO_FORMAT}/best[ext=mp4]/best"
        self.log.emit("    비디오 + 오디오 다운로드 + 병합 중…")
        merged = _ydl_download(
            item['url'], fmt=fmt, outtmpl=tmpl,
            ffmpeg_loc=ff_dir, merge_format='mp4',
            progress_hook=self._make_progress_hook("비디오"),
        )
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
            os.rename(merged, out_path)
        except OSError as e:
            raise RuntimeError(f"파일명 변경 실패: {e}")
        return out_path
