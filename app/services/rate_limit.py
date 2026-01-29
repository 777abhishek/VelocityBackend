from __future__ import annotations

import time
from collections import defaultdict
from typing import DefaultDict, List


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._requests: DefaultDict[str, List[float]] = defaultdict(list)

    def allow(self, client_id: str) -> bool:
        now = time.time()
        self._requests[client_id] = [t for t in self._requests[client_id] if now - t < self.window_seconds]
        if len(self._requests[client_id]) >= self.limit:
            return False
        self._requests[client_id].append(now)
        return True

    def client_count(self) -> int:
        return len(self._requests)
