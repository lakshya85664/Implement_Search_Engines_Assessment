
import pytest
from pydantic import ValidationError

from src.gateway import dispatch
from src.search_engine import normalize_query, search


def test_query_normalization():
    assert normalize_query("  PYTHON   Documentation!! ") == "python documentation"


def test_search_returns_ranked_cited_results():
    output = search({"query": "Python documentation", "max_results": 5})
    assert output["result_count"] > 0
    assert output["result_count"] == len(output["results"])
    assert output["citations"] == [item["url"] for item in output["results"]]
    assert output["provider"] == "local_fixture"


def test_title_match_ranks_above_content_only_match():
    output = search({"query": "Python tutorial"})
    titles = [item["title"] for item in output["results"]]
    assert titles[0] == "Python Tutorial"


def test_max_results_is_respected():
    output = search({"query": "Python", "max_results": 1})
    assert len(output["results"]) <= 1


def test_domain_filter():
    output = search({
        "query": "documentation Python",
        "domains": ["docs.python.org"],
    })
    assert all(item["source"] == "docs.python.org" for item in output["results"])


def test_search_has_bounded_snippets():
    output = search({"query": "Python"})
    assert all(len(item["snippet"]) <= 500 for item in output["results"])


def test_repeat_search_is_deterministic():
    arguments = {"query": "Python documentation", "max_results": 5}
    assert search(arguments) == search(arguments)


def test_gateway_returns_success_and_trace_event():
    result = dispatch(
        {"name": "search_engine", "arguments": {"query": "Python documentation"}},
        {"role": "user", "id": "demo-user"},
    )
    assert result.status.value == "ok"
    assert result.data["result_count"] > 0
    assert result.events[0]["event"] == "tool.completed"


def test_punctuation_only_query_is_rejected():
    with pytest.raises(ValueError):
        search({"query": "!!!"})
