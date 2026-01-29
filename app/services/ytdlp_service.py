from __future__ import annotations

import hashlib
import tempfile
import time
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pydantic import HttpUrl
from yt_dlp import YoutubeDL


def cache_key(url: str | HttpUrl, cookies: Optional[str] = None, suffix: str = "") -> str:
    h = hashlib.md5(str(url).encode())
    if cookies:
        h.update(cookies.encode())
    base = f"cache:{h.hexdigest()}"
    return f"{base}:{suffix}" if suffix else base


def is_hls_format(fmt: Dict[str, Any]) -> bool:
    protocol = (fmt.get("protocol") or "").lower()
    ext = (fmt.get("ext") or "").lower()
    url = (fmt.get("url") or "").lower()
    return (
        "m3u8" in protocol
        or ext == "m3u8"
        or "m3u8" in url
        or "hls" in protocol
    )


def run_extract(url: str | HttpUrl, cookies: Optional[str], max_retries: int = 3) -> Dict[str, Any]:
    url_str = str(url)
    cookie_path = None
    if cookies:
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        temp.write(cookies.encode("utf-8"))
        temp.flush()
        cookie_path = temp.name

    for attempt in range(max_retries):
        try:
            ydl_opts = {
                "quiet": True,
                "skip_download": True,
                "nocheckcertificate": True,
                "noplaylist": False,
                "no_cookies": not cookies,
            }
            if cookie_path:
                ydl_opts["cookiefile"] = cookie_path

            try:
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url_str, download=False)
            except Exception as exc:  # noqa: BLE001
                error_msg = str(exc).lower()
                if "429" in error_msg or "too many requests" in error_msg:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 5  # 5s, 10s, 15s
                        print(f"Rate limited, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            finally:
                if cookie_path:
                    try:
                        import os
                        os.remove(cookie_path)
                    except OSError:
                        pass

            return info
        except Exception as e:
            if attempt == max_retries - 1:
                raise HTTPException(status_code=500, detail=f"Failed after {max_retries} retries: {str(e)}") from e
            time.sleep((attempt + 1) * 5)

    raise HTTPException(status_code=500, detail="Max retries exceeded")


def simplify_format(fmt: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "format_id": fmt.get("format_id"),
        "format": fmt.get("format"),
        "ext": fmt.get("ext"),
        "protocol": fmt.get("protocol"),
        "acodec": fmt.get("acodec"),
        "vcodec": fmt.get("vcodec"),
        "height": fmt.get("height"),
        "tbr": fmt.get("tbr"),
        "abr": fmt.get("abr"),
        "url": fmt.get("url"),
    }


def categorize_formats(formats: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    combined = [f for f in formats if f.get("acodec") != "none" and f.get("vcodec") != "none"]
    audio_only = [f for f in formats if f.get("vcodec") == "none" and f.get("acodec") != "none"]
    video_only = [f for f in formats if f.get("vcodec") != "none" and f.get("acodec") == "none"]
    return {
        "combined": combined,
        "video_only": video_only,
        "audio_only": audio_only,
    }


def pick_best_audio(formats: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    audio_formats = [f for f in formats if f.get("vcodec") == "none" and f.get("acodec") != "none"]
    if not audio_formats:
        return None
    non_hls = [f for f in audio_formats if not is_hls_format(f)]
    candidates = non_hls or audio_formats
    return max(candidates, key=lambda f: (f.get("abr") or 0, f.get("tbr") or 0))


def pick_best_av(formats: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    av_formats = [f for f in formats if f.get("vcodec") != "none" and f.get("acodec") != "none"]
    if not av_formats:
        return None
    non_hls = [f for f in av_formats if not is_hls_format(f)]
    candidates = non_hls or av_formats
    return max(candidates, key=lambda f: (f.get("height") or 0, f.get("tbr") or 0))


def find_format_by_id(formats: List[Dict[str, Any]], format_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not format_id:
        return None
    for fmt in formats:
        if fmt.get("format_id") == format_id:
            return fmt
    return None


def filter_formats(
    formats: List[Dict[str, Any]],
    max_height: Optional[int],
    preferred_ext: Optional[str],
    allow_muxed: bool = True,
) -> List[Dict[str, Any]]:
    filtered = formats
    if max_height:
        filtered = [f for f in filtered if (f.get("height") or 0) <= max_height]
    if preferred_ext:
        filtered = [f for f in filtered if (f.get("ext") or "").lower() == preferred_ext.lower()]
    if not allow_muxed:
        filtered = [f for f in filtered if f.get("acodec") == "none" or f.get("vcodec") == "none"]
    return filtered


def library_url(kind: str) -> str:
    if kind == "liked":
        return "https://www.youtube.com/playlist?list=LL"
    if kind == "watchlater":
        return "https://www.youtube.com/playlist?list=WL"
    if kind == "playlists":
        return "https://www.youtube.com/feed/playlists"
    raise ValueError("Unknown library kind")
