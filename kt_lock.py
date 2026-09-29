#!/usr/bin/env python3
"""Mark every clip the cloud says is published, so nothing re-cuts a live video.

13 Sept 2026. `locked` was set once, by hand, and then went stale. Fifteen clips
had gone out on four platforms while still unlocked, so every re-render rewrote
published videos - and one of those re-renders is how a clip the owner had already
watched changed under him.

A flag a human has to remember to refresh is not a lock. This reads the truth
from the cloud and is called by the renderer before it does anything.

REWRITTEN 15 SEPT 2026, AND IT HAD BEEN DEAD FOR TWO DAYS. Two faults, both
silent:

  1. IT WAS ASKING RAILWAY. The machine moved to GitHub on 13 Sept and Railway
     is down, so every call since then failed, printed one line to stderr inside
     a render's own noise, and returned 0. The renderer took "0 newly locked" to
     mean "nothing needed locking". The lock has been off since the migration.

  2. IT ONLY BELIEVED `posted_at`. Five KT_DEBT clips are live on Facebook and
     YouTube right now with no posted_at at all - `/retry` clears it, so a
     half-finished Instagram backfill leaves a published clip looking unposted.
     This is the same signature recorded in project_ar_retry_lost_posted_at.

A clip is published if there is ANY evidence of it: a timestamp, a link, or a
platform reporting success. Evidence of publication is not one field.
"""
import json
import os
import sys
import urllib.request

HOME = os.path.expanduser("~/ClipMachine")
STATE = ("https://raw.githubusercontent.com/truewealthformulas/clip-machine/"
         "main/state/manifest.json")


def _published(c):
    """Is this clip out in the world? Any one of these is enough."""
    if c.get("posted_at"):
        return True
    if c.get("links"):
        return True
    for v in (c.get("status") or {}).values():
        s = str(v).lower()
        if "posted" in s and "not on the account" not in s:
            return True
        if "inbox" in s or "uploaded" in s:
            return True
    return False


def sync(quiet=True):
    try:
        st = json.load(urllib.request.urlopen(STATE, timeout=45))
    except Exception as e:
        # LOUD, AND IT MATTERS. The previous version whispered this into stderr
        # in the middle of a render and carried on as if nothing were wrong,
        # which is how the lock stayed off for two days without anyone knowing.
        sys.stderr.write(f"\n  *** LOCK SYNC FAILED: {e}\n"
                         f"  *** Published clips are NOT protected this run.\n\n")
        return -1
    live = {c["file"] for c in st.get("clips", []) if _published(c)}
    p = os.path.join(HOME, "kt_series.json")
    d = json.load(open(p))
    n = 0
    for spec in d.values():
        for c in spec.get("clips", []):
            if c.get("locked"):
                continue
            if any(f.startswith(spec["brand"] + "/") and c["slug"] in f
                   for f in live):
                c["locked"] = True
                n += 1
                if not quiet:
                    print(f"  locked {spec['brand']}/{c['slug']}")
    if n:
        json.dump(d, open(p, "w"), indent=1, ensure_ascii=False)
    return n


if __name__ == "__main__":
    print(f"{sync(quiet=False)} clip(s) newly locked")
