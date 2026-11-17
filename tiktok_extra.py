#!/usr/bin/env python3
"""Five extra TikTok posts a day (17 Nov 2026, the owner: "Let's make 5 more posts
on TikTok per day so in total 10").

The main queue posts 5 a day everywhere. In between, at TT_EXTRA_SLOTS (New
York time), this sends ONE clip from the TikTok backlog - clips already posted
on the other platforms that never reached TikTok, re-cut full screen by the
tiktok-backlog workflow (tt_extra == "ready") - to TikTok only. Runs after
run_once.py in the same job, so it shares the `post` lock.
"""
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "engine"))
os.environ.setdefault("KT_DATA", os.path.join(HERE, "state"))
os.environ["KT_MEDIA_REMOTE"] = "1"
SLOTS = [s for s in os.environ.get("TT_EXTRA_SLOTS", "11:45,12:30,13:45,20:30,21:30").split(",") if s]
LATE_MIN = 90      # a slot older than this is skipped, not posted late


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] tiktok-extra: {m}", flush=True)


def main():
    import main as engine
    import poster
    engine.MANIFEST = os.path.join(HERE, "state", "manifest.json")
    if "tiktok" not in poster.ENABLED:
        log("TikTok not enabled")
        return 0
    man = engine.load()
    now = engine.now_local().replace(tzinfo=None)
    today = now.strftime("%Y-%m-%d")
    hm = now.strftime("%H:%M")
    due = [s for s in SLOTS if s <= hm and
           (now - now.replace(hour=int(s[:2]), minute=int(s[3:]), second=0)).total_seconds() / 60 <= LATE_MIN]
    sent = [c for c in man["clips"] if str(c.get("tt_extra_at") or "").startswith(today)]
    done_slots = {c.get("tt_extra_slot") for c in sent}
    todo = [s for s in due if s not in done_slots]
    if not todo:
        log(f"nothing due ({len(sent)} sent today)")
        return 0
    slot = todo[-1]
    ready = [c for c in man["clips"] if c.get("tt_extra") == "ready" and c.get("tiktok_file")]
    if not ready:
        log("backlog empty - nothing ready to send")
        return 0
    clip = ready[0]
    owner = os.environ["GH_REPO"]
    base = f"https://github.com/{owner}/releases/download/media/"
    url = base + clip["file"].replace("/", "--")
    path = os.path.join(HERE, "media", clip["file"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        urllib.request.urlretrieve(url, path)
    except Exception as e:
        log(f"could not fetch {clip['file']}: {e}")
        return 0
    if os.environ.get("DRY_RUN") == "1":
        log(f"DRY: would send {clip['file']} for the {slot} slot")
        return 0
    result, _ = poster.publish(clip, path, url, only=["tiktok"])
    res = str(result.get("tiktok"))
    m2 = engine.load()
    c2 = next(x for x in m2["clips"] if x["file"] == clip["file"])
    c2.setdefault("status", {})["tiktok"] = res
    ok = any(k in res for k in ("inbox", "posted", "rocess"))
    c2["tt_extra"] = "sent" if ok else f"failed - {res[:80]}"
    c2["tt_extra_at"] = now.strftime("%Y-%m-%dT%H:%M")
    c2["tt_extra_slot"] = slot
    engine.save(m2)
    log(f"{slot} slot: {clip['file']} -> {res}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
