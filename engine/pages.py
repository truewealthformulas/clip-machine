#!/usr/bin/env python3
"""HTML for the board, plus the Terms and Privacy pages the app forms require.

The Terms and Privacy text is NOT boilerplate padding. TikTok's app form and
Meta's both refuse to save without a reachable URL for each, and both are read by
a human reviewer if an audit is ever applied for. They describe what this system
actually does - posts the owner's own clips to the owner's own accounts, stores nothing
about anyone else - because that is both true and exactly what a reviewer needs.
"""
import html
import os
import re

CSS = """*{box-sizing:border-box}
body{font:16px/1.55 -apple-system,system-ui,sans-serif;margin:0;padding:14px;
background:#000;color:#eee;-webkit-text-size-adjust:100%}
h1{font-size:19px;margin:0 0 3px}
.sub{color:#7a7a7e;font-size:13px;margin:0 0 16px}
.c{background:#151517;border:1px solid #252528;border-radius:16px;padding:14px;
margin:0 0 13px}
.c.done{opacity:.4}
.ord{display:inline-block;background:#0a84ff;color:#fff;font-weight:700;
border-radius:8px;padding:1px 9px;font-size:14px;margin-right:8px}
.c.done .ord{background:#30d158;color:#000}
.n{font-weight:700;font-size:16px}
.m{color:#7a7a7e;font-size:12px;margin:4px 0 11px}
video{width:100%;border-radius:12px;background:#000;display:block;
margin-bottom:11px;max-height:60vh}
.row{display:flex;gap:8px;flex-wrap:wrap}
button{flex:1 1 30%;background:#0a84ff;color:#fff;border:0;padding:14px 6px;
border-radius:11px;font-weight:700;font-size:15px;font-family:inherit}
button.alt{background:#242427;color:#8ecdf8}
button.go{background:#30d158;color:#000}
button:disabled{background:#1c1c1f;color:#666}
textarea{width:100%;background:#000;color:#ddd;border:1px solid #2a2a2c;
border-radius:10px;padding:10px;font:13px/1.5 inherit;margin-top:10px}
.r{font:12px/1.7 ui-monospace,monospace;margin-top:9px}
.ok{color:#30d158}.no{color:#ff6961}.wait{color:#ffd60a}
.doc{max-width:680px;margin:0 auto;padding:24px 16px}
.doc h2{font-size:16px;margin:22px 0 6px}
.doc p,.doc li{color:#c9c9cd;font-size:14px}
a{color:#8ecdf8}
.nav{display:flex;gap:8px;margin:0 0 14px}
.nav a{flex:1;text-align:center;padding:11px;border-radius:11px;background:#151517;
border:1px solid #252528;text-decoration:none;color:#8ecdf8;font-weight:600;font-size:14px}
.nav a.on{background:#0a84ff;color:#fff;border-color:#0a84ff}
.day{margin:0 0 18px}
.dh{font-size:13px;font-weight:700;color:#8ecdf8;margin:0 0 8px;
padding-bottom:6px;border-bottom:1px solid #232326;display:flex;
justify-content:space-between}
.dh .cnt{color:#7a7a7e;font-weight:400}
.slot{display:flex;gap:11px;align-items:flex-start;background:#151517;
border:1px solid #252528;border-radius:14px;padding:10px;margin:0 0 9px}
.slot.past{opacity:.45}
.slot video{width:74px;min-width:74px;height:112px;object-fit:cover;
border-radius:9px;margin:0}
.st{font:12px/1.5 ui-monospace,monospace;color:#7a7a7e}
.slot .n{font-size:14px}
.when{color:#ffd60a;font-weight:700;font-size:13px}
.when.done{color:#30d158}
input[type=datetime-local]{background:#000;color:#eee;border:1px solid #2a2a2c;
border-radius:9px;padding:9px;font:13px inherit;width:100%;margin-top:9px}
.unsched{color:#7a7a7e;font-size:13px;margin:14px 0 8px;font-weight:700}
.ord.now{background:#ffd60a;color:#000}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 11px}
.chip{font:11px/1.4 ui-monospace,monospace;padding:4px 8px;border-radius:7px;
background:#242427;color:#8a8a8f;text-decoration:none;display:inline-block}
.chip.ok{background:#0f3d21;color:#43e07a}
.chip.no{background:#4a1520;color:#ff8a8a}
.chip.wait{background:#4a3a05;color:#ffd60a}
.chip.idle{background:#242427;color:#8a8a8f}
.btn{flex:1 1 30%;background:#0a84ff;color:#fff;border:0;padding:14px 6px;
border-radius:11px;font-weight:700;font-size:15px;text-align:center;
text-decoration:none;display:block}
.btn.go{background:#30d158;color:#000}
.tt{background:#0f1a12;border:1px solid #1e3b26;border-radius:13px;
padding:11px;margin:11px 0 0}
.tth{font:12px/1.4 ui-monospace,monospace;color:#43e07a;font-weight:700;
letter-spacing:.06em;text-transform:uppercase;margin:0 0 9px}
.note{color:#7a8a7e;font-size:12px;line-height:1.5;margin:10px 0 0}
.note b{color:#b9d4c2}
.cap{background:#151517;border:1px solid #252528;border-radius:18px;
padding:14px;margin:0 0 14px;transition:opacity .4s}
.cap.gone{opacity:.25}
.caphead{display:flex;gap:12px;align-items:center;margin:0 0 12px}
.day{display:flex;justify-content:space-between;align-items:baseline;margin:26px 0 10px;padding-bottom:6px;border-bottom:1px solid #2a2a2a;font-size:19px}
.day span{font-size:13px;opacity:.5;font-weight:400}
.thumb{width:92px;min-width:92px;height:138px;object-fit:cover;border-radius:10px;
background:#000}
.capname{font-weight:700;font-size:17px;line-height:1.3}
button.copy{width:100%;background:#30d158;color:#000;border:0;padding:22px 10px;
border-radius:14px;font-weight:800;font-size:18px;letter-spacing:.02em;
font-family:inherit}
button.copy.ok{background:#0f3d21;color:#43e07a}
.cap textarea{display:none;margin-top:10px}
.when2{color:#ffd60a;font:12px/1.5 ui-monospace,monospace;margin-top:3px}
.warn{background:#3a2e05;border:1px solid #5c4a08;border-radius:14px;
padding:13px;margin:0 0 15px;color:#ffd98a;font-size:14px;line-height:1.55}
.warn b{color:#ffd60a}
.empty{background:#151517;border:1px solid #252528;border-radius:16px;
padding:22px;color:#8a8a8f;font-size:15px;line-height:1.6;text-align:center}
"""

LANDING = f"""<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<title>KT Cloud</title><style>{CSS}</style><div class=doc>
<h1>KT Cloud</h1>
<p class=sub>Private publishing tool. Nothing here is public.</p>
<p><a href="/terms">Terms of Service</a> &middot; <a href="/privacy">Privacy Policy</a></p>
</div>"""

_DOC = """<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<title>{t}</title><style>{css}</style><div class=doc><h1>{t}</h1>
<p class=sub>Last updated 22 August 2026</p>{body}
<p><a href="/">Home</a></p></div>"""

TERMS = _DOC.format(t="Terms of Service", css=CSS, body="""
<h2>1. What this service is</h2>
<p>KT Cloud is a private, single-operator tool used by its owner to publish short
video clips to social media accounts that the owner personally controls. It is not
offered to the public, has no sign-up, and has no other users.</p>
<h2>2. Who may use it</h2>
<p>Only the owner. Access requires a private token. There are no accounts to
create and no service is sold to anyone.</p>
<h2>3. Content</h2>
<p>The clips published through this tool are edited excerpts of publicly available
interviews and talks, presented with commentary as an unofficial fan page. The
operator is solely responsible for what is published and for holding any rights
required to publish it.</p>
<h2>4. Third-party platforms</h2>
<p>The tool posts to TikTok, Instagram, YouTube and Facebook using each platform's
official API, under credentials the owner has granted. Use of those platforms is
governed by their own terms. Access can be revoked by the owner at any time from
the relevant platform's settings.</p>
<h2>5. No warranty</h2>
<p>The tool is provided as-is for personal use, with no warranty of any kind.</p>
<h2>6. Contact</h2>
<p>you@example.com</p>""")

PRIVACY = _DOC.format(t="Privacy Policy", css=CSS, body="""
<h2>1. Summary</h2>
<p>This tool collects no personal data from anybody. It has one user - its owner -
and it stores only the owner's own video files and the access tokens the owner
issued to their own social accounts.</p>
<h2>2. What is stored</h2>
<ul>
<li>Video files the owner uploads, and the captions the owner wrote.</li>
<li>OAuth tokens for the owner's own TikTok, Instagram, YouTube and Facebook
accounts, held as environment variables on the server and never displayed.</li>
<li>A record of which clips have been posted.</li>
</ul>
<h2>3. What is not stored</h2>
<p>No data about viewers, followers or any other person. No analytics, no
tracking, no cookies, no advertising identifiers. Nothing is shared with, sold to,
or transmitted to any third party other than the social platforms the owner is
publishing to.</p>
<h2>4. Retention and deletion</h2>
<p>Files are kept until the owner deletes them. Revoking the tool's access from a
platform's own settings immediately and permanently ends its ability to post.</p>
<h2>5. Security</h2>
<p>All access is over HTTPS. Control pages require a private token; media files
are served from unguessable paths. Credentials are stored as server environment
variables, never in the codebase.</p>
<h2>6. Contact</h2>
<p>you@example.com</p>""")


def _nav(page):
    """Two tabs. the owner, 26 Aug: "the dashboard looks little confusing and
    manythings". It was - the board still carried a POST button and a date
    picker per clip, which existed when posting was manual and now do nothing he
    needs. Posting is automatic on all four platforms; the ONLY thing he does by
    hand is paste a TikTok caption. So the home page is Captions, Calendar is
    there to see what is coming, and everything else moved out of the way."""
    return (f'<div class=nav>'
            f'<a href="./" class="{"on" if page == "cap" else ""}">Captions</a>'
            f'<a href="calendar" class="{"on" if page == "cal" else ""}">'
            f'What is coming</a></div>')


def clip_title(fn):
    """01_WHO-IS-THE-FOOL_30s.mp4 -> Who is the fool"""
    name = fn.split("/")[-1].rsplit(".", 1)[0]
    name = re.sub(r"^\d+_", "", name)
    name = re.sub(r"_\d+s$", "", name)
    return name.replace("-", " ").replace("_", " ").capitalize()


def _chip(platform, value, link=""):
    """One platform's outcome, in three words or fewer.

    A wall of API text on a phone is unreadable, and the only question he ever
    has is: did it go out. The full string stays available underneath.
    """
    if value == "posted":
        txt, cls = "live", "ok"
        if link:
            return f'<a class="chip ok" href="{html.escape(link)}">{platform} live</a>'
    elif "inbox" in (value or ""):
        txt, cls = "in inbox", "wait"
    elif not value:
        txt, cls = "waiting", "idle"
    else:
        txt, cls = "FAILED", "no"
    return f'<span class="chip {cls}">{platform} {txt}</span>'


def _due(c, now):
    """When this clip was meant to go out, and how late it is now."""
    from datetime import datetime
    when = (c.get("scheduled_at") or c.get("posted_at") or "")[:16]
    if not when:
        return "ready now"
    try:
        t = datetime.strptime(when, "%Y-%m-%dT%H:%M")
    except ValueError:
        return "ready now"
    mins = (now - t).total_seconds() / 60
    slot = t.strftime("%H:%M")
    if mins < 45:
        return f"slot {slot} &middot; post it now"
    if mins < 24 * 60:
        h = int(mins // 60)
        return f"slot {slot} &middot; {h}h ago"
    return f"slot {slot} &middot; {int(mins // 1440)}d ago"



def _hookline(c):
    """What is actually BURNED on the clip he is looking at in TikTok.

    30 Aug, the owner: "the names of the clips and the captions dosnt match so i
    dont know wich one is woch one and its confussing." He was matching a
    filename slug against a caption that opens with the same CTA on every clip -
    two identities, neither of which is on screen in his drafts.

    The hook is. It is the biggest thing on the video for the first three
    seconds, so it is the only label that can be matched by eye. The caption's
    first real line is that hook, or close enough - the CTA and hashtags are
    skipped to reach it.
    """
    for line in (c.get("caption") or "").split("\n"):
        line = line.strip()
        if (not line or line.startswith("#")
                or line.lower().startswith("comment ")):
            continue
        return line[:80]
    return clip_title(c["file"])


# Folders that post to the DEFAULT account even though their prefix is not KT.
# MINDSET_SHIFT is the owner's - it has no MINDSET_* credentials, so poster._cfg
# falls back to the unprefixed ones and it publishes to his Instagram.
FALLBACK_FOLDERS = {p.strip().upper() for p in os.environ.get(
    "KT_FALLBACK_BRANDS", "KT,MINDSET").split(",") if p.strip()}


# WHETHER A CLIP IS SITTING IN TIKTOK, waiting to be posted by hand.
#
# 10 Sept 2026. the owner: "the descriptions are not there for the tiktok videos."
# Two of his clips had reached TikTok and were invisible on this page, because
# it decided by searching the status SENTENCE for the word "inbox" - and the
# 9 Sept TikTok fix reworded that status to "uploaded but TikTok still
# processing". The clip was in his drafts; the page said nothing was waiting.
#
# This is the second bug of exactly this shape in three days (the other was
# filtering by folder name instead of account). Matching on prose that another
# change is free to reword is not a filter, it is a coincidence. Listed
# markers, and anything that reached TikTok counts.
TIKTOK_LANDED = ("inbox", "processing", "uploaded", "draft")


def in_tiktok(c):
    """True when this clip is in TikTok's drafts and still needs posting."""
    st = str((c.get("status") or {}).get("tiktok", "")).lower()
    if not st:
        return False
    if st.startswith(("not configured", "refused", "error")) or "failed" in st:
        return False
    return any(m in st for m in TIKTOK_LANDED)


def cap_prefix(c):
    """WHOSE PAGE a clip belongs on - by ACCOUNT, not by folder name.

    8 Sept 2026. the owner, needing to post right then: "i cant nott find the
    captions for the last clip to post in tiktok". The clip was
    MINDSET_SHIFT/01_SOUND-GOOD-ADVICE, posted to HIS Instagram 40 minutes
    earlier, sitting in HIS TikTok drafts - and invisible on his captions page.
    Its folder prefix is MINDSET; the page defaults to KT; so it was filtered
    out of the only screen he uses to post.
    It had been invisible since the day MINDSET_SHIFT existed.

    This is the same mistake as the slot double-booking on 3 Sept: a folder name
    is not an account. MINDSET_SHIFT has no credentials of its own, falls back to
    the default ones, and therefore belongs on the default page.
    """
    prefix = (c.get("file") or "").split("/")[0].split("_")[0].upper()
    return "KT" if prefix in FALLBACK_FOLDERS else prefix


def captions(clips, token, media_url, now, brand="", show_done=False):
    """The only page he needs on his phone, and it does exactly one thing.

    TikTok's inbox API accepts NO caption field - checked against their own API
    reference, the init endpoint takes source_info and nothing else. So the clip
    arrives in his drafts bare and the words have to come from somewhere else.
    That somewhere is this page.

    His words, 26 Aug: "we need a better easy straight super clear and fast way
    for me to get the captions in one go, in one copy paste right there in my
    phone." So: one screen, one thumbnail to match against the draft he is
    looking at, one enormous button. Copying marks it done and the card greys,
    because copying the caption IS the moment he posts it - making him tick a
    second box would just be a box he forgets to tick.

    Sorted OLDEST FIRST, because TikTok stacks drafts in arrival order and he
    works down the list the same way.
    """
    # TWO PEOPLE, ONE PAGE. 31 Aug 2026, brand-2 owner: "when brand2 goes to copy her
    # captions its no longer there because owner has already used them."
    # Exactly right, and it is this page's own design doing it. COPY marks the
    # clip pasted for WHOEVER taps it, the card then greys and drops off the
    # list, and nothing on the card ever said whose brand it belonged to. So
    # the owner working down the list in draft order was silently retiring her
    # captions, and by the time she looked they were gone with no way to tell
    # what had happened.
    #
    # ?b=AR shows one brand. No parameter shows everything, so the owner's saved
    # link keeps behaving exactly as it did. Every card now also carries its
    # brand, because the filter only helps the person who knows to use it and
    # the label helps whoever is holding the phone.
    # 1 Sept: "in the dashboard there is captions that i think are brand-2 owners
    # captions for her clips, it should instead show mine". The filter existed
    # but defaulted to EVERYTHING, so his saved link kept showing both people's
    # work mixed together. A shared default serves nobody: the page belongs to
    # whoever opened it. His link now shows his, hers shows hers, and All is one
    # tap away for anyone who wants the whole board.
    want = (brand or "").strip().upper().rstrip("_")
    if want == "*":
        want = ""                       # the All tab, asked for explicitly
    elif not want:
        want = "KT"                     # a bare link is the owner's own board
    pool = [(i, c) for i, c in enumerate(clips)
            if not want or cap_prefix(c) == want]
    rows = [(i, c) for i, c in pool
            if c.get("posted_at") and not c.get("tiktok_done") and in_tiktok(c)]
    # NEWEST FIRST, 5 Sept 2026. the owner: "i have to go all the way down of so
    # many videos to finde the one im posting, because im posting at my own
    # rythm and trying to keep up with you but ofcourse i got delayed."
    #
    # It was oldest-first to match the order TikTok stacks drafts. That was
    # right when he cleared the list daily and wrong the moment he fell behind:
    # it buries the clip that just went out under a week of stale ones. A clip
    # posted three weeks after its slot is not worth posting at all, so the
    # freshest is always the one to do next and belongs at the top.
    rows.sort(key=lambda x: x[1].get("posted_at") or "", reverse=True)
    done = sum(1 for _, c in pool if c.get("tiktok_done"))

    if show_done:
        rows = [(i, c) for i, c in pool if in_tiktok(c)]
        rows.sort(key=lambda x: x[1].get("posted_at") or "", reverse=True)

    brands = sorted({cap_prefix(c) for c in clips if in_tiktok(c)})
    title = f'Captions &middot; {html.escape(want)}' if want else 'Captions'
    out = [f'<h1>{title}</h1>',
           f'<p class=sub>{len(rows)} waiting to paste &middot; {done} done &middot; '
           f'match the picture to the draft in TikTok, tap COPY, paste.</p>',
           _nav("cap")]
    if len(brands) > 1:
        tabs = [f'<a href="./?b=*" class="{"on" if want == "*" else ""}">All</a>']
        for b in brands:
            tabs.append(f'<a href="./?b={b}" class="{"on" if want == b else ""}">'
                        f'{html.escape(b)}</a>')
        out.append('<div class=nav>' + "".join(tabs) + '</div>')
    # WHEN to post them, which is the question the page could not answer before.
    # A clip's slot IS its intended time - post it when the draft lands and the
    # timing is already decided. The problem is a BACKLOG: three drafts waiting
    # invite posting three at once, and [Likely] that is the worst thing he can
    # do with them - TikTok tests each video on a slice of his followers, so
    # simultaneous posts compete for the same people in the same early-engagement
    # window, and early engagement is the one lever his own data confirmed
    # (rho +0.69, biggest TikTok sample).
    if len(rows) > 1:
        out.append(f'<div class=warn><b>{len(rows)} waiting — do not post them '
                   f'together.</b><br>Space them at least 2 hours apart. They '
                   f'compete for the same followers in the first hour, and early '
                   f'engagement is what decides how far each one travels.</div>')
    if not rows:
        out.append('<div class=empty><b>Nothing waiting.</b><br>'
                   'When a clip lands in your TikTok drafts its caption appears '
                   'here automatically.</div>')
    # GROUPED BY DAY. A flat list of fourteen cards cannot answer "what is
    # today?", which is the only question he actually opens this page with.
    def daylabel(c):
        stamp = (c.get("posted_at") or "")[:10]
        if not stamp:
            return "No date"
        today = now.strftime("%Y-%m-%d")
        from datetime import timedelta
        y = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        if stamp == today:
            return "Today"
        if stamp == y:
            return "Yesterday"
        return stamp

    last = None
    for i, c in rows:
        lab = daylabel(c)
        if lab != last:
            n = sum(1 for _, x in rows if daylabel(x) == lab)
            out.append(f'<div class=day><b>{html.escape(lab)}</b> '
                       f'<span>{n} clip{"s" if n != 1 else ""}</span></div>')
            last = lab
        out.append(
            f'<div class="cap" id=k{i}>'
            f'<div class=caphead>'
            f'<video class=thumb preload=metadata playsinline muted '
            f'src="{media_url(c["file"])}#t=1.4"></video>'
            f'<div><div class=capname>{html.escape(_hookline(c))}</div>'
            f'<div class=when2><b>{html.escape(cap_prefix(c))}</b> &middot; '
            f'{html.escape(clip_title(c["file"]))} &middot; '
            f'{_due(c, now)}</div></div>'
            f'</div>'
            f'<button class=copy onclick="grab({i})">COPY CAPTION</button>'
            f'<textarea id=x{i} readonly>{html.escape(c.get("caption",""))}</textarea>'
            f'</div>')
    if done:
        link = "./?all=1" + (f"&b={want}" if want else "")
        out.append(f'<div class=unsched>{done} already pasted &middot; '
                   f'<a href="{link}">show them</a></div>')
    out.append(_CAP_JS)
    return ("<!doctype html><meta name=viewport content='width=device-width,"
            f"initial-scale=1'><title>Captions</title><style>{CSS}</style>"
            + "".join(out))


_CAP_JS = """<script>
const T=location.pathname.replace(/\\/c$/,'').replace(/\\/$/,'');
async function grab(i){
  const t=document.getElementById('x'+i), b=event.target;
  // Copy FIRST and only mark done if the clipboard actually took it. Marking a
  // caption pasted that never reached the clipboard would send him to TikTok
  // with nothing, which is the one failure this page exists to prevent.
  let ok=false;
  try{
    if(navigator.clipboard&&window.isSecureContext){
      await navigator.clipboard.writeText(t.value); ok=true;
    }
  }catch(e){}
  if(!ok){
    t.style.display='block'; t.removeAttribute('readonly'); t.focus();
    t.setSelectionRange(0,t.value.length);
    try{ ok=document.execCommand('copy'); }catch(e){}
    t.setAttribute('readonly','');
  }
  if(!ok){ b.textContent='SELECT IT AND COPY'; t.style.display='block'; return; }
  b.textContent='COPIED — paste it in TikTok';
  b.classList.add('ok');
  // Copying IS the moment it is posted, so this SETS done - it must never
  // toggle, or copying the same caption twice brings the card back.
  fetch(T+'/tiktok/'+i,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({done:true})});
  setTimeout(()=>{document.getElementById('k'+i).classList.add('gone');},1400);
}
</script>"""


def today(clips, token, media_url, now, slots, platforms, brand=""):
    """The one page he opens. Today, in order, already decided.

    Everything above the fold answers a single question: what is going out in
    the next few hours, and is there anything I personally have to do. The only
    manual job left is TikTok, so TikTok gets the biggest button on each card
    and its own tick, and nothing else asks him for a decision.

    1 Sept: it was answering that question for TWO people at once. brand-2's clips
    sat in his running order, so "what is going out" was a list he had to mentally
    filter before it meant anything. A page shared between two brands answers
    nobody's question. Bare link = the owner's own board; ?b=AR is hers; ?b=* is
    everything.
    """
    want = (brand or "").strip().upper().rstrip("_")
    if want == "*":
        want = ""
    elif not want:
        want = "KT"
    if want:
        clips = [c for c in clips if cap_prefix(c) == want]
    from datetime import datetime, timedelta
    tod = now.strftime("%Y-%m-%d")
    tom = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    hhmm = now.strftime("%H:%M")

    def rows_for(day):
        r = [(i, c) for i, c in enumerate(clips)
             if (c.get("scheduled_at") or "")[:10] == day]
        r.sort(key=lambda x: x[1]["scheduled_at"])
        return r

    mine = rows_for(tod)
    later = rows_for(tom)
    left = [1 for i, c in mine if c["scheduled_at"][11:16] > hhmm]
    tt_left = [1 for i, c in mine if not c.get("tiktok_done")]
    unsched = sum(1 for c in clips
                  if not c.get("scheduled_at") and not c.get("done")
                  and not c.get("posted_at"))

    out = [f'<h1>{now.strftime("%A %d %B")}</h1>',
           f'<p class=sub>{len(mine)} scheduled today &middot; {len(left)} still '
           f'to go &middot; {len(tt_left)} TikTok tap'
           f'{"s" if len(tt_left) != 1 else ""} left &middot; now {hhmm}</p>',
           _nav("today")]

    # THE TIKTOK CAPTIONS, RIGHT HERE. 10 Sept 2026, the owner: "the descriptions
    # are not in the link i have been using." This page carried the caption TEXT
    # but no way to copy it, and the Captions tab in the nav assumes he knows to
    # look for it. He had a link saved and used it; the page should serve him,
    # not send him somewhere else. Anything sitting in TikTok appears at the top
    # with a copy button, on whichever page he happens to open.
    waiting = [(i, c) for i, c in enumerate(clips)
               if c.get("posted_at") and not c.get("tiktok_done")
               and in_tiktok(c) and (not brand or cap_prefix(c) == brand.upper())]
    waiting.sort(key=lambda x: x[1].get("posted_at") or "", reverse=True)
    if waiting:
        out.append(f'<div class=warn><b>{len(waiting)} waiting in your TikTok '
                   f'drafts.</b> Newest first — tap COPY, then paste it in '
                   f'TikTok.</div>')
        for i, c in waiting:
            out.append(
                f'<div class="cap" id=k{i}>'
                f'<div class=caphead>'
                f'<video class=thumb preload=metadata playsinline muted '
                f'src="{media_url(c["file"])}#t=1.4"></video>'
                f'<div><div class=capname>{html.escape(_hookline(c))}</div>'
                f'<div class=when2>{html.escape(clip_title(c["file"]))}</div>'
                f'</div></div>'
                f'<button class=copy onclick="grab({i})">COPY CAPTION</button>'
                f'<textarea id=x{i} readonly>'
                f'{html.escape(c.get("caption", ""))}</textarea></div>')
    if not mine:
        out.append('<p class=sub>Nothing is scheduled for today. Upload clips and '
                   'they schedule themselves into the next free slots '
                   f'({", ".join(slots)}).</p>')

    for i, c in mine:
        t = c["scheduled_at"][11:16]
        past = t <= hhmm
        st = c.get("status") or {}
        links = c.get("links") or {}
        chips = "".join(_chip(p, st.get(p), links.get(p, "")) for p in platforms)
        chips += (f'<span class="chip {"ok" if c.get("tiktok_done") else "wait"}">'
                  f'tiktok {"done" if c.get("tiktok_done") else "your tap"}</span>')
        cap = c.get("caption", "")
        url = media_url(c["file"])
        fname = c["file"].split("/")[-1]
        failed = any(v and v != "posted" and "inbox" not in v for v in st.values())
        out.append(
            f'<div class="c{" done" if c.get("done") and c.get("tiktok_done") else ""}" id=c{i}>'
            f'<div><span class="ord{" now" if not past else ""}">{t}</span>'
            f'<span class=n>{html.escape(clip_title(c["file"]))}</span></div>'
            f'<div class=m>{html.escape(c["file"].split("/")[0])} &middot; '
            f'{c.get("bytes",0)/1e6:.0f} MB</div>'
            f'<div class=chips>{chips}</div>'
            f'<video controls preload=metadata playsinline src="{url}"></video>'
            + ('' if c.get("tiktok_done") else TIKTOK_BLOCK.format(
                url=url, fname=fname, i=i,
                cap_btn=(f'<button class=alt onclick="cp({i})">2 &middot; Copy'
                         f' caption</button>' if cap else '')))
            + (f'<div class=row><button class=alt id=tt{i} onclick="tt({i})">'
               f'TikTok done &mdash; undo</button></div>'
               if c.get("tiktok_done") else '')
            + (f'<button class=alt style="margin-top:8px;width:100%" '
               f'onclick="retry({i})">Retry the platforms that failed</button>'
               if failed else '')
            + (f'<textarea id=t{i} rows=5 readonly>{html.escape(cap)}</textarea>'
               if cap else '')
            + f'<div class=r id=r{i}></div></div>')

    if later:
        out.append('<div class=unsched>Tomorrow</div>')
        for i, c in later:
            out.append(
                f'<div class=slot><video preload=metadata playsinline muted '
                f'src="{media_url(c["file"])}#t=1"></video><div>'
                f'<div class=when>{c["scheduled_at"][11:16]}</div>'
                f'<div class=n>{html.escape(clip_title(c["file"]))}</div>'
                f'<div class=m>{html.escape(c["file"].split("/")[0])}</div>'
                f'</div></div>')
    if unsched:
        out.append(f'<p class=sub>{unsched} clip(s) still being placed on the '
                   f'calendar.</p>')
    out.append(_TODAY_JS)
    out.append(_CAP_JS)   # the COPY button above needs it
    return ("<!doctype html><meta name=viewport content='width=device-width,"
            f"initial-scale=1'><title>Today</title><style>{CSS}</style>"
            + "".join(out))


# THE ONE MANUAL STEP, spelled out. He could not find the download on 25 Aug -
# it was one button among three identical-looking ones, with the how-to in a
# paragraph at the bottom of the page. TikTok now gets its own boxed panel with
# the steps numbered ON the buttons and the phone route written underneath,
# because the phone route is four taps and none of them are guessable.
TIKTOK_BLOCK = """<div class=tt>
<div class=tth>TikTok &mdash; your tap</div>
<div class=row>
<a class="btn go" href="{url}" download="{fname}">1 &middot; Save video</a>
{cap_btn}
</div>
<div class=row style="margin-top:8px">
<button class=alt onclick="lk({i})">Copy link &middot; send to phone</button>
<button class=alt id=tt{i} onclick="tt({i})">3 &middot; Mark done</button>
</div>
<input type=hidden id=u{i} value="{url}">
<div class=note><b>On a computer (fastest):</b> Save video, then go to
<a href="https://www.tiktok.com/upload" target="_blank">tiktok.com/upload</a>,
drag the file in, paste the caption, post. No phone needed.<br>
<b>On the phone:</b> Save video &rarr; it lands in <b>Files</b> &rarr; open Files,
tap the clip, <b>Share &rarr; Save Video</b> &rarr; now it is in the camera roll
&rarr; TikTok &rarr; Upload. Either way: <b>no sound</b>.</div>
</div>"""


_TODAY_JS = """<script>
const T=location.pathname.replace(/\\/today$/,'').replace(/\\/$/,'');
function cp(i){
  const t=document.getElementById('t'+i), b=event.target, o=b.textContent;
  const ok=()=>{b.textContent='Copied';setTimeout(()=>b.textContent=o,1200);};
  if(navigator.clipboard&&window.isSecureContext){
    navigator.clipboard.writeText(t.value).then(ok).catch(()=>sel(t));
  } else sel(t);
}
function sel(t){t.removeAttribute('readonly');t.focus();
  t.setSelectionRange(0,t.value.length);try{document.execCommand('copy');}catch(e){}
  t.setAttribute('readonly','');}
function lk(i){
  const v=document.getElementById('u'+i).value, b=event.target, o=b.textContent;
  if(navigator.clipboard&&window.isSecureContext){
    navigator.clipboard.writeText(v).then(()=>{
      b.textContent='Link copied';setTimeout(()=>b.textContent=o,1400);}).catch(()=>{});
  }
}
async function tt(i){
  const r=await fetch(T+'/tiktok/'+i,{method:'POST'}), d=await r.json();
  location.reload();   // the whole card changes shape, not just a label
}
async function retry(i){
  const b=event.target, r=document.getElementById('r'+i);
  b.disabled=true; b.textContent='retrying...'; r.textContent='';
  try{
    const res=await fetch(T+'/retry/'+i,{method:'POST'}), d=await res.json();
    r.innerHTML=Object.entries(d).map(([k,v])=>
      '<div class="'+(v==='posted'?'ok':(v.indexOf('inbox')>=0?'wait':'no'))+'">'
      +k+': '+v+'</div>').join('');
  }catch(e){ r.innerHTML='<div class=no>'+e+'</div>'; }
  b.disabled=false; b.textContent='Retry the platforms that failed';
}
</script>"""


def calendar(clips, token, media_url, now):
    """Everything scheduled, grouped by day, newest work first.

    Deliberately a scrolling agenda rather than a month grid. A month grid on a
    phone gives each day a box too small to hold a thumbnail, and the thing he
    actually needs to see is WHAT goes out and WHEN, with the video right there.
    """
    from datetime import datetime
    sched, unsched = [], []
    for i, c in enumerate(clips):
        (sched if c.get("scheduled_at") else unsched).append((i, c))
    sched.sort(key=lambda x: x[1]["scheduled_at"])

    days, order = {}, []
    for i, c in sched:
        d = c["scheduled_at"][:10]
        if d not in days:
            days[d] = []; order.append(d)
        days[d].append((i, c))

    out = [f'<h1>Calendar</h1><p class=sub>{len(sched)} scheduled &middot; '
           f'{len(unsched)} unscheduled &middot; all times '
           f'{now.strftime("%d %b %H:%M")} local</p>', _nav("cal")]
    if not sched:
        out.append('<p class=sub>Nothing scheduled yet. Open <b>Clips</b>, '
                   'pick a date and time on any clip, and it appears here — '
                   'and posts itself when the slot arrives.</p>')
    for d in order:
        try:
            label = datetime.strptime(d, "%Y-%m-%d").strftime("%a %d %b")
        except ValueError:
            label = d
        out.append(f'<div class=day><div class=dh><span>{label}</span>'
                   f'<span class=cnt>{len(days[d])} post'
                   f'{"s" if len(days[d]) != 1 else ""}</span></div>')
        for i, c in days[d]:
            past = c["scheduled_at"][:16] <= now.strftime("%Y-%m-%dT%H:%M")
            name = c["file"].split("/")[-1].rsplit(".", 1)[0]
            head, _, tail = name.rpartition("_")
            if not re.fullmatch(r"\d+s", tail or ""):
                head = name
            st = c.get("status") or {}
            line = " ".join(f'{k}:{"ok" if v == "posted" else ("inbox" if "inbox" in v else "fail")}'
                            for k, v in st.items())
            done = c.get("done")
            out.append(
                f'<div class="slot{" past" if past and done else ""}">'
                f'<video preload=metadata playsinline muted '
                f'src="{media_url(c["file"])}#t=1"></video><div>'
                f'<div class="when{" done" if done else ""}">'
                f'{c["scheduled_at"][11:16]}{" &middot; posted" if done else ""}</div>'
                f'<div class=n>{html.escape(head.replace("_"," ").replace("-"," "))}</div>'
                f'<div class=m>{c["file"].split("/")[0]}</div>'
                f'<div class=st>{html.escape(line)}</div></div></div>')
        out.append('</div>')
    if unsched:
        out.append(f'<div class=unsched>{len(unsched)} not scheduled</div>')
        for i, c in unsched:
            name = c["file"].split("/")[-1].rsplit(".", 1)[0]
            out.append(f'<div class=slot><video preload=metadata playsinline muted '
                       f'src="{media_url(c["file"])}#t=1"></video><div>'
                       f'<div class=n>{html.escape(name.replace("_"," ").replace("-"," "))}</div>'
                       f'<div class=m>{c["file"].split("/")[0]}</div></div></div>')
    return ("<!doctype html><meta name=viewport content='width=device-width,"
            f"initial-scale=1'><title>Calendar</title><style>{CSS}</style>"
            + "".join(out))


def board(clips, token, media_url, now=None):
    todo = [c for c in clips if not c.get("done")]
    rows = [f"<h1>Post today</h1><p class=sub>{len(todo)} to post &middot; "
            f"{len(clips) - len(todo)} done &middot; TikTok lands in your inbox, "
            f"tap post there</p>", _nav("board")]
    for i, c in enumerate(clips):
        name = c["file"].split("/")[-1].rsplit(".", 1)[0]
        head, _, tail = name.rpartition("_")
        if not re.fullmatch(r"\d+s", tail or ""):
            head, tail = name, ""
        cap = c.get("caption", "")
        st = c.get("status") or {}
        res = "".join(
            f'<div class="{"ok" if v == "posted" else ("wait" if "inbox" in v else "no")}">'
            f'{html.escape(k)}: {html.escape(v)}</div>' for k, v in st.items())
        rows.append(
            f'<div class="c{" done" if c.get("done") else ""}" id=c{i}>'
            f'<div><span class=ord>{i+1}</span><span class=n>'
            f'{html.escape(head.replace("_"," ").replace("-"," "))}</span></div>'
            f'<div class=m>{c["file"].split("/")[0]}'
            f'{" &middot; " + tail if tail else ""} &middot; '
            f'{c.get("bytes",0)/1e6:.0f} MB</div>'
            f'<video controls preload=metadata playsinline '
            f'src="{media_url(c["file"])}"></video>'
            f'<div class=row>'
            f'<button class=go id=p{i} onclick="post({i})">POST</button>'
            + (f'<button class=alt onclick="cp({i})">Caption</button>' if cap else '')
            + f'<button class=alt id=d{i} onclick="mark({i})">'
              f'{"Posted" if c.get("done") else "Done"}</button></div>'
            + f'<input type=datetime-local id=s{i} '
              f'value="{(c.get("scheduled_at") or "")[:16]}" '
              f'onchange="sched({i})">'
            + (f'<textarea id=t{i} rows=5 readonly>{html.escape(cap)}</textarea>'
               if cap else '')
            + f'<div class=r id=r{i}>{res}</div></div>')
    rows.append("""<script>
const T=location.pathname.replace(/\\/$/,'');
function cp(i){
  const t=document.getElementById('t'+i), b=event.target, o=b.textContent;
  // navigator.clipboard needs a secure context. This IS https, so it normally
  // works - but fall back to selection rather than silently doing nothing.
  const ok=()=>{b.textContent='Copied';setTimeout(()=>b.textContent=o,1200);};
  if(navigator.clipboard&&window.isSecureContext){
    navigator.clipboard.writeText(t.value).then(ok).catch(()=>sel(t));
  } else sel(t);
}
function sel(t){t.removeAttribute('readonly');t.focus();
  t.setSelectionRange(0,t.value.length);try{document.execCommand('copy');}catch(e){}
  t.setAttribute('readonly','');}
async function mark(i){
  const r=await fetch(T+'/done/'+i,{method:'POST'}), d=await r.json();
  const c=document.getElementById('c'+i), b=document.getElementById('d'+i);
  c.classList.toggle('done',d.done); b.textContent=d.done?'Posted':'Done';
}
async function sched(i){
  const v=document.getElementById('s'+i).value;
  const r=await fetch(T+'/schedule/'+i,{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({at:v})});
  const d=await r.json();
  document.getElementById('r'+i).innerHTML =
    '<div class=ok>'+(d.scheduled_at?('scheduled '+d.scheduled_at.replace("T"," ")
      +' — it will post itself'):'schedule cleared')+'</div>';
}
async function post(i){
  const b=document.getElementById('p'+i), r=document.getElementById('r'+i);
  b.disabled=true; b.textContent='posting...'; r.textContent='';
  try{
    const res=await fetch(T+'/post/'+i,{method:'POST'}), d=await res.json();
    r.innerHTML=Object.entries(d).map(([k,v])=>
      '<div class="'+(v==='posted'?'ok':(v.indexOf('inbox')>=0?'wait':'no'))+'">'
      +k+': '+v+'</div>').join('');
    if(Object.values(d).every(v=>v==='posted'))
      document.getElementById('c'+i).classList.add('done');
  }catch(e){ r.innerHTML='<div class=no>'+e+'</div>'; }
  b.disabled=false; b.textContent='POST';
}
</script>""")
    return ("<!doctype html><meta name=viewport content='width=device-width,"
            f"initial-scale=1'><title>Post today</title><style>{CSS}</style>"
            + "".join(rows))


def oauth_result(code, err):
    """What TikTok bounces back to after the user approves.

    Shows the authorisation code so it can be carried back to the machine
    holding the PKCE verifier. The code is single-use and expires in minutes, so
    there is nothing lasting on screen.
    """
    if err:
        body = (f'<h2>Not authorised</h2><p>{html.escape(err)}</p>'
                '<p class=sub>Nothing was granted. Try the link again.</p>')
    elif code:
        body = ('<h2>Approved</h2><p class=sub>Copy this code and paste it back '
                'into the chat. It expires in a few minutes.</p>'
                f'<textarea rows=4 readonly onclick="this.select()" '
                f'style="width:100%">{html.escape(code)}</textarea>')
    else:
        body = '<h2>No code received</h2><p class=sub>Nothing to do.</p>'
    return ("<!doctype html><meta name=viewport content='width=device-width,"
            f"initial-scale=1'><title>Authorisation</title><style>{CSS}</style>"
            f"<div class=doc>{body}</div>")
