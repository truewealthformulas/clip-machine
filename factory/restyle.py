#!/usr/bin/env python3
"""THE SUCCESS CLUB LOOK.

STYLE T (19 Oct 2026, current): the TITLE BAR. A black band across the top with
the hook in white + gold for the WHOLE clip; the video sits under it (90 px of
ceiling and 240 px of desk trimmed, never his face). Copied from the two Kevin
pages that work (@trudeaumanifestation, @thecreationformula), where the title
stays on screen so the hook is in the grid, in the first second and all the way
through. The owner: "let replicate that". Style E below is kept for --style E.

STYLE E (10 Oct 2026): Kevin full screen, the hook in a black box for 3 s.

10 Oct 2026, the owner, after style C (a bar over the picture) hid Kevin's face
and style D (video on top, hook below) was previewed: "the black frame with
white and gold, this will last 3 seconds and then gone, just the transcript in
white continues".

So: the video stays full screen and untouched. For the first 3 seconds a black
rounded box sits just under the spoken captions, below his face, with the hook
in big white (line 1) and gold (line 2). Then it is gone and only the factory's
white transcript runs. The opening frame carries the hook, so covers show it.

The factory no longer burns its own small hook card (factory/setup.sh switches
it off), so new clips arrive clean. A clip that still carries the card is never
styled: painting it out smeared Kevin's face in testing.

Clips that were given style C are re-rendered clean by the factory from
factory/plans/redo_*.json (test plans - built, never queued) and picked up here
from that build's artifacts.

    python factory/restyle.py
    python factory/restyle.py --local in.mp4 "Line One|Line Two"
"""
import glob
import json
import os
import re
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(ROOT, "factory", "assets", "mont_black.ttf")
MAN = os.path.join(ROOT, "state", "manifest.json")
REPO = os.environ.get("GITHUB_REPOSITORY", "truewealthformulas/clip-machine")
STYLE = os.environ.get("RESTYLE_STYLE", "T2")   # back to T2 28 Oct: TikTok views fell after T4
# STYLE T2 (24 Oct 2026): T1 plus what makes each clip OURS. Instagram flagged
# the account for "duplicate content or content you don't have the rights to"
# and stopped recommending it to non-followers - Kevin's footage is posted by
# many pages and the copies match. T2 adds an original layer to every clip:
# a "THE SUCCESS CLUB · LESSON #N" label in the title band for the whole clip,
# and a 2.5 s closing card in the brand colours with the reflection question
# from our own caption ("ASK YOURSELF ...") and a follow line. A T1 clip is
# upgraded in place: the new band is opaque and sits exactly over the old one.
OUTRO_SECS = 2.5
HANDLE = os.environ.get("KT_HANDLE", "@thesuccessclubco")
BAND, TRIM_TOP = 330, 90  # style T: title band height; ceiling trimmed above the video
W, H = 1080, 1920
GOLD, INK, WHITE, GREY = (245, 197, 24), (11, 20, 48), (255, 255, 255), (165, 165, 165)   # INK: midnight navy #0B1430 (owner, 12 Oct)
HOOK_SECS = 4.5          # how long the FACTORY's old card stayed (used to detect it)
CARD_SECS = 3.0          # our hook box: 3 seconds, then only the white transcript
CARD_Y = 1165            # under the spoken captions (~y1040-1110), below his face


def sh(*a):
    subprocess.run(a, check=True)


def frames(path, times, w=270):
    out = []
    for t in times:
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", str(t), "-i", path, "-frames:v", "1",
                              "-vf", f"scale={w}:-1,format=gray", "-f", "rawvideo", "-"],
                             capture_output=True, check=True).stdout
        out.append(np.frombuffer(raw, np.uint8).reshape(-1, w).astype(np.int16))
    return out


def find_old_card(path):
    """(x, y, w, h) of the factory's 4.5 s hook card in 1080x1920 pixels, or None."""
    on = frames(path, [0.6, 1.4, 2.2, 3.0, 3.8])
    off = frames(path, [5.0, 6.0])
    static = np.stack(on).std(axis=0) < 4
    gone = np.minimum(abs(on[-1] - off[0]), abs(on[-1] - off[1])) > 18
    mask = static & gone
    band = mask.sum(axis=1) > 25
    best, cur = None, None
    for y, b in enumerate(band):
        if b and cur is None:
            cur = y
        if (not b or y == len(band) - 1) and cur is not None:
            end = y if not b else y + 1
            if best is None or end - cur > best[1] - best[0]:
                best = (cur, end)
            cur = None
    if not best or best[1] - best[0] < 6:
        return None
    cols = mask[best[0]:best[1]].sum(axis=0) > 1
    xs = np.where(cols)[0]
    if not len(xs):
        return None
    s = W / mask.shape[1]
    # the scan finds the text; the card is a little bigger all round
    x0, x1 = max(2, int(xs[0] * s) - 40), min(W - 3, int(xs[-1] * s) + 40)
    y0, y1 = max(2, int(best[0] * s) - 45), min(H - 3, int(best[1] * s) + 30)
    return x0, y0, x1 - x0, y1 - y0


def fit(d, text, size, maxw):
    while size > 40:
        f = ImageFont.truetype(FONT, size)
        if d.textlength(text, font=f) <= maxw:
            return f
        size -= 2
    return ImageFont.truetype(FONT, size)


def card_png(hook, out):
    """The hook in a black box, white first line + gold second line, centred."""
    lines = [l.strip().upper() for l in hook if l.strip()][:2]
    if len(lines) == 1 and len(lines[0]) > 16:
        words = lines[0].split()
        k = (len(words) + 1) // 2
        lines = [" ".join(words[:k]), " ".join(words[k:])]
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = min((fit(d, l, 84, W - 170) for l in lines), key=lambda x: x.size)
    lh = int(f.size * 1.18)
    tw = max(d.textlength(l, font=f) for l in lines)
    bw, bh = int(tw + 90), lh * len(lines) + 56
    x0, y0 = (W - bw) // 2, CARD_Y
    d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), radius=26, fill=INK + (240,))
    y = y0 + 26
    for i, l in enumerate(lines):
        w = d.textlength(l, font=f)
        d.text(((W - w) / 2, y), l, font=f, fill=(WHITE if i == 0 and len(lines) > 1 else GOLD) + (255,))
        y += lh
    im.save(out)


def band_png(hook, out, label=None):
    """Style T: the hook in the navy title band, white line 1 + gold line 2.

    T2 passes `label` ("THE SUCCESS CLUB · LESSON 47"): a small gold line with
    thin rules either side across the top of the band, the hook under it."""
    lines = [l.strip().upper() for l in hook if l.strip()][:2]
    if len(lines) == 1 and len(lines[0]) > 16:
        words = lines[0].split()
        k = (len(words) + 1) // 2
        lines = [" ".join(words[:k]), " ".join(words[k:])]
    im = Image.new("RGBA", (W, BAND), INK + (255,))   # the owner's navy (#0B1430), not black (21 Oct)
    d = ImageDraw.Draw(im)
    top = 0
    if label:
        lf = ImageFont.truetype(FONT, 30)
        lw = d.textlength(label, font=lf)
        ly = 26
        d.text(((W - lw) / 2, ly), label, font=lf, fill=GOLD + (255,))
        mid = ly + 19
        d.line(((60, mid), ((W - lw) / 2 - 22, mid)), fill=GOLD + (170,), width=2)
        d.line((((W + lw) / 2 + 22, mid), (W - 60, mid)), fill=GOLD + (170,), width=2)
        top = 62
    f = min((fit(d, l, 78 if not label else 70, W - 120) for l in lines), key=lambda x: x.size)
    lh = int(f.size * 1.2)
    y = top + (BAND - top - lh * len(lines)) // 2 + 8
    for i, l in enumerate(lines):
        w = d.textlength(l, font=f)
        d.text(((W - w) / 2, y), l, font=f, fill=(WHITE if i == 0 and len(lines) > 1 else GOLD) + (255,))
        y += lh
    im.save(out)


def question_of(caption):
    """Our own reflection question from the caption (its last sentence ending '?')."""
    body = "\n".join(l for l in (caption or "").splitlines()
                     if l.strip() and not l.strip().startswith("#"))
    qs = re.findall(r"[^.!?\n\"]*\?", body)
    q = qs[-1].strip() if qs else ""
    return q if 12 <= len(q) <= 110 else ""


def _wrap(d, text, f, maxw):
    out, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= maxw or not cur:
            cur = t
        else:
            out.append(cur)
            cur = w
    return out + ([cur] if cur else [])


def outro_png(question, out):
    """T2 closing card: navy, gold label, our question in white, follow line."""
    im = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(im)
    lf = ImageFont.truetype(FONT, 40)
    y = 560
    lab = "ASK YOURSELF" if question else "THE SUCCESS CLUB"
    lw = d.textlength(lab, font=lf)
    d.text(((W - lw) / 2, y), lab, font=lf, fill=GOLD)
    d.line(((W - lw) / 2, y + 62, (W + lw) / 2, y + 62), fill=GOLD, width=3)
    y += 120
    text = (question or "One success principle a day changes everything.").upper()
    for size in range(78, 44, -4):
        f = ImageFont.truetype(FONT, size)
        lines = _wrap(d, text, f, W - 160)
        if len(lines) <= 5:
            break
    lh = int(f.size * 1.22)
    for l in lines:
        w = d.textlength(l, font=f)
        d.text(((W - w) / 2, y), l, font=f, fill=WHITE)
        y += lh
    y += 90
    ff = ImageFont.truetype(FONT, 44)
    for i, l in enumerate(["FOLLOW " + HANDLE.upper(), "A NEW SUCCESS PRINCIPLE EVERY DAY"]):
        w = d.textlength(l, font=ff if i == 0 else ImageFont.truetype(FONT, 32))
        d.text(((W - w) / 2, y), l, font=ff if i == 0 else ImageFont.truetype(FONT, 32),
               fill=GOLD if i == 0 else (200, 205, 220))
        y += 70
    im.save(out)


def lesson_of(man, c):
    """A stable lesson number per clip, counting on from everything already posted."""
    if not c.get("lesson"):
        have = [x.get("lesson") or 0 for x in man.get("clips", [])]
        posted = sum(1 for x in man.get("clips", []) if x.get("posted_at"))
        c["lesson"] = max(max(have or [0]), posted) + 1
    return c["lesson"]


# THE GRID COVER (21 Oct 2026, the owner: "we need to improve the cover of each
# video to have more reach", pointing at @trudeaumanifestation). Instagram's
# profile grid shows the MIDDLE 3:4 of a reel (rows 240-1680 of 1920), so the
# title bar at the very top of the video is cut off there, and the cover was a
# frame picked by timestamp - often mid-word. Each clip now gets its own cover
# image: the hook in big white + gold inside the part the grid shows, over the
# sharpest close-up of Kevin from the first seconds. Sent as cover_url.
COVER_TITLE = (250, 660)      # y range of the title block (inside the grid crop)
COVER_V = 4                   # bump to redo every queued cover
_DET = []


def _face_score(crop):
    """How good a cover face this is: Kevin facing the camera, eyes open, close.

    21 Oct 2026, the owner: some covers caught him looking down with his eyes
    half shut. YuNet gives the face and its eye/nose points; the nose centred
    between level eyes means he faces the camera, and a high-contrast patch at
    each eye means the eye is open (iris on white). Sharpness alone picked blinks.
    """
    import cv2
    if not _DET:
        _DET.append(cv2.FaceDetectorYN.create(os.path.join(ROOT, "factory", "assets", "yunet.onnx"),
                                              "", (540, 450), 0.6))
    hh, ww = crop.shape[:2]
    sw, sh_ = 540, int(540 * hh / ww)
    _DET[0].setInputSize((sw, sh_))
    small = cv2.resize(cv2.cvtColor(crop, cv2.COLOR_RGB2BGR), (sw, sh_))
    _, faces = _DET[0].detect(small)
    if faces is None:
        return 0.0, None
    f = max(faces, key=lambda r: r[2] * r[3])
    re_, le_, nose = (f[4], f[5]), (f[6], f[7]), (f[8], f[9])
    eyed = abs(le_[0] - re_[0]) or 1
    frontal = max(0.0, 1 - abs((nose[0] - (re_[0] + le_[0]) / 2) / eyed) * 2)
    level = max(0.0, 1 - abs(le_[1] - re_[1]) / eyed * 3)
    g = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)

    def eye(px, py):
        r = int(eyed * 0.22)
        patch = g[max(0, int(py - r)):int(py + r), max(0, int(px - r)):int(px + r)]
        return float(patch.std()) if patch.size else 0.0
    eyes = (eye(*re_) + eye(*le_)) / 2
    score = float(f[14]) * frontal * level * min(1.0, eyes / 30) * min(1.0, f[2] / 200)
    return score, (f[1] + f[3] * 0.45) * hh / sh_          # face centre, full-size rows


def _cover_lines(hook):
    words = " ".join(h.strip() for h in hook if h.strip()).upper().split()
    if len(" ".join(words)) <= 26 or len(words) < 3:
        n = 2
    else:
        n = 3
    n = min(n, len(words)) or 1
    k = -(-len(words) // n)
    return [" ".join(words[i:i + k]) for i in range(0, len(words), k)]


def _frame_rgb(path, t):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", path,
                          "-frames:v", "1", "-vf", f"scale={W}:{H}", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(H, W, 3) if len(raw) == W * H * 3 else None


def cover_jpg(styled, hook, out):
    """Grid cover from a style-T clip: title on top, Kevin's sharpest close-up below."""
    # 22 Oct: the window is placed around HIS FACE (found by YuNet), not at a
    # fixed height - fixed crops of tight close-ups showed only a forehead.
    PIC = H - COVER_TITLE[1]                     # 1260 rows of picture under the title
    best = None
    for t in np.arange(3.4, 16.0, 0.8):
        a = _frame_rgb(styled, float(t))
        if a is None:
            continue
        region = (a[T4_TOP:T4_TOP + T4_VID] if STYLE == "T4"   # Kevin's window only
                  else a[BAND:])                 # the video under the title band
        try:
            s, cy = _face_score(region)
        except Exception:
            s, cy = 0.0, None
        g = region[:900].astype(np.float32).mean(2)
        sharp = float(np.var(g[1:-1, 1:-1] * 4 - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]))
        key = (s, sharp)                         # best face first; sharpness breaks ties
        if best is None or key > best[0]:
            best = (key, region, cy)
    if best is None:
        raise RuntimeError("no frame for the cover")
    # The spoken word stays on the cover: Kevin's subtitles are on screen in
    # every frame, and the pages we copy show them on their grid too.
    region, cy = best[1], best[2]
    top = int(min(max((cy if cy is not None else 450) - 0.40 * 1020, 0), region.shape[0] - PIC))
    im = Image.new("RGB", (W, H), INK)
    im.paste(Image.fromarray(region[top:top + PIC]), (0, COVER_TITLE[1]))
    fade = Image.linear_gradient("L").resize((W, 90))
    im.paste(Image.new("RGB", (W, 90), INK), (0, COVER_TITLE[1]),
             Image.eval(fade, lambda v: 255 - v))
    d = ImageDraw.Draw(im)
    lines = _cover_lines(hook)
    f = min((fit(d, l, 120, W - 110) for l in lines), key=lambda x: x.size)
    lh = int(f.size * 1.16)
    y = COVER_TITLE[0] + (COVER_TITLE[1] - COVER_TITLE[0] - lh * len(lines)) // 2
    for i, l in enumerate(lines):
        w = d.textlength(l, font=f)
        d.text(((W - w) / 2, y), l, font=f, fill=GOLD if i == len(lines) - 1 else WHITE)
        y += lh
    im.save(out, quality=90)
    return out


def add_cover(c, hook, styled, tmp):
    """Make, upload and record the grid cover for one queued clip. Never fatal."""
    try:
        name = c["file"].replace("/", "--").replace(".mp4", "__cover.jpg")
        out = os.path.join(tmp, "covers", name)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        cover_jpg(styled, hook, out)
        sh("gh", "release", "upload", "media", out, "-R", REPO, "--clobber")
        c["cover"] = name
        c["cover_v"] = COVER_V
        print(f"cover {name}", flush=True)
    except Exception as e:
        print(f"  no cover for {c['file']}: {type(e).__name__} {str(e)[:120]}", flush=True)


def duration(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                capture_output=True, text=True, check=True).stdout.strip())


# STYLE T3 (27 Oct 2026). The owner: "continue posting and just make a
# differentiation". Every Kevin page posts the same full-screen clip with a
# title on top; ours now carries our own editorial layer around it: the lesson
# label and hook in the band, Kevin in a gold-framed window, and under him a
# "THE LESSON" panel with our own one-line takeaway (the first line of our
# caption, written for that clip), then the closing question card.
VID_BOX = (60, 372, 1020, 1572)      # x0, y0, x1, y1 of Kevin's window (960x1200)
LESSON_Y = 1610


def frame_t3_png(hook, label, takeaway, out):
    """The still layer of a T3 clip: band, gold frame, lesson panel."""
    band = out + ".band.png"
    band_png(hook, band, label=label)
    im = Image.new("RGB", (W, H), INK)
    im.paste(Image.open(band).convert("RGB"), (0, 0))
    os.remove(band)
    d = ImageDraw.Draw(im)
    x0, y0, x1, y1 = VID_BOX
    d.rounded_rectangle((x0 - 6, y0 - 6, x1 + 6, y1 + 6), radius=18, outline=GOLD, width=5)
    lf = ImageFont.truetype(FONT, 34)
    lab = "THE LESSON"
    lw = d.textlength(lab, font=lf)
    d.text(((W - lw) / 2, LESSON_Y), lab, font=lf, fill=GOLD)
    d.line((90, LESSON_Y + 21, (W - lw) / 2 - 20, LESSON_Y + 21), fill=GOLD, width=2)
    d.line(((W + lw) / 2 + 20, LESSON_Y + 21, W - 90, LESSON_Y + 21), fill=GOLD, width=2)
    text = (takeaway or "").strip()
    for size in range(54, 30, -2):
        f = ImageFont.truetype(FONT, size)
        words, lines, cur = text.split(), [], ""
        for w_ in words:
            t = (cur + " " + w_).strip()
            if d.textlength(t, font=f) <= W - 140 or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = w_
        lines += [cur] if cur else []
        if len(lines) <= 3:
            break
    y = LESSON_Y + 70
    for l in lines[:3]:
        w_ = d.textlength(l, font=f)
        d.text(((W - w_) / 2, y), l, font=f, fill=WHITE)
        y += int(f.size * 1.22)
    im.save(out)


def takeaway_of(caption):
    """Our own one-line takeaway: the caption's first real sentence (we wrote it)."""
    for l in (caption or "").splitlines():
        l = l.strip()
        if not l or l.startswith("#") or l.lower().startswith(("comment ", "ad:")):
            continue
        return l if len(l) <= 120 else l[:117].rsplit(" ", 1)[0] + "..."
    return ""


def restyle_t3(src, hook, dst, label, question, takeaway, prior=None):
    """T3: Kevin in a gold frame between our band and our lesson panel, then the card.

    `prior`: the style src already carries. A T1/T2 clip already has the band
    (and T2 the closing card), so only the picture under the band is taken and
    any old closing card is cut off before the new one goes on."""
    still, card = dst + ".t3.png", dst + ".outro.png"
    frame_t3_png(hook, label, takeaway, still)
    outro_png(question, card)
    full = duration(src)
    keep = full - (OUTRO_SECS if prior == "T2" else 0)
    # the window shows 4:5 of the picture: his face and the spoken subtitles
    crop_y = 420 if prior in ("T1", "T2") else 160
    sh("ffmpeg", "-loglevel", "error", "-y", "-t", f"{keep:.2f}", "-i", src, "-i", still,
       "-loop", "1", "-framerate", "30", "-t", f"{OUTRO_SECS}", "-i", card,
       "-f", "lavfi", "-t", f"{OUTRO_SECS}", "-i", "anullsrc=r=48000:cl=stereo",
       "-filter_complex",
       f"[0:v]scale={W}:{H},setsar=1,crop={W}:1350:0:{crop_y},scale=960:1200,setsar=1[k];"
       f"[1:v][k]overlay={VID_BOX[0]}:{VID_BOX[1]},fps=30,format=yuv420p[m];"
       f"[2:v]scale={W}:{H},setsar=1,fps=30,format=yuv420p,fade=t=in:st=0:d=0.3[o];"
       f"[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a0];"
       f"[3:a]aformat=sample_fmts=fltp:channel_layouts=stereo[a1];"
       f"[m][a0][o][a1]concat=n=2:v=1:a=1[v][a]",
       "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
       "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", dst)
    os.remove(still)
    os.remove(card)


# STYLE T4 (27 Oct 2026), the owner on T3: "more professional". Editorial, not
# loud: a quiet header (club name, lesson number, the hook set left and smaller),
# Kevin edge to edge in a 4:5 window between two thin gold rules, and a
# documentary lower third (name, title, our handle). No boxes, no panels.
T4_TOP, T4_VID = 285, 1350           # header height; Kevin's window height (4:5)


def _spaced(d, xy, text, font, fill, track=4):
    """Text with letter spacing (PIL has none)."""
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill)
        x += d.textlength(ch, font=font) + track
    return x


def _spaced_len(d, text, font, track=4):
    return sum(d.textlength(ch, font=font) + track for ch in text) - track


def frame_t4_png(hook, lesson_no, out, name="KEVIN TRUDEAU",
                 title="Author · Your Wish Is Your Command", handle="@thesuccessclubco"):
    im = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(im)
    m = 72                                         # side margin
    small = ImageFont.truetype(FONT, 24)
    _spaced(d, (m, 62), "THE SUCCESS CLUB", small, GOLD, track=5)
    no = f"LESSON {lesson_no}" if lesson_no else ""
    if no:
        _spaced(d, (W - m - _spaced_len(d, no, small, 5), 62), no, small, (150, 160, 185), track=5)
    lines = [l.strip() for l in hook if l.strip()][:2]
    if len(lines) == 1 and len(lines[0]) > 18:
        ws = lines[0].split()
        k = (len(ws) + 1) // 2
        lines = [" ".join(ws[:k]), " ".join(ws[k:])]
    lines = [l.upper() for l in lines]
    f = min((fit(d, l, 60, W - 2 * m) for l in lines), key=lambda x: x.size)
    y = 118
    for i, l in enumerate(lines):
        d.text((m, y), l, font=f, fill=WHITE if i == 0 and len(lines) > 1 else GOLD)
        y += int(f.size * 1.16)
    # thin rules framing Kevin's window
    d.line((0, T4_TOP - 2, W, T4_TOP - 2), fill=GOLD, width=2)
    yb = T4_TOP + T4_VID
    d.line((0, yb + 1, W, yb + 1), fill=GOLD, width=2)
    # lower third
    d.line((m, yb + 62, m + 64, yb + 62), fill=GOLD, width=4)
    nf = ImageFont.truetype(FONT, 38)
    _spaced(d, (m, yb + 84), name, nf, WHITE, track=3)
    tf = ImageFont.truetype(FONT, 25)
    d.text((m, yb + 140), title, font=tf, fill=(160, 170, 195))
    hw = d.textlength(handle, font=tf)
    d.text((W - m - hw, yb + 140), handle, font=tf, fill=GOLD)
    im.save(out)


# ENERGY (27 Oct 2026, the owner: "let put energy in the post, so it can become
# viral, let beat our best post"). Our two best reels were watched to 73% and
# 62% (36.5 s of 50, 19.8 s of 32); a typical reel is watched to ~30%. So the
# edit keeps them watching: every pause cut out (jump cuts), a punch-in zoom
# on every other cut so the frame keeps moving, 7% faster, and a gold
# progress bar so the end is always in sight.
EN_SPEED = float(os.environ.get("EN_SPEED", "1.07"))
EN_ZOOM = 1.12
EN_GAP = 0.32          # a silence longer than this is cut
EN_PAD = 0.07          # breath kept either side of speech


def _speech_spans(path, total):
    """Spans with speech, from ffmpeg silencedetect."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af",
                        f"silencedetect=noise=-32dB:d={EN_GAP}", "-f", "null", "-"],
                       capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    spans, t = [], 0.0
    for s, e in zip(starts, ends + [total] * (len(starts) - len(ends))):
        if s - t > 0.15:
            spans.append((max(0.0, t - EN_PAD), min(total, s + EN_PAD)))
        t = e
    if total - t > 0.15:
        spans.append((max(0.0, t - EN_PAD), total))
    merged = []
    for a, b in spans:                       # join tiny gaps so it never stutters
        if merged and a - merged[-1][1] < 0.12:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return merged or [(0.0, total)]


def energize(src, out, crop_y, keep):
    """Kevin's 1080x1350 window with the pauses cut, alternating punch-ins, faster."""
    spans = _speech_spans(src, keep)
    zw, zh = int(W / EN_ZOOM) // 2 * 2, int(T4_VID / EN_ZOOM) // 2 * 2
    parts, labels = [], []
    for i, (a, b) in enumerate(spans):
        base = f"[0:v]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS,scale={W}:{H},setsar=1,crop={W}:{T4_VID}:0:{crop_y}"
        if i % 2:   # punch in, a little above centre so his eyes stay in frame
            base += f",crop={zw}:{zh}:{(W - zw) // 2}:{int((T4_VID - zh) * 0.35)},scale={W}:{T4_VID}"
        parts.append(base + f",setsar=1[v{i}];[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    fc = ";".join(parts) + ";" + "".join(labels) + f"concat=n={len(spans)}:v=1:a=1[cv][ca];" \
        f"[cv]setpts=PTS/{EN_SPEED}[sv];[ca]atempo={EN_SPEED}[sa]"
    sh("ffmpeg", "-loglevel", "error", "-y", "-t", f"{keep:.2f}", "-i", src, "-filter_complex", fc,
       "-map", "[sv]", "-map", "[sa]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
       "-c:a", "aac", "-b:a", "160k", out)
    return duration(out), len(spans)


def restyle_t4(src, hook, dst, lesson_no, question, prior=None, energy=True):
    """T4: the editorial frame around Kevin edge to edge, then the closing card."""
    still, card = dst + ".t4.png", dst + ".outro.png"
    frame_t4_png(hook, lesson_no, still)
    outro_png(question, card)
    full = duration(src)
    keep = full - (OUTRO_SECS if prior == "T2" else 0)
    crop_y = 400 if prior in ("T1", "T2") else 150
    if energy:
        win = dst + ".win.mp4"
        clip_len, _ = energize(src, win, crop_y, keep)
        vin, vsel, tlim = win, "[0:v]setsar=1[k];", []
    else:
        clip_len = keep
        vin, vsel, tlim = src, f"[0:v]scale={W}:{H},setsar=1,crop={W}:{T4_VID}:0:{crop_y},setsar=1[k];", \
            ["-t", f"{keep:.2f}"]
    bar_y = T4_TOP + T4_VID - 8
    sh("ffmpeg", "-loglevel", "error", "-y", *tlim, "-i", vin, "-i", still,
       "-loop", "1", "-framerate", "30", "-t", f"{OUTRO_SECS}", "-i", card,
       "-f", "lavfi", "-t", f"{OUTRO_SECS}", "-i", "anullsrc=r=48000:cl=stereo",
       "-f", "lavfi", "-i", f"color=c=0xF5C518:s={W}x8:r=30",
       "-filter_complex",
       vsel +
       f"[1:v][k]overlay=0:{T4_TOP},fps=30[m0];"
       # gold progress bar: slides in from the left over the length of the clip
       f"[m0][4:v]overlay=x='-{W}+{W}*t/{clip_len:.3f}':y={bar_y}:shortest=1,format=yuv420p[m];"
       f"[2:v]scale={W}:{H},setsar=1,fps=30,format=yuv420p,fade=t=in:st=0:d=0.3[o];"
       f"[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a0];"
       f"[3:a]aformat=sample_fmts=fltp:channel_layouts=stereo[a1];"
       f"[m][a0][o][a1]concat=n=2:v=1:a=1[v][a]",
       "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
       "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", dst)
    os.remove(still)
    os.remove(card)
    if energy:
        os.remove(win)


def restyle_t2(src, hook, dst, label, question, from_t1=False):
    """T2: title band with the lesson label over the video, then the closing card.

    `from_t1`: src is already a T1 clip (band on top, video under it) - only the
    band is replaced, nothing is cropped twice."""
    band, card = dst + ".band.png", dst + ".outro.png"
    band_png(hook, band, label=label)
    outro_png(question, card)
    base = ("[0:v]scale=1080:1920,setsar=1" if from_t1 else
            f"[0:v]scale={W}:{H},crop={W}:{H - BAND}:0:{TRIM_TOP},pad={W}:{H}:0:{BAND}:0x0B1430,setsar=1")
    sh("ffmpeg", "-loglevel", "error", "-y", "-i", src, "-i", band,
       "-loop", "1", "-framerate", "30", "-t", f"{OUTRO_SECS}", "-i", card,
       "-f", "lavfi", "-t", f"{OUTRO_SECS}", "-i", "anullsrc=r=48000:cl=stereo",
       "-filter_complex",
       f"{base}[b];[b][1:v]overlay=0:0,fps=30,format=yuv420p[m];"
       f"[2:v]scale={W}:{H},setsar=1,fps=30,format=yuv420p,fade=t=in:st=0:d=0.3[o];"
       f"[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a0];"
       f"[3:a]aformat=sample_fmts=fltp:channel_layouts=stereo[a1];"
       f"[m][a0][o][a1]concat=n=2:v=1:a=1[v][a]",
       "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
       "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", dst)
    os.remove(band)
    os.remove(card)


def restyle(src, hook, dst, check=True):
    # The factory's old card always sat ABOVE the spoken captions (its bottom
    # edge at y930), so a "card" found lower down is a caption that paused on
    # screen, not a card (10 Oct: strongcreditfile was skipped for exactly that).
    # Clean re-renders from redo_ builds skip the check altogether.
    card = find_old_card(src) if check else None
    if card and card[1] > 980:
        card = None
    if card:
        # Painting the old card out smeared his face on real clips (10 Oct test).
        # A clip that still has it waits for a clean re-render instead.
        raise RuntimeError(f"old hook card still burned in at {card}")
    png = dst + ".png"
    if STYLE.startswith("T"):
        band_png(hook, png)
        sh("ffmpeg", "-loglevel", "error", "-y", "-i", src, "-i", png, "-filter_complex",
           f"[0:v]scale={W}:{H},crop={W}:{H - BAND}:0:{TRIM_TOP},pad={W}:{H}:0:{BAND}:0x0B1430[b];"
           f"[b][1:v]overlay=0:0,format=yuv420p[v]",
           "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-c:a", "copy", "-movflags", "+faststart", dst)
        os.remove(png)
        return None
    card_png(hook, png)
    dur = duration(src)
    sh("ffmpeg", "-loglevel", "error", "-y", "-i", src, "-loop", "1", "-framerate", "30",
       "-t", f"{CARD_SECS:.2f}", "-i", png, "-filter_complex",
       f"[0:v][1:v]overlay=0:0:eof_action=pass:enable='lt(t,{CARD_SECS})',format=yuv420p[v]",
       "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
       "-c:a", "copy", "-movflags", "+faststart", dst)
    os.remove(png)
    return None


def hooks_index():
    idx, brands = {}, {}
    for p in glob.glob(os.path.join(ROOT, "factory", "plans", "*.json")):
        key = os.path.basename(p)[:-5]
        if key.startswith("_"):
            continue
        try:
            d = json.load(open(p))
        except Exception:
            continue
        brands[key] = d.get("brand")
        for c in d.get("clips", []):
            idx.setdefault((d.get("brand"), c.get("slug")), c.get("hook"))
    # Hook rewrites for clips already built (factory/hooks.json, "BRAND/slug": [lines]).
    # 10 Oct 2026: every hook now carries a high-interest word (money, success, ...).
    hp = os.path.join(ROOT, "factory", "hooks.json")
    if os.path.exists(hp):
        for k, v in json.load(open(hp)).items():
            b, s = k.split("/", 1)
            idx[(b, s)] = v
    return idx, brands


def slug_of(file):
    brand, name = file.split("/", 1)
    s = re.sub(r"^\d+_", "", name)
    s = re.sub(r"_\d+s\.mp4$", "", s)
    return brand, s


def originals(plan_brands, tmp):
    """(brand, slug) -> a clean render of that clip from a factory "redo_" test build.

    Clips styled before style D were re-rendered from the source episode with the
    factory's hook card switched off (plans factory/plans/redo_*.json, test=true, so
    they are never queued twice). Only those builds count: an older build still
    has the card burned in, and painting it out smears his face.
    """
    found = {}
    runs = subprocess.run(["gh", "run", "list", "-R", REPO, "--workflow", "factory.yml", "-L", "40",
                           "--json", "databaseId"], capture_output=True, text=True)
    for r in json.loads(runs.stdout or "[]"):                 # newest first
        d = os.path.join(tmp, "runs", str(r["databaseId"]))
        if subprocess.run(["gh", "run", "download", str(r["databaseId"]), "-R", REPO, "-p", "shard-redo_*",
                           "-D", d], capture_output=True).returncode:
            continue
        for f in glob.glob(os.path.join(d, "**", "*.mp4"), recursive=True):
            m = re.search(r"shard-(redo_.+)-\d+", f)
            brand = plan_brands.get(m[1]) if m else None
            name = os.path.basename(f)
            if brand and "__" not in name:
                b, sl = slug_of(f"{brand}/{name}")
                found.setdefault((b, sl), f)
                # A published clip is locked against re-rendering (kt_render), so
                # repost re-renders use the slug + "rp"; map them back.
                if sl.endswith("rp"):
                    found.setdefault((b, sl[:-2]), f)
    return found


def main():
    if "--local" in sys.argv:
        i = sys.argv.index("--local")
        src, hook = sys.argv[i + 1], sys.argv[i + 2].split("|")
        print(restyle(src, hook, src.replace(".mp4", "_E.mp4")))
        return
    limit = int(os.environ.get("RESTYLE_LIMIT", "40"))
    man = json.load(open(MAN, encoding="utf-8"))
    idx, plan_brands = hooks_index()
    todo = [c for c in man.get("clips", [])
            if not c.get("done") and not c.get("posting") and c.get("style") != STYLE
            and not any("posted" in str(v) for v in (c.get("status") or {}).values())]
    tmp = tempfile.mkdtemp()
    orig = originals(plan_brands, tmp)
    print(f"{len(todo)} clip(s) to style; {len(orig)} original(s) recovered from factory builds")
    done, skipped = 0, []
    for c in todo[:limit]:
        hook = idx.get(slug_of(c["file"]))
        if not hook:
            skipped.append(f"{c['file']}: no hook on file")
            continue
        asset = c["file"].replace("/", "--")
        src, dst = os.path.join(tmp, asset), os.path.join(tmp, "out_" + asset)
        clean = False
        if STYLE == "T4":
            # T4 = the editorial frame + the energy edit (27 Oct 2026). A T1/T2 clip
            # already has our band; only the picture under it is used again.
            prior = c.get("style") if c.get("style") in ("T1", "T2") else None
            if c.get("style") not in (None, "none", "T1", "T2"):
                if slug_of(c["file"]) not in orig:
                    skipped.append(f"{c['file']}: styled {c.get('style')} and no clean re-render yet - left as is")
                    continue
                src = orig[slug_of(c["file"])]
            else:
                sh("gh", "release", "download", "media", "-R", REPO, "-p", asset, "-O", src, "--clobber")
            try:
                restyle_t4(src, hook, dst, lesson_of(man, c), question_of(c.get("caption", "")), prior=prior)
            except Exception as e:
                skipped.append(f"{c['file']}: {type(e).__name__} {str(e)[:120]}")
                continue
            card = None
        elif STYLE == "T2" and c.get("style") == "T1":
            # Upgrade in place: the T1 file already has the band and the crop.
            sh("gh", "release", "download", "media", "-R", REPO, "-p", asset, "-O", src, "--clobber")
            try:
                restyle_t2(src, hook, dst, f"THE SUCCESS CLUB · LESSON {lesson_of(man, c)}",
                           question_of(c.get("caption", "")), from_t1=True)
            except Exception as e:
                skipped.append(f"{c['file']}: {type(e).__name__} {str(e)[:120]}")
                continue
            card = None
        elif c.get("style") not in (None, "none"):
            if slug_of(c["file"]) not in orig:
                skipped.append(f"{c['file']}: styled before and no clean re-render yet - left as is")
                continue
            src = orig[slug_of(c["file"])]
            clean = True
        else:
            sh("gh", "release", "download", "media", "-R", REPO, "-p", asset, "-O", src, "--clobber")
        if STYLE != "T4" and not (STYLE == "T2" and c.get("style") == "T1"):
            try:
                if STYLE == "T2":
                    restyle_t2(src, hook, dst, f"THE SUCCESS CLUB · LESSON {lesson_of(man, c)}",
                               question_of(c.get("caption", "")))
                    card = None
                else:
                    card = restyle(src, hook, dst, check=False)
            except Exception as e:
                skipped.append(f"{c['file']}: {type(e).__name__} {str(e)[:120]}")
                continue
        up = os.path.join(tmp, "up", asset)
        os.makedirs(os.path.dirname(up), exist_ok=True)
        os.replace(dst, up)
        sh("gh", "release", "upload", "media", up, "-R", REPO, "--clobber")
        c["style"] = STYLE
        if STYLE.startswith("T"):
            add_cover(c, hook, up, tmp)
        c["bytes"] = os.path.getsize(up)
        done += 1
        print(f"styled {c['file']}" + (f"  (old card painted out at {card})" if card else ""), flush=True)
        os.remove(up)
        with open(MAN, "w", encoding="utf-8") as f:
            json.dump(man, f, indent=1, ensure_ascii=False)
    # COVERS for clips styled before covers existed (queued, style T, no cover).
    for c in man.get("clips", []):
        if (c.get("done") or c.get("posting") or c.get("cover_v") == COVER_V or c.get("style") != STYLE
                or not STYLE.startswith("T")
                or any("posted" in str(v) for v in (c.get("status") or {}).values())):
            continue
        hook = idx.get(slug_of(c["file"]))
        if not hook:
            continue
        asset = c["file"].replace("/", "--")
        src = os.path.join(tmp, "cv_" + asset)
        if subprocess.run(["gh", "release", "download", "media", "-R", REPO, "-p", asset,
                           "-O", src, "--clobber"], capture_output=True).returncode:
            continue
        add_cover(c, hook, src, tmp)
        os.remove(src)
        with open(MAN, "w", encoding="utf-8") as f:
            json.dump(man, f, indent=1, ensure_ascii=False)
    # REPOSTS. 10 Oct 2026, the owner: "lets reposted them ... with the new version".
    # Clips listed in factory/repost.json go out again in the new look, as NEW
    # queue entries (new file name, same caption), once each.
    rp = os.path.join(ROOT, "factory", "repost.json")
    for f in (json.load(open(rp)) if os.path.exists(rp) else []):
        if any(c.get("repost_of") == f for c in man["clips"]):
            continue
        old = next((c for c in man["clips"] if c["file"] == f), None)
        hook = idx.get(slug_of(f))
        if not old or not hook or slug_of(f) not in orig:
            skipped.append(f"repost {f}: not ready (clean re-render or hook missing)")
            continue
        brand, name = f.split("/", 1)
        new = f"{brand}/" + re.sub(r"^\d+_", "91_", name)
        dst = os.path.join(tmp, "up", new.replace("/", "--"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        restyle(orig[slug_of(f)], hook, dst, check=False)
        sh("gh", "release", "upload", "media", dst, "-R", REPO, "--clobber")
        entry = {"file": new, "caption": old.get("caption", ""), "bytes": os.path.getsize(dst),
                 "done": False, "status": {}, "style": STYLE, "repost_of": f}
        if old.get("cta_kind"):
            entry["cta_kind"] = old["cta_kind"]
        man["clips"].append(entry)
        with open(MAN, "w", encoding="utf-8") as fh:
            json.dump(man, fh, indent=1, ensure_ascii=False)
        print(f"repost queued: {new} (was {f})", flush=True)
    print(f"restyle: {done} clip(s) styled")
    for s in skipped:
        print("  skipped", s)


if __name__ == "__main__":
    main()
