"""Download workers for ut_download. Made by Daru."""
import os
import re
import sys
import shutil
import subprocess

from PyQt5.QtCore import QThread, pyqtSignal

from pytubefix import YouTube, Search

AUDIO_ITAG = 140  # m4a 128kbps — required by spec


# YouTube has been increasingly bot-blocking the default `WEB` client.
# These clients don't require a PO-token and tend to pass; we try them in
# order until one resolves. Order matters: keep WEB first (best metadata)
# and fall through to embed / mobile / TV variants for bot evasion.
_YT_CLIENTS = ("WEB", "WEB_EMBED", "ANDROID_VR", "IOS", "TV_EMBED")


def _is_bot_block(err: Exception) -> bool:
    msg = str(err).lower()
    return any(k in msg for k in ("bot", "detect", "po_token"))


def _make_yt(url: str, on_progress_callback=None):
    """Build a YouTube and force network resolution; fall through clients
    on bot-detection until one succeeds. Raises the last error if all fail."""
    last = None
    for client in _YT_CLIENTS:
        try:
            kwargs = {"client": client}
            if on_progress_callback is not None:
                kwargs["on_progress_callback"] = on_progress_callback
            yt = YouTube(url, **kwargs)
            _ = yt.title          # force a network round-trip
            return yt
        except Exception as e:
            last = e
            if _is_bot_block(e):
                continue
            raise
    raise last if last else RuntimeError("all YouTube clients failed")


def _make_search(query: str, *, max_results: int = 25):
    """Same fall-through logic for `Search`. Verifies the videos list is
    actually non-empty before returning — when YouTube silently throttles
    a client it sometimes returns zero results (no exception, just nothing),
    so we treat empty as "try the next client" rather than reporting a
    false "0 found" to the user."""
    last = None
    for client in _YT_CLIENTS:
        try:
            s = Search(query, client=client)
            videos = list(s.videos)[:max_results]
            if videos:                    # got real results — accept
                return s
            # silent-throttle / hidden bot-block — try next client
            last = RuntimeError(f"empty results from client={client}")
        except Exception as e:
            last = e
            if _is_bot_block(e):
                continue
            raise
    raise last if last else RuntimeError("all Search clients failed or empty")


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', '_', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:180] if len(name) > 180 else name


def find_ffmpeg() -> str:
    """Return path to ffmpeg.exe — bundled, alongside exe, then PATH."""
    candidates = []
    # PyInstaller --onefile extracts to sys._MEIPASS
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


def _video_to_dict(v) -> dict:
    return {
        'title': v.title,
        'author': getattr(v, 'author', '') or '',
        'length': getattr(v, 'length', 0) or 0,
        'url': v.watch_url,
        'video_id': v.video_id,
    }


class SearchWorker(QThread):
    """Initial search — returns the first `initial_count` videos AND the
    Search object so the caller can fetch more pages on scroll-end."""
    finished_results = pyqtSignal(list, object)
    error = pyqtSignal(str)

    def __init__(self, query: str, initial_count: int = 10):
        super().__init__()
        self.query = query
        self.initial_count = initial_count

    def run(self):
        try:
            s = _make_search(self.query, max_results=self.initial_count)
            videos = list(s.videos)[:self.initial_count]
            results = []
            for v in videos:
                try:
                    results.append(_video_to_dict(v))
                except Exception:
                    continue
            self.finished_results.emit(results, s)
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")


class LoadMoreWorker(QThread):
    """Fetch the next batch of videos from an existing Search object."""
    new_results = pyqtSignal(list)

    def __init__(self, search_obj, current_offset: int, batch_size: int = 5):
        super().__init__()
        self.search_obj = search_obj
        self.current_offset = current_offset
        self.batch_size = batch_size

    def run(self):
        try:
            videos = self.search_obj.videos
            attempts = 0
            # Pull more pages until we have enough, or until the API stops giving more.
            while len(videos) < self.current_offset + self.batch_size and attempts < 3:
                prev_len = len(videos)
                try:
                    self.search_obj.get_next_results()
                except Exception:
                    break
                videos = self.search_obj.videos
                if len(videos) == prev_len:
                    break  # no progress
                attempts += 1

            new_videos = list(videos)[self.current_offset : self.current_offset + self.batch_size]
            results = []
            for v in new_videos:
                try:
                    results.append(_video_to_dict(v))
                except Exception:
                    continue
            self.new_results.emit(results)
        except Exception:
            self.new_results.emit([])


class AudioDownloadWorker(QThread):
    """Download itag 140 (m4a/AAC), then transcode to MP3 with ffmpeg.

    Why MP3? Qt's Windows backend (DirectShow) can't decode raw AAC/m4a on
    every Windows install — playing the .m4a directly throws DirectShow
    error 0x80040266 (no decoder for format). MP3 is decoded natively.
    The conversion is fast (~1–2 s for typical 4-min audio), and once cached
    on disk subsequent plays of the same video are instant.
    """
    file_ready = pyqtSignal(str, str)   # video_id, file_path
    error = pyqtSignal(str, str)        # video_id, message

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
            yt = _make_yt(self.video_url)
            stream = yt.streams.get_by_itag(AUDIO_ITAG)
            if stream is None:
                self.error.emit(self.video_id, "오디오 스트림을 찾을 수 없습니다")
                return

            tmp_name = f"_tmp_{self.video_id}.m4a"
            m4a_path = stream.download(output_path=self.dest_dir, filename=tmp_name)

            ff = find_ffmpeg()
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


class FetchInfoWorker(QThread):
    """Fetch info for a pasted URL without blocking the UI."""
    finished_info = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            yt = _make_yt(self.url)
            self.finished_info.emit({
                'title': yt.title,
                'author': yt.author or '',
                'length': yt.length or 0,
                'url': self.url,
                'video_id': yt.video_id,
            })
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")


class SuggestWorker(QThread):
    """Fetch YouTube search suggestions for the autocomplete dropdown."""
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
            # silent on suggest errors — we don't want autocomplete to ever block UX
            pass


class ThumbnailWorker(QThread):
    """Fetch YouTube thumbnails in parallel."""
    loaded = pyqtSignal(str, bytes)  # video_id, jpeg bytes
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


class DownloadWorker(QThread):
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)  # current_index, total_items
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
                    out = self._download_mp3(item, ff, batch_index=i)
                else:
                    out = self._download_video(item, ff, batch_index=i)
                self.log.emit(f"  ✔ 저장됨: {out}")
                self.item_done.emit(i, True, out)
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                self.log.emit(f"  ✘ 오류: {msg}")
                self.item_done.emit(i, False, msg)
        self.finished_all.emit()

    # ------------------------------------------------------------------
    def _make_progress_cb(self, label: str):
        last = [-10]

        def cb(stream, chunk, bytes_remaining):
            total = stream.filesize or 1
            done = total - bytes_remaining
            pct = int(done * 100 / total)
            if pct >= last[0] + 10:
                last[0] = pct
                self.log.emit(f"    {label} {pct}%")
        return cb

    def _output_basename(self, item, batch_index: int) -> str:
        title = item.get('title') or 'video'
        custom = (item.get('custom_name') or '').strip()
        if custom:
            return sanitize_filename(custom)
        prefix = (self.options.get('prefix') or '').strip()
        if prefix:
            # When numbering helps, we still keep title — prefix is descriptive.
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

    # ------------------------------------------------------------------
    def _download_mp3(self, item, ff: str, batch_index: int) -> str:
        cb = self._make_progress_cb("오디오")
        yt = _make_yt(item['url'], on_progress_callback=cb)
        stream = yt.streams.get_by_itag(AUDIO_ITAG)
        if stream is None:
            raise RuntimeError("이 영상의 오디오 스트림을 사용할 수 없습니다")

        dest = self.options['dest']
        os.makedirs(dest, exist_ok=True)
        base = self._output_basename(item, batch_index)
        tmp_name = f"_tmp_audio_{batch_index}_{os.getpid()}.m4a"
        out_path = self._unique_path(dest, base, 'mp3')

        self.log.emit("    오디오 다운로드 중…")
        m4a_path = stream.download(output_path=dest, filename=tmp_name)

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

    def _download_video(self, item, ff: str, batch_index: int) -> str:
        cb = self._make_progress_cb("비디오")
        yt = _make_yt(item['url'], on_progress_callback=cb)

        # progressive=False + mp4, video-only (DASH)
        v_streams = list(yt.streams.filter(progressive=False, file_extension='mp4',
                                           only_video=True))
        if not v_streams:
            raise RuntimeError("사용 가능한 mp4 비디오 스트림이 없습니다")

        chosen = self._pick_video(v_streams, self.options.get('resolution', 'Highest'))
        if chosen is None:
            raise RuntimeError("비디오 스트림을 선택할 수 없습니다")

        dest = self.options['dest']
        os.makedirs(dest, exist_ok=True)
        base = self._output_basename(item, batch_index)

        # video-only output
        if not self.options.get('include_audio', True):
            out_path = self._unique_path(dest, base + ' (영상만)', 'mp4')
            tmp_name = f"_tmp_v_{batch_index}_{os.getpid()}.mp4"
            self.log.emit(f"    비디오 다운로드 중 ({chosen.resolution})…")
            v_path = chosen.download(output_path=dest, filename=tmp_name)
            try:
                if os.path.exists(out_path):
                    os.remove(out_path)
                os.rename(v_path, out_path)
            except OSError as e:
                raise RuntimeError(f"파일명 변경 실패: {e}")
            return out_path

        # video + audio merge
        a_stream = yt.streams.get_by_itag(AUDIO_ITAG)
        if a_stream is None:
            raise RuntimeError("이 영상의 오디오 스트림을 사용할 수 없습니다")

        tmp_v = f"_tmp_v_{batch_index}_{os.getpid()}.mp4"
        tmp_a = f"_tmp_a_{batch_index}_{os.getpid()}.m4a"
        out_path = self._unique_path(dest, base, 'mp4')

        self.log.emit(f"    비디오 다운로드 중 ({chosen.resolution})…")
        v_path = chosen.download(output_path=dest, filename=tmp_v)

        # second progress meter for audio
        a_cb = self._make_progress_cb("오디오")
        yt._on_progress_callback = a_cb  # pytubefix internal but supported
        self.log.emit("    오디오 다운로드 중…")
        a_path = a_stream.download(output_path=dest, filename=tmp_a)

        self.log.emit("    오디오 + 비디오 병합 중…")
        cmd = [ff, '-y', '-loglevel', 'error',
               '-i', v_path, '-i', a_path,
               '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
               '-shortest', out_path]
        try:
            r = subprocess.run(cmd, capture_output=True, **_no_window_kwargs())
        finally:
            for p in (v_path, a_path):
                try:
                    os.remove(p)
                except OSError:
                    pass
        if r.returncode != 0:
            err = r.stderr.decode('utf-8', errors='ignore')[:400]
            raise RuntimeError(f"ffmpeg 병합 실패: {err}")
        return out_path

    @staticmethod
    def _pick_video(streams, target: str):
        def res_num(s):
            m = re.search(r'(\d+)', s.resolution or '')
            return int(m.group(1)) if m else 0

        if not streams:
            return None
        if target == 'Highest':
            return max(streams, key=res_num)
        if target == 'Lowest':
            return min(streams, key=lambda s: res_num(s) or 99999)
        # exact match first
        for s in streams:
            if (s.resolution or '').lower() == target.lower():
                return s
        # closest by numeric height
        m = re.search(r'(\d+)', target)
        target_n = int(m.group(1)) if m else 0
        return min(streams, key=lambda s: abs(res_num(s) - target_n))
