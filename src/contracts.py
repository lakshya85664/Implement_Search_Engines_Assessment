
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ToolStatus(str, Enum):
    OK = "ok"
    INVALID = "invalid"
    DENIED = "denied"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    FAILED = "failed"
    REVIEW_REQUIRED = "review_required"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    description: str
    access: str
    allowed_roles: tuple[str, ...]
    input_schema: str
    output_schema: str
    max_calls_per_minute: int = 30


@dataclass
class ToolResult:
    run_id: str
    status: ToolStatus
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    next_action: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
