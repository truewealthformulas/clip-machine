#!/usr/bin/env python3
"""One offer story a day on Instagram (10 Oct 2026, the owner: "do both").

The API cannot put a link sticker on a story, so the daily card ends on
"Reply <KEYWORD>" and the owner's DM auto-reply sends the link. The cards live
on GitHub Pages (docs/stories/), built by factory/make_story_cards.py.

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
BASE = os.environ.get("STORY_BASE_URL", "https://truewealthformulas.github.io/clip-machine/stories/")
ROTATION = ["training", "gin", "book", "training", "gin", "book", "daily"]
V = "v21.0"
# For the link-sticker stories the owner posts by hand (Mon + Thu reminders).
LINKS = {
    "training": "https://freeyourwish.kevintrudeau.com/?ref=ftad8p",
    "gin": "https://signup.globalinformationnetwork.com/?ref=ftad8p",
    "book": "https://getyourwishbook.com/?ref=ftad8p",
    "daily": "https://worldsbestnutritionals.com/daily?ref=ftad8p",
}
NAMES = {"training": "Free Your Wish training", "gin": "GIN", "book": "Your Wish book",
         "daily": "Daily nutrition"}


def reminder():
    """Markdown for the Mon/Thu reminder issue (GitHub emails it to the owner)."""
    now = datetime.datetime.now(ZoneInfo("America/New_York"))
    key = {0: "training", 3: "gin"}.get(now.weekday())
    if not key:
        return None
    week = now.isocalendar()[1]
    look = "photo" if week % 2 else "text"
    img = f"{BASE}sticker_{key}_{look}.jpg"
    return (f"Story with a LINK STICKER today: **{NAMES[key]}**\n\n"
            f"![card]({img})\n\n"
            f"1. On your phone, open {img} and save the image.\n"
            f"2. Instagram > new Story > pick the image.\n"
            f"3. Sticker icon > **Link** > paste: `{LINKS[key]}`\n"
            f"4. Put the sticker under the gold arrow > Share.\n\n"
            f"All cards and links: https://truewealthformulas.github.io/clip-machine/stories.html")


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
    if any(p.get("date") == today and p.get("ok") for p in log["posted"]):
        print("offer story: already posted today")
        return
    n = log["n"]
    key = ROTATION[n % len(ROTATION)]
    look = "photo" if n % 2 == 0 else "text"
    url = f"{BASE}auto_{key}_{look}.jpg"
    print(f"offer story #{n}: {key} ({look}) {url}")
    if "--dry" in sys.argv:
        return
    ig, tok = os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"]
    c = call("POST", f"{ig}/media", media_type="STORIES", image_url=url, access_token=tok)
    status = "container failed: " + str(c)[:200]
    if c.get("id"):
        for _ in range(12):
            s = call("GET", c["id"], fields="status_code", access_token=tok)
            if s.get("status_code") in ("FINISHED", "ERROR"):
                break
            time.sleep(5)
        p = call("POST", f"{ig}/media_publish", creation_id=c["id"], access_token=tok)
        status = "posted" if p.get("id") else "publish failed: " + str(p)[:200]
    ok = status == "posted"
    log["posted"].append({"date": today, "offer": key, "look": look, "ok": ok, "status": status})
    log["posted"] = log["posted"][-60:]
    if ok:
        log["n"] = n + 1
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    json.dump(log, open(LOG, "w"), indent=1)
    print("offer story:", status)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
