
import time

import pytest

from src.reliability import (
    IdempotencyStore,
    ProviderTimeout,
    RetryPolicy,
    SlidingWindowRateLimiter,
)


def test_retry_policy_succeeds_without_retry():
    attempts = []

    def operation():
        attempts.append(1)
        return "success"

    assert RetryPolicy(max_attempts=3).run(operation) == "success"
    assert len(attempts) == 1


def test_retry_policy_retries_transient_failure():
    attempts = []

    def operation():
        attempts.append(1)
        if len(attempts) < 3:
            raise ConnectionError("temporary failure")
        return "recovered"

    result = RetryPolicy(max_attempts=3).run(operation)

    assert result == "recovered"
    assert len(attempts) == 3


def test_retry_policy_stops_at_attempt_limit():
    attempts = []

    def operation():
        attempts.append(1)
        raise ConnectionError("unavailable")

    with pytest.raises(ConnectionError):
        RetryPolicy(max_attempts=2).run(operation)

    assert len(attempts) == 2


def test_retry_policy_does_not_retry_unclassified_errors():
    attempts = []

    def operation():
        attempts.append(1)
        raise ValueError("invalid operation")

    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=3).run(operation)

    assert len(attempts) == 1


def test_retry_policy_rejects_invalid_attempt_count():
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)


def test_provider_timeout_returns_fast_result():
    timeout = ProviderTimeout(timeout_seconds=1.0)
    assert timeout.run(lambda: "finished") == "finished"


def test_provider_timeout_raises_for_slow_operation():
    timeout = ProviderTimeout(timeout_seconds=0.02)

    with pytest.raises(TimeoutError):
        timeout.run(lambda: time.sleep(0.15))


def test_rate_limiter_enforces_limit_and_resets():
    now = [100.0]

    limiter = SlidingWindowRateLimiter(
        max_calls=2,
        window_seconds=10.0,
        clock=lambda: now[0],
    )

    assert limiter.allow("user-1") is True
    assert limiter.allow("user-1") is True
    assert limiter.allow("user-1") is False

    now[0] += 11.0
    assert limiter.allow("user-1") is True


def test_rate_limiter_isolated_by_key():
    limiter = SlidingWindowRateLimiter(max_calls=1)

    assert limiter.allow("user-1") is True
    assert limiter.allow("user-1") is False
    assert limiter.allow("user-2") is True


def test_idempotency_store_returns_cached_result():
    store = IdempotencyStore()
    key = store.fingerprint(
        "search_engine",
        {"query": "Python", "max_results": 5},
    )
    result = {"status": "ok", "result_count": 2}

    assert store.get(key) is None
    store.put(key, result)

    assert store.get(key) == result


def test_idempotency_fingerprint_is_order_independent():
    first = IdempotencyStore.fingerprint(
        "search_engine",
        {"query": "Python", "max_results": 5},
    )
    second = IdempotencyStore.fingerprint(
        "search_engine",
        {"max_results": 5, "query": "Python"},
    )

    assert first == second


def test_different_requests_have_different_fingerprints():
    first = IdempotencyStore.fingerprint(
        "search_engine", {"query": "Python"}
    )
    second = IdempotencyStore.fingerprint(
        "search_engine", {"query": "HTTPX"}
    )

    assert first != second
