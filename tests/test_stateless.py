"""Tests for stateless mode behavior."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from mcpcat.modules.internal import (
    get_server_tracking_data,
    set_server_tracking_data,
    reset_all_tracking_data,
)
from mcpcat.modules.session import get_server_session_id
from mcpcat.modules.identify import identify_session
from mcpcat.types import MCPCatData, MCPCatOptions, SessionInfo, UserIdentity

from .test_utils.todo_server import create_todo_server


def _make_identify_fn(user_id="user_123", user_name="Test User"):
    """Return an identify function that always returns a UserIdentity."""
    def identify(request, context):
        return UserIdentity(user_id=user_id, user_name=user_name, user_data=None)
    return identify


class TestStatelessMode:
    """Tests for SDK stateless mode behavior."""

    def setup_method(self):
        reset_all_tracking_data()
        self.server = create_todo_server()

    def teardown_method(self):
        reset_all_tracking_data()

    def _setup_data(self, stateless=False, identify=None):
        """Create and store MCPCatData on the server."""
        options = MCPCatOptions()
        if identify:
            options.identify = identify
        data = MCPCatData(
            project_id="test_project",
            session_id="ses_existing123",
            session_info=SessionInfo(),
            last_activity=datetime.now(timezone.utc),
            identified_sessions={},
            options=options,
            is_stateless=stateless,
        )
        set_server_tracking_data(self.server, data)
        return data

    def test_stateless_option_sets_flag(self):
        """MCPCatOptions(stateless=True) should set is_stateless on data."""
        data = self._setup_data(stateless=True)
        assert data.is_stateless is True

    def test_stateless_session_id_is_none(self):
        """In stateless mode, get_server_session_id() should return None."""
        self._setup_data(stateless=True)
        session_id = get_server_session_id(self.server)
        assert session_id is None

    @patch("mcpcat.modules.identify.event_queue")
    def test_stateless_identify_runs_every_time(self, mock_event_queue):
        """In stateless mode, identify should run on every call (no early-return guard)."""
        mock_fn = MagicMock(return_value=UserIdentity(
            user_id="alice", user_name="Alice", user_data=None
        ))
        self._setup_data(stateless=True, identify=mock_fn)

        identify_session(self.server, MagicMock(), MagicMock())
        identify_session(self.server, MagicMock(), MagicMock())

        assert mock_fn.call_count == 2

    @patch("mcpcat.modules.identify.event_queue")
    def test_stateless_identify_returns_identity(self, mock_event_queue):
        """In stateless mode, identify_session() should return the UserIdentity."""
        self._setup_data(stateless=True, identify=_make_identify_fn())

        result = identify_session(self.server, MagicMock(), MagicMock())

        assert isinstance(result, UserIdentity)
        assert result.user_id == "user_123"
        assert result.user_name == "Test User"

    @patch("mcpcat.modules.identify.event_queue")
    def test_stateless_identify_no_shared_state(self, mock_event_queue):
        """In stateless mode, identified_sessions should remain empty."""
        self._setup_data(stateless=True, identify=_make_identify_fn())

        identify_session(self.server, MagicMock(), MagicMock())

        data = get_server_tracking_data(self.server)
        assert data.identified_sessions == {}

    @patch("mcpcat.modules.identify.event_queue")
    def test_stateful_unchanged(self, mock_event_queue):
        """Default (stateful) mode: session_id is a string, identify guard skips second call."""
        mock_fn = MagicMock(return_value=UserIdentity(
            user_id="alice", user_name="Alice", user_data=None
        ))
        self._setup_data(stateless=False, identify=mock_fn)

        # Session ID should be a string
        session_id = get_server_session_id(self.server)
        assert isinstance(session_id, str)
        assert session_id.startswith("ses_")

        # First identify call should work
        identify_session(self.server, MagicMock(), MagicMock())
        assert mock_fn.call_count == 1

        # Second call should be skipped (early-return guard)
        identify_session(self.server, MagicMock(), MagicMock())
        assert mock_fn.call_count == 1
