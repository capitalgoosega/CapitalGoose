import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    """In-process limiter. Fine for one replica; move to Redis if we scale out."""

    def __init__(self, limit: int, window_seconds: float, clock=time.monotonic):
        self.limit = limit
        self.window = window_seconds
        self.clock = clock
        self._hits = defaultdict(deque)

    def allow(self, key) -> bool:
        now = self.clock()
        hits = self._hits[key]
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True
