"""Unit tests for the truncation module."""

from unittest.mock import patch

from mcpcat.modules.truncation import (
    _truncate_value,
    truncate_event,
    MAX_STRING_BYTES,
    MAX_DEPTH,
    MAX_BREADTH,
    MAX_EVENT_BYTES,
)
from mcpcat.types import UnredactedEvent


def _make_event(**overrides) -> UnredactedEvent:
    """Helper to build a minimal valid event with optional overrides."""
    defaults = {
        "event_type": "mcp:tools/call",
        "resource_name": "test_tool",
        "session_id": "test-session-id",
    }
    defaults.update(overrides)
    return UnredactedEvent(**defaults)


class TestStringTruncation:
    """String values over MAX_STRING_BYTES are truncated."""

    def test_short_string_unchanged(self):
        assert _truncate_value("hello") == "hello"

    def test_string_at_limit_unchanged(self):
        s = "a" * MAX_STRING_BYTES
        assert _truncate_value(s) == s

    def test_string_over_limit_truncated_with_marker(self):
        original = "a" * (MAX_STRING_BYTES + 500)
        result = _truncate_value(original)
        byte_size = len(original.encode("utf-8"))
        expected_suffix = f"[string truncated by MCPcat from {byte_size} bytes]"
        assert result.endswith(expected_suffix)
        assert len(result.encode("utf-8")) < len(original.encode("utf-8"))

    def test_utf8_multibyte_truncated_by_bytes_no_broken_codepoints(self):
        # Each emoji is 4 bytes. 2560 emojis = 10,240 bytes = exactly at limit
        s = "\U0001f600" * 2561  # 10,244 bytes — just over limit
        result = _truncate_value(s)
        byte_size = len(s.encode("utf-8"))
        assert f"[string truncated by MCPcat from {byte_size} bytes]" in result
        # Verify valid UTF-8 — would raise if broken
        result.encode("utf-8")


class TestDepthLimiting:
    """Structures nested beyond MAX_DEPTH are replaced with a marker."""

    def test_at_max_depth_passes_through(self):
        # Build nested dict exactly MAX_DEPTH levels deep
        value = "leaf"
        for _ in range(MAX_DEPTH):
            value = {"nested": value}
        result = _truncate_value(value)
        # Should reach the leaf string
        inner = result
        for _ in range(MAX_DEPTH):
            inner = inner["nested"]
        assert inner == "leaf"

    def test_exceeds_max_depth_replaced_with_marker(self):
        # Build nested dict MAX_DEPTH + 1 levels deep
        value = "leaf"
        for _ in range(MAX_DEPTH + 1):
            value = {"nested": value}
        result = _truncate_value(value)
        # Walk to depth MAX_DEPTH — should hit marker
        inner = result
        for _ in range(MAX_DEPTH):
            inner = inner["nested"]
        assert inner == f"[nested content truncated by MCPcat at depth {MAX_DEPTH}]"

    def test_max_depth_zero_preserves_top_level_mapping(self):
        value = {
            "event_type": "mcp:tools/call",
            "parameters": {"nested": {"x": "y"}},
        }
        result = _truncate_value(value, max_depth=0)
        assert isinstance(result, dict)
        assert result["event_type"] == "mcp:tools/call"
        assert result["parameters"] == "[nested content truncated by MCPcat at depth 0]"


class TestBreadthLimiting:
    """Dicts/lists with more than MAX_BREADTH items are trimmed."""

    def test_dict_at_breadth_limit_unchanged(self):
        d = {f"key_{i}": i for i in range(MAX_BREADTH)}
        result = _truncate_value(d)
        assert len(result) == MAX_BREADTH

    def test_dict_over_breadth_limit_trimmed_with_marker(self):
        d = {f"key_{i}": i for i in range(MAX_BREADTH + 5)}
        result = _truncate_value(d)
        assert len(result) == MAX_BREADTH + 1  # MAX_BREADTH items + 1 marker
        assert "__truncated__" in result
        assert "5 more items truncated by MCPcat" in result["__truncated__"]

    def test_list_at_breadth_limit_unchanged(self):
        lst = list(range(MAX_BREADTH))
        result = _truncate_value(lst)
        assert len(result) == MAX_BREADTH

    def test_list_over_breadth_limit_trimmed_with_marker(self):
        lst = list(range(MAX_BREADTH + 30))
        result = _truncate_value(lst)
        assert len(result) == MAX_BREADTH + 1  # MAX_BREADTH items + 1 marker string
        assert "30 more items truncated by MCPcat" in result[-1]


class TestCircularReferences:
    """Circular references are detected and replaced with a marker."""

    def test_self_referencing_dict_replaced(self):
        d: dict = {"key": "value"}
        d["self"] = d
        result = _truncate_value(d)
        assert result["key"] == "value"
        assert result["self"] == "[circular reference]"

    def test_same_object_at_two_positions_not_falsely_flagged(self):
        shared = {"data": "hello"}
        parent = {"a": shared, "b": shared}
        result = _truncate_value(parent)
        # Both should resolve to the actual value, not circular marker
        assert result["a"] == {"data": "hello"}
        assert result["b"] == {"data": "hello"}


class TestTruncateEventFastPath:
    """Events under MAX_EVENT_BYTES are returned unchanged."""

    def test_small_event_returned_unchanged(self):
        event = _make_event(parameters={"key": "small"})
        result = truncate_event(event)
        assert result is event  # Same object — no copy made

    def test_none_returns_none(self):
        assert truncate_event(None) is None


class TestTruncateEventOversized:
    """Events over MAX_EVENT_BYTES are truncated."""

    def test_large_string_in_parameters_truncated(self):
        big = "x" * 200_000  # ~200 KB string
        event = _make_event(parameters={"data": big})
        result = truncate_event(event)
        # Result should be a different object
        assert result is not event
        # The big string should be truncated
        assert len(result.parameters["data"]) < len(big)
        assert "truncated by MCPcat" in result.parameters["data"]

    def test_large_string_in_response_truncated(self):
        big = "x" * 200_000
        event = _make_event(response={"output": big})
        result = truncate_event(event)
        assert "truncated by MCPcat" in result.response["output"]

    def test_large_string_in_error_truncated(self):
        big = "x" * 200_000
        event = _make_event(error={"message": "fail", "stack": big})
        result = truncate_event(event)
        assert "truncated by MCPcat" in result.error["stack"]

    def test_large_identify_data_truncated(self):
        big = "x" * 200_000
        event = _make_event(identify_data={"bio": big})
        result = truncate_event(event)
        assert "truncated by MCPcat" in result.identify_data["bio"]

    def test_original_event_not_mutated(self):
        big = "x" * 200_000
        event = _make_event(parameters={"data": big})
        original_data = event.parameters["data"]
        truncate_event(event)
        assert event.parameters["data"] == original_data


class TestSizeGuarantee:
    """Truncated events are guaranteed to be <= MAX_EVENT_BYTES."""

    def test_single_large_string_under_limit(self):
        big = "x" * 200_000
        event = _make_event(parameters={"data": big})
        result = truncate_event(event)
        result_bytes = len(result.model_dump_json().encode("utf-8"))
        assert result_bytes <= MAX_EVENT_BYTES

    def test_many_large_strings_under_limit(self):
        """20 strings of 10 KB each = 200 KB of strings before truncation."""
        params = {f"key_{i}": "x" * 20_000 for i in range(20)}
        event = _make_event(parameters=params)
        result = truncate_event(event)
        result_bytes = len(result.model_dump_json().encode("utf-8"))
        assert result_bytes <= MAX_EVENT_BYTES

    def test_deeply_nested_wide_structure_under_limit(self):
        """Deeply nested + wide structure that exceeds 100 KB."""
        value = {f"k{i}": "x" * 5_000 for i in range(15)}
        for _ in range(6):
            value = {f"level_{i}": value for i in range(5)}
        event = _make_event(parameters=value)
        result = truncate_event(event)
        result_bytes = len(result.model_dump_json().encode("utf-8"))
        assert result_bytes <= MAX_EVENT_BYTES

    def test_depth_reduces_progressively(self):
        """Verify depth reduction kicks in when first pass isn't enough."""
        # Build a structure that's over 100 KB even after depth=5 truncation
        # 20 keys * 10 KB string = 200 KB at each level, nested 5 deep
        level = {f"k{i}": "x" * 10_000 for i in range(20)}
        for _ in range(5):
            level = {"nested": level, "extra": "x" * 10_000}
        event = _make_event(parameters=level)
        result = truncate_event(event)
        result_bytes = len(result.model_dump_json().encode("utf-8"))
        assert result_bytes <= MAX_EVENT_BYTES


class TestTruncateEventErrorHandling:
    """Truncation failures return the original event."""

    def test_exception_during_truncation_returns_original(self):
        big = "x" * 200_000
        event = _make_event(parameters={"data": big})
        with patch(
            "mcpcat.modules.truncation._truncate_value",
            side_effect=RuntimeError("boom"),
        ):
            result = truncate_event(event)
        # Should return original event, not crash
        assert result is event


class TestPipelineIntegration:
    """Truncation runs after sanitization in the event pipeline."""

    def test_truncation_is_imported_in_event_queue(self):
        """Verify truncate_event is used in event_queue module."""
        import inspect
        from mcpcat.modules.event_queue import EventQueue
        source = inspect.getsource(EventQueue._process_event)
        assert "truncate_event" in source
