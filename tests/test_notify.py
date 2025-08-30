import logging
from pathlib import Path
from unittest.mock import Mock

import pytest

import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))
from app.core import notify


def test_push_posts_when_url_present(monkeypatch):
    """Push posts to Discord when DISCORD_WEBHOOK_URL is configured."""
    mock_post = Mock(return_value=Mock(raise_for_status=Mock()))
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "http://example.com")
    monkeypatch.setattr(notify.requests, "post", mock_post)
    notify.push("Title", ["line1", "line2"])
    mock_post.assert_called_once_with(
        "http://example.com",
        json={"content": "**Title**\nline1\nline2"},
        timeout=10,
    )


def test_push_skips_when_url_missing(monkeypatch, caplog):
    """If DISCORD_WEBHOOK_URL is missing, the POST is skipped and error logged."""
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    mock_post = Mock()
    monkeypatch.setattr(notify.requests, "post", mock_post)
    with caplog.at_level(logging.ERROR):
        notify.push("Title", ["line"])
    mock_post.assert_not_called()
    assert "DISCORD_WEBHOOK_URL is not set" in caplog.text

