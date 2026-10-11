#!/usr/bin/env python3
"""THE SUCCESS CLUB LOOK (style D): Kevin's video on top, the hook frame BELOW it.

10 Oct 2026, the owner, after style C went live: "the face of kevin is not been
seen ... put it below the video, in all new clips". Style C laid a hook bar over
the picture; on some clips it sat on his face. Style D never draws on the
picture at all:

    y    0-130   black, club name
    y  130-1230  the video: rows 40-1140 of the rendered clip (his head down to
                 the spoken captions, which the factory burns at ~y1070)
    y 1230-1242  gold progress bar
    y 1242-1600  the hook frame: hook in big white + gold, gold rule, club name
    y 1600-1920  black - where Instagram/TikTok print the caption and buttons

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
STYLE = "D1"
W, H = 1080, 1920
GOLD, INK, WHITE, GREY = (245, 197, 24), (12, 12, 14), (255, 255, 255), (165, 165, 165)
HOOK_SECS = 4.5
SRC_Y, VID_H, VID_Y = 40, 1100, 130          # rows taken from the clip / where they go
BAR_Y = VID_Y + VID_H                        # progress bar
FRAME_Y = BAR_Y + 12                         # hook frame


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


def frame_png(hook, out):
    lines = [l.strip().upper() for l in hook if l.strip()][:2]
    if len(lines) == 1 and len(lines[0]) > 16:
        words = lines[0].split()
        k = (len(words) + 1) // 2
        lines = [" ".join(words[:k]), " ".join(words[k:])]
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    small = ImageFont.truetype(FONT, 30)
    t = "THE SUCCESS CLUB"
    d.text(((W - d.textlength(t, font=small)) / 2, 62), t, font=small, fill=GOLD + (255,))
    f = min((fit(d, l, 92, W - 100) for l in lines), key=lambda x: x.size)
    lh = int(f.size * 1.17)
    y = FRAME_Y + 54
    for i, l in enumerate(lines):
        w = d.textlength(l, font=f)
        d.text(((W - w) / 2, y), l, font=f, fill=(WHITE if i == 0 and len(lines) > 1 else GOLD) + (255,))
        y += lh
    d.rectangle((W / 2 - 90, y + 22, W / 2 + 90, y + 30), fill=GOLD + (255,))
    t2 = "KEVIN TRUDEAU"
    d.text(((W - d.textlength(t2, font=small)) / 2, y + 50), t2, font=small, fill=GREY + (255,))
    im.save(out)


def duration(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                capture_output=True, text=True, check=True).stdout.strip())


def restyle(src, hook, dst):
    card = find_old_card(src)
    if card:
        # Painting the old card out smeared his face on real clips (10 Oct test).
        # A clip that still has it waits for a clean re-render instead.
        raise RuntimeError(f"old hook card still burned in at {card}")
    png = dst + ".png"
    frame_png(hook, png)
    dur = duration(src)
    clean = ""
    fc = (f"color=c=0x0C0C0E:s={W}x{H}:r=30:d={dur:.2f}[bg];"
          f"[0:v]{clean}crop={W}:{VID_H}:0:{SRC_Y}[vid];"
          f"[bg][vid]overlay=0:{VID_Y}[a];"
          f"[a][1:v]overlay=0:0[b];"
          f"color=c=0xF5C518:s={W}x12:r=30[g];"
          f"[b][g]overlay=x='-w+w*t/{dur:.2f}':y={BAR_Y}:shortest=1,format=yuv420p[v]")
    sh("ffmpeg", "-loglevel", "error", "-y", "-i", src, "-i", png, "-filter_complex", fc,
       "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
       "-c:a", "copy", "-movflags", "+faststart", "-t", f"{dur:.2f}", dst)
    os.remove(png)
    return card


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
                found.setdefault(slug_of(f"{brand}/{name}"), f)
    return found


def main():
    if "--local" in sys.argv:
        i = sys.argv.index("--local")
        src, hook = sys.argv[i + 1], sys.argv[i + 2].split("|")
        print(restyle(src, hook, src.replace(".mp4", "_D.mp4")))
        return
    limit = int(os.environ.get("RESTYLE_LIMIT", "40"))
    man = json.load(open(MAN, encoding="utf-8"))
    idx, plan_brands = hooks_index()
    todo = [c for c in man.get("clips", [])
            if not c.get("done") and not c.get("posting") and c.get("style") != STYLE]
    tmp = tempfile.mkdtemp()
    orig = originals(plan_brands, tmp) if any(c.get("style") not in (None, "none") for c in todo) else {}
    print(f"{len(todo)} clip(s) to style; {len(orig)} original(s) recovered from factory builds")
    done, skipped = 0, []
    for c in todo[:limit]:
        hook = idx.get(slug_of(c["file"]))
        if not hook:
            skipped.append(f"{c['file']}: no hook on file")
            continue
        asset = c["file"].replace("/", "--")
        src, dst = os.path.join(tmp, asset), os.path.join(tmp, "out_" + asset)
        if c.get("style") not in (None, "none"):
            if slug_of(c["file"]) not in orig:
                skipped.append(f"{c['file']}: styled before and no clean re-render yet - left as is")
                continue
            src = orig[slug_of(c["file"])]
        else:
            sh("gh", "release", "download", "media", "-R", REPO, "-p", asset, "-O", src, "--clobber")
        try:
            card = restyle(src, hook, dst)
        except Exception as e:
            skipped.append(f"{c['file']}: {type(e).__name__} {str(e)[:120]}")
            continue
        up = os.path.join(tmp, "up", asset)
        os.makedirs(os.path.dirname(up), exist_ok=True)
        os.replace(dst, up)
        sh("gh", "release", "upload", "media", up, "-R", REPO, "--clobber")
        c["style"] = STYLE
        c["bytes"] = os.path.getsize(up)
        done += 1
        print(f"styled {c['file']}" + (f"  (old card painted out at {card})" if card else ""), flush=True)
        os.remove(up)
        with open(MAN, "w", encoding="utf-8") as f:
            json.dump(man, f, indent=1, ensure_ascii=False)
    print(f"restyle: {done} clip(s) styled")
    for s in skipped:
        print("  skipped", s)


if __name__ == "__main__":
    main()
