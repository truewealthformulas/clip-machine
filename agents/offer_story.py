#!/usr/bin/env python3
"""One offer story a day on Instagram (10 Oct 2026, the owner: "do both").

The owner's own highlight stories are reposted (state/story_pool.json, built by
the owner's 19 highlight videos + 6 photos, 11 Oct - "do it with the same pictures of my highlight").
The API cannot put a link sticker on a story, so each carries a band "Reply
<KEYWORD>" and the owner's DM auto-reply sends the link. If the pool has nothing
for an offer, the branded card from docs/stories/ is used instead.

Rotation (free training and GIN get the most days): training, gin, book,
training, gin, book, daily. Photo and text looks alternate. Once per New York
day; the log is state/stories.json.

    python agents/offer_story.py [--dry]
"""
import datetime
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "state", "stories.json")
POOL = os.path.join(ROOT, "state", "story_pool.json")
MEDIA = f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', 'truewealthformulas/clip-machine')}/releases/download/media/"
BASE = os.environ.get("STORY_BASE_URL", "https://truewealthformulas.github.io/clip-machine/stories/")
ROTATION = ["training", "gin", "book", "training", "gin", "book", "daily"]
V = "v21.0"
# For the link-sticker stories the owner posts by hand (Mon + Thu reminders).
LINKS = {
    "training": "https://freeyourwish.kevintrudeau.com/?ref=ftad8p",
    "gin": "https://signup.globalinformationnetwork.com/?ref=ftad8p",
    "book": "https://getyourwishbook.com/?ref=ftad8p",
    "daily": "https://worldsbestnutritionals.com/daily?ref=ftad8p",
    "call": "https://freecallwithkevin.com/?ref=ftad8p",
}
# Kevin's free live Zoom (13 Oct 2026, the owner): until it starts, Sat 17 Oct
# 11 am CT, the story slot promotes the call instead - twice a day (the workflow
# also runs at 13:05 UTC) - and the sticker reminder is daily.
CALL_END = 1792252800          # 2026-10-17 16:00 UTC
NAMES = {"training": "Free Your Wish training", "gin": "GIN", "book": "Your Wish book",
         "daily": "Daily nutrition", "call": "Kevin's FREE live Zoom (Sat Oct 17, 11 am CT)"}


def campaign():
    return time.time() < CALL_END


def reminder():
    """Markdown for the Mon/Thu reminder issue (GitHub emails it to the owner)."""
    now = datetime.datetime.now(ZoneInfo("America/New_York"))
    morning = datetime.datetime.now(datetime.timezone.utc).hour < 15
    if campaign():
        key = "call" if morning else None          # call sticker: the 09:05 run only
    else:
        key = None if morning else {0: "training", 3: "gin"}.get(now.weekday())
    if not key:
        return None
    week = now.isocalendar()[1]
    look = "photo" if (week % 2 or key == "call") else "text"
    img = f"{BASE}sticker_{key}_{look}.jpg"
    return (f"Story with a LINK STICKER today: **{NAMES[key]}**\n\n"
            f"![card]({img})\n\n"
            f"1. On your phone, open {img} and save the image.\n"
            f"2. Instagram > new Story > pick the image.\n"
            f"3. Sticker icon > **Link** > paste: `{LINKS[key]}`\n"
            f"4. Put the sticker under the gold arrow > Share.\n\n"
            f"All cards and links: https://truewealthformulas.github.io/clip-machine/stories.html")


def live(url):
    """True when the release file exists (the owner uploads the highlight files by hand)."""
    try:
        req = urllib.request.Request(url, method="HEAD")
        return urllib.request.urlopen(req, timeout=30).status == 200
    except Exception:
        return False


def call(method, path, **params):
    data = urllib.parse.urlencode(params).encode()
    url = f"https://graph.facebook.com/{V}/{path}"
    req = urllib.request.Request(url if method == "POST" else url + "?" + data.decode(),
                                 data=data if method == "POST" else None, method=method)
    try:
        return json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:300]}


def main():
    if "--remind" in sys.argv:
        r = reminder()
        if r:
            print(r)
        return
    log = json.load(open(LOG)) if os.path.exists(LOG) else {"n": 0, "posted": []}
    today = datetime.datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    n = log["n"]
    if campaign():
        done = sum(1 for p in log["posted"] if p.get("date") == today and p.get("ok") and p.get("offer") == "call")
        if done >= 2:
            print("offer story: 2 call stories already today")
            return
        key = "call"
    elif any(p.get("date") == today and p.get("ok") and p.get("offer") != "call" for p in log["posted"]):
        print("offer story: already posted today")
        return
    elif datetime.datetime.now(datetime.timezone.utc).hour < 15:
        print("offer story: morning slot is only used for the call campaign")
        return
    else:
        key = ROTATION[n % len(ROTATION)]
    pool = [p for p in (json.load(open(POOL)) if os.path.exists(POOL) else []) if p["offer"] == key]
    pool = [p for p in pool if live(MEDIA + p["file"])]
    if pool:
        k = sum(1 for p in log["posted"] if p.get("ok") and p.get("offer") == key)
        item = pool[k % len(pool)]
        look, url, kind = item["file"], MEDIA + item["file"], item["type"]
    else:
        flip = sum(1 for p in log["posted"] if p.get("ok") and p.get("offer") == "call") if key == "call" else n
        look = "photo" if flip % 2 == 0 else "text"
        url, kind = f"{BASE}auto_{key}_{look}.jpg", "image"
    print(f"offer story #{n}: {key} ({look}) {url}")
    if "--dry" in sys.argv:
        return
    ig, tok = os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"]
    media = {"video_url": url} if kind == "video" else {"image_url": url}
    # Affiliate promotion -> Instagram's "Paid partnership" label (15 Oct 2026).
    c = call("POST", f"{ig}/media", media_type="STORIES", access_token=tok,
             is_paid_partnership="true", **media)
    if not c.get("id"):
        c = call("POST", f"{ig}/media", media_type="STORIES", access_token=tok, **media)
    status = "container failed: " + str(c)[:200]
    if c.get("id"):
        for _ in range(40):
            s = call("GET", c["id"], fields="status_code", access_token=tok)
            if s.get("status_code") in ("FINISHED", "ERROR"):
                break
            time.sleep(5)
        p = call("POST", f"{ig}/media_publish", creation_id=c["id"], access_token=tok)
        status = "posted" if p.get("id") else "publish failed: " + str(p)[:200]
    ok = status == "posted"
    log["posted"].append({"date": today, "offer": key, "look": look, "ok": ok, "status": status})
    log["posted"] = log["posted"][-60:]
    if ok and key != "call":
        log["n"] = n + 1
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    json.dump(log, open(LOG, "w"), indent=1)
    print("offer story:", status)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
