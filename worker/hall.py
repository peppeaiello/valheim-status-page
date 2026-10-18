"""Hall of Valhalla: deaths, titles and records of the players.

- Deaths come from the server log, read a piece at a time (the container starts a new
  log at every restart): Valheim writes "Got character ZDOID from NAME : 0:0" when a
  character dies, and a ZDOID other than 0:0 when it respawns.
- Every status tick samples who is online and adds play time by hour of the day, on
  weekends, alone or in a group, the days played (for streaks) and the deaths in the
  same session.
"""

import datetime
import os
import re
import time

from .util import log

SAMPLE_MAX_GAP = 300     # seconds: a longer gap between two samples is not counted as play time
RECENT_DEATHS = 8

ZDOID_RE = re.compile(r"^(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}): Got character ZDOID from (.+) : (-?\d+):(-?\d+)\s*$")
STAMP_RE = re.compile(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}:")

# Hours of the day for the titles (local time of the container, start included, end excluded)
NIGHT = range(0, 5)
DAWN = range(5, 9)
WEEKEND = (5, 6)         # tm_wday: Saturday and Sunday
PACK = 3                 # "in a group" = at least 3 online (the player and two others)

PLAYER_DEFAULTS = {
    "deaths": 0, "last_death": None, "life": 0, "best_life": 0,
    "hours": [0] * 24, "days": [],
    "solo": 0, "pack": 0, "weekend": 0, "sess_deaths": 0, "best_sess_deaths": 0,
}

# key, title, why, field, minimum value to earn it
TITLES = [
    ("valhalla", "Valhalla regular", "most deaths of all", "deaths", 1),
    ("immortal", "Troll hide", "longest life without dying", "life", 600),
    ("streak", "Odin's faithful", "most days in a row on the server", "streak", 2),
    ("night", "Odin's owl", "most hours played between midnight and 5", "night", 1800),
    ("dawn", "Rooster of Midgard", "most hours played between 5 and 9", "dawn", 1800),
    ("solo", "Lone wolf", "most hours played alone on the server", "solo", 1800),
    ("pack", "Heart of the pack", "most hours played with at least two others online", "pack", 1800),
    ("risen", "Risen", "most deaths in a single session", "sess_deaths", 2),
    ("weekend", "Weekend warrior", "most hours played on Saturday and Sunday", "weekend", 1800),
]


def _state(state, now):
    return state.setdefault("hall", {"since": now, "players": {}, "log": {}, "recent": [], "last_sample": None})


def _player(st, name):
    p = st["players"].setdefault(name, {})
    for k, v in PLAYER_DEFAULTS.items():
        p.setdefault(k, list(v) if isinstance(v, list) else v)
    return p


# ---------- deaths from the server log ----------

def _fingerprint(f):
    """The first line with a date identifies the server start: if it changes, the log is new."""
    for _ in range(3000):
        line = f.readline()
        if not line:
            break
        if STAMP_RE.match(line):
            return line[:19]
    return None


def read_log(state, path, now):
    st = _state(state, now)
    try:
        f = open(path, encoding="utf-8", errors="replace")
    except OSError:
        if not st.get("log_missing"):
            log(f"hall: server log not found ({path}), deaths are not counted")
            st["log_missing"] = True
        return
    st.pop("log_missing", None)
    with f:
        size = os.fstat(f.fileno()).st_size
        fp = _fingerprint(f)
        if fp is None:
            return   # server just started, no dated line yet
        cur = st["log"]
        if cur.get("fingerprint") != fp or size < cur.get("offset", 0):
            cur.clear()
            cur.update({"fingerprint": fp, "offset": 0})
        f.seek(cur["offset"])
        while True:
            line = f.readline()
            if not line or not line.endswith("\n"):
                break   # incomplete line: read it again next time
            cur["offset"] = f.tell()
            m = ZDOID_RE.match(line)
            if not m:
                continue
            stamp, name, uid, _ = m.groups()
            if uid != "0":
                continue
            when = datetime.datetime.strptime(stamp, "%m/%d/%Y %H:%M:%S").timestamp()
            p = _player(st, name)
            p["best_life"] = max(p["best_life"], p["life"])
            p["life"] = 0
            p["deaths"] += 1
            p["last_death"] = when
            p["sess_deaths"] += 1
            p["best_sess_deaths"] = max(p["best_sess_deaths"], p["sess_deaths"])
            st["recent"].insert(0, {"name": name, "at": when})
            del st["recent"][RECENT_DEATHS:]


# ---------- play time by hour of the day ----------

def sample(state, online, now):
    """online: names of the players online right now (empty when the server is unreachable)."""
    st = _state(state, now)
    last = st.get("last_sample")
    gap = now - last if last else 0
    st["last_sample"] = now
    st["online"] = sorted(online)
    # Whoever is not online closed the session: deaths "in one session" start again from zero
    for name, p in st["players"].items():
        if name not in online:
            p["sess_deaths"] = 0
    if not online or not 0 < gap <= SAMPLE_MAX_GAP:
        return
    mid = time.localtime(now - gap / 2)
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    for name in online:
        p = _player(st, name)
        p["hours"][mid.tm_hour] += gap
        if mid.tm_wday in WEEKEND:
            p["weekend"] += gap
        if len(online) == 1:
            p["solo"] += gap
        elif len(online) >= PACK:
            p["pack"] += gap
        p["life"] += gap   # a life counts online time only: logouts and restarts do not end it
        if today not in p["days"]:
            p["days"].append(today)


def _streaks(days):
    """Longest run of consecutive days, and the current one (ended today or yesterday)."""
    best = run = 0
    prev = None
    for d in sorted(datetime.date.fromisoformat(d) for d in days):
        run = run + 1 if prev and (d - prev).days == 1 else 1
        best = max(best, run)
        prev = d
    current = run if prev and (datetime.date.today() - prev).days <= 1 else 0
    return best, current


def _titles(rows):
    """Each title goes to the highest value; no title when nobody earned it yet."""
    out = []
    for key, title, why, field, minimum in TITLES:
        best = max(rows, key=lambda r: r[field], default=None)
        if not best or best[field] < minimum:
            continue
        names = [r["name"] for r in rows if r[field] == best[field]]
        out.append({"key": key, "title": title, "why": why, "names": names, "value": round(best[field])})
    return out


def export(state, now):
    st = state.get("hall")
    if not st or not st["players"]:
        return None
    online = set(st.get("online", []))
    rows = []
    for name in list(st["players"]):
        p = _player(st, name)
        best, current = _streaks(p["days"])
        rows.append({
            "name": name,
            "deaths": p["deaths"],
            "last_death": p["last_death"],
            "life": round(max(p["best_life"], p["life"])),
            "online": name in online,
            "streak": best,
            "streak_now": current,
            "days": len(p["days"]),
            "night": sum(p["hours"][h] for h in NIGHT),
            "dawn": sum(p["hours"][h] for h in DAWN),
            "solo": round(p["solo"]),
            "pack": round(p["pack"]),
            "weekend": round(p["weekend"]),
            "sess_deaths": p["best_sess_deaths"],
        })
    return {
        "updated_at": now,
        "since": st["since"],
        "titles": _titles(rows),
        "deaths_total": sum(r["deaths"] for r in rows),
        "recent": st["recent"],
        "players": rows,
    }
