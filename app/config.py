from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    cache_ttl: int = int(os.getenv("VELOCITY_CACHE_TTL", "300"))
    rate_limit: int = int(os.getenv("VELOCITY_RATE_LIMIT", "60"))
    rate_window: int = int(os.getenv("VELOCITY_RATE_WINDOW", "60"))
    api_key: str | None = os.getenv("VELOCITY_API_KEY")


settings = Settings()
