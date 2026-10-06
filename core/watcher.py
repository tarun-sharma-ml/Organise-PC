"""
Watchdog-based event handlers for the 3 scoped folders.
Reacts instantly to new/modified files — no polling.
"""

import threading
import time
from pathlib import Path
from utils.partial import _is_partial

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from config import settings
from core import maintenance, pipeline
from utils import telegram_bot
from utils.logger import log_action

# Small delay before processing, so we don't grab a file mid-write (e.g. large downloads)
SETTLE_SECONDS = 2

def _wait_until_stable(path: Path, checks: int = 3, interval: float = 1.0) -> bool:
    """True once the file size is unchanged for `checks` consecutive polls."""
    last, stable = -1, 0
    while stable < checks:
        try:
            size = path.stat().st_size
        except OSError:
            return False  # vanished (e.g. browser renamed it) -> nothing to do
        stable = stable + 1 if size == last else 0
        last = size
        time.sleep(interval)
    return True

def _process_when_ready(func, path: Path):
    if _is_partial(path) or not _wait_until_stable(path):
        return
    func(path)

class DownloadsHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._handle(event.dest_path)

    def _handle(self, path):
        p = _as_path(path)
        if _is_partial(p):
            return
        threading.Thread(
            target=_process_when_ready,
            args=(pipeline.process_downloads_file, p),
            daemon=True,
        ).start()

class MediaHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._handle(event.dest_path)

    def _handle(self, path):
        p = _as_path(path)
        if _is_partial(p):
            return
        threading.Thread(
            target=_process_when_ready,
            args=(pipeline.process_downloads_file, p),
            daemon=True,
        ).start()


def _as_path(path_str):
    from pathlib import Path

    return Path(path_str)


def _maintenance_loop():
    while True:
        if settings.MAINTENANCE_ENABLED:
            maintenance.run_maintenance()
        time.sleep(settings.MAINTENANCE_INTERVAL_HOURS * 3600)


def start():
    log_action(f"Organise_PC starting (DRY_RUN={settings.DRY_RUN})")
    log_action(f"Watching: {settings.DOWNLOADS_FOLDER}")
    log_action(f"Watching: {settings.PICTURES_FOLDER}")
    log_action(f"Watching: {settings.VIDEOS_FOLDER}")

    # Start the Telegram approval bot (if configured) before the initial
    # sweep, so any AI rename suggestions it generates have somewhere to go.
    telegram_bot.start()

    # Initial sweep of existing files, so nothing already sitting there is missed
    pipeline.run_initial_sweep()

    observer = Observer()

    if settings.DOWNLOADS_FOLDER.exists():
        observer.schedule(
            DownloadsHandler(), str(settings.DOWNLOADS_FOLDER), recursive=False
        )

    if settings.PICTURES_FOLDER.exists():
        observer.schedule(MediaHandler(), str(settings.PICTURES_FOLDER), recursive=True)

    if settings.VIDEOS_FOLDER.exists():
        observer.schedule(MediaHandler(), str(settings.VIDEOS_FOLDER), recursive=True)

    observer.start()

    # Run maintenance on its own schedule in a background thread
    if settings.MAINTENANCE_ENABLED:
        threading.Thread(target=_maintenance_loop, daemon=True).start()

    log_action("Suite is running. Press Ctrl+C to stop (or close this window).")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        log_action("Suite stopped by user.")
    observer.join()
