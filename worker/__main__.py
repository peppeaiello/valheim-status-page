"""
valheim-status-page worker: keeps the JSON files the page reads up to date.

Every `status_seconds`: server status and player sessions (status.json).
Every `slow_seconds`: world progression, leaderboard, mod and settings news,
Discord posts (stats.json, news.json). Every 6 hours: EpicLoot enchantments.
"""

import os
import time

from . import config, configwatch, discord, epicloot, huginn, news, players, world
from .util import load_json, log, save_json


def main():
    cfg = config.load()
    paths = cfg["paths"]
    state_file = os.path.join(paths["data"], "state.json")
    web = paths["web_data"]
    state = load_json(state_file, {})
    world_name = ""
    last_slow = last_ench = 0
    log("worker started")

    while True:
        now = time.time()
        try:
            status = huginn.fetch(cfg["server"]["huginn_url"])
            reachable = True
        except Exception as e:
            log(f"huginn unreachable ({e})")
            status, reachable = None, False

        srv = state.setdefault("server", {})
        online = bool(status and status["online"])
        if online and not srv.get("online"):
            srv["started_at"] = now          # first time online after being offline = a (re)start
        srv["online"] = online

        if status and cfg["features"]["leaderboard"]:
            players.update(state, status["sessions"], now)
        save_json(os.path.join(web, "status.json"), {
            "updated_at": now, "reachable": reachable,
            **({k: v for k, v in status.items()} if status else {"online": False}),
            "sessions": [{"name": n, "joined_at": j} for n, j in (status or {}).get("sessions", {}).items()],
        })

        if now - last_slow >= cfg["intervals"]["slow_seconds"]:
            last_slow = now
            try:
                if online and cfg["features"]["mod_news"]:
                    news.mod_changes(state, status, now)
                if cfg["features"]["config_watch"]:
                    configwatch.check(state, cfg, now)
                w = None
                if cfg["features"]["world_progress"]:
                    world_name = world_name or world.detect_world(paths["saves"], cfg["server"]["world"])
                    if world_name:
                        try:
                            w = world.read(os.path.join(paths["saves"], "worlds_local", world_name))
                        except Exception as e:
                            log(f"world: cannot read the save ({e})")
                    if w:
                        for boss in world.date_bosses(state, w, paths["backups"], world_name,
                                                      cfg["features"]["boss_dates_from_backups"]):
                            news.boss_defeated(state, boss, w)
                        state["world"] = w
                    w = w or state.get("world")
                save_json(os.path.join(web, "stats.json"), {
                    "updated_at": now, "world_name": world_name, "world": w,
                    "leaderboard": players.export(state, reachable) if cfg["features"]["leaderboard"] else None,
                })
                feed = news.feed(state, paths["announcements"])
                save_json(os.path.join(web, "news.json"), {"updated_at": now, "entries": feed})
                discord.run(state, cfg, feed)
            except Exception as e:
                log(f"slow tasks failed ({e})")

            if now - last_ench >= 6 * 3600:
                last_ench = now
                ench = cfg["features"]["epicloot"]
                if ench is True or (ench == "auto" and epicloot.installed(paths["server"])):
                    try:
                        effects = epicloot.build(paths["server"])
                        if effects:
                            save_json(os.path.join(web, "enchantments.json"), {"updated_at": now, "effects": effects})
                    except Exception as e:
                        log(f"epicloot: {e}")

            save_json(os.path.join(web, "site.json"), {
                "page": cfg["page"],
                "features": {k: v for k, v in cfg["features"].items() if k in ("leaderboard", "world_progress")},
            })
            save_json(state_file, state, mode=0o600)

        time.sleep(cfg["intervals"]["status_seconds"])


if __name__ == "__main__":
    main()
