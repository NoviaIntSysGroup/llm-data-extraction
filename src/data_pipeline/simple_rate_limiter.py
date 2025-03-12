import threading
import time

class SimpleRateLimiter:
    """
    A naive rate limiter that allows 'calls_per_minute' operations in total.
    Once you acquire it (using 'with'), it ensures the operation does not
    exceed the desired rate when invoked from multiple threads.
    """

    def __init__(self, max_calls_per_interval: float, interval_seconds: float):
        self._interval_seconds = interval_seconds / max_calls_per_interval
        self._lock = threading.Lock()
        self._next_allowed_time = time.monotonic()

    def __enter__(self):
        with self._lock:
            now = time.monotonic()
            if now < self._next_allowed_time:
                time.sleep(self._next_allowed_time - now)
            self._next_allowed_time = time.monotonic() + self._interval_seconds

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
