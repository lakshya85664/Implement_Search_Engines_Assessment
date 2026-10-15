
import time

from src.contracts import ToolStatus
from src.gateway import dispatch
from src.reliability import (
    IdempotencyStore,
    ProviderTimeout,
    RetryPolicy,
    SlidingWindowRateLimiter,
)
from src.search_engine import search


def make_call(query="Python documentation"):
    return {
        "name": "search_engine",
        "arguments": {"query": query},
    }


def test_gateway_retries_transient_provider_failure():
    attempts = []

    def flaky_provider(arguments):
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionError("temporary provider failure")
        return search(arguments)

    result = dispatch(
        make_call(),
        {"role": "user", "id": "retry-user"},
        search_fn=flaky_provider,
        retry_policy=RetryPolicy(max_attempts=2),
    )

    assert result.status == ToolStatus.OK
    assert len(attempts) == 2


def test_gateway_stops_after_retry_limit():
    attempts = []

    def unavailable_provider(arguments):
        attempts.append(1)
        raise ConnectionError("provider unavailable")

    result = dispatch(
        make_call(),
        {"role": "user", "id": "retry-user"},
        search_fn=unavailable_provider,
        retry_policy=RetryPolicy(max_attempts=2),
    )

    assert result.status == ToolStatus.FAILED
    assert len(attempts) == 2
    assert result.error == "Search provider is unavailable"


def test_gateway_enforces_provider_timeout():
    def slow_provider(arguments):
        time.sleep(0.2)
        return search(arguments)

    result = dispatch(
        make_call(),
        {"role": "user", "id": "timeout-user"},
        search_fn=slow_provider,
        provider_timeout=ProviderTimeout(timeout_seconds=0.02),
    )

    assert result.status == ToolStatus.TIMEOUT
    assert result.error == "Search provider timed out"


def test_gateway_rate_limit_blocks_provider_call():
    calls = []

    def provider(arguments):
        calls.append(1)
        return search(arguments)

    limiter = SlidingWindowRateLimiter(max_calls=1)

    first = dispatch(
        make_call(),
        {"role": "user", "id": "limited-user"},
        search_fn=provider,
        rate_limiter=limiter,
    )
    second = dispatch(
        make_call("HTTPX documentation"),
        {"role": "user", "id": "limited-user"},
        search_fn=provider,
        rate_limiter=limiter,
    )

    assert first.status == ToolStatus.OK
    assert second.status == ToolStatus.RATE_LIMITED
    assert len(calls) == 1


def test_gateway_cache_prevents_repeated_provider_call():
    calls = []

    def provider(arguments):
        calls.append(1)
        return search(arguments)

    store = IdempotencyStore()

    first = dispatch(
        make_call(),
        {"role": "user", "id": "cache-user"},
        search_fn=provider,
        idempotency_store=store,
    )
    second = dispatch(
        make_call(),
        {"role": "user", "id": "cache-user"},
        search_fn=provider,
        idempotency_store=store,
    )

    assert first.status == ToolStatus.OK
    assert second.status == ToolStatus.OK
    assert first.data == second.data
    assert len(calls) == 1
    assert any(event["event"] == "tool.cache_hit" for event in second.events)


def test_gateway_cache_is_separated_by_query():
    calls = []

    def provider(arguments):
        calls.append(arguments["query"])
        return search(arguments)

    store = IdempotencyStore()

    dispatch(
        make_call("Python documentation"),
        {"role": "user", "id": "cache-user"},
        search_fn=provider,
        idempotency_store=store,
    )
    dispatch(
        make_call("HTTPX documentation"),
        {"role": "user", "id": "cache-user"},
        search_fn=provider,
        idempotency_store=store,
    )

    assert calls == ["Python documentation", "HTTPX documentation"]
