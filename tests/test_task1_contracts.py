
import pytest
from pydantic import ValidationError

from src.contracts import ToolStatus
from src.registry import REGISTRY, get_tool, registry_summary
from src.schemas import SearchInput, SearchOutput, SearchResultItem


def test_valid_search_input():
    request = SearchInput(
        query="Python search engine",
        max_results=3,
        freshness="week",
        domains=["docs.python.org"],
    )
    assert request.query == "Python search engine"
    assert request.max_results == 3
    assert request.freshness == "week"
    assert request.domains == ["docs.python.org"]


def test_invalid_short_query_is_rejected():
    with pytest.raises(ValidationError):
        SearchInput(query="x")


def test_unknown_input_field_is_rejected():
    with pytest.raises(ValidationError):
        SearchInput(query="Python", unexpected="value")


def test_invalid_result_limit_is_rejected():
    with pytest.raises(ValidationError):
        SearchInput(query="Python", max_results=11)


def test_invalid_freshness_is_rejected():
    with pytest.raises(ValidationError):
        SearchInput(query="Python", freshness="forever")


def test_invalid_domain_is_rejected():
    with pytest.raises(ValidationError):
        SearchInput(query="Python", domains=["bad domain"])


def test_output_contract_accepts_cited_result():
    item = SearchResultItem(
        title="Python Documentation",
        url="https://docs.python.org/",
        snippet="Official Python documentation.",
        source="docs.python.org",
        score=0.95,
    )
    output = SearchOutput(
        query="Python documentation",
        results=[item],
        result_count=1,
        citations=[item.url],
        provider="local_fixture",
    )
    assert output.result_count == len(output.results)
    assert output.citations == [item.url]


def test_search_tool_is_registered_read_only():
    spec = get_tool("search_engine")
    assert spec is not None
    assert spec.access == "read_only"
    assert "user" in spec.allowed_roles
    assert "search_engine" in REGISTRY


def test_registry_summary_is_serializable():
    summary = registry_summary()
    assert len(summary) == 1
    assert summary[0]["name"] == "search_engine"
    assert summary[0]["max_calls_per_minute"] == 30


def test_tool_status_values_are_defined():
    assert ToolStatus.OK.value == "ok"
    assert ToolStatus.DENIED.value == "denied"
    assert ToolStatus.TIMEOUT.value == "timeout"
