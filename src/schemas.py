
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator


class StrictInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class SearchInput(StrictInput):
    query: StrictStr = Field(
        min_length=2,
        max_length=300,
        description="Natural-language query for the local knowledge search engine",
    )
    max_results: int = Field(default=5, ge=1, le=10)
    freshness: str = Field(
        default="any",
        description="Freshness preference: any, day, week, or month",
    )
    domains: list[StrictStr] = Field(default_factory=list, max_length=10)

    @field_validator("freshness")
    @classmethod
    def validate_freshness(cls, value: str) -> str:
        allowed = {"any", "day", "week", "month"}
        if value not in allowed:
            raise ValueError("freshness must be any, day, week, or month")
        return value

    @field_validator("domains")
    @classmethod
    def validate_domains(cls, values: list[str]) -> list[str]:
        cleaned = []
        for domain in values:
            domain = domain.strip().lower()
            if not domain or len(domain) > 253 or "/" in domain or " " in domain:
                raise ValueError("each domain must be a valid hostname-like value")
            cleaned.append(domain)
        return cleaned


class SearchResultItem(BaseModel):
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    snippet: str = Field(min_length=1, max_length=500)
    source: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)


class SearchOutput(BaseModel):
    query: str
    results: list[SearchResultItem] = Field(max_length=10)
    result_count: int = Field(ge=0, le=10)
    citations: list[str] = Field(max_length=10)
    provider: str
