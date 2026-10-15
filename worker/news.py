"""
One news feed for the page and for Discord: mod changes, settings changes,
defeated bosses, plus the announcements you write in announcements.json.
"""

import hashlib
from datetime import datetime

from .util import iso, load_json, log, pretty_mod_name

MAX_ENTRIES = 50


def _id(kind, date, title):
    return hashlib.sha1(f"{kind}|{date}|{title}".encode("utf-8")).hexdigest()[:16]


def add(state, kind, title, ts, text="", items=None):
    date = iso(ts)
    entry = {"id": _id(kind, date, title), "kind": kind, "date": date, "title": title,
             "text": text, "items": items or []}
    feed = state.setdefault("news", [])
    feed.insert(0, entry)
    del feed[MAX_ENTRIES:]
    log(f"news: {title}")
    return entry


def mod_changes(state, status, now):
    """Compare the mod list and game version with the previous run."""
    seen = state.get("mods_seen")
    mods = {m["name"]: m["version"] for m in status["mods"]}
    version = status["version"]
    state["mods_seen"] = {"version": version, "mods": mods}
    if seen is None:
        return  # first run: just remember
    items = []
    if seen.get("version") and version and seen["version"] != version:
        items.append({"type": "game", "text": f"Valheim updated: {seen['version']} → {version}"})
    old = seen.get("mods", {})
    for name in sorted(set(mods) - set(old), key=str.lower):
        items.append({"type": "add", "text": f"Added {pretty_mod_name(name)} {mods[name]}"})
    for name in sorted(set(old) - set(mods), key=str.lower):
        items.append({"type": "remove", "text": f"Removed {pretty_mod_name(name)}"})
    for name in sorted(set(mods) & set(old), key=str.lower):
        if mods[name] != old[name]:
            items.append({"type": "update", "text": f"Updated {pretty_mod_name(name)}: {old[name]} → {mods[name]}"})
    if items:
        title = "Server update" if any(i["type"] == "game" for i in items) else "Mod changes"
        add(state, "mods", title, now, items=items)


def boss_defeated(state, boss, world):
    when = boss
    day = (f"Day {when['day_to']}" if when.get("day_from") in (None, when["day_to"])
           else f"Day {when['day_from']}–{when['day_to']}")
    lines = [day + (f" · {boss['biome']}" if boss.get("biome") else "")]
    nxt = next((b for b in world["bosses"] if not b["defeated"]), None)
    lines.append(f"Next target: {nxt['name']} ({nxt['biome']})" if nxt else "All bosses defeated. Skål!")
    add(state, "boss", f"⚔️ {boss['name']} has been defeated!", when["at"], text="\n".join(lines))


def _announcements(path):
    out = []
    for a in load_json(path, {}).get("announcements", []):
        raw = str(a.get("date", "")).strip()
        ts = None
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                ts = datetime.strptime(raw, fmt).astimezone().timestamp()
                break
            except ValueError:
                pass
        if ts is None:
            continue
        date = iso(ts)
        title = a.get("title") or "Announcement"
        out.append({"id": _id("announcement", date, title), "kind": "announcement", "date": date,
                    "date_only": len(raw) <= 10, "title": title, "text": a.get("text") or "", "items": []})
    return out


def feed(state, announcements_path):
    """All news, newest first."""
    entries = list(state.get("news", [])) + _announcements(announcements_path)
    return sorted(entries, key=lambda e: e["date"], reverse=True)
