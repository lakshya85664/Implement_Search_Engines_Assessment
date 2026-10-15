
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pydantic import ValidationError

from src.gateway import dispatch
from src.reliability import (
    IdempotencyStore,
    ProviderTimeout,
    RetryPolicy,
    SlidingWindowRateLimiter,
)
from src.search_engine import search


EVIDENCE_DIR = Path(__file__).resolve().parent
FIXTURE_PATH = PROJECT_ROOT / "workspace" / "knowledge.json"


def write_json(filename: str, payload: dict) -> None:
    output_path = EVIDENCE_DIR / filename
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Created: evidence/{filename}")


def main() -> None:
    timestamp = datetime.now(timezone.utc).isoformat()

    # Task 1: Ranked search results and citations.
    search_result = search(
        {
            "query": "Python documentation tutorial",
            "max_results": 5,
            "freshness": "any",
            "domains": [],
        },
        fixture_path=FIXTURE_PATH,
    )
    write_json(
        "task1_search_results.json",
        {
            "generated_at": timestamp,
            "task": "Search results and ranking",
            "result_count": search_result["result_count"],
            "results": search_result["results"],
            "citations": search_result["citations"],
        },
    )

    # Task 2: Execute a search through the actual dispatch function.
    call = {
        "name": "search_engine",
        "arguments": {
            "query": "Python documentation",
            "max_results": 3,
            "freshness": "any",
            "domains": [],
        },
    }
    principal = {"id": "evidence-runner", "role": "analyst"}
    gateway_result = dispatch(call, principal)

    write_json(
        "task2_gateway_execution.json",
        {
            "generated_at": timestamp,
            "task": "Gateway execution",
            "run_id": gateway_result.run_id,
            "status": gateway_result.status.value,
            "data": gateway_result.data,
            "error": gateway_result.error,
            "next_action": gateway_result.next_action,
            "events": gateway_result.events,
        },
    )

    # Task 3: Verify invalid input is rejected.
    try:
        search(
            {
                "query": "x",
                "max_results": 100,
                "freshness": "any",
                "domains": [],
            },
            fixture_path=FIXTURE_PATH,
        )
        validation = {
            "rejected": False,
            "message": "Unexpectedly accepted invalid input",
        }
    except (ValidationError, ValueError) as exc:
        validation = {
            "rejected": True,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }

    write_json(
        "task3_validation.json",
        {
            "generated_at": timestamp,
            "task": "Strict input validation",
            **validation,
        },
    )

    # Task 4: Exercise reliability features through dispatch.
    # Transient provider failure followed by success.
    retry_state = {"calls": 0}

    def flaky_provider(arguments: dict) -> dict:
        retry_state["calls"] += 1
        if retry_state["calls"] < 3:
            raise ConnectionError("Simulated transient failure")
        return search(arguments, fixture_path=FIXTURE_PATH)

    retry_result = dispatch(
        call,
        principal,
        search_fn=flaky_provider,
        retry_policy=RetryPolicy(max_attempts=3),
        provider_timeout=ProviderTimeout(timeout_seconds=1.0),
    )

    write_json(
        "task4_retry_evidence.json",
        {
            "generated_at": timestamp,
            "task": "Transient provider retry",
            "status": retry_result.status.value,
            "provider_calls": retry_state["calls"],
            "events": retry_result.events,
            "error": retry_result.error,
        },
    )

    # Rate limiting: allow one request and reject the next.
    rate_state = {"calls": 0}

    def counting_provider(arguments: dict) -> dict:
        rate_state["calls"] += 1
        return search(arguments, fixture_path=FIXTURE_PATH)

    limiter = SlidingWindowRateLimiter(max_calls=1, window_seconds=60.0)
    first = dispatch(
        call,
        principal,
        search_fn=counting_provider,
        rate_limiter=limiter,
    )
    second = dispatch(
        call,
        principal,
        search_fn=counting_provider,
        rate_limiter=limiter,
    )

    write_json(
        "task5_rate_limit_evidence.json",
        {
            "generated_at": timestamp,
            "task": "Per-principal rate limiting",
            "first_status": first.status.value,
            "second_status": second.status.value,
            "provider_calls": rate_state["calls"],
            "second_error": second.error,
        },
    )

    # Idempotency: repeated equivalent requests use cached data.
    store = IdempotencyStore()
    cache_state = {"calls": 0}

    def cached_provider(arguments: dict) -> dict:
        cache_state["calls"] += 1
        return search(arguments, fixture_path=FIXTURE_PATH)

    cached_first = dispatch(
        call,
        principal,
        search_fn=cached_provider,
        idempotency_store=store,
    )
    cached_second = dispatch(
        call,
        principal,
        search_fn=cached_provider,
        idempotency_store=store,
    )

    write_json(
        "task6_idempotency_evidence.json",
        {
            "generated_at": timestamp,
            "task": "Idempotency and replay",
            "first_status": cached_first.status.value,
            "second_status": cached_second.status.value,
            "provider_calls": cache_state["calls"],
            "second_events": cached_second.events,
            "same_data": cached_first.data == cached_second.data,
        },
    )

    print("\nEvidence generation completed.")


if __name__ == "__main__":
    main()
