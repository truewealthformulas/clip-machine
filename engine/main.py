#!/usr/bin/env python3
"""KT Cloud — the posting system. One Railway service, four jobs.

WHY THIS REPLACED THE LAPTOP PAGE
The previous page ran on the owner's Mac and served the LAN. It died when the Mac
slept, the address changed with the network, and on 22 Aug he opened it to post
and there was nothing there. A business does not run on a laptop being awake.

WHAT IT DOES, AND WHY EACH PIECE EARNS ITS PLACE

  /p/<token>/         the posting page. Public HTTPS, works from any network,
                      Mac off. Watch, copy caption, post, mark done.
  /m/<secret>/...     the clip files. Unguessable path, byte-range enabled.
                      INSTAGRAM'S API CANNOT TAKE FILE BYTES - it fetches from a
                      public URL - so this is what makes IG posting possible at
                      all. Same URLs feed the <video> players.
  /terms /privacy     real pages. TikTok's app form and Meta's both refuse to
                      save without them. This is what unblocked the TikTok app.
  /<verify>.txt       TikTok's URL-prefix signature file, served from an env var.
                      This is why NO DOMAIN PURCHASE IS NEEDED: TikTok does not
                      require you to own a domain, only to place a file at a URL
                      you control. Railway gives us that.

POSTING: YouTube, Instagram and Facebook publish automatically. TikTok goes to
the creator INBOX and the owner taps post in the app - that is the one manual step he
accepted, and it is the only one. Direct post needs TikTok's audit; with real
terms/privacy pages and history, that audit becomes applicable for later.

NOTHING IS EVER REPORTED AS POSTED WITHOUT THE PLATFORM CONFIRMING IT.
"""
import hashlib
import html
import json
import mimetypes
import os
import re
import secrets
import sys
import threading
import time
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

import poster
import pages
import metrics

# Stamped at deploy time. /health reports it, so a deploy can be verified by
# BEHAVIOUR rather than by "did /health answer" - which the PREVIOUS build also
# answers. Checking health three times in one session let me test old code and
# misread the results twice. Never again: poll for the build id.
BUILD_ID = "20260912-retry-respects-gap"

DATA = os.environ.get("KT_DATA", "/data")
MEDIA = os.path.join(DATA, "media")
MANIFEST = os.path.join(DATA, "manifest.json")
METRICS = os.path.join(DATA, "metrics.json")
METRICS_EVERY = int(os.environ.get("KT_METRICS_EVERY", str(6 * 3600)))
PORT = int(os.environ.get("PORT", "8080"))

# Page token gates every control surface. Media token is separate and only
# grants read access to the files - Instagram fetches with no auth header, so
# media must be reachable by URL alone, and that URL must not also hand out
# the ability to publish.
TOKEN = os.environ.get("KT_TOKEN", "")
MEDIA_TOKEN = os.environ.get("KT_MEDIA_TOKEN", "")
UPLOAD_KEY = os.environ.get("KT_UPLOAD_KEY", "")
BASE_URL = os.environ.get("KT_BASE_URL", "").rstrip("/")
TIKTOK_VERIFY = os.environ.get("TIKTOK_VERIFY_FILE", "")   # "name.txt:contents"

LOCK = threading.Lock()
os.makedirs(MEDIA, exist_ok=True)

TZ = os.environ.get("KT_TZ", "America/New_York")
STALE_AFTER = 8 * 3600   # a slot missed by more than this lapses
# EIGHT HOURS, NOT THREE. 13 Sept 2026, first day on GitHub Actions: the cron
# says every 20 minutes and GitHub actually ran it twice in four hours - 109
# minutes apart. Scheduled workflows are best-effort and get queued or dropped
# under load, and a public repository is not first in that queue.
#
# With a three-hour window a run that arrives late finds the slot already
# lapsed and the post never happens. The slots already carry 40 minutes of
# jitter, so a post landing an hour or two late is invisible; a post that never
# lands is not.
MIN_GAP = 45 * 60        # seconds between two posts by the SAME person

# THE DAILY PLAN. the owner does not choose what goes out or when - that is the
# whole point of the system. Anything uploaded with no schedule gets dropped
# into the next free slot automatically, so the calendar is always full and the
# only thing he ever does is look at it.
SLOTS = [t.strip() for t in os.environ.get(
    "KT_SLOTS", "08:00,11:30,14:30,17:30,20:30").split(",") if t.strip()]


def brand_slots(prefix):
    """The daily slot grid for ONE brand. `AR_SLOTS` overrides `KT_SLOTS`.

    30 AUG 2026, AND THIS IS WHY BRAND TWO COULD NOT SHIP TODAY. Every brand
    shared one grid of five times, so the owner's 45-clip queue owned every slot for
    the next NINE DAYS. brand-2's six clips would have been planned for 8 Sep - a
    brand-new account posting nothing for over a week, which is the one thing
    that kills a new account.

    There was never a reason to share. The brands post to DIFFERENT accounts on
    every platform, so two clips at 08:00 do not collide with each other in any
    way that matters - the contention was an artefact of one global list, not a
    real constraint. Each brand now gets its own grid and its own booked-slot
    set, so one brand's backlog can never delay another's.
    """
    raw = os.environ.get((prefix or "") + "_SLOTS", "")
    out = [t.strip() for t in raw.split(",") if t.strip()]
    return out or SLOTS
LEAD_MIN = int(os.environ.get("KT_LEAD_MIN", "20"))   # never schedule this close
JITTER_MIN = int(os.environ.get("KT_JITTER_MIN", "40"))  # drift each slot +/- this
HORIZON_DAYS = 30
AUTOPLAN = os.environ.get("KT_AUTOPLAN", "1") != "0"
try:
    from zoneinfo import ZoneInfo
    ZONE = ZoneInfo(TZ)
except Exception:
    ZONE = None


def now_local():
    """Now, in the brand's timezone.

    Every timestamp a human sees or types here is New York local. Railway runs
    UTC. Mixing the two is exactly the bug that had the old Railway sweeper
    deleting scheduled posts four hours early, so there is one function and
    everything uses it.
    """
    from datetime import datetime, timezone
    if ZONE:
        return datetime.now(timezone.utc).astimezone(ZONE).replace(tzinfo=None)
    return datetime.utcnow()


def _person(clip):
    """AR_MIND and AR_LUCK are the same person. The gap below is per PERSON."""
    b = brand_of(clip)
    return b.split("_")[0] if "_" in b else b


def _last_post(man, who):
    """When this person last posted anything, as a local datetime or None."""
    from datetime import datetime
    best = None
    for c in man["clips"]:
        pa = c.get("posted_at")
        if not pa or _person(c) != who:
            continue
        try:
            t = datetime.strptime(pa[:16], "%Y-%m-%dT%H:%M")
        except ValueError:
            continue
        if best is None or t > best:
            best = t
    return best


def due_clips(man):
    """Which clips to post right now, and whether any were pushed later.

    ONE PER PERSON PER TICK, AND NEVER INSIDE MIN_GAP. 10 Sept 2026: nine of
    brand-2's clips went into her TikTok inbox between 15:33 and 15:48 - a
    fifteen-minute dump of a day's content. The loop posted every due clip
    back to back, so any backlog (a restart, a re-plan, a stretch offline)
    emptied itself in one burst. That is the opposite of the spaced, steady
    account the whole schedule exists to produce, and on TikTok it buries her
    own clips under each other in one notification stack.

    A clip that has to wait is MOVED, not dropped - its slot is pushed past the
    gap so it still goes out today instead of lapsing at STALE_AFTER.
    """
    from datetime import datetime, timedelta
    now = now_local()
    out = []
    moved = 0
    for i, c in enumerate(man["clips"]):
        when = c.get("scheduled_at")
        # posted_at is set after ANY attempt, success or not. Without this a
        # clip whose Facebook leg failed would re-run every 60s for three hours.
        # A clip carrying retry_only is being re-run for named platforms only.
        # It keeps its posted_at (it really did publish), so the normal guard
        # would skip it forever - this is the one case that overrides it.
        if c.get("retry_only") and not c.get("posting"):
            out.append(i)
            continue
        if not when or c.get("done") or c.get("posting") or c.get("posted_at"):
            continue
        try:
            t = datetime.strptime(when[:16], "%Y-%m-%dT%H:%M")
        except ValueError:
            continue
        # A slot that is already well past does NOT fire. On 24 Aug a schedule
        # left over from a test two days earlier fired the instant Instagram
        # credentials were loaded, and posted a clip the owner had not asked for.
        # A missed slot is a scheduling decision that has expired, not a queued
        # instruction - it should lapse quietly and be visible on the board.
        if t <= now:
            if (now - t).total_seconds() > STALE_AFTER:
                c["stale"] = True
                continue
            out.append(i)

    # Space them. Earliest slot wins the tick; the rest are pushed past the gap.
    keep, seen = [], {}
    for i in sorted(out, key=lambda j: man["clips"][j].get("scheduled_at") or ""):
        c = man["clips"][i]
        # A RETRY IS STILL A POST. 12 Sept 2026: this exemption is what let nine
        # of brand-2's Meta backfills land on Instagram between 15:37 and 15:48 -
        # nine posts in twelve minutes on an account with 84 followers, which is
        # the same burst pattern the gap exists to prevent.
        #
        # The reasoning behind the exemption was that a MANUAL retry should not
        # be delayed. True for one clip. But a backfill is a retry of a whole
        # backlog, and that is exactly the case that arrives in bulk. The gap
        # costs a single retry up to 45 minutes; skipping it cost a day's
        # content in one stack.
        #
        # Deliberately NOT exempted any more. If one retry ever needs to jump
        # the queue, post it by hand.
        who = _person(c)
        if who not in seen:
            seen[who] = _last_post(man, who)
        last = seen[who]
        if last is not None and (now - last).total_seconds() < MIN_GAP:
            c["scheduled_at"] = (last + timedelta(seconds=MIN_GAP)
                                 ).strftime("%Y-%m-%dT%H:%M")
            c.pop("stale", None)
            moved += 1
            continue
        keep.append(i)
        seen[who] = now                    # this person is done for this gap
    return keep, moved


def brand_of(clip):
    return clip["file"].split("/")[0]


def plan(man):
    """Give every unscheduled clip a time. Returns how many were placed.

    Planned SEPARATELY PER BRAND, each on its own grid (see brand_slots), so a
    brand with a long backlog cannot push a newer brand out to next week.

    Within one brand, ordering interleaves that brand's own folders round-robin.
    Five clips from one series back to back reads as a dump; alternating them
    makes the account look like it is running, which is also what the platforms
    reward.

    A slot is skipped if that BRAND has already taken it, or if it is too close
    to now. Nothing is ever moved once placed - it may already be on a calendar
    someone has looked at.
    """
    from datetime import datetime, timedelta
    now = now_local()

    pool = {}
    for i, c in enumerate(man["clips"]):
        if c.get("done") or c.get("scheduled_at") or c.get("posted_at"):
            continue
        pool.setdefault(poster.account_key(brand_of(c)), []).append(i)
    if not pool:
        return 0

    placed = 0
    for prefix, idxs in sorted(pool.items()):
        slots = brand_slots(prefix)
        # A SLOT IS ONLY TAKEN BY A CLIP THAT WILL ACTUALLY POST.
        #
        # 5 Sept 2026. the owner: "the number of posts posting its too low and its
        # kind off." He was right and this was why. The next three days were
        # 3/5 full while later days were 5/5 - backwards, since near days fill
        # first.
        #
        # Cause: a clip keeps its `scheduled_at` after it is marked done, and
        # this set counted every clip that had one. Eight retired clips were
        # squatting on future slots - THE-GAWKERS-TRAFFIC-JAM held Sunday 08:00
        # and was never going to post at it. The slot looked booked, the
        # planner skipped it, and that hour of the day simply went dark.
        #
        # Nothing announces this. The board shows a full-looking calendar and
        # the account quietly posts three times a day instead of five.
        taken = {c["scheduled_at"][:16] for c in man["clips"]
                 if c.get("scheduled_at")
                 and not c.get("done") and not c.get("posted_at")
                 and poster.account_key(brand_of(c)) == prefix}

        # MIX THE SOURCES ACROSS EACH DAY. 11 Sept 2026, the owner: "we just posted
        # 4 clips together from the same source and it looks bored... i want
        # multiples sources per day all mixed up."
        #
        # The interleave above only refuses the same source twice IN A ROW, so
        # when one folder is the only one with clips left it quietly took the
        # whole day - four KT_RICH posts on 11 Sept, same interview, same shirt,
        # same room. To a scroller that is one video cut up, which it is.
        #
        # AT MOST TWO PER SOURCE PER DAY, not one. A hard limit of one would
        # need five different videos every single day to hit five posts, and
        # with three series in the library that would quietly cut the day to
        # three - trading the mix problem for a volume problem. Two keeps a day
        # of five spread over at least three different videos.
        #
        # Counts clips ALREADY scheduled too, so a re-plan cannot stack onto a
        # day that is already carrying that source.
        PER_SOURCE_PER_DAY = 2
        last_src = [None]          # source of the post placed immediately before
        used = {}
        for c in man["clips"]:
            sa = c.get("scheduled_at")
            if sa and not c.get("done") and not c.get("posted_at"):
                d0 = used.setdefault(sa[:10], {})
                d0[brand_of(c)] = d0.get(brand_of(c), 0) + 1

        # ORDER, 5 Sept 2026. the owner: "posting all clips from a same video all
        # together following on another its bored, it need to be separate kind
        # like random but not random more stratigically."
        #
        # It was ALREADY interleaved across folders - only 4 back-to-back pairs
        # in 22 - so "all together" was not the real fault. Two real ones were:
        #
        #   1. A FIXED ROTA. sorted(folders) meant the same cycle every round:
        #      LIES, MED, MIND, PROB, STUDENT, MINDSET, LIES, MED... Predictable
        #      to anyone scrolling the grid, and it is why it reads as a queue
        #      being drained rather than an account being run.
        #   2. FILE ORDER INSIDE A FOLDER. Clips went 01, 02, 03 - the order
        #      they happen to sit in the source talk. A talk's best moment is
        #      rarely its first, so the strongest clip could wait nine slots.
        #
        # Fixed: the folder that goes next is the one with the MOST clips left
        # (ties broken by a per-round rotation), which drains long series
        # without letting any one dominate and never gives the same cycle twice.
        # Inside a folder, SHORTER clips go first - the one thing the numbers
        # actually support, since a 33s clip and a 166s clip get the same ~1,000
        # impressions and the short one has to hold attention for a fifth as
        # long. That is a real edge, not a guess about content.
        folders = {}
        for i in idxs:
            folders.setdefault(brand_of(man["clips"][i]), []).append(i)

        def secs(i):
            m = re.search(r"_(\d+)s\.mp4$", man["clips"][i]["file"])
            return int(m.group(1)) if m else 999

        for v in folders.values():
            v.sort(key=secs)
        queue, rnd = [], 0
        while any(folders.values()):
            live = [b for b in folders if folders[b]]
            live.sort(key=lambda b: (-len(folders[b]), b))
            # rotate the tie-break so consecutive rounds do not repeat a rota
            if len(live) > 1:
                live = live[rnd % len(live):] + live[:rnd % len(live)]
                live.sort(key=lambda b: -len(folders[b]))
            picked = None
            for b in live:
                # never the same source twice in a row
                if queue and brand_of(man["clips"][queue[-1]]) == b and len(live) > 1:
                    continue
                picked = b
                break
            picked = picked or live[0]
            queue.append(folders[picked].pop(0))
            rnd += 1

        day = now.date()
        for _ in range(HORIZON_DAYS):
            for hhmm in slots:
                if not queue:
                    break
                try:
                    h, m = (int(x) for x in hhmm.split(":"))
                except ValueError:
                    continue
                when = datetime(day.year, day.month, day.day, h, m)
                # JITTER, 8 Sept 2026. the owner found Facebook AND YouTube limiting
                # reach on BOTH his accounts and BOTH of brand-2's. Four accounts
                # across two platforms is not four content penalties - it points
                # at HOW we post, and the loudest signal we give off is the
                # clock: five posts a day landing at exactly 08:00, 11:30, 13:30,
                # 17:30 and 20:30, to the minute, every day, from an API, on
                # accounts with 119 and 2 followers. No human posts like that.
                #
                # So each slot drifts by up to +/-JITTER minutes, derived from
                # the date and the slot rather than random, so a replan does not
                # reshuffle a calendar someone has already looked at.
                seed = f"{day.isoformat()}{hhmm}{prefix}"
                off = (int(hashlib.sha256(seed.encode()).hexdigest()[:6], 16)
                       % (2 * JITTER_MIN + 1)) - JITTER_MIN
                when = when + timedelta(minutes=off)
                if when < now + timedelta(minutes=LEAD_MIN):
                    continue
                key = when.strftime("%Y-%m-%dT%H:%M")
                if key in taken:
                    continue
                # Take the first clip in the queue whose SOURCE has not already
                # posted today. If every remaining clip is from that one source,
                # the day gets it anyway - a gap serves nobody - but that is now
                # the exception it should always have been.
                dkey = when.strftime("%Y-%m-%d")
                spent = used.setdefault(dkey, {})

                def ok(qi, strict):
                    b = brand_of(man["clips"][qi])
                    if spent.get(b, 0) >= PER_SOURCE_PER_DAY:
                        return False
                    # and not the same source as the post immediately before it
                    return not (strict and b == last_src[0])

                pick = next((n for n, qi in enumerate(queue) if ok(qi, True)),
                            next((n for n, qi in enumerate(queue)
                                  if ok(qi, False)), 0))
                nxt = man["clips"][queue.pop(pick)]
                spent[brand_of(nxt)] = spent.get(brand_of(nxt), 0) + 1
                last_src[0] = brand_of(nxt)
                nxt["scheduled_at"] = key
                # ROTATE THE COMMENT KEYWORD, IN POSTING ORDER. Daniel's point
                # via the owner: consecutive posts must ask for DIFFERENT words so
                # each one feels like a new thing rather than the same ad. Doing
                # it here, at the moment a slot is assigned, is what makes
                # "consecutive" mean anything - a hash of the filename would
                # happily give three WISHes in a row.
                #
                # Frozen onto the clip, so the caption that goes out always
                # matches the keyword, even if the clip is re-planned later.
                # PER BRAND, 9 Sept 2026, AND THIS IS THE BUG THAT MADE
                # BRAND2'S CTA DEAD FOR TWO WEEKS. This line read
                # `poster.KEYWORDS`, which is the GLOBAL (the owner's) list, so her
                # clips were frozen with WISH / KT / FREE - his words, listened
                # for only by HIS automation on HIS account. Read back off live
                # Instagram: her last five posts said "Comment YES" and the
                # three before them "Comment WISH". Not one ever said RISE.
                # Every comment her viewers left hit silence.
                #
                # `poster.keywords_for(brand)` has existed since the brand fence
                # was built for exactly this, and plan() never called it.
                kws = poster.keywords_for(brand_of(nxt))
                if not nxt.get("cta_keyword"):
                    nxt["cta_keyword"] = kws[placed % len(kws)]
                # The WORDING rotates too, in posting order and for the same
                # reason - so two posts in a row never read identically.
                if nxt.get("cta_variant") is None:
                    nxt["cta_variant"] = placed
                # ONE OFFER FOR EVERY TWO QUESTIONS. kevins_apprentice ends two
                # of every three posts on a question with no link at all, and
                # outreaches us 4,000 to 1 on the same material. Reach has to
                # come before the sell - we have been asking strangers to buy
                # before giving them a reason to care.
                # HOW OFTEN THE ASK APPEARS, per brand. the owner keeps one offer
                # in three (kevins_apprentice analysis). brand-2 owner, 9 Sept: "lets put
                # it on every other video instead of every video" - so AR_* is
                # one in two. Her money-specific clips override this per clip by
                # carrying cta_kind = "offer" already.
                every = 2 if poster.cred_prefix(brand_of(nxt)) == "AR" else 3
                if not nxt.get("cta_kind"):
                    nxt["cta_kind"] = "offer" if placed % every == 0 else "question"
                taken.add(key)
                placed += 1
            if not queue:
                break
            day += timedelta(days=1)
    return placed


AUDIT_EVERY = int(os.environ.get("KT_AUDIT_MIN", "60")) * 60
# YouTube rate-limits thumbnail uploads hard and without documenting the number.
# Five a day clears the backlog in under a week and never competes with the
# covers that scheduled posts set at publish time.
COVER_EVERY = int(os.environ.get("KT_COVER_HOURS", "24")) * 3600
COVER_N = int(os.environ.get("KT_COVER_N", "5"))


def audit(man):
    """Ask Instagram what is really on the account and correct the board.

    Anything that says posted and is not there is put back to work with the
    reason written in its status, so it is visible rather than quietly wrong.
    """
    bad = poster.audit_instagram(man["clips"])
    for i in bad:
        c = man["clips"][i]
        c.setdefault("status", {})["instagram"] = (
            "NOT on the account - it was reported posted and it is not there. "
            "Re-queued.")
        c["done"] = False
        c["posted_at"] = None
        c["scheduled_at"] = None
        (c.setdefault("links", {})).pop("instagram", None)

    # Facebook, audited for the first time on 3 Sept 2026. It was left out
    # because /feed answered "(#10) requires pages_read_engagement" and I took
    # that to mean the Page could not be read at all. /video_reels answers fine.
    # Ten days of Facebook posts went unverified on the strength of one refused
    # endpoint I never followed up.
    #
    # NOT re-queued the way Instagram is. A Facebook reel that is missing is
    # usually missing because Facebook deduplicated it, and re-queuing a
    # duplicate is how this whole mess started. It is marked, loudly, and left
    # for a person to look at.
    for i in poster.audit_facebook(man["clips"]):
        c = man["clips"][i]
        c.setdefault("status", {})["facebook"] = (
            "NOT on the Page - reported posted and it is not there. Most likely "
            "Facebook already had this video and returned the original reel. "
            "NOT re-queued.")
        if i not in bad:
            bad.append(i)
    return bad


def record(man, i, result, links):
    """One place where the outcome of an attempt is written down."""
    c = man["clips"][i]
    c["status"] = result
    c["links"] = links
    # The caption AS POSTED, frozen. Captions get rewritten later (hook changes,
    # reordering) and the audit used to compare a rewritten caption against a
    # post made with the old one, decide the post was missing, and publish it a
    # second time. Whatever identifies a post must be captured at the moment of
    # posting and never edited afterwards.
    if any(v == "posted" for v in result.values()):
        c.setdefault("caption_at_post", c.get("caption", ""))
    c["posting"] = False
    c.pop("posting_at", None)          # the lock is released with the flag
    c.pop("retry_only", None)          # one retry, not a standing instruction
    c["posted_at"] = now_local().strftime("%Y-%m-%dT%H:%M")
    auto = [p for p in poster.ENABLED if p != "tiktok"]
    if auto and all(result.get(p) == "posted" for p in auto):
        c["done"] = True
    # A clip Facebook already has is FINISHED, not failed. Without this it keeps
    # its schedule, comes round again on the next tick, and re-posts to the
    # three platforms that do not dedupe - the exact loop this is here to stop.
    if str(result.get("facebook", "")).startswith("DUPLICATE"):
        c["done"] = True
    return c


def scheduler_loop():
    """Publish anything whose slot has arrived. Checks every 60s.

    Marks `posting` before releasing the lock so a slow upload cannot be started
    twice by the next tick. Anything that fails keeps its schedule and its error
    so it is visible on the board rather than silently dropped.
    """
    while True:
        try:
            now_ts = time.time()
            with LOCK:
                man = load()
                bad = []
                if now_ts - state["audited"] > AUDIT_EVERY:
                    state["audited"] = now_ts
                    bad = audit(man)
                    if bad:
                        sys.stderr.write(
                            "audit: re-queued " + ", ".join(
                                man["clips"][i]["file"] for i in bad) + "\n")
                changed = plan(man) if AUTOPLAN else 0
                # Once a day, give a few already-published Shorts the cover we
                # chose instead of the frame YouTube guessed. Server-side and
                # paced so it needs no laptop, no command and nobody's attention.
                # MEASURE, DAILY, SERVER-SIDE. The loop the owner described -
                # post, measure, learn, change - had no measurement step. The
                # only numbers we had were a snapshot taken by hand on 27 Aug
                # on a Mac that is usually shut.
                if now_ts - state.get("measured", 0) > METRICS_EVERY:
                    state["measured"] = now_ts
                    try:
                        n = metrics.collect(man["clips"], METRICS)
                        if n:
                            sys.stderr.write(f"metrics: sampled {n} post(s)\n")
                    except Exception as e:
                        sys.stderr.write(f"metrics failed: {e}\n")
                if now_ts - state["covered"] > COVER_EVERY:
                    state["covered"] = now_ts
                    got = poster.backfill_covers(man["clips"], MEDIA, COVER_N)
                    if got:
                        changed += len(got)
                        sys.stderr.write("covers set: " + ", ".join(got) + "\n")
                idxs, moved = due_clips(man)
                for i in idxs:
                    man["clips"][i]["posting"] = True
                if idxs or changed or bad or moved:
                    save(man)
                if moved:
                    sys.stderr.write(f"spacing: pushed {moved} clip(s) past "
                                     f"the {MIN_GAP // 60}min gap\n")
                if changed:
                    sys.stderr.write(f"autoplan: scheduled {changed} clip(s)\n")
            for i in idxs:
                with LOCK:
                    clip = dict(load()["clips"][i])
                result, links = poster.publish(
                    clip, os.path.join(MEDIA, clip["file"]), media_url(clip["file"]),
                    only=clip.get("retry_only"))
                with LOCK:
                    man = load()
                    record(man, i, result, links)
                    save(man)
                sys.stderr.write(f"scheduled post {clip['file']}: {result}\n")
        except Exception as e:
            sys.stderr.write(f"scheduler error: {type(e).__name__}: {e}\n")
        time.sleep(60)


# First tick audits immediately, then once an hour.
state = {"audited": 0.0, "covered": 0.0, "measured": 0.0}

VIDEO_EXT = (".mp4", ".mov", ".m4v")


def load():
    if not os.path.exists(MANIFEST):
        return {"clips": []}
    try:
        with open(MANIFEST) as fh:
            m = json.load(fh)
    except (ValueError, OSError):
        return {"clips": []}
    # Self-heal: drop anything that is not a video, and anything whose file has
    # gone. An earlier build let an uploaded asset (the TikTok app icon) become a
    # board entry, and a stale entry with no file behind it shows a dead player.
    # Filtering on read means the board is correct even for manifests written by
    # an older version, with no migration step.
    # THE FILE CHECK IS ONLY VALID WHERE THE FILES LIVE. 13 Sept 2026, moving
    # to GitHub Actions: the videos are release assets and a runner starts with
    # an empty media folder, fetching only the clip it is about to publish. The
    # existence test then matched nothing and this quietly returned ZERO clips
    # from a manifest of 145 - which the workflow would have committed back over
    # the real state, erasing every posted_at and re-posting the whole library.
    #
    # Caught before it ran, by reading what load() returned instead of trusting
    # it. On Railway the check still earns its place, so it stays there.
    remote = os.environ.get("KT_MEDIA_REMOTE") == "1"
    before = len(m.get("clips", []))
    m["clips"] = [c for c in m.get("clips", [])
                  if c.get("file", "").lower().endswith(VIDEO_EXT)
                  and "__yt" not in os.path.basename(c.get("file", ""))
                  and (remote or os.path.exists(os.path.join(MEDIA, c["file"])))]
    if len(m["clips"]) != before:
        sys.stderr.write(f"manifest: dropped {before - len(m['clips'])} non-clip "
                         f"or missing entr(ies)\n")
    return m


def save(m):
    tmp = MANIFEST + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(m, fh, indent=1)
    os.replace(tmp, tmp.replace(".tmp", ""))   # atomic; a crash never truncates


def media_url(rel):
    return f"{BASE_URL}/m/{MEDIA_TOKEN}/{urllib.parse.quote(rel)}"


class H(BaseHTTPRequestHandler):
    server_version = "ktcloud"

    # ---------------------------------------------------------------- helpers
    def _send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
        body = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, code, obj):
        self._send(code, json.dumps(obj), "application/json")

    def calendar_ics(self):
        """Every post, scheduled and past, as a calendar Google can subscribe to.

        11 Sept 2026. the owner asked for "a very nice calendar map" like Metricool
        and said to stop building him dashboards - the captions page he already
        has is "very bad and confusing". He is right that a board nobody wants
        to open is not a board.

        So this is not a page. It is an .ics feed he subscribes to ONCE in the
        Google Calendar he already has open all day. It costs nothing, needs no
        account, no API key and no login, and it keeps refreshing while his Mac
        is shut - which the Mac-side tools cannot do.

        Two calendars in one: his posts and brand-2's, told apart in the title, so
        he can see at a glance that both accounts are actually running.
        """
        from datetime import datetime, timedelta
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(TZ)
        except Exception:
            tz = None

        def stamp(txt, mins=0):
            try:
                t = datetime.strptime(txt[:16], "%Y-%m-%dT%H:%M")
            except (ValueError, TypeError):
                return None
            t = t + timedelta(minutes=mins)
            if tz is not None:
                t = t.replace(tzinfo=tz).astimezone(ZoneInfo("UTC"))
            return t.strftime("%Y%m%dT%H%M%SZ")

        def esc(t):
            return (t.replace("\\", "\\\\").replace(";", "\\;")
                     .replace(",", "\\,").replace("\n", "\\n"))

        out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//KT Cloud//EN",
               "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
               "X-WR-CALNAME:Posts - the owner + Brand 2",
               "X-WR-TIMEZONE:" + TZ,
               "REFRESH-INTERVAL;VALUE=DURATION:PT30M",
               "X-PUBLISHED-TTL:PT30M"]
        now = datetime.now().strftime("%Y%m%dT%H%M%SZ")
        for c in load()["clips"]:
            when = c.get("posted_at") or c.get("scheduled_at")
            start = stamp(when)
            if not start:
                continue
            f = c["file"]
            who = "BRAND 2" if f.startswith("AR_") else "OWNER"
            live = bool(c.get("posted_at"))
            cap = (c.get("caption") or "").strip().splitlines()
            title = cap[0] if cap else f.split("/")[-1]
            status = "POSTED" if live else "scheduled"
            where = ", ".join(sorted((c.get("status") or {}).keys())) or "-"
            body = [f"{status} - {f}", f"platforms: {where}"]
            links = c.get("links") or {}
            for k, v in sorted(links.items()):
                body.append(f"{k}: {v}")
            out += ["BEGIN:VEVENT",
                    "UID:" + f.replace("/", "-").replace(" ", "_") + "@ktcloud",
                    "DTSTAMP:" + now,
                    "DTSTART:" + start,
                    "DTEND:" + (stamp(when, 15) or start),
                    "SUMMARY:" + esc(f"{'' if live else '[ ] '}{who} - {title}"),
                    "DESCRIPTION:" + esc("\n".join(body)),
                    "STATUS:" + ("CONFIRMED" if live else "TENTATIVE"),
                    "END:VEVENT"]
        out.append("END:VCALENDAR")
        return self._send(200, "\r\n".join(out) + "\r\n",
                          "text/calendar; charset=utf-8")

    def _authed(self, prefix):
        """Path is /p/<TOKEN>/... — constant-time compare, no token no service."""
        m = re.match(r"^/p/([^/]+)(/.*)?$", prefix)
        if not m or not TOKEN or not secrets.compare_digest(m.group(1), TOKEN):
            return None
        return m.group(2) or "/"

    def log_message(self, fmt, *a):
        sys.stderr.write("%s\n" % (fmt % a))

    # -------------------------------------------------------------------- GET
    def do_GET(self):
        path = self.path.split("?", 1)[0]

        # What the cloud already holds, keyed by path -> bytes. Guarded by the
        # UPLOAD key rather than the page token, because the uploader has that
        # one and nothing here is worth reading without it.
        if path == "/manifest":
            if not UPLOAD_KEY or not secrets.compare_digest(
                    self.headers.get("X-Upload-Key", ""), UPLOAD_KEY):
                return self._send(404, "Not found", "text/plain; charset=utf-8")
            m = load()
            out = {c["file"]: c.get("bytes", 0) for c in m["clips"]}
            # The 59s YouTube cuts are deliberately not clips, so they are not in
            # the manifest - and without this the pusher would re-send every one
            # of them on every push, which is exactly the 200MB-to-move-nothing
            # waste the size check was added to stop.
            for brand in os.listdir(MEDIA):
                bdir = os.path.join(MEDIA, brand)
                if not os.path.isdir(bdir):
                    continue
                for f in os.listdir(bdir):
                    if "__yt" in f:
                        out[f"{brand}/{f}"] = os.path.getsize(
                            os.path.join(bdir, f))
            return self._json(200, out)

        if path == "/health":
            return self._json(200, {"ok": True, "build": BUILD_ID,
                                    "clips": len(load()["clips"])})

        # TikTok's URL-prefix verification file, straight from the env var.
        if TIKTOK_VERIFY and ":" in TIKTOK_VERIFY:
            name, _, contents = TIKTOK_VERIFY.partition(":")
            if path == "/" + name.lstrip("/"):
                return self._send(200, contents, "text/plain; charset=utf-8")

        # OAuth callback. TikTok refuses any redirect URI that is not https, so
        # localhost cannot be used - this app's own verified domain can. The code
        # is shown on screen rather than exchanged here because the PKCE verifier
        # lives on the machine that started the flow, never on the server.
        if path.startswith("/p/") and path.endswith("/calendar.ics"):
            if self._authed(path[:-len("/calendar.ics")] or "/p/x") is not None:
                return self.calendar_ics()
            return self._send(404, "not found")

        if path.startswith("/oauth/"):
            q = urllib.parse.parse_qs(
                urllib.parse.urlparse(self.path).query)
            code = (q.get("code") or [""])[0]
            err = (q.get("error_description") or q.get("error") or [""])[0]
            return self._send(200, pages.oauth_result(code, err))

        if path == "/terms":
            return self._send(200, pages.TERMS)
        if path == "/privacy":
            return self._send(200, pages.PRIVACY)
        if path in ("/", "/index.html"):
            return self._send(200, pages.LANDING)

        if path.startswith("/m/"):
            return self.serve_media(path)

        sub = self._authed(path)
        if sub is None:
            return self._send(404, "Not found", "text/plain; charset=utf-8")
        if sub in ("/", "", "/c"):
            # Home IS the captions page now - the one thing he does by hand.
            # ?b=AR narrows it to one brand. Two people share this page and one
            # tap of COPY retires a caption for BOTH of them, so without a
            # filter the owner working down the list was quietly removing brand-2's.
            # No parameter still means every brand, so his link is unchanged.
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            m = load()
            return self._send(200, pages.captions(
                m["clips"], TOKEN, media_url, now_local(),
                brand=(q.get("b") or [""])[0],
                show_done=bool(q.get("all"))))
        if sub == "/all":
            m = load()
            return self._send(200, pages.board(m["clips"], TOKEN, media_url,
                                               now_local()))
        if sub == "/calendar":
            m = load()
            return self._send(200, pages.calendar(m["clips"], TOKEN, media_url,
                                                  now_local()))
        if sub == "/today":
            m = load()
            q = urllib.parse.parse_qs(
                urllib.parse.urlparse(self.path).query).get("b", [""])[0]
            # The empty-state line quotes the slot grid, so it has to be the
            # grid for the brand being LOOKED AT. With `?b=AR` it used to quote
            # the owner's times at brand-2 owner, which reads as her setting being ignored.
            return self._send(200, pages.today(m["clips"], TOKEN, media_url,
                                               now_local(),
                                               brand_slots(poster.cred_prefix(q))
                                               if q else SLOTS,
                                               poster.ENABLED, q))
        if sub == "/metrics":
            # WHAT ACTUALLY WORKED. Not a dump - the comparisons we change
            # behaviour on: offer vs question, and clip length. Anything with
            # fewer than 3 posts on a side is NOT reported, because two posts
            # is a coin flip and acting on it is how the silence ladder got
            # shipped and had to be reverted.
            hist = []
            if os.path.exists(METRICS):
                try:
                    hist = json.load(open(METRICS))
                except ValueError:
                    hist = []
            latest = {}
            for r in hist:
                latest[r["file"]] = r          # history is append-ordered
            man = load()
            meta = {c["file"]: c for c in man["clips"]}

            def eng(r):
                n = 0
                for p in ("instagram", "youtube", "facebook"):
                    v = r.get(p) or {}
                    n += (v.get("likes") or 0) + (v.get("comments") or 0)
                return n

            def views(r):
                return ((r.get("youtube") or {}).get("views") or 0)

            groups = {}
            for f, r in latest.items():
                c = meta.get(f, {})
                kind = r.get("cta_kind") or c.get("cta_kind") or "unset"
                groups.setdefault(kind, []).append((eng(r), views(r)))
            out = {"posts_measured": len(latest), "samples": len(hist)}
            for k, rows in sorted(groups.items()):
                if len(rows) < 3:
                    out[k] = f"only {len(rows)} post(s) - not enough to say"
                    continue
                out[k] = {
                    "posts": len(rows),
                    "avg_engagement": round(sum(a for a, _ in rows) / len(rows), 1),
                    "avg_yt_views": round(sum(b for _, b in rows) / len(rows), 1),
                }
            top = sorted(latest.items(), key=lambda kv: -eng(kv[1]))[:8]
            out["best"] = [{"file": f, "engagement": eng(r),
                            "yt_views": views(r),
                            "cta": r.get("cta_kind")} for f, r in top]
            return self._json(200, out)

        if sub == "/state.json":
            # The machine-readable truth. Everything the pages render comes from
            # here, so anything checking on this system checks the same thing a
            # human sees rather than a second, drifting copy.
            m = load()
            return self._json(200, {"build": BUILD_ID,
                                    "now": now_local().strftime("%Y-%m-%dT%H:%M"),
                                    "tz": TZ, "slots": SLOTS,
                                    "platforms": poster.ENABLED,
                                    "clips": m["clips"]})
        return self._send(404, "Not found", "text/plain; charset=utf-8")

    def serve_media(self, path):
        m = re.match(r"^/m/([^/]+)/(.+)$", path)
        if not m or not MEDIA_TOKEN or not secrets.compare_digest(m.group(1), MEDIA_TOKEN):
            return self._send(404, "Not found", "text/plain; charset=utf-8")
        rel = urllib.parse.unquote(m.group(2))
        full = os.path.join(MEDIA, *[c for c in rel.split("/")
                                     if c not in ("", ".", "..")])
        if not os.path.isfile(full):
            return self._send(404, "Not found", "text/plain; charset=utf-8")
        size = os.path.getsize(full)
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"

        # Byte ranges are NOT optional. Safari opens every <video> with a range
        # request and shows a dead player if the server answers 200 instead of
        # 206. Instagram's fetcher also ranges. Both break silently without this.
        start, end, code = 0, size - 1, 200
        rng = self.headers.get("Range", "")
        if rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            try:
                if a:
                    start = int(a)
                    end = int(b) if b else size - 1
                elif b:
                    start = max(0, size - int(b))
                if 0 <= start <= end < size:
                    code = 206
                else:
                    start, end = 0, size - 1
            except ValueError:
                start, end = 0, size - 1

        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "private, max-age=3600")
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        remaining = end - start + 1
        with open(full, "rb") as fh:
            fh.seek(start)
            while remaining > 0:
                chunk = fh.read(min(1 << 20, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                remaining -= len(chunk)

    # ------------------------------------------------------------------- POST
    def do_POST(self):
        path = self.path.split("?", 1)[0]

        if path == "/captions":
            # Caption-only update. Editing words should never cost a re-upload of
            # the video - 1.3GB on his uplink to change a line of text is how a
            # good change stops being worth making.
            if not UPLOAD_KEY or not secrets.compare_digest(
                    self.headers.get("X-Upload-Key", ""), UPLOAD_KEY):
                return self._json(404, {"error": "not found"})
            try:
                n = int(self.headers.get("Content-Length", 0))
                incoming = json.loads(self.rfile.read(n))
            except Exception as e:
                return self._json(400, {"error": f"bad body: {e}"})
            hit = 0
            with LOCK:
                man = load()
                for c in man["clips"]:
                    if c["file"] in incoming:
                        c["caption"] = incoming[c["file"]]
                        hit += 1
                save(man)
            return self._json(200, {"updated": hit, "sent": len(incoming)})

        if path == "/replan":
            # Unschedule future clips so plan() can place them again under the
            # CURRENT rules. 11 Sept 2026: the source-mixing rule shipped after
            # a week of clips were already placed, and "nothing is ever moved
            # once placed" meant the fix could not reach them.
            #
            # Only clips that have NOT posted, and only slots still in the
            # future. A clip that has gone out keeps everything - clearing a
            # posted clip's fields is what re-posted ten of brand-2's in
            # September, and this endpoint must never be able to do that.
            if not UPLOAD_KEY or not secrets.compare_digest(
                    self.headers.get("X-Upload-Key", ""), UPLOAD_KEY):
                return self._json(404, {"error": "not found"})
            try:
                n = int(self.headers.get("Content-Length", 0) or 0)
                body = json.loads(self.rfile.read(n)) if n else {}
            except Exception:
                body = {}
            pre = str(body.get("prefix") or "")
            cut = now_local().strftime("%Y-%m-%dT%H:%M")
            freed = []
            with LOCK:
                man = load()
                for c in man["clips"]:
                    sa = c.get("scheduled_at")
                    if (sa and sa > cut and not c.get("posted_at")
                            and not c.get("done") and not c.get("posting")
                            and (not pre or c["file"].startswith(pre))):
                        c["scheduled_at"] = None
                        c.pop("stale", None)
                        freed.append(c["file"])
                save(man)
            return self._json(200, {"unscheduled": len(freed), "files": freed[:40]})

        if path == "/upload":
            return self.receive_upload()

        sub = self._authed(path)
        if sub is None:
            return self._json(404, {"error": "not found"})

        rst = re.match(r"^/reset/(\d+)$", sub)
        if rst:
            with LOCK:
                man = load()
                i = int(rst.group(1))
                if i >= len(man["clips"]):
                    return self._json(404, {"error": "no such clip"})
                c = man["clips"][i]
                for k in ("done", "posted_at", "scheduled_at", "posting"):
                    c[k] = None if k != "done" else False
                c["status"], c["links"] = {}, {}
                plan(man)
                save(man)
            return self._json(200, {"reset": True,
                                    "scheduled_at": c.get("scheduled_at")})

        rty = re.match(r"^/retry/(\d+)$", sub)
        if rty:
            # Re-run ONLY the platforms that have not already succeeded. This is
            # what a half-posted clip needs: AR's first batch went out on
            # YouTube and TikTok while Instagram and Facebook said "not
            # configured", and when those credentials arrive the clip must
            # finish - WITHOUT republishing the two that worked. /reset would
            # wipe the status and double-post them, which is why it is not the
            # tool for this. `status` is kept intact and publish() skips
            # anything already marked posted.
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            with LOCK:
                man = load()
                i = int(rty.group(1))
                if i >= len(man["clips"]):
                    return self._json(404, {"error": "no such clip"})
                c = man["clips"][i]
                want = body.get("platforms") or []
                # A RETRY MUST NOT MAKE A POSTED CLIP LOOK UNPOSTED.
                #
                # 10 Sept 2026. the owner: "the last post on ig didn't went to fb".
                # KT_DEBT/06_THREE-CARDS-AT-ZERO published on 31 Aug, and on
                # 5 Sept I retried its failed Instagram leg. This cleared
                # posted_at - so the planner saw a clip that had never posted,
                # gave it a fresh slot, and on 10 Sept it published AGAIN to
                # Instagram and YouTube. Facebook refused to duplicate it and
                # handed back the 31 Aug reel, which is exactly why Facebook
                # looked frozen while the others moved.
                #
                # Clearing posted_at is only safe when NOTHING has ever been
                # published. Once any platform has succeeded, the clip keeps its
                # posted_at and is re-run through `retry_only` instead, which
                # due_clips honours without the clip ever re-entering the plan.
                ever = any(v == "posted" for v in (c.get("status") or {}).values())
                if ever:
                    c["retry_only"] = want or None
                    c["posting"] = False
                    c["done"] = False
                else:
                    c["posted_at"] = None
                    c["scheduled_at"] = None
                    c["posting"] = False
                    c["done"] = False
                for p in want:
                    (c.get("status") or {}).pop(p, None)
                # 6 SEPT: REMEMBER WHICH PLATFORMS THIS RETRY IS FOR.
                # publish() skips a platform whose status is already "posted",
                # which is why a retry never re-published YouTube. TikTok never
                # says "posted" - it says "in your TikTok inbox", because the
                # last step is a human tapping post - so nothing skipped it and
                # a retry silently uploaded the clip to the inbox a SECOND time.
                # One duplicate draft is a nuisance; backfilling twelve clips
                # onto Instagram and Facebook would have made twelve of them.
                if want:
                    c["retry_only"] = want
                plan(man)
                save(man)
            return self._json(200, {"retry": want or "all not-yet-posted",
                                    "scheduled_at": c.get("scheduled_at")})

        tri = re.match(r"^/trial/([A-Za-z0-9\-_]+)$", sub)
        if tri:
            # Post every rendered hook variant of one clip as an INSTAGRAM
            # TRIAL REEL, in one call. Daniel's routine: seven variants of the
            # same video, only the hook text different, all on the same day,
            # shown to non-followers. The winner is graduated by hand in the
            # app - which hook wins is the whole point and it is the owner's to see.
            slug = tri.group(1)
            vdir = os.path.join(MEDIA, "_VARIANTS", slug)
            if not os.path.isdir(vdir):
                return self._json(404, {"error": f"no variants for {slug}",
                                        "hint": "render them with kt_variants.py "
                                                "--apply, then upload"})
            vids = sorted(f for f in os.listdir(vdir) if f.endswith(".mp4"))
            with LOCK:
                man = load()
            src = next((c for c in man["clips"] if slug in c["file"]), None)
            caption = (src or {}).get("caption", "")
            out = []
            for f in vids:
                rel = f"_VARIANTS/{slug}/{f}"
                res = poster.instagram(os.path.join(vdir, f), caption,
                                       media_url(rel), src, trial=True)
                ok = isinstance(res, tuple)
                out.append({"variant": f,
                            "status": res[0] if ok else res,
                            "link": res[1] if ok else None})
                sys.stderr.write(f"trial {rel}: {out[-1]['status']}\n")
                # STOP ON THE FIRST ONE THAT IS NOT A TRIAL. If trial_params
                # did not take, every remaining variant would publish to his
                # followers - seven near-identical reels in one day. Losing the
                # experiment costs a re-render; spamming the account does not
                # get undone. One is recoverable, seven is not.
                st = str(out[-1]["status"])
                if st.startswith("PUBLISHED BUT NOT A TRIAL") or not ok:
                    return self._json(200, {
                        "slug": slug, "posted": len(out), "results": out,
                        "STOPPED": "a variant did not publish as a trial - the "
                                   "rest were NOT posted. Fix before retrying."})
            return self._json(200, {"slug": slug, "posted": len(out),
                                    "results": out})

        if sub == "/audit":
            with LOCK:
                man = load()
                bad = audit(man)
                plan(man)
                save(man)
            return self._json(200, {"requeued": [man["clips"][i]["file"]
                                                 for i in bad]})

        if sub == "/plan":
            with LOCK:
                man = load()
                n = plan(man)
                save(man)
            return self._json(200, {"scheduled": n})

        tt = re.match(r"^/tiktok/(\d+)$", sub)
        if tt:
            # TikTok is posted by hand until the app audit lands. This is the tick
            # box for it - kept separate from `done` so the automatic platforms
            # and the manual one never overwrite each other's state.
            #
            # 6 SEPT: THIS USED TO ALWAYS TOGGLE, AND THAT WAS WRONG FOR COPY.
            # brand-2 owner: "even though i am copying tiktok captions, they are not
            # getting deleted... there are captions that I have already used
            # sitting there." The marking worked; the semantics did not. COPY
            # CAPTION fired a toggle, so copying a caption a SECOND time - to
            # re-paste it, or a stray double tap - flipped it back to unpasted
            # and the card returned as if it had never been done. A button
            # labelled COPY must only ever mean done.
            #
            # So an explicit {"done": true|false} sets the value outright, and
            # only a request with no body still toggles - which is what the
            # board's own Mark control wants.
            length = int(self.headers.get("Content-Length", "0"))
            body = {}
            if length:
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                except ValueError:
                    body = {}
            with LOCK:
                man = load()
                i = int(tt.group(1))
                if i >= len(man["clips"]):
                    return self._json(404, {"error": "no such clip"})
                c = man["clips"][i]
                c["tiktok_done"] = (bool(body["done"]) if "done" in body
                                    else not c.get("tiktok_done"))
                save(man)
                return self._json(200, {"tiktok_done": c["tiktok_done"]})

        sch = re.match(r"^/schedule/(\d+)$", sub)
        if sch:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            with LOCK:
                man = load()
                i = int(sch.group(1))
                if i >= len(man["clips"]):
                    return self._json(404, {"error": "no such clip"})
                when = (body.get("at") or "").strip()
                man["clips"][i]["scheduled_at"] = when or None
                save(man)
            return self._json(200, {"scheduled_at": when or None})

        m = re.match(r"^/(done|post|retry)/(\d+)$", sub)
        if not m:
            return self._json(404, {"error": "not found"})
        action, idx = m.group(1), int(m.group(2))
        only = None
        with LOCK:
            man = load()
            if idx >= len(man["clips"]):
                return self._json(404, {"error": "no such clip"})
            clip = man["clips"][idx]
            if action == "done":
                clip["done"] = not clip.get("done")
                save(man)
                return self._json(200, {"done": clip["done"]})
            if action == "retry":
                # Only the legs that did not land. A retry must never risk a
                # second copy of a post that already worked.
                only = {p for p in poster.ENABLED
                        if clip.get("status", {}).get(p) != "posted"}
                if not only:
                    return self._json(200, clip.get("status", {}))
            clip = dict(clip)
        # publishing happens OUTSIDE the lock - it takes minutes, and holding the
        # lock would freeze the page for every other request.
        result, links = poster.publish(clip, os.path.join(MEDIA, clip["file"]),
                                       media_url(clip["file"]), only=only)
        with LOCK:
            man = load()
            record(man, idx, result, links)
            save(man)
        return self._json(200, result)

    def receive_upload(self):
        """Streamed upload from the Mac. Never buffers a 70MB clip in memory."""
        def reject(code, msg):
            # DRAIN THE BODY BEFORE ANSWERING. Replying 403 while the client is
            # still streaming 70MB makes the connection die and the uploader sees
            # "Broken pipe" - which says nothing about the actual cause. A wrong
            # upload key looked like a network fault until this was fixed.
            left = int(self.headers.get("Content-Length", "0"))
            while left > 0:
                blob = self.rfile.read(min(1 << 20, left))
                if not blob:
                    break
                left -= len(blob)
            return self._json(code, {"error": msg})

        if not UPLOAD_KEY or not secrets.compare_digest(
                self.headers.get("X-Upload-Key", ""), UPLOAD_KEY):
            return reject(403, "bad upload key")
        rel = self.headers.get("X-Rel-Path", "")
        if not rel or ".." in rel:
            return reject(400, "bad X-Rel-Path")
        caption = urllib.parse.unquote(self.headers.get("X-Caption", ""))
        length = int(self.headers.get("Content-Length", "0"))
        dest = os.path.join(MEDIA, *[c for c in rel.split("/") if c not in ("", ".", "..")])
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        sha = hashlib.sha256()
        remaining = length
        with open(dest + ".part", "wb") as fh:
            while remaining > 0:
                chunk = self.rfile.read(min(1 << 20, remaining))
                if not chunk:
                    break
                fh.write(chunk)
                sha.update(chunk)
                remaining -= len(chunk)
        if remaining:
            os.remove(dest + ".part")
            return self._json(400, {"error": f"truncated, {remaining} bytes short"})
        os.replace(dest + ".part", dest)

        # Only VIDEO goes on the board. The upload endpoint is also how assets
        # get hosted - the TikTok app icon, for one - and without this every
        # asset appeared as a clip to post. Files still land on disk and are
        # served; they just are not work items.
        # A "__yt59" file is the SAME clip cut to 59 seconds for YouTube, which
        # blocks Content-ID material in Shorts over 60s. It has to reach the
        # server as media so the youtube adapter can upload it, but it is not a
        # second thing to post - without this it would appear on the board and
        # get its own slot, double-posting every clip everywhere.
        if (not rel.lower().endswith((".mp4", ".mov", ".m4v"))
                or "__yt" in os.path.basename(rel)
                # HOOK VARIANTS ARE NOT SEVEN POSTS. They are one
                # experiment with seven arms, posted as trial reels via
                # /trial/<slug>. On the board they would each take a slot
                # and publish the same footage seven times to followers.
                or rel.startswith("_VARIANTS/")):
            return self._json(200, {"ok": True, "file": rel, "bytes": length,
                                    "sha256": sha.hexdigest()[:16],
                                    "note": "stored as an asset, not a clip"})

        with LOCK:
            man = load()
            existing = next((c for c in man["clips"] if c["file"] == rel), None)
            if existing:
                existing["caption"] = caption or existing.get("caption", "")
                existing["bytes"] = length
            else:
                man["clips"].append({
                    "file": rel, "caption": caption, "bytes": length,
                    "done": False, "status": {}})
            man["clips"].sort(key=lambda c: c["file"])
            save(man)
        return self._json(200, {"ok": True, "file": rel, "bytes": length,
                                "sha256": sha.hexdigest()[:16]})


if __name__ == "__main__":
    missing = [k for k, v in (("KT_TOKEN", TOKEN), ("KT_MEDIA_TOKEN", MEDIA_TOKEN),
                              ("KT_UPLOAD_KEY", UPLOAD_KEY)) if not v]
    if missing:
        sys.stderr.write("FATAL: missing env " + ", ".join(missing) + "\n")
        sys.exit(1)
    threading.Thread(target=scheduler_loop, daemon=True).start()
    sys.stderr.write(f"kt-cloud up on :{PORT}, data={DATA}, tz={TZ}\n")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
