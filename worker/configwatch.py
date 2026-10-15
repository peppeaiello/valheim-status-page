"""
Watches selected mod settings (BepInEx .cfg files). After each server restart,
once the mods have rewritten their files, the values are compared with the
previous start and a news entry lists what changed. Values only change for
players after a restart, so announcing at that moment is accurate.

If Spawn That is installed, its spawn multipliers are summarized too.
"""

import os
import re

from . import news

SPAWN_THAT_FILE = "spawn_that.simple.cfg"


def read_cfg(path):
    """BepInEx .cfg -> {(section, key): value}."""
    out, section = {}, ""
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1]
            elif line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[(section, k.strip())] = v.strip()
    return out


def snapshot(config_dir, watch):
    snap, files = {}, {}
    for w in watch:
        f = w["file"]
        if f not in files:
            try:
                files[f] = read_cfg(os.path.join(config_dir, f))
            except OSError:
                files[f] = {}
        value = files[f].get((w["section"], w["key"]))
        if value is not None:
            snap[f"{f}|{w['section']}|{w['key']}"] = value
    try:
        spawn = read_cfg(os.path.join(config_dir, SPAWN_THAT_FILE))
        for (section, k), prefab in spawn.items():
            if k == "PrefabName" and spawn.get((section, "Enable"), "true").lower() == "true":
                snap[f"spawn|{prefab}"] = "{}/{}".format(spawn.get((section, "SpawnMaxMultiplier"), "1"),
                                                        spawn.get((section, "SpawnFrequencyMultiplier"), "1"))
    except OSError:
        pass
    return snap


def fmt(value, unit=""):
    v = value.strip()
    if v.lower() in ("true", "on"):
        return "on"
    if v.lower() in ("false", "off"):
        return "off"
    try:
        v = f"{float(v):g}"
    except ValueError:
        return v
    if unit == "×":
        return f"×{v}"
    if unit == "%":
        return f"{v}%"
    return f"{v} {unit}".strip()


def changes(old, new, watch):
    items = []
    for w in watch:
        k = f"{w['file']}|{w['section']}|{w['key']}"
        if k in old and k in new and old[k] != new[k]:
            unit = w.get("unit", "")
            items.append({"type": "update", "text": f"{w.get('label') or w['key']}: {fmt(old[k], unit)} → {fmt(new[k], unit)}"})
    groups = {}
    for k in sorted(set(old) | set(new)):
        if k.startswith("spawn|"):
            before, after = old.get(k, "1/1"), new.get(k, "1/1")
            if before != after:
                groups.setdefault((before, after), []).append(re.sub(r"(?<=[a-z])(?=[A-Z])", " ", k[6:]))
    for (before, after), names in groups.items():
        (bm, bf), (am, af) = before.split("/"), after.split("/")
        parts = []
        if bm != am:
            parts.append(f"max {fmt(bm, '×')} → {fmt(am, '×')}")
        if bf != af:
            parts.append(f"frequency {fmt(bf, '×')} → {fmt(af, '×')}")
        items.append({"type": "update", "text": f"Spawns of {', '.join(names)}: {', '.join(parts)}"})
    return items


def check(state, cfg, now):
    """Once per server start, after the settle time."""
    started = state.get("server", {}).get("started_at")
    if not started or now - started < cfg["intervals"]["settle_seconds"]:
        return
    cw = state.get("config_watch")
    if cw and cw.get("started_at") == started:
        return
    config_dir = os.path.join(cfg["paths"]["server"], "BepInEx", "config")
    snap = snapshot(config_dir, cfg["config_watch"])
    if cw:
        items = changes(cw["values"], snap, cfg["config_watch"])
        if items:
            news.add(state, "settings", "Server settings", started, items=items)
    state["config_watch"] = {"started_at": started, "values": snap}
