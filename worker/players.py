"""Play time per player, built from the sessions Huginn reports."""

MIN_SESSION = 60         # shorter visits add their time but do not count as a session
REJOIN_TOLERANCE = 120   # seconds: a different joined_at means a new session


def _close(state, name, sess):
    p = state["players"][name]
    dur = max(0, sess["last_seen"] - sess["joined_at"])
    p["total"] += dur
    p["longest"] = max(p.get("longest", 0), dur)
    if dur >= MIN_SESSION:
        p["sessions"] += 1
    p["last_seen"] = sess["last_seen"]


def update(state, sessions, now):
    """sessions: name -> joined_at of the players online right now."""
    st = state.setdefault("leaderboard", {"since": now, "players": {}, "open": {}, "peak": {"count": 0, "at": None}})
    open_ = st["open"]
    for name in list(open_):
        joined = sessions.get(name, "missing")
        if joined == "missing" or (joined and abs(joined - open_[name]["joined_at"]) > REJOIN_TOLERANCE):
            _close(st, name, open_.pop(name))
    for name, joined in sessions.items():
        p = st["players"].setdefault(name, {"total": 0, "sessions": 0, "longest": 0, "first_seen": now, "last_seen": now})
        if name not in open_:
            open_[name] = {"joined_at": joined or now, "last_seen": now}
        open_[name]["last_seen"] = now
        p["last_seen"] = now
    if len(sessions) > st["peak"]["count"]:
        st["peak"] = {"count": len(sessions), "at": now}


def export(state, reachable):
    st = state.get("leaderboard")
    if not st:
        return None
    rows = []
    for name, p in st["players"].items():
        sess = st["open"].get(name) if reachable else None
        rows.append({
            "name": name,
            "total": round(p["total"]),
            "sessions": p["sessions"],
            "longest": round(p.get("longest", 0)),
            "first_seen": p["first_seen"],
            "last_seen": p["last_seen"],
            "online_since": sess["joined_at"] if sess else None,
        })
    return {"since": st["since"], "peak": st["peak"], "players": rows}
