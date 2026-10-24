import pytest

from app import settings


@pytest.fixture(autouse=True)
def no_partial_decisions(monkeypatch):
    monkeypatch.setattr(settings, "PARTIAL_DECIDE_SECS", 0.0)
