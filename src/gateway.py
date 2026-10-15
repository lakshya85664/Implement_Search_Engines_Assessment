
from __future__ import annotations

import json
import sys
import time
import uuid
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from src.contracts import ToolResult, ToolStatus
from src.registry import get_tool
from src.reliability import (
    IdempotencyStore,
    ProviderTimeout,
    RetryPolicy,
    SlidingWindowRateLimiter,
)
from src.schemas import SearchInput
from src.search_engine import search


SearchFunction = Callable[[dict[str, Any]], dict[str, Any]]


def dispatch(
    call: dict,
    principal: dict,
    registry: dict | None = None,
    search_fn: SearchFunction | None = None,
    *,
    retry_policy: RetryPolicy | None = None,
    provider_timeout: ProviderTimeout | None = None,
    rate_limiter: SlidingWindowRateLimiter | None = None,
    idempotency_store: IdempotencyStore | None = None,
) -> ToolResult:
    """Validate, authorize, and reliably dispatch a search request."""
    run_id = f"RUN-{uuid.uuid4().hex[:12].upper()}"
    started = time.perf_counter()
    events: list[dict[str, Any]] = []

    def finish(
        status: ToolStatus,
        *,
        data: dict[str, Any] | None = None,
        error: str | None = None,
        next_action: str | None = None,
        event_type: str = "tool.completed",
    ) -> ToolResult:
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        events.append({
            "event": event_type,
            "run_id": run_id,
            "tool": "search_engine",
            "status": status.value,
            "duration_ms": duration_ms,
        })
        return ToolResult(
            run_id=run_id,
            status=status,
            data=data or {},
            error=error,
            next_action=next_action,
            events=events.copy(),
        )

    # 1. Validate the call envelope.
    if not isinstance(call, dict):
        return finish(
            ToolStatus.INVALID,
            error="Tool call must be an object",
            next_action="correct_arguments",
        )

    if set(call) - {"name", "arguments"}:
        return finish(
            ToolStatus.INVALID,
            error="Tool call contains unsupported fields",
            next_action="correct_arguments",
        )

    name = call.get("name")
    arguments = call.get("arguments", {})

    if not isinstance(name, str) or not name:
        return finish(
            ToolStatus.INVALID,
            error="Tool name must be a non-empty string",
            next_action="correct_arguments",
        )

    spec = get_tool(name) if registry is None else registry.get(name)

    if spec is None:
        return finish(
            ToolStatus.DENIED,
            error="Unknown tool",
            next_action="choose_registered_tool",
            event_type="tool.denied",
        )

    # 2. Authorize before invoking any provider.
    if not isinstance(principal, dict):
        return finish(
            ToolStatus.DENIED,
            error="Principal is not authorized",
            next_action="request_authorization",
            event_type="tool.denied",
        )

    role = principal.get("role")
    if not isinstance(role, str) or role not in spec.allowed_roles:
        return finish(
            ToolStatus.DENIED,
            error="Principal is not authorized for this tool",
            next_action="request_authorization",
            event_type="tool.denied",
        )

    if spec.access != "read_only":
        return finish(
            ToolStatus.DENIED,
            error="Tool access policy is not permitted",
            next_action="review_tool_policy",
            event_type="tool.denied",
        )

    if not isinstance(arguments, dict):
        return finish(
            ToolStatus.INVALID,
            error="Arguments must be an object",
            next_action="correct_arguments",
        )

    # 3. Validate and normalize arguments before computing a cache key.
    try:
        request = SearchInput.model_validate(arguments)
        validated_arguments = request.model_dump()
    except ValidationError:
        return finish(
            ToolStatus.INVALID,
            error="Search arguments failed validation",
            next_action="correct_arguments",
        )

    if retry_policy is None:
        retry_policy = RetryPolicy(max_attempts=1)

    if provider_timeout is None:
        provider_timeout = ProviderTimeout(timeout_seconds=2.0)

    # 4. Apply per-principal rate limiting when configured.
    if rate_limiter is not None:
        principal_key = str(
            principal.get("id") or principal.get("role") or "anonymous"
        )
        if not rate_limiter.allow(principal_key):
            return finish(
                ToolStatus.RATE_LIMITED,
                error="Search rate limit exceeded",
                next_action="wait_before_retry",
                event_type="tool.rate_limited",
            )

    # 5. Return cached successful results if an idempotency store is supplied.
    cache_key = None
    if idempotency_store is not None:
        cache_key = idempotency_store.fingerprint(name, validated_arguments)
        cached = idempotency_store.get(cache_key)
        if cached is not None:
            events.append({
                "event": "tool.cache_hit",
                "run_id": run_id,
                "tool": name,
                "status": "ok",
            })
            return finish(
                ToolStatus.OK,
                data=cached,
                event_type="tool.completed",
            )

    provider = search_fn or search

    def invoke_provider() -> dict[str, Any]:
        return provider(validated_arguments)

    # 6. Execute with bounded retry attempts and a bounded wait.
    try:
        data = retry_policy.run(
            lambda: provider_timeout.run(invoke_provider),
            retry_on=(ConnectionError, OSError),
        )

        if not isinstance(data, dict):
            return finish(
                ToolStatus.FAILED,
                error="Search provider returned an invalid response",
                next_action="review_provider",
                event_type="provider.failed",
            )

        events.append({
            "event": "provider.completed",
            "run_id": run_id,
            "provider": data.get("provider", "injected"),
            "status": "ok",
        })
        events.insert(0, {
            "event": "tool.completed",
            "run_id": run_id,
            "tool": name,
            "status": "ok",
            "provider": data.get("provider", "injected"),
            "result_count": data.get("result_count", 0),
        })

        if idempotency_store is not None and cache_key is not None:
            idempotency_store.put(cache_key, data)

        return finish(ToolStatus.OK, data=data)

    except TimeoutError:
        return finish(
            ToolStatus.TIMEOUT,
            error="Search provider timed out",
            next_action="retry_or_review",
            event_type="provider.timeout",
        )
    except ValidationError:
        return finish(
            ToolStatus.INVALID,
            error="Search arguments failed validation",
            next_action="correct_arguments",
        )
    except (ConnectionError, OSError):
        return finish(
            ToolStatus.FAILED,
            error="Search provider is unavailable",
            next_action="retry_or_review",
            event_type="provider.failed",
        )
    except Exception:
        return finish(
            ToolStatus.FAILED,
            error="Search provider failed",
            next_action="review_provider",
            event_type="provider.failed",
        )


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]).strip() or "Python documentation"

    result = dispatch(
        {
            "name": "search_engine",
            "arguments": {"query": query},
        },
        {"role": "user", "id": "demo-user"},
    )

    print(json.dumps({
        "run_id": result.run_id,
        "status": result.status.value,
        "data": result.data,
        "error": result.error,
        "next_action": result.next_action,
        "events": result.events,
    }, indent=2))
