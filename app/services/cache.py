from __future__ import annotations

import time
from typing import Any, Dict, Optional


class MemoryCache:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Any] = {}
        self._timestamps: Dict[str, float] = {}

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        if time.time() - self._timestamps.get(key, 0) > self.ttl_seconds:
            self._cache.pop(key, None)
            self._timestamps.pop(key, None)
            return None
        return self._cache[key]

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = value
        self._timestamps[key] = time.time()

    def clear(self) -> None:
        self._cache.clear()
        self._timestamps.clear()

    def size(self) -> int:
        return len(self._cache)
