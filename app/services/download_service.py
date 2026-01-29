from __future__ import annotations

import os
import threading
import tempfile
import time
from typing import Dict, Optional
from uuid import uuid4

from yt_dlp import YoutubeDL


class DownloadManager:
    def __init__(self) -> None:
        self._jobs: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(self, url: str, cookies: Optional[str], format_id: Optional[str], output_dir: Optional[str], max_height: Optional[int], preferred_ext: Optional[str], codec: Optional[str], container: Optional[str]) -> dict:
        job_id = str(uuid4())
        job = {
            "job_id": job_id,
            "status": "queued",
            "progress": 0.0,
            "filename": None,
            "file_path": None,
            "error": None,
            "cancel": False,
        }
        with self._lock:
            self._jobs[job_id] = job

        thread = threading.Thread(
            target=self._run,
            args=(job_id, url, cookies, format_id, output_dir, max_height, preferred_ext, codec, container),
            daemon=True,
        )
        thread.start()
        return job

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False
            job["cancel"] = True
            job["status"] = "cancelling"
            return True

    def _run(self, job_id: str, url: str, cookies: Optional[str], format_id: Optional[str], output_dir: Optional[str], max_height: Optional[int], preferred_ext: Optional[str], codec: Optional[str], container: Optional[str]) -> None:
        def hook(d: dict) -> None:
            with self._lock:
                job = self._jobs.get(job_id)
                if not job:
                    return
                if job.get("cancel"):
                    raise Exception("Download cancelled")
                if d.get("status") == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    downloaded = d.get("downloaded_bytes") or 0
                    job["progress"] = (downloaded / total * 100) if total else job["progress"]
                    job["status"] = "downloading"
                elif d.get("status") == "finished":
                    job["progress"] = 100.0
                    job["status"] = "processing"
                    job["file_path"] = d.get("filename")
                    if d.get("filename"):
                        job["filename"] = os.path.basename(d.get("filename"))

        cookie_path = None
        if cookies:
            temp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
            temp.write(cookies.encode("utf-8"))
            temp.flush()
            cookie_path = temp.name

        format_selector = format_id or "best"
        if (max_height or preferred_ext or codec or container):
            parts = []
            if max_height:
                parts.append(f"[height<={max_height}]")
            if preferred_ext:
                parts.append(f"ext={preferred_ext}")
            if codec:
                parts.append(f"acodec={codec}")
            if container:
                parts.append(f"container={container}")
            format_selector = "+".join(parts) or format_id or "best"

        output_root = output_dir or "downloads"
        os.makedirs(output_root, exist_ok=True)

        ydl_opts = {
            "quiet": True,
            "format": format_selector,
            "outtmpl": f"{output_root}/%(title)s.%(ext)s",
            "progress_hooks": [hook],
            "noplaylist": True,
            "no_cookies": not cookies,
        }
        if cookie_path:
            ydl_opts["cookiefile"] = cookie_path

        attempts = 0
        max_retries = 3
        backoff_seconds = 2
        while True:
            try:
                with YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                with self._lock:
                    job = self._jobs.get(job_id)
                    if job:
                        job["status"] = "completed"
                        job["progress"] = 100.0
                break
            except Exception as exc:  # noqa: BLE001
                attempts += 1
                should_retry = "HTTP Error 429" in str(exc) and attempts <= max_retries
                with self._lock:
                    job = self._jobs.get(job_id)
                    if job:
                        if should_retry:
                            job["status"] = "retrying"
                        else:
                            job["status"] = "failed"
                        job["error"] = str(exc)
                if should_retry:
                    time.sleep(backoff_seconds * attempts)
                    continue
                break
            finally:
                if cookie_path:
                    try:
                        os.remove(cookie_path)
                    except OSError:
                        pass
