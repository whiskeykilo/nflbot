import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.errors import OddsApiQuotaError
from app.adapters.hardrock_odds import fetch_hr_nfl_moneylines
from app.adapters.reference_probs import reference_probs_for


class Resp:
    def __init__(self, status=402, data=None):
        self.status_code = status
        self._data = data or []
        self.headers = {"X-Requests-Remaining": "0"}

    def raise_for_status(self):
        if self.status_code != 200:
            raise requests.HTTPError(response=self)

    def json(self):
        return self._data


def test_hardrock_quota_raises():
    with patch("app.adapters.hardrock_odds.requests.get", return_value=Resp(402)):
        with pytest.raises(OddsApiQuotaError):
            fetch_hr_nfl_moneylines(days_from=1)


def test_reference_quota_raises():
    with patch("app.adapters.reference_probs.requests.get", return_value=Resp(429)):
        with pytest.raises(OddsApiQuotaError):
            reference_probs_for([{"game_id": "G1"}])

