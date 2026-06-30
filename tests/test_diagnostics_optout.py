"""Tests for diagnostics opt-out (option + DISABLE_DIAGNOSTICS env var)."""

import pytest

from mcpcat.modules import diagnostics


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    diagnostics._reset_diagnostics_for_test()
    monkeypatch.delenv("DISABLE_DIAGNOSTICS", raising=False)
    yield
    diagnostics._reset_diagnostics_for_test()


def test_enabled_by_default():
    diagnostics.init_diagnostics("proj_1")
    assert diagnostics.is_diagnostics_enabled() is True


def test_disabled_via_option():
    diagnostics.init_diagnostics("proj_1", disabled=True)
    assert diagnostics.is_diagnostics_enabled() is False


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", "on"])
def test_disabled_via_env(monkeypatch, value):
    monkeypatch.setenv("DISABLE_DIAGNOSTICS", value)
    diagnostics.init_diagnostics("proj_1")
    assert diagnostics.is_diagnostics_enabled() is False


@pytest.mark.parametrize("value", ["false", "0", "no", "off", "  "])
def test_stays_enabled_for_falsy_values(monkeypatch, value):
    """The Kashish case: a value-interpreted env var, not presence-based."""
    monkeypatch.setenv("DISABLE_DIAGNOSTICS", value)
    diagnostics.init_diagnostics("proj_1")
    assert diagnostics.is_diagnostics_enabled() is True
