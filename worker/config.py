"""Configuration: defaults, overridden by config.toml, overridden by environment variables."""

import copy
import os
import tomllib

DEFAULTS = {
    "server": {
        # Huginn, the status server bundled with mbround18/valheim (HTTP_PORT, default 3000).
        "huginn_url": "http://valheim:3000",
        # World to read progression from. Empty = auto-detect when there is only one world.
        "world": "",
    },
    "paths": {
        # Mounts of the mbround18/valheim volumes, read-only.
        "server": "/valheim/server",      # /home/steam/valheim
        "saves": "/valheim/saves",        # /home/steam/.config/unity3d/IronGate/Valheim
        "backups": "/valheim/backups",    # /home/steam/backups (optional)
        # Writable: state of the worker, and the JSON files served to the page.
        "data": "/data",
        "web_data": "/usr/share/nginx/html/data",
        # Announcements you write by hand (see announcements.example.json).
        "announcements": "/config/announcements.json",
    },
    "page": {
        "title": "",                      # empty = server name reported by Huginn
        "subtitle": "Valheim dedicated server",
        "map_url": "",                    # e.g. a ValheimWebMap URL; shown in an iframe when set
        "join_hint": "",                  # free text shown under the status, e.g. "Import Gale profile CODE"
        "refresh_seconds": 15,
        "restart_warning_minutes": 30,
    },
    "features": {
        "leaderboard": True,              # play time per player, from Huginn sessions
        "world_progress": True,           # day, bosses, milestones, read from the world save (experimental)
        "boss_dates_from_backups": True,  # date bosses defeated before the first run, using backups
        "mod_news": True,                 # news entry when mods or the Valheim version change
        "config_watch": True,             # news entry when watched mod settings change after a restart
        "epicloot": False,                # enchantments section, opt-in: shown only if true AND EpicLoot is installed
    },
    "discord": {
        # The webhook URL is a secret: set it with the DISCORD_WEBHOOK_URL environment variable.
        "webhook_url": "",
        "username": "",                   # empty = the name configured on the webhook in Discord
        "post": ["announcement", "mods", "settings", "boss"],
        # Profile code players should import after mod changes. Empty = read it from the
        # GALE_SYNC_CODE download of mbround18/valheim (server/.staging/mods/gale-<CODE>.json).
        "gale_code": "",
    },
    # Mod settings to watch, see config.example.toml.
    "config_watch": [],
    "intervals": {
        "status_seconds": 10,
        "slow_seconds": 60,
        "settle_seconds": 120,            # wait after a restart before reading mod configs
    },
}


def _merge(base, extra):
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path=None):
    path = path or os.environ.get("VSP_CONFIG", "/config/config.toml")
    user = {}
    if os.path.exists(path):
        with open(path, "rb") as f:
            user = tomllib.load(f)
    cfg = _merge(DEFAULTS, user)
    env = {
        ("server", "huginn_url"): "HUGINN_URL",
        ("server", "world"): "WORLD_NAME",
        ("discord", "webhook_url"): "DISCORD_WEBHOOK_URL",
        ("discord", "gale_code"): "GALE_CODE",
    }
    for (section, key), var in env.items():
        if os.environ.get(var):
            cfg[section][key] = os.environ[var]
    return cfg
