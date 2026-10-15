
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.schemas import SearchInput, SearchOutput, SearchResultItem


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = PROJECT_ROOT / "workspace" / "knowledge.json"


def normalize_query(query: str) -> str:
    """Normalize whitespace and case while preserving useful word characters."""
    normalized = query.casefold()
    normalized = re.sub(r"[^\w\s.-]", " ", normalized)
    return " ".join(normalized.split())


def tokenize(text: str) -> list[str]:
    """Return normalized alphanumeric search terms."""
    return re.findall(r"[a-z0-9]+", normalize_query(text))


def load_documents(fixture_path: str | Path = DEFAULT_FIXTURE) -> list[dict[str, Any]]:
    """Load the controlled JSON fixture."""
    path = Path(fixture_path).resolve(strict=True)
    if not path.is_file():
        raise FileNotFoundError("Knowledge fixture is not a file")

    with path.open("r", encoding="utf-8") as file:
        documents = json.load(file)

    if not isinstance(documents, list):
        raise ValueError("Knowledge fixture must contain a JSON list")

    for document in documents:
        if not isinstance(document, dict):
            raise ValueError("Knowledge fixture contains an invalid record")
        for field in ("title", "url", "domain", "content", "updated_at"):
            if not isinstance(document.get(field), str) or not document[field]:
                raise ValueError("Knowledge fixture contains an invalid record")

        parsed_url = urlparse(document["url"])
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise ValueError("Knowledge fixture contains an invalid URL")

    return documents


def _freshness_cutoff(freshness: str) -> date | None:
    today = date.today()
    if freshness == "day":
        return today - timedelta(days=1)
    if freshness == "week":
        return today - timedelta(days=7)
    if freshness == "month":
        return today - timedelta(days=30)
    return None


def _score_document(query_terms: list[str], document: dict[str, Any]) -> float:
    """Score title matches more highly than content-only matches."""
    if not query_terms:
        return 0.0

    title_terms = set(tokenize(document["title"]))
    content_terms = set(tokenize(document["content"]))
    matched_title = sum(term in title_terms for term in query_terms)
    matched_content = sum(term in content_terms for term in query_terms)

    # Deterministic score; the same input produces the same score.
    raw_score = (2.0 * matched_title + matched_content) / (3.0 * len(query_terms))
    return round(min(1.0, raw_score), 4)


def search(
    arguments: dict[str, Any],
    fixture_path: str | Path = DEFAULT_FIXTURE,
) -> dict[str, Any]:
    """Search the local fixture and return validated, ranked, cited results."""
    request = SearchInput.model_validate(arguments)
    normalized_query = normalize_query(request.query)
    query_terms = tokenize(normalized_query)

    if not query_terms:
        # Punctuation-only queries are not useful search requests.
        raise ValueError("Query must contain searchable terms")

    documents = load_documents(fixture_path)
    requested_domains = set(request.domains)
    cutoff = _freshness_cutoff(request.freshness)

    ranked: list[tuple[float, str, dict[str, Any]]] = []

    for document in documents:
        if requested_domains and document["domain"].casefold() not in requested_domains:
            continue

        try:
            updated = date.fromisoformat(document["updated_at"])
        except ValueError as exc:
            raise ValueError("Knowledge fixture contains an invalid date") from exc

        if cutoff is not None and updated < cutoff:
            continue

        score = _score_document(query_terms, document)
        if score > 0:
            ranked.append((score, document["title"].casefold(), document))

    # Score descending, then title ascending for deterministic tie-breaking.
    ranked.sort(key=lambda item: (-item[0], item[1]))
    ranked = ranked[: request.max_results]

    results = []
    citations = []

    for score, _, document in ranked:
        content = " ".join(document["content"].split())
        snippet = content[:497].rstrip()
        if len(content) > 497:
            snippet += "..."

        item = SearchResultItem(
            title=document["title"],
            url=document["url"],
            snippet=snippet,
            source=document["domain"],
            score=score,
        )
        results.append(item)
        citations.append(item.url)

    output = SearchOutput(
        query=normalized_query,
        results=results,
        result_count=len(results),
        citations=citations,
        provider="local_fixture",
    )
    return output.model_dump(mode="json")
