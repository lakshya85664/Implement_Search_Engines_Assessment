
from __future__ import annotations

from src.contracts import ToolSpec


SEARCH_TOOL = ToolSpec(
    name="search_engine",
    version="1.0.0",
    description=(
        "Search the approved knowledge fixture and return ranked results "
        "with source URLs and cited snippets."
    ),
    access="read_only",
    allowed_roles=("user", "analyst", "admin"),
    input_schema="SearchInput",
    output_schema="SearchOutput",
    max_calls_per_minute=30,
)

REGISTRY: dict[str, ToolSpec] = {
    SEARCH_TOOL.name: SEARCH_TOOL,
}


def get_tool(name: str) -> ToolSpec | None:
    return REGISTRY.get(name)


def registry_summary() -> list[dict[str, object]]:
    return [
        {
            "name": spec.name,
            "version": spec.version,
            "description": spec.description,
            "access": spec.access,
            "allowed_roles": list(spec.allowed_roles),
            "input_schema": spec.input_schema,
            "output_schema": spec.output_schema,
            "max_calls_per_minute": spec.max_calls_per_minute,
        }
        for spec in REGISTRY.values()
    ]
