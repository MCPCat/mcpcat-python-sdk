"""
Shared trace context management for all exporters.
Maintains one trace ID per session for proper observability tool correlation.
"""

import random
from typing import Dict, Optional


class TraceContext:
    """Manages trace and span ID generation for all exporters."""

    def __init__(self):
        self.session_traces: Dict[str, str] = {}

    def get_trace_id(self, session_id: Optional[str] = None) -> str:
        """
        Get or create a trace ID for a session.
        Returns the same trace ID for all events in a session.

        Args:
            session_id: Optional session identifier

        Returns:
            32-character hex trace ID
        """
        if not session_id:
            # No session, return random trace ID
            return self.random_hex(32)

        if session_id not in self.session_traces:
            # First event in session, create new trace ID
            self.session_traces[session_id] = self.random_hex(32)

        return self.session_traces[session_id]

    def generate_span_id(self) -> str:
        """
        Generate a random span ID.
        Always returns a new random ID for uniqueness.

        Returns:
            16-character hex span ID
        """
        return self.random_hex(16)

    def random_hex(self, length: int) -> str:
        """
        Generate random hex string of specified length.
        Uses random.choices for performance (same approach as OpenTelemetry).

        Args:
            length: Length of hex string to generate

        Returns:
            Random hex string
        """
        return "".join(random.choices("0123456789abcdef", k=length))

    def clear_old_sessions(self, max_sessions: int = 1000) -> None:
        """
        Optional: Clear old sessions to prevent memory leaks.
        Can be called periodically for long-running servers.

        Args:
            max_sessions: Maximum number of sessions to keep
        """
        if len(self.session_traces) > max_sessions:
            # Simple strategy: clear oldest half when limit exceeded
            # In production, might want LRU cache or timestamp-based clearing
            to_remove = len(self.session_traces) - (max_sessions // 2)
            for key in list(self.session_traces.keys())[:to_remove]:
                del self.session_traces[key]


# Export singleton instance
trace_context = TraceContext()
