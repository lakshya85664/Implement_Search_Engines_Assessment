
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Any, Callable


class RetryPolicy:
    """Bounded retries for explicitly classified transient failures."""

    def __init__(self, max_attempts: int = 3) -> None:
        if max_attempts < 1 or max_attempts > 5:
            raise ValueError("max_attempts must be between 1 and 5")
        self.max_attempts = max_attempts

    def run(
        self,
        operation: Callable[[], Any],
        retry_on: tuple[type[BaseException], ...] = (ConnectionError,),
    ) -> Any:
        last_error: BaseException | None = None

        for attempt in range(self.max_attempts):
            try:
                return operation()
            except retry_on as exc:
                last_error = exc

        if last_error is not None:
            raise last_error

        raise RuntimeError("Retry operation did not execute")


class ProviderTimeout:
    """Run a provider call with a bounded wait for its result."""

    def __init__(self, timeout_seconds: float = 2.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds

    def run(self, operation: Callable[[], Any]) -> Any:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(operation)

        try:
            return future.result(timeout=self.timeout_seconds)
        except FutureTimeout as exc:
            future.cancel()
            raise TimeoutError("Provider call exceeded its deadline") from exc
        finally:
            # Do not wait for a timed-out operation to finish.
            executor.shutdown(wait=False, cancel_futures=True)


class SlidingWindowRateLimiter:
    """In-memory per-key request limiter using a sliding time window."""

    def __init__(
        self,
        max_calls: int = 30,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_calls < 1 or window_seconds <= 0:
            raise ValueError("Rate limit and window must be positive")

        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.clock = clock
        self._calls: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self.clock()

        with self._lock:
            calls = self._calls[key]

            while calls and now - calls[0] >= self.window_seconds:
                calls.popleft()

            if len(calls) >= self.max_calls:
                return False

            calls.append(now)
            return True


class IdempotencyStore:
    """Small in-memory cache for completed request results."""

    def __init__(self) -> None:
        self._results: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def fingerprint(tool_name: str, arguments: dict[str, Any]) -> str:
        serialized = json.dumps(
            {"tool": tool_name, "arguments": arguments},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            value = self._results.get(key)
            return dict(value) if value is not None else None

    def put(self, key: str, result: dict[str, Any]) -> None:
        with self._lock:
            self._results[key] = dict(result)
