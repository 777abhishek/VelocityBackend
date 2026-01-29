# VelocityBackend

FastAPI + yt-dlp backend for fetching YouTube metadata, formats, and stream URLs.

## Requirements
- Python 3.10–3.13 (Python 3.14 currently fails building pydantic-core)
- ffmpeg in PATH

## Install
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

If you must use Python 3.14, run this before `pip install`:
```bash
set PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1
```

## Run (local)
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Endpoints
- `GET /health`
- `POST /info` {"url": "..."}
- `POST /info/raw` {"url": "..."}
- `POST /formats` {"url": "..."}
- `GET /formats?url=...`
- `POST /stream` {"url": "...", "mode": "audio"|"av"}
- `POST /playlist` {"url": "..."}
- `POST /library/{kind}` (kind: liked | watchlater | playlists)
- `POST /download` {"url": "...", "format_id": "...", "merge_av": true, "output_dir": "...", "max_height": 720, "preferred_ext": "mp4", "codec": "mp4a", "container": "mp4"}
- `GET /download/{job_id}`
- `POST /download/{job_id}/cancel`

## Notes
- Stream URLs from YouTube expire quickly. Fetch them just before playback.
- Cookies are optional for public videos and format lists.
- Cookies are typically required for playlists, private videos, age‑restricted videos, or region‑blocked content.
- Some public videos may still require cookies if the host IP is throttled.
- If needed, send cookies as `cookies` (Netscape format) in the request body.

## Streaming options
`/stream` accepts these optional fields:
- `format_id`
- `audio_format_id`
- `video_format_id`
- `max_height`
- `preferred_ext`

## Download options
`/download` accepts these optional fields:
- `format_id` – specific format ID
- `merge_av` – merge best video+audio when `true` (default)
- `max_height` – max video height (e.g., 720)
- `preferred_ext` – preferred extension (e.g., mp4, webm)
- `codec` – audio codec (e.g., mp4a, opus)
- `container` – container format (e.g., mp4, mkv)
- `output_dir` – custom output directory

### Download examples (best video + best audio)
```json
{
  "url": "https://youtu.be/dQw4w9WgXcQ",
  "merge_av": true,
  "max_height": 720,
  "preferred_ext": "mp4"
}
```

## Deployment

### Render (free hosting)
1. Push this repo to GitHub
2. Go to [render.com](https://render.com) and connect your GitHub
3. Create a new Web Service
4. Select this repo
5. Render will detect `render.yaml` and configure automatically
6. Deploy

### Docker
```bash
docker build -t velocity-backend .
docker run -p 8000:8000 velocity-backend
```

### Environment variables
- `VELOCITY_CACHE_TTL` – cache TTL in seconds (default: 300)
- `VELOCITY_RATE_LIMIT` – requests per minute (default: 60)
- `VELOCITY_RATE_WINDOW` – rate limit window in seconds (default: 60)
- `VELOCITY_API_KEY` – optional API key for authentication
