import os, requests

def push(title:str, lines:list[str]):
    url = os.environ["DISCORD_WEBHOOK_URL"]
    content = f"**{title}**\n" + "\n".join(lines)
    r = requests.post(url, json={"content": content}, timeout=10)
    r.raise_for_status()