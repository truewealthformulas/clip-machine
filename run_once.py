#!/usr/bin/env python3
"""One scheduling pass. Publishes whatever is due, then exits.

WHY THIS EXISTS. 13 Sept 2026. The machine ran on Railway, which bills for a
service that is awake 24 hours a day so it can be useful for the few seconds a
day something is actually due. the owner's bill reached $13.79 against a $15 cap
with an estimate of $28.16, and he was clear: "im already paying you 20$ a
month, that already its my limit."

GitHub Actions is free without limit on a public repository - verified, not
assumed - so the same work costs nothing if it runs as a cron job instead of a
daemon. That is the whole change: `while True` becomes one pass, and the state
that lived on a Railway volume is committed back to the repository.

The media moves too. Instagram's API will not take bytes; it fetches from a
URL, which is why a server was needed at all. GitHub Releases serve public
files for free, so a release asset replaces the Railway media route.

WHAT IS DELIBERATELY UNCHANGED: every posting rule, the spacing, the source
mixing, the keyword freezing, the fence between the two accounts. All of that
is hard-won and lives in engine/. This file only decides when it runs and where
the files are.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "engine"))

STATE = os.path.join(HERE, "state", "manifest.json")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    # BEFORE the import, not after. engine/main.py reads KT_DATA at module level
    # and creates the directory as it loads, so setting the attribute afterwards
    # is too late - on a runner it tries to mkdir /data and dies read-only.
    os.environ.setdefault("KT_DATA", os.path.join(HERE, "state"))
    os.environ["KT_MEDIA_REMOTE"] = "1"      # videos are release assets, not files
    os.makedirs(os.path.join(HERE, "state"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "media"), exist_ok=True)

    import main as engine                                   # noqa: E402
    import poster                                           # noqa: E402

    # Point the engine at the repository instead of a Railway volume.
    engine.MANIFEST = STATE
    engine.MEDIA = os.path.join(HERE, "media")

    # And at GitHub Releases instead of the Railway media route. Release assets
    # have no folders, so a clip's path becomes its filename with a separator
    # that survives a URL untouched.
    owner = os.environ["GH_REPO"]                # e.g. truewealthformulas/clip-machine
    tag = os.environ.get("MEDIA_TAG", "media")

    def media_url(rel):
        return (f"https://github.com/{owner}/releases/download/{tag}/"
                + rel.replace("/", "--"))
    engine.media_url = media_url

    # DRY RUN. Railway is still live during the changeover, and two schedulers
    # both seeing a clip as due would publish it twice - the duplicate-post
    # failure this project has already paid for. So the new machine proves it
    # can read the state, resolve credentials and reach the media BEFORE it is
    # ever allowed to publish anything.
    dry = os.environ.get("DRY_RUN") == "1"

    man = engine.load()
    if not man.get("clips"):
        log("no clips in state - nothing to do")
        return 0

    # RELEASE A LOCK NOBODY IS HOLDING.
    #
    # 14 Sept 2026, the owner: "today felt like it was less posting". It was: three
    # posts instead of five, and his queue was empty behind them. Two clips -
    # KT_MED/13 and KT_RICH/05 - were carrying posting=True with an empty status
    # and no posted_at, one of them since 8 September.
    #
    # The flag is set just before publishing and cleared by record(). A run that
    # dies in between - a timed-out upload, a cancelled job, a runner killed
    # mid-step - leaves it set, and due_clips() then skips that clip FOREVER.
    # Nothing reports it. The clip is simply never posted again and the day
    # quietly gets shorter, which is exactly what he noticed.
    #
    # A lock is only meaningful while the run holding it is alive. This one is
    # stamped, and anything older than an hour is assumed dead - the job itself
    # times out at 25 minutes, so an hour cannot be a live run.
    freed = 0
    for c in man["clips"]:
        if not c.get("posting") or c.get("posted_at"):
            continue
        t = c.get("posting_at")
        if t and (time.time() - t) < 3600:
            continue                      # a live run really is holding it
        c.pop("posting", None)
        c.pop("posting_at", None)
        c.pop("stale", None)
        c.pop("scheduled_at", None)       # that slot is long past; re-plan it
        freed += 1
        log(f"released a dead posting lock: {c['file']}")
    if freed:
        engine.save(man)

    changed = engine.plan(man)
    if changed:
        log(f"scheduled {changed} clip(s)")

    idxs, moved = engine.due_clips(man)
    if dry:
        import urllib.request
        log(f"DRY RUN - would publish {len(idxs)} clip(s)")
        missing = 0
        for c in man["clips"]:
            if c.get("posted_at") or c.get("done") or not c.get("scheduled_at"):
                continue
            u = media_url(c["file"])
            try:
                r = urllib.request.urlopen(urllib.request.Request(u, method="HEAD"),
                                           timeout=30)
                ok = r.status == 200
            except Exception:
                ok = False
            if not ok:
                missing += 1
                log(f"  MEDIA MISSING: {c['file']}")
        log(f"credentials visible: " + ", ".join(
            k for k in ("IG_ACCESS_TOKEN", "FB_ACCESS_TOKEN", "YT_REFRESH_TOKEN",
                        "TT_REFRESH_TOKEN", "AR_IG_ACCESS_TOKEN")
            if os.environ.get(k)))
        log(f"scheduled clips whose media is unreachable: {missing}")
        for i in idxs:
            log(f"  would post now: {man['clips'][i]['file']}")
        return 1 if missing else 0
    if moved:
        log(f"pushed {moved} clip(s) past the spacing gap")
    if not idxs:
        engine.save(man)
        log("nothing due this run")
        return 0

    for i in idxs:
        man["clips"][i]["posting"] = True
        man["clips"][i]["posting_at"] = int(time.time())
    engine.save(man)

    for i in idxs:
        clip = dict(engine.load()["clips"][i])
        path = os.path.join(engine.MEDIA, clip["file"])
        if not os.path.exists(path):
            # The bytes live in the release, not the repository. Fetch just the
            # one file that is about to be posted; a checkout carrying three
            # gigabytes of video on every run would be its own kind of waste.
            log(f"fetching {clip['file']}")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            import urllib.request
            try:
                urllib.request.urlretrieve(media_url(clip["file"]), path)
            except Exception as e:
                log(f"  could not fetch: {e}")
                continue
        # INSTAGRAM LIMIT, CHECKED AGAINST THE BOARD (26 Oct 2026). The counter
        # file in poster.py did not hold on the runner - six reels on 25 Oct and
        # two an hour apart overnight. This second gate counts what the board
        # itself says went to Instagram today, so it cannot drift.
        only = clip.get("retry_only")
        held = None
        cap = int(os.environ.get("IG_PER_DAY", "3") or 0)
        if cap > 0 and not only and "instagram" in poster.ENABLED:
            from datetime import datetime
            now = engine.now_local()
            today = now.strftime("%Y-%m-%d")
            ig = [c.get("posted_at") or "" for c in engine.load()["clips"]
                  if (c.get("status") or {}).get("instagram") == "posted"
                  and (c.get("posted_at") or "").startswith(today)]
            last = max(ig) if ig else ""
            gap_h = float(os.environ.get("IG_MIN_GAP_H", "4"))
            mins = ((now.replace(tzinfo=None) - datetime.strptime(last[:16], "%Y-%m-%dT%H:%M"))
                    .total_seconds() / 60) if last else 1e9
            if len(ig) >= cap:
                held = f"held - Instagram limited to {cap} a day while under review"
            elif mins < gap_h * 60:
                held = f"held - Instagram spaced {gap_h:g}h apart while under review"
            log(f"instagram gate: {len(ig)} today, last {last or '-'}, "
                + (held or "allowed"))
            if held:
                only = [p for p in poster.ENABLED if p != "instagram"]
        # FLAGGED SOURCE -> NOT ON META (26 Oct 2026). Instagram flagged every
        # clip cut from two recordings (factory/flagged_sources.json). Clips from
        # them still in the queue skip Instagram and Facebook; TikTok and YouTube
        # still get them.
        meta_held = None
        try:
            flagged = {k for k in json.load(open(os.path.join(HERE, "factory", "flagged_sources.json")))
                       if not k.startswith("_")}
            series = json.load(open(os.path.join(HERE, "factory", "kt_series.json")))
            brand = clip["file"].split("/", 1)[0]
            srcs = {str(v.get("source", ""))[:-4] for v in series.values() if v.get("brand") == brand}
            if srcs & flagged and not clip.get("retry_only"):
                meta_held = "held - this source was flagged by Instagram (rights match)"
                only = [p for p in (only or poster.ENABLED) if p not in ("instagram", "facebook")]
                log(f"flagged source {sorted(srcs & flagged)}: skipping Instagram and Facebook")
        except Exception as e:
            log(f"flagged-source check skipped: {e}")
        result, links = poster.publish(
            clip, path, media_url(clip["file"]), only=only)
        if held:
            result["instagram"] = held
        if meta_held:
            result["instagram"] = result["facebook"] = meta_held
        m2 = engine.load()
        engine.record(m2, i, result, links)
        engine.save(m2)
        log(f"{clip['file']}: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
