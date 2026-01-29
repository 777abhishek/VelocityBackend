from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, HttpUrl


class UrlRequest(BaseModel):
    url: HttpUrl
    cookies: Optional[str] = None


class StreamRequest(BaseModel):
    url: HttpUrl
    mode: str = "audio"
    cookies: Optional[str] = None
    format_id: Optional[str] = None
    audio_format_id: Optional[str] = None
    video_format_id: Optional[str] = None
    max_height: Optional[int] = None
    preferred_ext: Optional[str] = None


class RawInfoRequest(BaseModel):
    url: HttpUrl
    cookies: Optional[str] = None


class LibraryRequest(BaseModel):
    cookies: Optional[str] = None
    limit: Optional[int] = None
    offset: Optional[int] = None


class PlaylistRequest(BaseModel):
    url: HttpUrl
    cookies: Optional[str] = None
    limit: Optional[int] = None
    offset: Optional[int] = None


class DownloadRequest(BaseModel):
    url: HttpUrl
    cookies: Optional[str] = None
    format_id: Optional[str] = None
    output_dir: Optional[str] = None


class DownloadJob(BaseModel):
    job_id: str
    status: str
    progress: float
    filename: Optional[str] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    cache_size: int
    rate_limit_clients: int
    api_key_required: bool
    uptime: float
    requests: int
    errors: int


class FormatsResponse(BaseModel):
    formats: list[Dict[str, Any]]
    subtitles: Dict[str, Any]
    automatic_captions: Dict[str, Any]
