"""Event truncation for MCPcat.

Enforces a maximum event payload size by truncating oversized string
values, limiting nesting depth and collection breadth, and detecting
circular references. Acts as a safety net — most events pass through
unchanged.
"""

from datetime import date, datetime
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from mcpcat.types import UnredactedEvent

from .logging import write_to_log

MAX_EVENT_BYTES = 102_400   # 100 KB total event size
MAX_STRING_BYTES = 10_240   # 10 KB per individual string
MAX_DEPTH = 5               # Max nesting depth for dicts/lists
MAX_BREADTH = 500           # Max items per dict/list


def _truncate_string(value: str, max_bytes: int = MAX_STRING_BYTES) -> str:
    """Truncate a string if its UTF-8 byte size exceeds *max_bytes*."""
    byte_size = len(value.encode("utf-8"))
    if byte_size <= max_bytes:
        return value

    marker = f"[string truncated by MCPcat from {byte_size} bytes]"
    marker_bytes = len(marker.encode("utf-8"))
    keep_bytes = max_bytes - marker_bytes

    if keep_bytes <= 0:
        return marker

    truncated = value.encode("utf-8")[:keep_bytes].decode("utf-8", errors="ignore")
    return truncated + marker


def _truncate_value(
    value: Any,
    *,
    max_depth: int = MAX_DEPTH,
    max_string_bytes: int = MAX_STRING_BYTES,
    _depth: int = 0,
    _seen: set[int] | None = None,
) -> Any:
    """Recursively walk a value and apply truncation limits."""
    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, (datetime, date)):
        return value

    if isinstance(value, str):
        return _truncate_string(value, max_bytes=max_string_bytes)

    if _seen is None:
        _seen = set()

    obj_id = id(value)
    if obj_id in _seen:
        return "[circular reference]"

    _seen.add(obj_id)
    try:
        at_depth_limit = _depth >= max_depth

        if isinstance(value, dict):
            items = list(value.items())
            result = {}
            for i, (k, v) in enumerate(items):
                if i >= MAX_BREADTH:
                    remaining = len(items) - MAX_BREADTH
                    result["__truncated__"] = (
                        f"[... {remaining} more items truncated by MCPcat]"
                    )
                    break
                if at_depth_limit:
                    result[str(k)] = (
                        f"[nested content truncated by MCPcat at depth {max_depth}]"
                        if isinstance(v, (dict, list, tuple))
                        else _truncate_value(
                            v, max_depth=max_depth, max_string_bytes=max_string_bytes,
                            _depth=_depth + 1, _seen=_seen,
                        )
                    )
                else:
                    result[str(k)] = _truncate_value(
                        v, max_depth=max_depth, max_string_bytes=max_string_bytes,
                        _depth=_depth + 1, _seen=_seen,
                    )
            return result

        if isinstance(value, (list, tuple)):
            if at_depth_limit:
                return f"[nested content truncated by MCPcat at depth {max_depth}]"
            result_list = [
                _truncate_value(
                    item, max_depth=max_depth, max_string_bytes=max_string_bytes,
                    _depth=_depth + 1, _seen=_seen,
                )
                for i, item in enumerate(value)
                if i < MAX_BREADTH
            ]
            if len(value) > MAX_BREADTH:
                remaining = len(value) - MAX_BREADTH
                result_list.append(
                    f"[... {remaining} more items truncated by MCPcat]"
                )
            return result_list

        if at_depth_limit:
            return f"[nested content truncated by MCPcat at depth {max_depth}]"

        # Fallback for unknown types — repr and truncate
        return _truncate_string(repr(value), max_bytes=max_string_bytes)
    finally:
        _seen.discard(obj_id)


def truncate_event(event: Optional["UnredactedEvent"]) -> Optional["UnredactedEvent"]:
    """Return a truncated copy of *event* if it exceeds MAX_EVENT_BYTES.

    Uses size-targeted normalization strategy: normalize with the
    current limits, check JSON byte size, and if still over the limit tighten
    limits and re-normalize until it fits.

    Each pass reduces depth by 1 and halves the per-string byte limit.

    - Checks serialized JSON byte size first (fast path)
    - Never mutates the original event
    - Returns original event unchanged if under limit
    - Returns original event unchanged if truncation itself fails
    """
    if event is None:
        return None

    try:
        serialized_bytes = event.model_dump_json().encode("utf-8")
        byte_size = len(serialized_bytes)
        if byte_size <= MAX_EVENT_BYTES:
            return event

        write_to_log(
            f"Event {event.id or 'unknown'} exceeds {MAX_EVENT_BYTES} bytes "
            f"({byte_size} bytes), truncating"
        )

        truncated_dict = event.model_dump()
        depth = MAX_DEPTH
        string_bytes = MAX_STRING_BYTES

        event_cls = type(event)

        while depth >= 0:
            truncated_dict = _truncate_value(
                truncated_dict, max_depth=depth, max_string_bytes=string_bytes,
            )
            candidate = event_cls.model_validate(truncated_dict)
            result_bytes = len(candidate.model_dump_json().encode("utf-8"))
            if result_bytes <= MAX_EVENT_BYTES:
                return candidate
            write_to_log(
                f"Event still {result_bytes} bytes at depth={depth} "
                f"string_limit={string_bytes}, tightening limits"
            )
            depth -= 1
            string_bytes //= 2

        return candidate

    except Exception as e:
        write_to_log(f"WARNING: Truncation failed for event {event.id or 'unknown'}: {e}")
        return event
