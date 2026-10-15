"""Small helpers shared by the worker modules."""

import json
import os
import tempfile
from datetime import datetime, timezone


def log(msg):
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}", flush=True)


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data, mode=0o644):
    """Atomic write: the page never reads a half-written file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def pretty_mod_name(name):
    """"AzuCraftyBoxes" -> "Azu Crafty Boxes", "balrond_secondchance" -> "Balrond Secondchance"."""
    import re
    s = re.sub(r"[_-]+", " ", name)
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    return " ".join(w[:1].upper() + w[1:] for w in s.split())


def game_version(raw):
    """Huginn reports "g=1.0.17,n=40,m=": keep the game version."""
    import re
    m = re.search(r"g=([^,]+)", raw or "")
    return m.group(1) if m else (raw or "")
