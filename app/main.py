from __future__ import annotations

import logging
import time
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.models import (
    DownloadJob,
    DownloadRequest,
    FormatsResponse,
    HealthResponse,
    LibraryRequest,
    PlaylistRequest,
    RawInfoRequest,
    StreamRequest,
    UrlRequest,
)
from app.services.auth import is_authorized
from app.services.cache import MemoryCache
from app.services.download_service import DownloadManager
from app.services.rate_limit import RateLimiter
from app.services.ytdlp_service import (
    cache_key,
    filter_formats,
    find_format_by_id,
    library_url,
    pick_best_audio,
    pick_best_av,
    run_extract,
    simplify_format,
)

app = FastAPI(
    title="VelocityBackend",
    version="1.2.0",
    description="FastAPI + yt-dlp backend for fetching YouTube metadata, formats, and stream URLs.",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Services
cache = MemoryCache(settings.cache_ttl)
rate_limiter = RateLimiter(settings.rate_limit, settings.rate_window)
download_manager = DownloadManager()

# Stats
_start_time = time.time()
_requests = 0
_errors = 0


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "error": str(exc)},
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    global _requests, _errors
    start = time.time()
    try:
        response = await call_next(request)
        _requests += 1
    except Exception:
        _errors += 1
        raise
    duration = time.time() - start
    logger.info(
        "%s %s %s %s",
        request.method,
        request.url.path,
        response.status_code,
        f"{duration:.3f}s",
    )
    return response


@app.middleware("http")
async def auth_and_rate_limit(request: Request, call_next):
    if request.url.path in ["/health", "/docs", "/openapi.json"]:
        return await call_next(request)

    client_id = request.headers.get("X-Client-ID", "default")
    if not rate_limiter.allow(client_id):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Rate limit exceeded"},
        )

    if not is_authorized(request, settings.api_key):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Unauthorized"},
        )

    return await call_next(request)


@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "name": "VelocityBackend",
        "version": "1.2.0",
        "endpoints": [
            "GET  /health",
            "POST /info",
            "POST /formats",
            "POST /stream",
            "POST /playlist",
            "POST /cache/clear",
        ],
        "docs": "/docs",
    }


@app.get("/health")
def health() -> HealthResponse:
    return {
        "status": "ok",
        "cache_size": cache.size(),
        "rate_limit_clients": rate_limiter.client_count(),
        "api_key_required": settings.api_key is not None,
        "uptime": time.time() - _start_time,
        "requests": _requests,
        "errors": _errors,
    }


@app.post("/cache/clear")
def cache_clear() -> Dict[str, str]:
    cache.clear()
    return {"status": "cache_cleared"}


@app.post("/info")
def info(req: UrlRequest) -> Dict[str, Any]:
    key = cache_key(req.url, req.cookies)
    cached = cache.get(key)
    if cached:
        logger.info("Cache hit for info: %s", req.url)
        return cached
    data = run_extract(req.url, req.cookies)
    result = {
        "id": data.get("id"),
        "title": data.get("title"),
        "duration": data.get("duration"),
        "thumbnail": data.get("thumbnail"),
        "uploader": data.get("uploader"),
        "view_count": data.get("view_count"),
        "webpage_url": data.get("webpage_url"),
        "availability": data.get("availability"),
    }
    cache.set(key, result)
    return result


@app.post("/info/raw")
def info_raw(req: RawInfoRequest) -> Dict[str, Any]:
    data = run_extract(req.url, req.cookies)
    return data


@app.get("/formats")
def formats_get(url: str = Query(..., description="Video URL"), cookies: str | None = None) -> Dict[str, Any]:
    key = cache_key(url, cookies, "formats")
    cached = cache.get(key)
    if cached:
        logger.info("Cache hit for formats: %s", url)
        return cached
    data = run_extract(url, cookies)
    formats_list = [simplify_format(f) for f in data.get("formats", [])]
    result: FormatsResponse = {
        "formats": formats_list,
        "subtitles": data.get("subtitles", {}),
        "automatic_captions": data.get("automatic_captions", {}),
    }
    cache.set(key, result)
    return result


@app.post("/formats")
def formats(req: UrlRequest) -> Dict[str, Any]:
    key = cache_key(req.url, req.cookies, "formats")
    cached = cache.get(key)
    if cached:
        logger.info("Cache hit for formats: %s", req.url)
        return cached
    data = run_extract(req.url, req.cookies)
    formats_list = [simplify_format(f) for f in data.get("formats", [])]
    result: FormatsResponse = {
        "formats": formats_list,
        "subtitles": data.get("subtitles", {}),
        "automatic_captions": data.get("automatic_captions", {}),
    }
    cache.set(key, result)
    return result


@app.post("/stream")
def stream(req: StreamRequest) -> Dict[str, Any]:
    data = run_extract(req.url, req.cookies)
    formats = data.get("formats", [])
    formats = filter_formats(formats, req.max_height, req.preferred_ext)

    if req.format_id:
        chosen = find_format_by_id(formats, req.format_id)
        return {
            "audio_url": chosen.get("url") if chosen else None,
            "video_url": chosen.get("url") if chosen else None,
            "format_id": req.format_id,
            "audio_format_id": None,
            "subtitles": data.get("subtitles", {}),
            "automatic_captions": data.get("automatic_captions", {}),
        }

    audio = find_format_by_id(formats, req.audio_format_id) or pick_best_audio(formats)
    av = find_format_by_id(formats, req.video_format_id) or pick_best_av(formats)

    if req.mode not in {"audio", "av"}:
        raise HTTPException(status_code=400, detail="mode must be 'audio' or 'av'")

    return {
        "audio_url": audio.get("url") if audio else None,
        "video_url": av.get("url") if req.mode == "av" and av else None,
        "format_id": av.get("format_id") if av else None,
        "audio_format_id": audio.get("format_id") if audio else None,
        "subtitles": data.get("subtitles", {}),
        "automatic_captions": data.get("automatic_captions", {}),
    }


@app.post("/playlist")
def playlist(req: PlaylistRequest) -> Dict[str, Any]:
    data = run_extract(req.url, req.cookies)
    entries = data.get("entries", []) or []
    total = len(entries)
    limit = req.limit if req.limit and req.limit > 0 else total
    offset = req.offset if req.offset and req.offset >= 0 else 0
    paginated = entries[offset : offset + limit]
    simplified = [
        {
            "id": entry.get("id"),
            "title": entry.get("title"),
            "duration": entry.get("duration"),
            "thumbnail": entry.get("thumbnail"),
            "webpage_url": entry.get("webpage_url"),
        }
        for entry in paginated
    ]
    return {
        "id": data.get("id"),
        "title": data.get("title"),
        "total": total,
        "offset": offset,
        "limit": limit,
        "entries": simplified,
    }


@app.post("/library/{kind}")
def library(kind: str, req: LibraryRequest) -> Dict[str, Any]:
    url = library_url(kind)
    data = run_extract(url, req.cookies)
    entries = data.get("entries", []) or []
    total = len(entries)
    limit = req.limit if req.limit and req.limit > 0 else total
    offset = req.offset if req.offset and req.offset >= 0 else 0
    paginated = entries[offset : offset + limit]
    simplified = [
        {
            "id": entry.get("id"),
            "title": entry.get("title"),
            "duration": entry.get("duration"),
            "thumbnail": entry.get("thumbnail"),
            "webpage_url": entry.get("webpage_url"),
        }
        for entry in paginated
    ]
    return {
        "kind": kind,
        "total": total,
        "offset": offset,
        "limit": limit,
        "entries": simplified,
    }


@app.post("/download")
def download(req: DownloadRequest) -> DownloadJob:
    job = download_manager.start(str(req.url), req.cookies, req.format_id, req.output_dir)
    return job


@app.get("/download/{job_id}")
def download_status(job_id: str) -> DownloadJob:
    job = download_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/download/{job_id}/cancel")
def download_cancel(job_id: str) -> Dict[str, Any]:
    if not download_manager.cancel(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "cancelling"}
