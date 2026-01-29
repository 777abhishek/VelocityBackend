from __future__ import annotations

import hashlib
import tempfile
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


def run_extract(url: str | HttpUrl, cookies: Optional[str]) -> Dict[str, Any]:
    url_str = str(url)
    cookie_path = None
    if cookies:
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        temp.write(cookies.encode("utf-8"))
        temp.flush()
        cookie_path = temp.name

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
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if cookie_path:
            try:
                import os

                os.remove(cookie_path)
            except OSError:
                pass

    return info


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
