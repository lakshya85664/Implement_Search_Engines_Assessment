
from src.contracts import ToolStatus
from src.gateway import dispatch
from src.search_engine import search


def valid_call():
    return {
        "name": "search_engine",
        "arguments": {"query": "Python documentation"},
    }


def test_authorized_user_can_search():
    result = dispatch(valid_call(), {"role": "user"})
    assert result.status == ToolStatus.OK


def test_unknown_role_is_denied_before_provider_execution():
    calls = []

    def provider(arguments):
        calls.append(arguments)
        return search(arguments)

    result = dispatch(
        valid_call(),
        {"role": "guest"},
        search_fn=provider,
    )

    assert result.status == ToolStatus.DENIED
    assert calls == []
    assert result.events[0]["event"] == "tool.denied"


def test_missing_principal_is_denied_before_provider_execution():
    calls = []

    def provider(arguments):
        calls.append(arguments)
        return search(arguments)

    result = dispatch(valid_call(), {}, search_fn=provider)

    assert result.status == ToolStatus.DENIED
    assert calls == []


def test_unknown_tool_is_denied_before_provider_execution():
    calls = []

    def provider(arguments):
        calls.append(arguments)
        return search(arguments)

    result = dispatch(
        {"name": "delete_files", "arguments": {}},
        {"role": "admin"},
        search_fn=provider,
    )

    assert result.status == ToolStatus.DENIED
    assert calls == []


def test_malformed_arguments_are_rejected_before_provider_execution():
    calls = []

    def provider(arguments):
        calls.append(arguments)
        return search(arguments)

    result = dispatch(
        {
            "name": "search_engine",
            "arguments": {"query": "x", "unexpected": "value"},
        },
        {"role": "user"},
        search_fn=provider,
    )

    assert result.status == ToolStatus.INVALID
    assert calls == []


def test_extra_tool_call_field_is_rejected():
    result = dispatch(
        {
            "name": "search_engine",
            "arguments": {"query": "Python"},
            "write": True,
        },
        {"role": "admin"},
    )

    assert result.status == ToolStatus.INVALID


def test_provider_timeout_is_mapped_to_timeout_status():
    def timeout_provider(arguments):
        raise TimeoutError("private provider detail")

    result = dispatch(valid_call(), {"role": "user"}, search_fn=timeout_provider)

    assert result.status == ToolStatus.TIMEOUT
    assert result.error == "Search provider timed out"
    assert "private provider detail" not in str(result.__dict__)


def test_provider_connection_failure_is_safe():
    def failed_provider(arguments):
        raise ConnectionError("internal connection details")

    result = dispatch(valid_call(), {"role": "user"}, search_fn=failed_provider)

    assert result.status == ToolStatus.FAILED
    assert result.error == "Search provider is unavailable"
    assert "internal connection details" not in str(result.__dict__)


def test_unexpected_provider_error_does_not_leak_details():
    def broken_provider(arguments):
        raise RuntimeError("secret diagnostic")

    result = dispatch(valid_call(), {"role": "user"}, search_fn=broken_provider)

    assert result.status == ToolStatus.FAILED
    assert result.error == "Search provider failed"
    assert "secret diagnostic" not in str(result.__dict__)


def test_provider_receives_validated_arguments():
    received = []

    def provider(arguments):
        received.append(arguments)
        return search(arguments)

    result = dispatch(
        valid_call(),
        {"role": "analyst"},
        search_fn=provider,
    )

    assert result.status == ToolStatus.OK
    assert len(received) == 1
    assert received[0]["query"] == "Python documentation"
    assert "unexpected" not in received[0]
