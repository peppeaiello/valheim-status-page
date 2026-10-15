"""Next run of a 5-field cron expression, in the container's local time (set TZ like the server)."""

from datetime import datetime, timedelta


def _field(field, lo, hi):
    values = set()
    for part in field.split(","):
        rng, _, step = part.partition("/")
        step = int(step) if step else 1
        if rng == "*":
            a, b = lo, hi
        elif "-" in rng:
            a, b = (int(x) for x in rng.split("-"))
        else:
            a = int(rng)
            b = hi if step > 1 else a
        values.update(range(a, b + 1, step))
    return {0 if (v == 7 and hi == 6) else v for v in values}


def next_run(expr, now=None):
    """Unix time of the next run, or None if the expression is not understood."""
    parts = str(expr or "").split()
    if len(parts) != 5:
        return None
    try:
        mins, hours = _field(parts[0], 0, 59), _field(parts[1], 0, 23)
        doms, mons, dows = _field(parts[2], 1, 31), _field(parts[3], 1, 12), _field(parts[4], 0, 6)
    except ValueError:
        return None
    dom_any, dow_any = parts[2] == "*", parts[4] == "*"
    t = (now or datetime.now()).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(60 * 24 * 366):
        dow = (t.weekday() + 1) % 7   # cron: Sunday = 0
        day_ok = (True if dom_any and dow_any else dow in dows if dom_any
                  else t.day in doms if dow_any else t.day in doms or dow in dows)
        if t.minute in mins and t.hour in hours and t.month in mons and day_ok:
            return t.timestamp()
        t += timedelta(minutes=1)
    return None


def describe(expr):
    """"0 7 * * *" -> "every day at 07:00"; anything else is returned as is."""
    p = str(expr or "").split()
    if len(p) == 5 and p[2:] == ["*", "*", "*"] and p[0].isdigit() and p[1].isdigit():
        return f"every day at {int(p[1]):02d}:{int(p[0]):02d}"
    return expr or ""
