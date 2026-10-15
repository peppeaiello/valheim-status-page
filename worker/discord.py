"""Posts new feed entries to a Discord webhook."""

import json
import os
import time
import urllib.error
import urllib.request

from .util import log

COLORS = {"announcement": 0x9CC7E6, "mods": 0xC9A25A, "settings": 0xA9D39A, "boss": 0xD9574A}
TAGS = {"announcement": "📢 Announcement", "mods": "🛠️ Mods", "settings": "⚙️ Settings", "boss": "⚔️ Boss"}
ICONS = {"add": "➕", "remove": "➖", "update": "🔄", "game": "⭐"}
MAX_PER_RUN = 5
MAX_ATTEMPTS = 3


def gale_code(cfg):
    if cfg["discord"]["gale_code"]:
        return cfg["discord"]["gale_code"]
    staging = os.path.join(cfg["paths"]["server"], ".staging", "mods")
    try:
        files = [f for f in os.listdir(staging) if f.startswith("gale-") and f.endswith(".json")]
    except OSError:
        return ""
    if not files:
        return ""
    newest = max(files, key=lambda f: os.path.getmtime(os.path.join(staging, f)))
    return newest[len("gale-"):-len(".json")]


def _blocks(text):
    """Blank-line separated blocks; a first line ending with ':' is the block title; '- ' lines are bullets."""
    out = []
    for chunk in str(text or "").replace("\r", "").split("\n\n"):
        lines = [l.strip() for l in chunk.split("\n") if l.strip()]
        if not lines:
            continue
        title = lines[0][:-1].strip() if lines[0].endswith(":") and len(lines) > 1 else None
        body = lines[1:] if title else lines
        out.append((title, ["• " + l[2:].strip() if l.startswith("- ") else l for l in body]))
    return out


def payload(entry, cfg):
    embed = {"title": entry["title"][:256], "color": COLORS.get(entry["kind"], 0x9A958C),
             "timestamp": entry["date"], "footer": {"text": TAGS.get(entry["kind"], "News")}}
    intro, fields = [], []
    for title, lines in _blocks(entry.get("text")):
        if title and len(fields) < 24:
            fields.append({"name": title[:256], "value": "\n".join(lines)[:1024], "inline": False})
        else:
            intro.append("\n".join(lines))
    for it in entry.get("items") or []:
        intro.append(f"{ICONS.get(it.get('type'), '•')} {it.get('text', '')}")
    types = {it.get("type") for it in entry.get("items") or []}
    todo = []
    if types & {"add", "remove", "update"} and entry["kind"] == "mods":
        code = gale_code(cfg)
        todo.append("• Update your mods to match the server before joining"
                    + (f": import the Gale profile **`{code}`**" if code else ""))
    if "game" in types:
        todo.append("• Update **Valheim** on Steam")
    if todo:
        fields.append({"name": "What to do", "value": "\n".join(todo)[:1024], "inline": False})
    if intro:
        embed["description"] = "\n".join(intro)[:4000]
    if fields:
        embed["fields"] = fields
    body = {"allowed_mentions": {"parse": []}, "embeds": [embed]}   # never ping anyone
    if cfg["discord"]["username"]:
        body["username"] = cfg["discord"]["username"]
    return body


def _post(url, body):
    req = urllib.request.Request(url + ("&" if "?" in url else "?") + "wait=true", method="POST",
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "User-Agent": "valheim-status-page"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return True, json.loads(r.read().decode("utf-8")).get("id")
    except urllib.error.HTTPError as err:
        if err.code == 429:
            try:
                return False, float(json.loads(err.read().decode("utf-8")).get("retry_after", 2))
            except ValueError:
                return False, 2.0
        log(f"discord: HTTP {err.code} {err.read()[:200]!r}")
    except OSError as err:
        log(f"discord: unreachable ({err})")
    return False, None


def run(state, cfg, entries):
    url = cfg["discord"]["webhook_url"].strip()
    if not url:
        return
    if not url.startswith(("https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/")):
        log("discord: DISCORD_WEBHOOK_URL is not a Discord webhook URL")
        return
    st = state.setdefault("discord", {"sent": [], "failed": {}, "messages": {}})
    kinds = set(cfg["discord"]["post"])
    todo = [e for e in reversed(entries) if e["kind"] in kinds and e["id"] not in st["sent"]]
    if not st.get("initialized"):
        # First run: do not flood the channel with history
        st["sent"] += [e["id"] for e in todo]
        st["initialized"] = True
        return
    for e in todo[:MAX_PER_RUN]:
        ok, info = _post(url, payload(e, cfg))
        if not ok and info:
            time.sleep(min(info, 10))
            ok, info = _post(url, payload(e, cfg))
        if ok:
            st["sent"].append(e["id"])
            st["messages"][e["id"]] = info
            st["failed"].pop(e["id"], None)
            log(f"discord: posted {e['title']}")
            time.sleep(1)
        else:
            n = st["failed"].get(e["id"], 0) + 1
            st["failed"][e["id"]] = n
            if n >= MAX_ATTEMPTS:
                st["sent"].append(e["id"])
                log(f"discord: giving up on {e['title']}")
            break
    del st["sent"][:-500]
