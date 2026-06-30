"""End-to-end: init_diagnostics + real write_to_log buffers and posts."""

from unittest.mock import patch

import pytest

from mcpcat.modules import diagnostics
from mcpcat.modules.logging import write_to_log


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    diagnostics._reset_diagnostics_for_test()
    monkeypatch.delenv("DISABLE_DIAGNOSTICS", raising=False)
    yield
    diagnostics._reset_diagnostics_for_test()


def test_end_to_end_buffers_and_posts():
    diagnostics.init_diagnostics("proj_int")
    write_to_log("MCPCat setup started | project proj_int | server lowlevel")

    with patch("mcpcat.modules.diagnostics.requests.post") as mock_post:
        diagnostics.flush_diagnostics()

        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        records = payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
        assert len(records) > 0


def test_disabled_never_posts():
    diagnostics.init_diagnostics("proj_int", disabled=True)
    write_to_log("nothing should buffer")

    with patch("mcpcat.modules.diagnostics.requests.post") as mock_post:
        diagnostics.flush_diagnostics()
        mock_post.assert_not_called()
