#!/usr/bin/env python3
"""Ask Instagram what it will actually tell us about one reel, and print it raw.

Written because two guesses in a row came back empty with no error: a `views`
field on the media edge returned null for every one of 102 posts, and then
insights.metric(plays,reach) through the ids= form returned nothing at all.
Both "succeeded". Guessing a third metric name would be the same mistake again.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
import requests                                               # noqa: E402

T = 30
V = os.environ.get("IG_API_VERSION", "v21.0")
ig = os.environ["IG_USER_ID"]
tok = os.environ["IG_ACCESS_TOKEN"]

d = requests.get(f"https://graph.facebook.com/{V}/{ig}/media", timeout=T,
                 params={"fields": "id,media_product_type", "limit": 5,
                         "access_token": tok}).json()
media = [m for m in d.get("data", []) if m.get("media_product_type") == "REELS"]
if not media:
    print("no reels came back:", json.dumps(d)[:400])
    raise SystemExit(1)
mid = media[0]["id"]
print(f"api {V}, reel {mid}\n")

for label, params in (
        ("media edge: views/play_count",
         {"fields": "id,like_count,comments_count,views,play_count"}),
        ("insights: plays", {"metric": "plays"}),
        ("insights: views", {"metric": "views"}),
        ("insights: reach", {"metric": "reach"}),
        ("insights: video_views", {"metric": "video_views"}),
        ("insights: total_interactions", {"metric": "total_interactions"}),
):
    path = f"{mid}/insights" if label.startswith("insights") else mid
    p = dict(params, access_token=tok)
    r = requests.get(f"https://graph.facebook.com/{V}/{path}", timeout=T, params=p)
    body = r.json()
    err = (body.get("error") or {}).get("message", "")
    print(f"{label:34} {r.status_code}  "
          + (f"ERROR: {err[:110]}" if err else json.dumps(body)[:200]))
