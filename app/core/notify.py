import logging
import os
import time

import requests


logger = logging.getLogger(__name__)

# (connect, read) — Discord can be slow under load; separate from Odds API budgets.
_DISCORD_TIMEOUT = (5.0, 15.0)
_MAX_ATTEMPTS = 3
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


def push(title: str, lines: list[str]):
    url = os.getenv("DISCORD_WEBHOOK_URL")
    if not url:
        logger.error("DISCORD_WEBHOOK_URL is not set; skipping notification")
        return
    content = f"**{title}**\n" + "\n".join(lines)
    payload = {"content": content}
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            r = requests.post(url, json=payload, timeout=_DISCORD_TIMEOUT)
            if r.status_code in _RETRY_STATUS and attempt < _MAX_ATTEMPTS:
                wait = 0.5 * (2 ** (attempt - 1))
                ra = r.headers.get("Retry-After")
                if ra is not None:
                    try:
                        wait = max(wait, float(ra))
                    except ValueError:
                        pass
                logger.warning(
                    "Discord webhook HTTP %s (attempt %d/%d); retrying in %.1fs",
                    r.status_code,
                    attempt,
                    _MAX_ATTEMPTS,
                    wait,
                )
                time.sleep(wait)
                continue
            r.raise_for_status()
            return
        except requests.HTTPError as e:
            resp = e.response
            code = resp.status_code if resp is not None else None
            if code in _RETRY_STATUS and attempt < _MAX_ATTEMPTS:
                wait = 0.5 * (2 ** (attempt - 1))
                logger.warning(
                    "Discord webhook HTTP error %s (attempt %d/%d); retrying in %.1fs",
                    code,
                    attempt,
                    _MAX_ATTEMPTS,
                    wait,
                )
                time.sleep(wait)
                continue
            logger.error("Discord webhook failed after %d attempt(s): %s", attempt, e)
            raise
        except requests.RequestException as e:
            if attempt < _MAX_ATTEMPTS:
                wait = 0.5 * (2 ** (attempt - 1))
                logger.warning(
                    "Discord webhook request error (attempt %d/%d): %s; retrying in %.1fs",
                    attempt,
                    _MAX_ATTEMPTS,
                    e,
                    wait,
                )
                time.sleep(wait)
                continue
            logger.error("Discord webhook failed after %d attempt(s): %s", attempt, e)
            raise
