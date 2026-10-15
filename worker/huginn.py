"""Reads the server status from Huginn (mbround18/valheim)."""

import json
import urllib.request

from . import cron
from .util import game_version


def _get(base, path, timeout=8):
    req = urllib.request.Request(base.rstrip("/") + path, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch(base):
    """
    Current status in one dict. Raises if Huginn is unreachable.
    /players is optional: older Huginn versions only have /status.
    """
    status = _get(base, "/status")
    try:
        players = _get(base, "/players")
    except Exception:
        players = None

    online = bool(status.get("online"))
    sessions = {}
    if players and online:
        for s in players.get("sessions") or []:
            if s.get("name"):
                sessions[s["name"]] = s.get("joined_at")
        for n in players.get("names") or []:
            sessions.setdefault(n, None)
    mods = sorted(({"name": m["name"], "version": m.get("version", "")}
                   for m in (status.get("bepinex") or {}).get("mods", []) if m.get("name")),
                  key=lambda m: m["name"].lower())
    restart = next((j.get("schedule") for j in status.get("jobs") or []
                    if j.get("name") == "SCHEDULED_RESTART" and j.get("enabled")), None)
    return {
        "online": online,
        "name": status.get("name") or "",
        "version": game_version(status.get("version")),
        "players": (players or {}).get("players", status.get("players", 0)) or 0,
        "max_players": (players or {}).get("max_players") or status.get("max_players") or 0,
        "sessions": sessions,                      # name -> joined_at (unix) or None
        "mods": mods,
        "restart_schedule": restart,               # cron expression of SCHEDULED_RESTART, if enabled
        "restart_text": cron.describe(restart) if restart else "",
        "next_restart": cron.next_run(restart) if restart else None,
    }
