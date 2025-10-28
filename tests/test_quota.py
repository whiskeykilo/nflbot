import importlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.errors import OddsApiQuotaError
from app.adapters.hardrock_odds import fetch_hr_nfl_moneylines
from app.adapters.reference_probs import reference_probs_for


class FixedDatetimeFactory:
    """Helper to create deterministic datetime classes for patching."""

    def __init__(self, year: int, month: int, day: int):
        from datetime import datetime as _dt

        class _FixedDateTime(_dt):
            @classmethod
            def now(cls, tz=None):
                from datetime import timezone as _tz

                return _dt(year, month, day, 12, 0, 0, tzinfo=tz or _tz.utc)

        self.cls = _FixedDateTime


def _reload_main():
    import app.main as main

    return importlib.reload(main)


class Resp:
    def __init__(self, status=402, data=None, text=""):
        self.status_code = status
        self._data = data or []
        self.headers = {"X-Requests-Remaining": "0"}
        self.text = text

    def raise_for_status(self):
        if self.status_code != 200:
            raise requests.HTTPError(response=self)

    def json(self):
        return self._data


def test_hardrock_quota_raises():
    with patch("app.adapters.hardrock_odds.requests.get", return_value=Resp(402)):
        with pytest.raises(OddsApiQuotaError):
            fetch_hr_nfl_moneylines(days_from=1)


def test_hardrock_unauthorized_quota_raises():
    payload = {"success": False, "message": "Monthly plan quota reached"}
    with patch("app.adapters.hardrock_odds.requests.get", return_value=Resp(401, data=payload)):
        with pytest.raises(OddsApiQuotaError):
            fetch_hr_nfl_moneylines(days_from=1)


def test_reference_quota_raises():
    with patch("app.adapters.reference_probs.requests.get", return_value=Resp(429)):
        with pytest.raises(OddsApiQuotaError):
            reference_probs_for([{"game_id": "G1"}])


def test_run_once_quota_notified_once_per_month(monkeypatch):
    main = _reload_main()
    fixed_dt = FixedDatetimeFactory(2024, 2, 15).cls
    monkeypatch.setattr(main, "datetime", fixed_dt)

    with (
        patch.object(main, "fetch_hr_nfl_moneylines", side_effect=main.OddsApiQuotaError("quota")) as fetch_mock,
        patch.object(main, "push") as push_mock,
    ):
        main.run_once()
        assert push_mock.call_count == 1
        push_mock.reset_mock()

        main.run_once()
        assert fetch_mock.call_count == 2
        push_mock.assert_not_called()


def test_run_once_quota_resets_on_new_month(monkeypatch):
    main = _reload_main()
    jan_dt = FixedDatetimeFactory(2024, 1, 31).cls
    feb_dt = FixedDatetimeFactory(2024, 2, 1).cls

    with (
        patch.object(main, "fetch_hr_nfl_moneylines", side_effect=main.OddsApiQuotaError("quota")) as fetch_mock,
        patch.object(main, "push") as push_mock,
    ):
        monkeypatch.setattr(main, "datetime", jan_dt)
        main.run_once()
        assert push_mock.call_count == 1

        monkeypatch.setattr(main, "datetime", feb_dt)
        push_mock.reset_mock()
        main.run_once()
        assert fetch_mock.call_count == 2
        assert push_mock.call_count == 1

