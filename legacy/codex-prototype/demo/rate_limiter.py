"""Demo module for harness evaluation sessions: a naive rate limiter."""
import time


class RateLimiter:
    """Allows at most `limit` calls per `window` seconds (naive implementation)."""

    def __init__(self, limit: int, window: float):
        self.limit = limit
        self.window = window
        self.calls: list[float] = []

    def allow(self) -> bool:
        now = time.time()
        # BUG: list grows forever; old timestamps are filtered but never removed
        recent = [t for t in self.calls if now - t < self.window]
        if len(recent) < self.limit:
            self.calls.append(now)
            return True
        return False
