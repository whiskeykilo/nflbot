import logging
import os
import requests


logger = logging.getLogger(__name__)


def push(title: str, lines: list[str]):
    url = os.getenv("DISCORD_WEBHOOK_URL")
    if not url:
        logger.error("DISCORD_WEBHOOK_URL is not set; skipping notification")
        return
    content = f"**{title}**\n" + "\n".join(lines)
    r = requests.post(url, json={"content": content}, timeout=10)
    r.raise_for_status()
