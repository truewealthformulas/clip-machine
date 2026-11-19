#!/usr/bin/env python3
"""ORIGINAL CAROUSELS FOR INSTAGRAM (18 Nov 2026).

Account Status: "Your account and content can't be recommended to people who
don't follow you" - Contenido no original. Instagram counts every Kevin clip as
unoriginal however it is edited, and an account becomes eligible again "when
most of your recently posted reels, photos, and carousels are considered
original in a 30-day period". So for 30 days Instagram gets no Kevin reels and,
instead, 3 ORIGINAL carousels a day (the owner: "let's do 3 posts per day
original"): one lesson Kevin teaches, rewritten by Claude as our own short
framework, designed here as 8 slides. No footage, no frames of Kevin - type,
colour and our words only.

  python agents/carousel.py            # make + post one
  python agents/carousel.py --dry      # make one, save the slides to /tmp/carousel, post nothing
"""
import json
import os
import random
import re
import subprocess
import sys
import time

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import common as AC  # noqa: E402

A = os.path.join(ROOT, "factory", "assets")
STATE = os.path.join(ROOT, "state", "carousels.json")
MAN = os.path.join(ROOT, "state", "manifest.json")
HANDLE = os.environ.get("KT_HANDLE", "@thesuccessclubco")
W, H = 1080, 1350
G = "https://graph.facebook.com/v21.0"
THEMES = [  # background, accent, soft text
    ((11, 11, 13), (232, 190, 92), (205, 205, 205)),
    ((12, 20, 34), (232, 190, 92), (200, 208, 220)),
    ((18, 14, 10), (226, 176, 98), (214, 204, 190)),
    ((10, 24, 20), (214, 190, 120), (196, 214, 204)),
]
CLUB = ("If you’re looking to improve your finances, improve your health, create great long-lasting "
        "relationships with like-minded people and feel better about yourself → link in my bio ⬆️")


def font(name, size, w=None):
    f = ImageFont.truetype(os.path.join(A, name), size)
    if w:
        try:
            f.set_variation_by_axes([w])
        except Exception:
            pass
    return f


SANS = lambda s, w=700: font("Montserrat.ttf", s, w)  # noqa: E731
BLACK = lambda s: font("mont_black.ttf", s)  # noqa: E731
SER = lambda s: font("PlayfairDisplay-Italic.ttf", s)  # noqa: E731


def wrap(d, text, f, width):
    out, line = [], ""
    for w in text.split():
        t = (line + " " + w).strip()
        if line and d.textlength(t, font=f) > width:
            out.append(line)
            line = w
        else:
            line = t
    if line:
        out.append(line)
    return out


def block(d, text, f, y, fill, width=880, gap=1.3, x=100, center=False):
    for ln in wrap(d, text, f, width):
        xx = (W - d.textlength(ln, font=f)) / 2 if center else x
        d.text((xx, y), ln, font=f, fill=fill)
        y += int(f.size * gap)
    return y


def fit(d, text, mk, start, width, lines_max):
    s = start
    while s > 40:
        f = mk(s)
        if len(wrap(d, text, f, width)) <= lines_max:
            return f
        s -= 6
    return mk(40)


def canvas(theme, seed):
    bg, acc, soft = theme
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    r = random.Random(seed)
    glow = Image.new("RGB", (W, H), bg)
    gd = ImageDraw.Draw(glow)
    cx, cy = r.choice([(W * 0.85, H * 0.1), (W * 0.15, H * 0.9), (W * 0.9, H * 0.85)])
    for rad in range(700, 0, -20):
        k = (700 - rad) / 700 * 0.10
        col = tuple(int(bg[i] + (acc[i] - bg[i]) * k) for i in range(3))
        gd.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=col)
    im = Image.blend(im, glow.filter(ImageFilter.GaussianBlur(60)), 1.0)
    d = ImageDraw.Draw(im)
    d.rectangle((60, 60, W - 60, H - 60), outline=tuple(int(c * 0.35) for c in acc), width=2)
    return im, d


def footer(d, n, tot, theme):
    d.text((100, 1230), HANDLE, font=SANS(30, 600), fill=theme[2])
    s = f"{n}/{tot}"
    d.text((W - 100 - d.textlength(s, font=SANS(30, 600)), 1230), s, font=SANS(30, 600), fill=theme[2])


def render(c, out_dir, seed):
    theme = THEMES[seed % len(THEMES)]
    bg, acc, soft = theme
    pts = c["points"][:5]
    tot = len(pts) + 3
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    # 1 cover
    im, d = canvas(theme, seed)
    d.text((100, 300), "  ".join(c["kicker"].upper()), font=SANS(28, 700), fill=soft)
    d.line((100, 360, 300, 360), fill=acc, width=4)
    f = fit(d, c["title"], SER, 150, 880, 3)
    y = block(d, c["title"], f, 400, acc, gap=1.08, x=92)
    block(d, c["subtitle"], SANS(42, 500), y + 50, (240, 240, 240))
    d.text((W - 100 - d.textlength("Swipe  →", font=SANS(34, 700)), 1230), "Swipe  →", font=SANS(34, 700), fill=acc)
    d.text((100, 1230), HANDLE, font=SANS(30, 600), fill=soft)
    paths.append(im)
    # points
    for i, p in enumerate(pts):
        im, d = canvas(theme, seed + i + 1)
        d.text((90, 210), str(i + 1), font=SER(280), fill=acc)
        d.line((100, 600, 260, 600), fill=acc, width=4)
        fh = fit(d, p["head"], BLACK, 72, 880, 3)
        y = block(d, p["head"], fh, 650, (245, 245, 245), gap=1.18)
        block(d, p["body"], SANS(42, 500), y + 36, soft, gap=1.4)
        footer(d, i + 2, tot, theme)
        paths.append(im)
    # why
    im, d = canvas(theme, seed + 9)
    d.text((100, 280), "  ".join("WHY IT WORKS"), font=SANS(30, 700), fill=acc)
    d.line((100, 340, 260, 340), fill=acc, width=4)
    f = fit(d, c["why_head"], SER, 96, 880, 3)
    y = block(d, c["why_head"], f, 400, (245, 245, 245), gap=1.12)
    block(d, c["why_body"], SANS(42, 500), y + 46, soft, gap=1.4)
    footer(d, tot - 1, tot, theme)
    paths.append(im)
    # CTA
    im, d = canvas(theme, seed + 10)
    t = "  ".join("SAVE THIS FOR LATER")
    d.text(((W - d.textlength(t, font=SANS(30, 700))) / 2, 380), t, font=SANS(30, 700), fill=soft)
    d.line((W / 2 - 120, 440, W / 2 + 120, 440), fill=acc, width=4)
    for j, line in enumerate(["The full lesson,", "free on YouTube"]):
        fl = SER(104)
        d.text(((W - d.textlength(line, font=fl)) / 2, 480 + j * 135), line, font=fl, fill=acc)
    block(d, "Kevin Trudeau's full talks & training", SANS(40, 600), 800, (240, 240, 240), center=True)
    block(d, "Link in my bio", BLACK(56), 930, (255, 255, 255), center=True)
    block(d, "Share it with someone who needs it today.", SANS(34, 500), 1060, soft, center=True)
    footer(d, tot, tot, theme)
    paths.append(im)
    out = []
    for i, im in enumerate(paths):
        p = os.path.join(out_dir, f"s{i + 1}.jpg")
        im.save(p, "JPEG", quality=92)
        out.append(p)
    return out


# ---------------------------------------------------------------- PHOTO CAROUSELS
# 18 Nov 2026, the owner: "photos of GIN and the events - post them in the
# carousel and talk about success, money, phrases that Kevin uses". The photos
# are the owner's own, from the Global Information Network events (agents/gin/).
# The words are Kevin's EXACT words, lifted from the transcript of one of his
# talks and checked word for word against it - nothing is put in his mouth.
GIN = os.path.join(HERE, "gin")
SERIES = os.path.join(ROOT, "factory", "kt_series.json")


def _norm(t):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]+", " ", t.lower().replace("’", "'"))).strip()


def _srt_text(path):
    out = []
    for ln in open(path, encoding="utf-8", errors="ignore").read().splitlines():
        ln = ln.strip()
        if not ln or ln.isdigit() or "-->" in ln:
            continue
        out.append(ln)
    return " ".join(out)


def transcript(rng):
    series = json.load(open(SERIES))
    vids = sorted({v["source"][:-4] for v in series.values() if v.get("source")})
    rng.shuffle(vids)
    repo = os.environ.get("GITHUB_REPOSITORY", "truewealthformulas/clip-machine")
    for vid in vids[:6]:
        enc, srt = f"/tmp/{vid}.srt.enc", f"/tmp/{vid}.srt"
        r = subprocess.run(["gh", "release", "download", "sources", "-R", repo, "-p", f"{vid}.srt.enc",
                            "-D", "/tmp", "--clobber"], capture_output=True)
        if r.returncode or not os.path.exists(enc):
            continue
        r = subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-pass", "env:FACTORY_KEY",
                            "-in", enc, "-out", srt], capture_output=True)
        if r.returncode:
            continue
        t = _srt_text(srt)
        if len(t) > 3000:
            return vid, t
    raise RuntimeError("no transcript could be read")


def write_photo(rng):
    sysmsg = ("You pick Kevin Trudeau's own words from a transcript of one of his talks for an Instagram "
              "carousel about success, money and mindset. Every quote must be copied EXACTLY from the "
              "transcript (you may only fix capitalisation and add end punctuation). Never pick lines that "
              "promise income, money results or health results, nothing about diseases, cures, medicine "
              "or any book about health. Return JSON only.")
    for _ in range(3):
        vid, text = transcript(rng)
        start = rng.randrange(0, max(1, len(text) - 14000))
        chunk = text[start:start + 14000]
        user = ("Transcript excerpt:\n" + chunk + "\n\n"
                "Choose 5 or 6 short, powerful, self-contained sentences he says about success, money, "
                "wealth, discipline or thinking - each 8 to 28 words, quoted exactly. Then: title (3-6 words, "
                "e.g. 'What Kevin Says About Money'), and caption: 3-4 sentences in our own words that open "
                "with a hook, say these are words Kevin Trudeau teaches, shown with moments from the Global "
                "Information Network events, end with a question to comment on, then 4 hashtags.\n"
                'Reply: {"title":"","quotes":[""],"caption":""}')
        c = AC.ask_json(sysmsg, user, max_tokens=2000)
        nt = _norm(chunk)
        good = [q.strip().strip('"“”') for q in c.get("quotes") or [] if len(_norm(q)) > 20 and _norm(q) in nt]
        AC.log(f"photo carousel: {len(good)}/{len(c.get('quotes') or [])} quotes verified in {vid}")
        if len(good) >= 4:
            c["quotes"] = good[:6]
            c["source"] = vid
            return c
    raise RuntimeError("could not find 4 exact quotes")


def pick_photos(state, n, rng):
    fs = sorted(f for f in os.listdir(GIN) if f.endswith(".jpg"))
    used = state.get("gin_used", [])
    fresh = [f for f in fs if f not in used] or fs
    rng.shuffle(fresh)
    big = [f for f in fresh if min(Image.open(os.path.join(GIN, f)).size) >= 1000]
    first = big[0] if big else fresh[0]
    rest = [f for f in fresh if f != first]
    rest += [f for f in fs if f not in rest and f != first]
    pick = [first] + rest[:n - 1]
    state["gin_used"] = (used + pick)[-30:]
    return [os.path.join(GIN, f) for f in pick]


def _cover_crop(im, w, h):
    s = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * s) + 1, round(im.height * s) + 1), Image.LANCZOS)
    x, y = (im.width - w) // 2, max(0, int((im.height - h) * 0.35))
    return im.crop((x, y, x + w, y + h))


def _fade(im, y0, y1, a1=255):
    sh = Image.new("L", (1, H), 0)
    for y in range(H):
        sh.putpixel((0, y), 0 if y < y0 else int(a1 * min(1.0, (y - y0) / max(1, y1 - y0))))
    blk = Image.new("RGB", (W, H), (8, 8, 10))
    return Image.composite(blk, im, sh.resize((W, H)))


RED = (200, 30, 36)


def label(d, text, x, y, fill=(235, 235, 235)):
    f = SANS(26, 600)
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + 7


def render_photo(c, photos, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    quotes = c["quotes"]
    tot = len(quotes) + 2
    slides = []
    # 1 - cover: full photo, the student look
    im = _cover_crop(Image.open(photos[0]).convert("RGB"), W, H)
    im = _fade(im, int(H * 0.40), int(H * 0.78), 235)
    d = ImageDraw.Draw(im)
    title = c["title"].upper()
    f = fit(d, title, BLACK, 104, 860, 3)
    lines = wrap(d, title, f, 860)
    y = 1000 - len(lines) * int(f.size * 1.02)
    label(d, "KEVIN TRUDEAU", 120, y - 64)
    d.rectangle((90, y + 8, 98, y + len(lines) * int(f.size * 1.02) + 70), fill=RED)
    for ln in lines:
        d.text((120, y), ln, font=f, fill=(255, 255, 255))
        y += int(f.size * 1.02)
    d.text((120, y + 10), "In his own words.", font=SER(56), fill=(240, 236, 228))
    d.text((W - 100 - d.textlength("Swipe  →", font=SANS(34, 700)), 1240), "Swipe  →", font=SANS(34, 700),
           fill=(255, 255, 255))
    d.text((100, 1240), HANDLE, font=SANS(30, 600), fill=(210, 210, 210))
    slides.append(im)
    # quotes - the photo on top, his words under it
    for i, q in enumerate(quotes):
        ph = Image.open(photos[(i + 1) % len(photos)]).convert("RGB")
        top = _cover_crop(ph, W, 700)
        im = Image.new("RGB", (W, H), (8, 8, 10))
        im.paste(top, (0, 0))
        im = _fade(im, 520, 720)
        d = ImageDraw.Draw(im)
        label(d, "KEVIN TRUDEAU", 120, 690)
        q2 = "“" + q.rstrip() + "”"
        fq = fit(d, q2, SER, 66, 840, 6)
        yy = 750
        lines = wrap(d, q2, fq, 840)
        d.rectangle((90, yy + 10, 98, yy + len(lines) * int(fq.size * 1.28)), fill=RED)
        for ln in lines:
            d.text((120, yy), ln, font=fq, fill=(255, 255, 255))
            yy += int(fq.size * 1.28)
        footer(d, i + 2, tot, ((0, 0, 0), (0, 0, 0), (200, 200, 200)))
        slides.append(im)
    # last - invitation
    im = _cover_crop(Image.open(photos[-1]).convert("RGB"), W, H)
    im = _fade(im, int(H * 0.25), int(H * 0.60), 240)
    d = ImageDraw.Draw(im)
    label(d, "THE FULL TALKS", 120, 820)
    d.rectangle((90, 880, 98, 1100), fill=RED)
    d.text((120, 870), "HEAR THE REST", font=BLACK(92), fill=(255, 255, 255))
    d.text((120, 980), "free on Kevin's YouTube.", font=SER(62), fill=(240, 236, 228))
    d.text((120, 1070), "Link in my bio", font=SANS(44, 700), fill=(232, 190, 92))
    footer(d, tot, tot, ((0, 0, 0), (0, 0, 0), (200, 200, 200)))
    slides.append(im)
    out = []
    for i, im in enumerate(slides):
        p = os.path.join(out_dir, f"s{i + 1}.jpg")
        im.save(p, "JPEG", quality=92)
        out.append(p)
    return out


def pick_source(state):
    man = json.load(open(MAN))
    used = {x["file"] for x in state.get("posts", [])}
    cands = [c for c in man["clips"] if c.get("posted_at") and c.get("caption") and c["file"] not in used
             and len(c.get("caption", "")) > 200]
    cands.sort(key=lambda c: c["posted_at"], reverse=True)
    if not cands:
        return None
    return random.Random(time.strftime("%Y%m%d%H")).choice(cands[:40])


def write(clip):
    cap = re.sub(r"#\w+", "", clip.get("caption", "")).replace("Ad:", "").strip()
    sysmsg = ("You write ORIGINAL Instagram carousels for The Success Club, a self-improvement page. "
              "You take one idea a teacher (Kevin Trudeau) talks about and turn it into OUR OWN short, "
              "practical framework in plain words: original structure, original examples, no quotes from "
              "him, no promises of money, health results or income. Return JSON only.")
    user = ("The idea, from a summary of one of his talks:\n" + cap[:1500] + "\n\n"
            "Write a carousel: kicker (2-4 words, e.g. 'THE PLAN OF THE DAY'), title (3-6 words, "
            "punchy), subtitle (one sentence, max 16 words), 5 points each with head (max 7 words, an "
            "action) and body (max 28 words, concrete), why_head (max 8 words), why_body (max 40 words), "
            "and caption: an original 3-5 sentence Instagram caption that opens with a hook question or "
            "statement, explains the idea in our words, credits 'an idea Kevin Trudeau teaches', ends with "
            "a question to comment on, then 4 relevant hashtags.\n"
            'Reply: {"kicker":"","title":"","subtitle":"","points":[{"head":"","body":""}],'
            '"why_head":"","why_body":"","caption":""}')
    c = AC.ask_json(sysmsg, user, max_tokens=2500)
    if len(c.get("points") or []) < 4:
        raise RuntimeError("carousel came back without enough points")
    return c


def upload(paths, slug):
    repo = os.environ.get("GITHUB_REPOSITORY", "truewealthformulas/clip-machine")
    urls = []
    for i, p in enumerate(paths):
        name = f"carousel--{slug}--{i + 1}.jpg"
        dst = os.path.join("/tmp", name)
        subprocess.run(["cp", p, dst], check=True)
        subprocess.run(["gh", "release", "upload", "media", dst, "-R", repo, "--clobber"], check=True)
        urls.append(f"https://github.com/{repo}/releases/download/media/{name}")
    return urls


def ig_post(urls, caption):
    ig, tok = os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"]
    kids = []
    for u in urls:
        r = requests.post(f"{G}/{ig}/media", data={"image_url": u, "is_carousel_item": "true",
                                                   "access_token": tok}, timeout=60).json()
        if not r.get("id"):
            raise RuntimeError(f"slide refused: {str(r)[:200]}")
        kids.append(r["id"])
    r = requests.post(f"{G}/{ig}/media", data={"media_type": "CAROUSEL", "children": ",".join(kids),
                                               "caption": caption[:2100], "access_token": tok},
                      timeout=60).json()
    if not r.get("id"):
        raise RuntimeError(f"carousel refused: {str(r)[:200]}")
    cid = r["id"]
    for _ in range(24):
        s = requests.get(f"{G}/{cid}", params={"fields": "status_code", "access_token": tok}, timeout=30).json()
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            raise RuntimeError(f"carousel error: {s}")
        time.sleep(5)
    p = requests.post(f"{G}/{ig}/media_publish", data={"creation_id": cid, "access_token": tok}, timeout=60).json()
    if not p.get("id"):
        raise RuntimeError(f"publish failed: {str(p)[:200]}")
    link = requests.get(f"{G}/{p['id']}", params={"fields": "permalink", "access_token": tok}, timeout=30).json()
    return p["id"], link.get("permalink")


def fb_post(urls, caption):
    """The same carousel on the Facebook Page as a multi-photo post (18 Nov 2026,
    the owner: "Let's improve Facebook"). Meta: Pages "receive the greatest
    distribution when they consist primarily of original content", and the
    same original content may go to every Page and profile you run."""
    page, tok = os.environ.get("FB_PAGE_ID"), os.environ.get("FB_ACCESS_TOKEN")
    if not page or not tok:
        return None
    ids = []
    for u in urls:
        r = requests.post(f"{G}/{page}/photos", data={"url": u, "published": "false", "access_token": tok},
                          timeout=90).json()
        if not r.get("id"):
            raise RuntimeError(f"facebook photo refused: {str(r)[:200]}")
        ids.append(r["id"])
    data = {"message": caption.replace("link in my bio ⬆️", "link on my page ⬆️"), "access_token": tok}
    for i, pid in enumerate(ids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": pid})
    r = requests.post(f"{G}/{page}/feed", data=data, timeout=90).json()
    if not r.get("id"):
        raise RuntimeError(f"facebook post refused: {str(r)[:200]}")
    return r["id"]


SLOTS = [(9, 0), (13, 0), (19, 30)]   # New York


def due(state):
    """18 Nov 2026: GitHub started the 13:00 carousel at 18:41 and the 19:30 one
    not at all. So the 10-minute post chain asks too: one carousel per slot
    already passed today (New York), at least 2 h apart."""
    from datetime import datetime, timezone, timedelta
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    now = datetime.now(ny)
    passed = sum(1 for h, m in SLOTS if (now.hour, now.minute) >= (h, m))
    today, last = 0, None
    for p in state.get("posts", []):
        try:
            t = datetime.strptime(p["at"], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc).astimezone(ny)
        except Exception:
            continue
        today += t.date() == now.date()
        last = t if last is None or t > last else last
    if today >= passed:
        return False
    if last and now - last < timedelta(hours=2):
        return False
    return True


def main():
    dry = "--dry" in sys.argv
    state = json.load(open(STATE)) if os.path.exists(STATE) else {"posts": []}
    if "--due" in sys.argv and not due(state):
        print("carousel: nothing due")
        return 0
    # every other carousel is a PHOTO carousel (GIN events + Kevin's own words)
    photo = "--photo" in sys.argv or (os.path.isdir(GIN) and "--text" not in sys.argv
                                      and len(state.get("posts", [])) % 2 == 1)
    rng = random.Random(time.strftime("%Y%m%d%H"))
    if photo:
        c = write_photo(rng)
        clip = {"file": "photo:" + c["source"] + time.strftime(":%Y%m%d%H")}
        slug = "gin-" + re.sub(r"[^a-z0-9]+", "-", c["title"].lower()).strip("-")[:34] + time.strftime("-%m%d%H")
        paths = render_photo(c, pick_photos(state, len(c["quotes"]) + 2, rng), f"/tmp/carousel/{slug}")
    else:
        clip = pick_source(state)
        if not clip:
            AC.log("carousel: no source left")
            return 0
        c = write(clip)
        slug = re.sub(r"[^a-z0-9]+", "-", c["title"].lower()).strip("-")[:40] + time.strftime("-%m%d%H")
        paths = render(c, f"/tmp/carousel/{slug}", int(time.time()) // 3600)
    caption = c["caption"].strip() + "\n\n" + CLUB + "\n\n🎬 Watch the full video free on Kevin’s YouTube → link in my bio ⬆️"
    AC.log(f"carousel: '{c['title']}' from {clip['file']} ({len(paths)} slides)")
    if dry:
        print(json.dumps(c, indent=1, ensure_ascii=False))
        print(caption)
        if photo:  # look at it without posting
            print("\n".join(upload(paths, "dry-" + slug)))
        return 0
    urls = upload(paths, slug)
    time.sleep(5)
    mid, link = None, None
    try:
        mid, link = ig_post(urls, caption)
    except Exception as e:
        AC.log(f"carousel: Instagram failed: {e}")
    fid = None
    try:
        fid = fb_post(urls, caption)
    except Exception as e:
        AC.log(f"carousel: Facebook failed: {e}")
    if not mid and not fid:
        raise RuntimeError("carousel posted nowhere")
    state["posts"].append({"file": clip["file"], "title": c["title"], "at": time.strftime("%Y-%m-%dT%H:%M"),
                           "id": mid, "link": link, "fb": fid})
    json.dump(state, open(STATE, "w"), indent=1, ensure_ascii=False)
    AC.log(f"carousel posted: {link}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
