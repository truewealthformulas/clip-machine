#!/usr/bin/env python3
"""The calendar feed and the captions board, as files instead of a server.

The last two things keeping a paid service alive. Neither needs a server: a
calendar feed is a text file a calendar app fetches on a timer, and the board
is a page the owner opens to copy a caption into TikTok. Both are written here on
every scheduling run and committed, then served by GitHub Pages for nothing.

The calendar is the one that matters. the owner subscribed to it in Google Calendar
on the wealth broadcast account, so its URL has to keep working - the new one
replaces the old subscription once Railway is gone.
"""
import html
import json
import os
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state", "manifest.json")
DOCS = os.path.join(HERE, "docs")
TZ = os.environ.get("KT_TZ", "America/New_York")


def clips():
    try:
        return json.load(open(STATE)).get("clips", [])
    except (OSError, ValueError):
        return []


def _utc(txt, plus=0):
    try:
        t = datetime.strptime(txt[:16], "%Y-%m-%dT%H:%M") + timedelta(minutes=plus)
    except (ValueError, TypeError):
        return None
    try:
        from zoneinfo import ZoneInfo
        t = t.replace(tzinfo=ZoneInfo(TZ)).astimezone(ZoneInfo("UTC"))
    except Exception:
        pass
    return t.strftime("%Y%m%dT%H%M%SZ")


def esc(t):
    return (t.replace("\\", "\\\\").replace(";", r"\;")
             .replace(",", r"\,").replace("\n", r"\n"))


def calendar_ics(cs):
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//kt-machine//EN",
           "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
           "X-WR-CALNAME:Posts - the owner + Brand 2",
           "X-WR-TIMEZONE:" + TZ,
           "REFRESH-INTERVAL;VALUE=DURATION:PT30M", "X-PUBLISHED-TTL:PT30M"]
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    for c in cs:
        when = c.get("posted_at") or c.get("scheduled_at")
        start = _utc(when)
        if not start:
            continue
        f = c["file"]
        who = "BRAND 2" if f.startswith("AR_") else "OWNER"
        live = bool(c.get("posted_at"))
        cap = (c.get("caption") or "").strip().splitlines()
        title = cap[0] if cap else f.split("/")[-1]
        body = [f"{'POSTED' if live else 'scheduled'} - {f}"]
        for k, v in sorted((c.get("links") or {}).items()):
            body.append(f"{k}: {v}")
        out += ["BEGIN:VEVENT",
                "UID:" + f.replace("/", "-").replace(" ", "_") + "@kt-machine",
                "DTSTAMP:" + now, "DTSTART:" + start,
                "DTEND:" + (_utc(when, 15) or start),
                "SUMMARY:" + esc(f"{'' if live else '[ ] '}{who} - {title}"),
                "DESCRIPTION:" + esc("\n".join(body)),
                "STATUS:" + ("CONFIRMED" if live else "TENTATIVE"),
                "END:VEVENT"]
    out += queue_alarm_events(cs, now)
    out.append("END:VCALENDAR")
    return "\r\n".join(out) + "\r\n"


def queue_alarm_events(cs, now):
    """THE QUEUE MUST NEVER RUN DRY UNNOTICED AGAIN.

    17 Sept 2026: the owner's account had ZERO clips left to post and nobody knew
    until he asked why only one clip went out. His phone already shows this
    calendar, so the warning lives here: an all-day event on the day the clips
    run out, and - once that is 3 days away or less - a second one TODAY that
    says how many days are left. Stable UIDs, so they move instead of piling up.
    the owner's account only; Brand 2's queue is brand-2's.
    """
    from zoneinfo import ZoneInfo
    left = [c for c in cs if not c.get("done") and not c.get("posted_at")
            and not c["file"].startswith("AR_")]
    today = datetime.now(ZoneInfo(TZ)).date()
    last = max((c["scheduled_at"][:10] for c in left if c.get("scheduled_at")),
               default=None)
    runs_out = (datetime.strptime(last, "%Y-%m-%d").date() + timedelta(days=1)
                if last else today)
    days = (runs_out - today).days
    ev = []

    def allday(uid, day, text):
        return ["BEGIN:VEVENT", f"UID:{uid}@kt-machine", "DTSTAMP:" + now,
                "DTSTART;VALUE=DATE:" + day.strftime("%Y%m%d"),
                "DTEND;VALUE=DATE:" + (day + timedelta(days=1)).strftime("%Y%m%d"),
                "SUMMARY:" + esc(text), "TRANSP:TRANSPARENT", "END:VEVENT"]
    ev += allday("queue-runout-owner", runs_out,
                 f"!! OWNER - NO CLIPS LEFT TO POST ({len(left)} queued before this)")
    if days <= 3:
        ev += allday("queue-warning-owner", today,
                     f"!! OWNER - clips run out in {days} day(s), on {runs_out:%a %d %b} - make more")
    return ev


def thumbs():
    """Cover images, made on the Mac by make_thumbs.py. Absent is fine."""
    try:
        return json.load(open(os.path.join(DOCS, "thumbs.json")))
    except (OSError, ValueError):
        return {}


def board(cs):
    """Ready to post at the top, everything else behind a button.

    13 Sept 2026, the owner: "the one we want to post its not at the fron, its far
    and hard to find." He is right - the board listed everything newest-first,
    so the clip actually sitting in the TikTok inbox waiting to be posted was
    buried among fifty already-published ones.

    READY means: it has gone out on the other platforms and is waiting in the
    TikTok inbox for a human to tap post. That is the only reason this page
    exists, so that is what opens first.

    Pressing Copy marks the card done and hides it, so the list empties as he
    works through it instead of him re-reading the same captions.
    """
    # WHAT "WAITING FOR YOU" ACTUALLY MEANS.
    #
    # 14 Sept 2026, the owner: "the only 1 description available not a single time
    # was the clip i was intended to post... i got only the first tiktok message
    # to post, just one, and i went to the dashboard and it wasnt that one so i
    # had to look it up in ALL."
    #
    # This read `"inbox" in status`, and TikTok reports two different things for
    # the same outcome. When the upload finishes inside our 40-second poll the
    # status is "in your TikTok inbox"; when it does not, we stop polling and
    # write "uploaded but TikTok still processing". The clip lands in his inbox
    # either way - TikTok just took longer than we waited.
    #
    # All THREE of his own clips today were in the second group, so the one the
    # app notified him about was the one guaranteed to be missing from this
    # page. Waiting on our own poll timeout to decide what he can see was never
    # the right test: what matters is that TikTok accepted it and he has not
    # ticked it off.
    OK = ("inbox", "uploaded", "processing")

    def ready(c):
        s = str((c.get("status") or {}).get("tiktok", "")).lower()
        return bool(c.get("posted_at")) and any(k in s for k in OK) \
            and not c.get("tiktok_done")

    todo = [c for c in cs if ready(c)]
    rest = [c for c in cs if not ready(c) and (c.get("posted_at") or c.get("scheduled_at"))]
    todo.sort(key=lambda c: c.get("posted_at") or "", reverse=True)
    rest.sort(key=lambda c: (c.get("posted_at") or c.get("scheduled_at") or ""),
              reverse=True)

    css = ("body{font:15px/1.5 -apple-system,system-ui,sans-serif;margin:0;"
           "padding:16px;background:#0d0f13;color:#e8e8ea}"
           "h1{font-size:18px;margin:0 0 4px}"
           "h2{font-size:13px;letter-spacing:.09em;color:#8b93a5;margin:22px 0 10px}"
           ".c{border:1px solid #262a33;border-radius:12px;padding:14px;"
           "margin:0 0 14px;background:#141821}"
           ".c.ready{border-color:#f5c542}"
           ".w{font-size:11px;letter-spacing:.08em;color:#8b93a5}"
           ".fn{font-size:12px;color:#8b93a5;margin:2px 0 0;word-break:break-all}"
           ".hd{display:flex;gap:11px;align-items:flex-start;margin:0 0 10px}"
           ".th{width:54px;min-width:54px;aspect-ratio:9/16;object-fit:cover;"
           "border-radius:7px;background:#1d2230;display:block}"
           ".meta{min-width:0}"
           "pre{white-space:pre-wrap;margin:0;font:14px/1.55 inherit}"
           "button{margin-top:10px;padding:9px 16px;border-radius:8px;border:0;"
           "background:#f5c542;color:#111;font-weight:700}"
           "button.pick{background:#242a36;color:#e8e8ea;margin:2px 6px 12px 0;"
           "font-weight:600}button.pick.on{background:#f5c542;color:#111}"
           "#more{display:none}")

    tb = thumbs()
    # A picture on every one of a hundred cards is a 300KB page on a phone for
    # no gain - the ones behind "See all" are already published. Pictures go on
    # the cards he acts on, plus the newest handful for orientation.
    recent = {c["file"] for c in rest[:24]}

    def card(c, is_ready):
        f = c["file"]
        who = "BRAND 2" if f.startswith("AR_") else "OWNER"
        key = "AR" if f.startswith("AR_") else "OWNER"
        when = c.get("posted_at") or c.get("scheduled_at")
        tag = "READY TO POST" if is_ready else (
            "posted" if c.get("posted_at") else "scheduled")
        cid = "t" + str(abs(hash(f)))
        # The picture is the point: he is holding a phone with a clip in the
        # TikTok inbox and needs to know THIS caption belongs to THAT video.
        img = tb.get(f) if is_ready or f in recent else None
        pic = f"<img class=th src='{img}' alt=''>" if img else "<div class=th></div>"
        return (f"<div class='c{' ready' if is_ready else ''}' data-who='{key}'>"
                f"<div class=hd>{pic}<div class=meta>"
                f"<div class=w>{who} &middot; {tag} {when}</div>"
                f"<div class=fn>{html.escape(f)}</div></div></div>"
                f"<pre id='{cid}'>{html.escape(c.get('caption') or '')}</pre>"
                f"<button onclick=\"cp('{cid}',this)\">Copy</button></div>")

    p = ["<meta charset=utf-8><meta name=viewport "
         "content='width=device-width,initial-scale=1'><title>Captions</title>",
         f"<style>{css}</style>", "<h1>Captions</h1>",
         "<div><button class='pick on' onclick=\"pick('all',this)\">All</button>"
         "<button class='pick' onclick=\"pick('OWNER',this)\">the owner</button>"
         "<button class='pick' onclick=\"pick('AR',this)\">Brand 2</button></div>",
         f"<h2>READY TO POST ON TIKTOK &middot; {len(todo)}</h2>"]
    p += [card(c, True) for c in todo] or ["<div class=c>Nothing waiting.</div>"]
    p += [f"<button class='pick' onclick=\"document.getElementById('more')"
          f".style.display='block';this.remove()\">See all {len(rest)}</button>",
          "<div id=more>"]
    p += [card(c, False) for c in rest[:80]]
    p += ["</div>",
          "<script>"
          "function pick(w,b){document.querySelectorAll('button.pick')"
          ".forEach(x=>x.classList.remove('on'));b.classList.add('on');"
          "document.querySelectorAll('.c').forEach(e=>{"
          "e.hidden=w!=='all'&&e.dataset.who!==w;});}"
          # Copy then hide. The list should empty as he works through it.
          "function cp(id,b){navigator.clipboard.writeText("
          "document.getElementById(id).innerText);"
          "const c=b.closest('.c');c.style.transition='opacity .25s';"
          "c.style.opacity=0;setTimeout(()=>c.remove(),260);"
          "try{const d=JSON.parse(localStorage.done||'[]');d.push(id);"
          "localStorage.done=JSON.stringify(d);}catch(e){}}"
          "try{JSON.parse(localStorage.done||'[]').forEach(id=>{"
          "const el=document.getElementById(id);if(el)el.closest('.c').remove();});}"
          "catch(e){}"
          "</script>"]
    return "\n".join(p)


def main():
    os.makedirs(DOCS, exist_ok=True)
    cs = clips()
    open(os.path.join(DOCS, "calendar.ics"), "w").write(calendar_ics(cs))
    open(os.path.join(DOCS, "index.html"), "w").write(board(cs))
    print(f"pages built from {len(cs)} clips")


if __name__ == "__main__":
    main()
