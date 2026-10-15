"""
World progression read from the save file: in-game day, bosses, milestones.

EXPERIMENTAL. The save format is not documented. This reads the chunked format
used since Valheim 1.0 (worlds_local/<World>/_main.<N>.db2):

    int32 version | float64 net time | int32 length | gzip data

The global keys ("defeated_eikthyr", "killedtroll", ...) are found inside the
gzip data by looking for a list of short lowercase strings. If the format
changes, read() returns None and the page simply hides the section.
"""

import glob
import gzip
import os
import re
import struct
import tarfile

from .util import log

DAY_LENGTH = 1800  # seconds of net time in one in-game day

BOSSES = [  # progression order: global key, name, biome
    ("defeated_eikthyr", "Eikthyr", "Meadows"),
    ("defeated_gdking", "The Elder", "Black Forest"),
    ("defeated_bonemass", "Bonemass", "Swamp"),
    ("defeated_dragon", "Moder", "Mountains"),
    ("defeated_goblinking", "Yagluth", "Plains"),
    ("defeated_queen", "The Queen", "Mistlands"),
    ("defeated_fader", "Fader", "Ashlands"),
]
MILESTONES = {
    "killedtroll": "First troll slain",
    "killed_surtling": "First Surtling slain",
    "killedbat": "First bat slain",
    "hildir1": "Hildir's first quest",
    "hildir2": "Hildir's second quest",
    "hildir3": "Hildir's third quest",
}
KEY_RE = re.compile(r"^[a-z0-9_][a-z0-9_ .\-]{0,79}$")


def detect_world(saves_dir, configured):
    if configured:
        return configured
    root = os.path.join(saves_dir, "worlds_local")
    worlds = [d for d in sorted(os.listdir(root)) if "_backup_" not in d
              and glob.glob(os.path.join(root, d, "_main.*.db2"))] if os.path.isdir(root) else []
    if len(worlds) == 1:
        return worlds[0]
    if len(worlds) > 1:
        log(f"several worlds found ({', '.join(worlds)}): set server.world in config.toml")
    return ""


def latest_save(world_dir):
    """Newest complete save: _main.<N>.db2 with its .ok marker."""
    best = None
    for path in glob.glob(os.path.join(world_dir, "_main.*.db2")):
        m = re.search(r"_main\.(\d+)\.db2$", path)
        if m and os.path.exists(path[:-4] + ".ok"):
            n = int(m.group(1))
            if best is None or n > best[0]:
                best = (n, path)
    return best[1] if best else None


def _read_str(buf, i):
    """.NET BinaryWriter string: 7-bit encoded length + bytes."""
    length, shift = 0, 0
    while True:
        if i >= len(buf) or shift > 28:
            return None, i
        b = buf[i]
        i += 1
        length |= (b & 0x7F) << shift
        if not b & 0x80:
            break
        shift += 7
    if length == 0 or length > 80 or i + length > len(buf):
        return None, i
    try:
        return buf[i:i + length].decode("ascii"), i + length
    except UnicodeDecodeError:
        return None, i


def _find_global_keys(buf):
    """Best candidate for the global key list: int32 count + lowercase strings + a bool."""
    best, best_score = [], 0
    for i in range(0, len(buf) - 5):
        count = buf[i] | buf[i + 1] << 8 | buf[i + 2] << 16 | buf[i + 3] << 24
        if not 1 <= count <= 300:
            continue
        j, keys = i + 4, []
        for _ in range(count):
            s, j = _read_str(buf, j)
            if s is None or not KEY_RE.match(s):
                break
            keys.append(s)
        else:
            if j < len(buf) and buf[j] > 1:
                continue
            known = sum(1 for k in keys if k.startswith("defeated_") or k in MILESTONES or " " in k)
            score = known * 100 + len(keys)
            if known and score > best_score:
                best, best_score = keys, score
    return best


def parse_save(raw):
    version, net_time, size = struct.unpack_from("<idi", raw, 0)
    data = gzip.decompress(raw[16:16 + size])
    return version, net_time, _find_global_keys(data)


def read(world_dir):
    path = latest_save(world_dir)
    if not path:
        return None
    with open(path, "rb") as f:
        version, net_time, keys = parse_save(f.read())
    defeated = {k for k in keys if k.startswith("defeated_")}
    known = {b[0] for b in BOSSES}
    # Other "defeated_*" keys (e.g. defeated_writhan in 1.0.17) are not bosses: list them as milestones
    others = [k[len("defeated_"):].replace("_", " ").title() + " defeated" for k in sorted(defeated - known)]
    return {
        "day": int(net_time // DAY_LENGTH),
        "saved_at": os.path.getmtime(path),
        "save_version": version,
        "bosses": [{"key": k, "name": n, "biome": b, "defeated": k in defeated} for k, n, b in BOSSES],
        "milestones": [MILESTONES[k] for k in MILESTONES if k in keys] + others,
    }


def _backup_saves(backups_dir, world):
    """(backup time, day, keys) for each backup, oldest first."""
    out = []
    for path in sorted(glob.glob(os.path.join(backups_dir, "*.tar.gz"))):
        try:
            with tarfile.open(path, "r:gz") as tar:
                best = None
                for m in tar.getmembers():
                    r = re.search(rf"worlds_local/{re.escape(world)}/_main\.(\d+)\.db2$", m.name)
                    if r and m.isfile() and (best is None or int(r.group(1)) > best[0]):
                        best = (int(r.group(1)), m)
                if best:
                    _, net_time, keys = parse_save(tar.extractfile(best[1]).read())
                    out.append((best[1].mtime, int(net_time // DAY_LENGTH), set(keys)))
        except Exception as e:
            log(f"unreadable backup {os.path.basename(path)} ({e})")
    return out


def date_bosses(state, world, backups_dir, world_name, use_backups):
    """
    The save says IF a boss was defeated, not WHEN. A boss fell between the last
    save without its key and the first save with it. Returns the bosses seen
    falling right now (for news); bosses dated from backups are not announced.
    """
    dates = state.setdefault("boss_dates", {})
    prev = state.get("world")
    prev_defeated = {b["key"] for b in prev["bosses"] if b["defeated"]} if prev else None
    fresh, missing = [], []
    for b in world["bosses"]:
        if not b["defeated"] or b["key"] in dates:
            continue
        if prev_defeated is not None and b["key"] not in prev_defeated:
            dates[b["key"]] = {"day_from": prev["day"], "day_to": world["day"], "at": world["saved_at"]}
            fresh.append(b)
        else:
            missing.append(b["key"])
    if missing:
        saves = _backup_saves(backups_dir, world_name) if use_backups and os.path.isdir(backups_dir) else []
        for key in missing:
            before = [s for s in saves if key not in s[2]]
            after = [s for s in saves if key in s[2] and (not before or s[0] > before[-1][0])]
            first = after[0] if after else (None, world["day"], None)
            dates[key] = {"day_from": before[-1][1] if before else None, "day_to": first[1],
                          "at": first[0] or world["saved_at"]}
    for b in world["bosses"]:
        if b["defeated"] and b["key"] in dates:
            b.update(dates[b["key"]])
    return fresh
