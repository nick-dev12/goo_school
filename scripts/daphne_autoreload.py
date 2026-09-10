#!/usr/bin/env python
"""Daphne avec rechargement automatique (Windows-friendly)."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

ROOT = Path(__file__).resolve().parent.parent
WATCH_DIRS = [ROOT / "school_admin", ROOT / "school"]
EXTENSIONS = {".py", ".html", ".css", ".js"}
SKIP_PARTS = {
    "__pycache__",
    "env",
    "venv",
    ".git",
    "node_modules",
    "staticfiles",
    "media",
    "terminals",
}


def _should_watch(path: str) -> bool:
    p = Path(path)
    if p.suffix and p.suffix not in EXTENSIONS:
        return False
    return not any(part in SKIP_PARTS for part in p.parts)


class ReloadHandler(FileSystemEventHandler):
    def __init__(self, restart_callback):
        self.restart_callback = restart_callback
        self._cooldown_until = 0.0

    def _trigger(self, path: str) -> None:
        if not _should_watch(path):
            return
        now = time.time()
        if now < self._cooldown_until:
            return
        self._cooldown_until = now + 2.0
        self.restart_callback()

    def on_modified(self, event):
        if not event.is_directory:
            self._trigger(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._trigger(event.src_path)


def main() -> int:
    proc: subprocess.Popen | None = None

    def stop() -> None:
        nonlocal proc
        if proc is None or proc.poll() is not None:
            proc = None
            return
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
        proc = None
        time.sleep(0.8)

    def start() -> None:
        nonlocal proc
        stop()
        print("[autoreload] Démarrage Daphne sur http://127.0.0.1:8000", flush=True)
        proc = subprocess.Popen(
            [sys.executable, "-m", "daphne", "-b", "127.0.0.1", "-p", "8000", "school.asgi:application"],
            cwd=ROOT,
        )

    def restart() -> None:
        print("[autoreload] Fichier modifié, redémarrage de Daphne...", flush=True)
        start()

    start()

    observer = Observer()
    handler = ReloadHandler(restart)
    for directory in WATCH_DIRS:
        if directory.exists():
            observer.schedule(handler, str(directory), recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
            if proc and proc.poll() is not None:
                code = proc.returncode
                print(f"[autoreload] Daphne arrêté (code {code}), relance...", flush=True)
                start()
    except KeyboardInterrupt:
        print("[autoreload] Arrêt demandé.", flush=True)
    finally:
        stop()
        observer.stop()
        observer.join()

    return 0


if __name__ == "__main__":
    sys.exit(main())
