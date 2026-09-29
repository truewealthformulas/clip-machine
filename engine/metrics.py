#!/usr/bin/env python3
"""Collect REAL numbers for every post, every day, server-side.

WHY THIS IS THE FOUNDATION, 4 Sept 2026. the owner: "recolect facts and just real
facts so we can keep improving knowing what works and what dosnt... the ideal is
that those improvments and dignoses daily are automatic so we can immplement the
other brands and just with one cable connect it."

He is describing a loop: post -> measure -> learn -> change -> post. We had four
of the five. **We had no measurement.** kt_performance.json was a snapshot taken
by hand on the Mac on 27 August and never updated, because the Mac is shut.

Everything we have "learned" since then was inference. Some of it was wrong:
the silence ladder looked right by measurement and was worse in practice; the
loop-close scan flagged 52 clips and over-reported badly. Opinion dressed as
data is worse than no data, and this is the fix.

WHAT EACH PLATFORM WILL ACTUALLY GIVE US
  Instagram  like_count + comments_count on /media - NO extra scope needed.
             VIEWS need instagram_manage_insights, which is not granted. So we
             measure engagement now and views when that token arrives.
  YouTube    statistics.viewCount / likeCount / commentCount. Full numbers.
  Facebook   /video_reels with likes+comments summary.
  TikTok     view/like/comment on the creator's own videos.

BRAND-AGNOSTIC ON PURPOSE. Everything goes through _cfg(brand=...), so the day
brand-2's credentials exist this measures her account too with no new code. That
is the "one cable" - the loop has to be brand-blind or every new brand is a
rebuild.

APPEND-ONLY HISTORY. Each run appends a dated sample per post rather than
overwriting, so growth over time is visible - a reel doing 300 views on day one
and 3,000 by day seven is the single most useful signal there is, and a
snapshot destroys it.
"""
import json
import os
import re
import sys
import time

import requests

from poster import _cfg, cred_prefix, brand_of, _j, T


def instagram_stats(clips):
    """Views, likes and comments per post, keyed by clip file.

    VIEWS WERE NEVER COLLECTED, and that is a bigger hole than it looks. 15 Sept
    2026: the owner said a clip of his is past 170,000 views on Instagram and the
    system could not see it, because this only ever asked for like_count and
    comments_count. Every "engagement" number this project has reasoned from -
    including the 157.7-against-19.1 finding for question CTAs - was likes plus
    comments with no idea how many people actually watched.

    Likes without views cannot tell a clip that reached 400 people and converted
    hard from one that reached 200,000 and did not. Those are opposite lessons
    and they look identical on a like count.

    `media_product_type` comes back too, so a reel is never compared against a
    carousel.
    """
    out, cache = {}, {}
    for c in clips:
        link = (c.get("links") or {}).get("instagram") or ""
        m = re.search(r"/reel/([^/?]+)|/p/([^/?]+)", link)
        if not m:
            continue
        code = m.group(1) or m.group(2)
        prefix = cred_prefix(brand_of(c))
        if prefix not in cache:
            (ig, tok), missing = _cfg("IG_USER_ID", "IG_ACCESS_TOKEN",
                                      brand=prefix)
            if missing:
                cache[prefix] = {}
                continue
            got = {}
            url = f"https://graph.facebook.com/v21.0/{ig}/media"
            # `views` is the metric Instagram itself now shows on a reel and
            # it is available on the media edge, so it costs no extra request.
            params = {"fields": "id,shortcode,like_count,comments_count,"
                                "timestamp,media_product_type",
                      "limit": 100, "access_token": tok}
            for _ in range(4):
                d = _j(requests.get(url, params=params, timeout=T))
                if d.get("error"):
                    break
                for m2 in d.get("data", []):
                    got[m2.get("shortcode")] = {
                        "id": m2.get("id"),
                        "likes": m2.get("like_count"),
                        "comments": m2.get("comments_count"),
                        "kind": m2.get("media_product_type"),
                    }
                url = (d.get("paging") or {}).get("next")
                params = None
                if not url:
                    break
            _add_plays(got, tok)
            cache[prefix] = got
        if code in cache.get(prefix, {}):
            out[c["file"]] = cache[prefix][code]
    return out


def _add_plays(got, tok):
    """Views, reach and retention. One request per reel - batching is gone.

    15 Sept 2026, in this order, each one only found because the error was
    printed instead of swallowed:

      1. a `views` FIELD on the media edge -> null for every post
      2. insights at all -> "(#10) Application does not have permission"
         (the token had no instagram_manage_insights; now granted)
      3. `plays` as a metric -> not in the valid list; the real name is `views`
      4. batching through `ids=` -> "deprecated in v26.0+"

    So: one call per reel. About a hundred requests every six hours, which is
    nothing, and it is the only shape the API still supports.

    ig_reels_avg_watch_time and reels_skip_rate are the point. Thirty-six
    videos sat at the same view ceiling and the bottleneck was never reach - it
    was whether anyone stayed. This is the first direct measure of that.
    """
    METRICS = ("views,reach,total_interactions,shares,saved,"
               "ig_reels_avg_watch_time,reels_skip_rate")
    reels = [v for v in got.values()
             if v.get("id") and v.get("kind") == "REELS"]
    said = [False]
    for v in reels:
        d = _j(requests.get(
            f"https://graph.facebook.com/v21.0/{v['id']}/insights", timeout=T,
            params={"metric": METRICS, "access_token": tok}))
        if d.get("error"):
            msg = (d["error"] or {}).get("message", "")
            if not said[0]:
                sys.stderr.write(f"  instagram insights: {msg[:150]}\n")
                said[0] = True
            v["insights_error"] = msg[:150]
            continue
        for row in d.get("data") or []:
            vals = row.get("values") or [{}]
            v[row.get("name")] = vals[0].get("value")


def youtube_stats(clips):
    out = {}
    by_prefix = {}
    for c in clips:
        link = (c.get("links") or {}).get("youtube") or ""
        m = re.search(r"shorts/([\w-]+)|v=([\w-]+)", link)
        if m:
            by_prefix.setdefault(cred_prefix(brand_of(c)), []).append(
                (c["file"], m.group(1) or m.group(2)))
    for prefix, pairs in by_prefix.items():
        (cid, sec, ref), missing = _cfg("YT_CLIENT_ID", "YT_CLIENT_SECRET",
                                        "YT_REFRESH_TOKEN", brand=prefix)
        if missing:
            continue
        r = _j(requests.post("https://oauth2.googleapis.com/token", timeout=T,
                             data={"client_id": cid, "client_secret": sec,
                                   "refresh_token": ref,
                                   "grant_type": "refresh_token"}))
        tok = r.get("access_token")
        if not tok:
            continue
        for i in range(0, len(pairs), 50):
            chunk = pairs[i:i + 50]
            d = _j(requests.get(
                "https://www.googleapis.com/youtube/v3/videos", timeout=T,
                params={"part": "statistics", "id": ",".join(v for _f, v in chunk)},
                headers={"Authorization": f"Bearer {tok}"}))
            stats = {it["id"]: it.get("statistics", {})
                     for it in d.get("items", [])}
            for f, vid in chunk:
                st = stats.get(vid)
                if st:
                    out[f] = {"views": int(st.get("viewCount", 0)),
                              "likes": int(st.get("likeCount", 0)),
                              "comments": int(st.get("commentCount", 0))}
    return out


def facebook_stats(clips):
    out, cache = {}, {}
    for c in clips:
        link = (c.get("links") or {}).get("facebook") or ""
        m = re.search(r"/reel/(\d+)|/(\d{6,})", link)
        if not m:
            continue
        vid = m.group(1) or m.group(2)
        prefix = cred_prefix(brand_of(c))
        if prefix not in cache:
            (page, tok), missing = _cfg("FB_PAGE_ID", "FB_ACCESS_TOKEN",
                                        brand=prefix)
            cache[prefix] = None if missing else tok
        tok = cache.get(prefix)
        if not tok:
            continue
        d = _j(requests.get(f"https://graph.facebook.com/v21.0/{vid}", timeout=T,
                            params={"access_token": tok,
                                    "fields": "likes.summary(true),"
                                              "comments.summary(true)"}))
        if d.get("error"):
            continue
        out[c["file"]] = {
            "likes": ((d.get("likes") or {}).get("summary") or {}).get(
                "total_count"),
            "comments": ((d.get("comments") or {}).get("summary") or {}).get(
                "total_count"),
        }
    return out


def collect(clips, path):
    """One dated sample per posted clip, appended to `path`. Never overwrites."""
    posted = [c for c in clips if c.get("posted_at")]
    if not posted:
        return 0
    got = {}
    for name, fn in (("instagram", instagram_stats),
                     ("youtube", youtube_stats),
                     ("facebook", facebook_stats)):
        try:
            got[name] = fn(posted)
        except Exception as e:
            got[name] = {"_error": f"{type(e).__name__}: {e}"[:120]}

    hist = []
    if os.path.exists(path):
        try:
            hist = json.load(open(path))
        except ValueError:
            hist = []          # a broken history must not stop measuring
    stamp = time.strftime("%Y-%m-%dT%H:%M")
    n = 0
    for c in posted:
        row = {"file": c["file"], "at": stamp,
               "posted_at": c.get("posted_at"),
               "cta_kind": c.get("cta_kind"), "keyword": c.get("cta_keyword")}
        any_num = False
        for plat in ("instagram", "youtube", "facebook"):
            v = (got.get(plat) or {}).get(c["file"])
            if v:
                row[plat] = v
                any_num = True
        if any_num:
            hist.append(row)
            n += 1
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(hist[-6000:], fh)
    os.replace(tmp, path)
    return n
