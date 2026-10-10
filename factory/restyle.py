#!/usr/bin/env python3
"""THE SUCCESS CLUB LOOK (style C), applied to finished clips.

10 Oct 2026, the owner picked style C: a solid black hook bar with the hook in
big white + gold letters, a gold rule, the club name, and a gold progress bar
along the bottom. The point is that the clips look like OUR channel, not one
more repost of Kevin's footage - Instagram cuts the reach of reposts.

The factory still burns its small hook box for the first 4.5 s, placed away
from Kevin's face. We find that box (static and dark while it shows, gone right
after) and lay the new bar over it, so the old box is covered completely and
the bar sits where the face-aware placement already proved there is room. The
bar then stays for the whole clip.

A clip where the old box can't be found is left untouched and reported.

    python factory/restyle.py               # every queued clip without a style
    python factory/restyle.py --local a.mp4 "Line One|Line Two"   # test one file
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
STYLE = "C1"
W, H = 1080, 1920
GOLD, INK, WHITE = (245, 197, 24), (12, 12, 14), (255, 255, 255)
HOOK_SECS = 4.5
CAPTION_TOP = 1000        # spoken captions sit around y 1040-1110: never cover them
TOP_MIN = 150             # clear of the platform's own header


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


def find_old_hook(path):
    """(y0, y1) of the factory's hook box in 1920-px coordinates, or None."""
    on = frames(path, [0.6, 1.4, 2.2, 3.0, 3.8])
    off = frames(path, [5.0, 6.0])
    stack = np.stack(on)
    static = stack.std(axis=0) < 4
    gone = np.minimum(abs(on[-1] - off[0]), abs(on[-1] - off[1])) > 18
    mask = static & gone
    rows = mask.sum(axis=1)
    scale = H / mask.shape[0]
    band = rows > 25
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
    y0, y1 = best[0] * scale, best[1] * scale
    if y1 > CAPTION_TOP + 40 or y0 < 60:
        return None
    return int(y0), int(y1)


def faces(path, dur):
    """Face boxes (y0, y1) in 1920-px coordinates, sampled every 2 s after the old hook."""
    import cv2
    det = cv2.FaceDetectorYN_create(os.path.join(ROOT, "factory", "assets", "yunet.onnx"),
                                    "", (360, 640), 0.6, 0.3, 5000)
    out, t = [], HOOK_SECS + 0.5
    while t < dur - 0.5:
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", path, "-frames:v", "1",
                              "-vf", "scale=360:640", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                             capture_output=True, check=True).stdout
        img = np.frombuffer(raw, np.uint8).reshape(640, 360, 3)
        _, found = det.detect(img)
        if found is not None and len(found):
            x, y, w, h = max(found, key=lambda f: f[2] * f[3])[:4]
            # forehead to chin, plus room for the top of the head
            out.append(((y - 0.45 * h) * 3, (y + h) * 3))
        t += 2.0
    return out


def best_y(bar_h, face_boxes, y_now):
    """Where the bar should sit after the old hook: overlapping the face least."""
    if not face_boxes:
        return y_now
    def cost(y):
        return sum(max(0, min(y + bar_h, b) - max(y, a)) for a, b in face_boxes)
    cands = [y_now] + list(range(TOP_MIN, CAPTION_TOP - bar_h + 1, 20))
    return min(cands, key=lambda y: (cost(y), abs(y - y_now)))


def fit(d, text, size, maxw):
    while size > 40:
        f = ImageFont.truetype(FONT, size)
        if d.textlength(text, font=f) <= maxw:
            return f
        size -= 2
    return ImageFont.truetype(FONT, size)


def overlay_png(hook, old, out):
    lines = [l.strip().upper() for l in hook if l.strip()][:2]
    if len(lines) == 1 and len(lines[0]) > 16:      # one long line reads better as two
        words = lines[0].split()
        k = (len(words) + 1) // 2
        lines = [" ".join(words[:k]), " ".join(words[k:])]
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = min((fit(d, l, 84, W - 110) for l in lines), key=lambda x: x.size)
    lh = int(f.size * 1.18)
    bar_h = 34 + 14 + 24 + lh * len(lines) + 16 + 34 + 30
    old = (old[0] - 40, old[1] + 20)    # the scan finds the text rows; the box is a bit taller
    mid = (old[0] + old[1]) / 2
    y0 = int(max(TOP_MIN, min(mid - bar_h / 2, CAPTION_TOP - bar_h)))
    y0 = min(y0, old[0] - 10) if old[1] - old[0] + 20 <= bar_h else y0
    y0 = max(TOP_MIN, min(y0, CAPTION_TOP - bar_h))
    y1 = y0 + bar_h
    d.rectangle((0, y0, W, y1), fill=INK + (255,))
    d.rectangle((90, y0 + 34, W - 90, y0 + 46), fill=GOLD + (255,))
    y = y0 + 34 + 14 + 24
    for i, l in enumerate(lines):
        w = d.textlength(l, font=f)
        d.text(((W - w) / 2, y), l, font=f, fill=(WHITE if i == 0 and len(lines) > 1 else GOLD) + (255,))
        y += lh
    tag = ImageFont.truetype(FONT, 28)
    t = "THE SUCCESS CLUB"
    d.text(((W - d.textlength(t, font=tag)) / 2, y + 16), t, font=tag, fill=(170, 170, 170, 255))
    im.save(out)
    return y0, y1, bar_h


def duration(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                capture_output=True, text=True, check=True).stdout.strip())


def restyle(src, hook, dst):
    old = find_old_hook(src)
    if not old:
        return None
    png = dst + ".png"
    y0, y1, bar_h = overlay_png(hook, old, png)
    dur = duration(src)
    later = best_y(bar_h, faces(src, dur), y0)
    dy = later - y0           # after the old hook is gone, step the bar off Kevin's face
    sh("ffmpeg", "-loglevel", "error", "-y", "-i", src, "-i", png, "-filter_complex",
       f"[0:v][1:v]overlay=x=0:y='if(lt(t,{HOOK_SECS}),0,{dy})'[a];color=c=0xF5C518:s={W}x14:r=30[g];"
       f"[a][g]overlay=x='-w+w*t/{dur:.2f}':y={H - 14}:shortest=1,format=yuv420p[v]",
       "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
       "-c:a", "copy", "-movflags", "+faststart", dst)
    os.remove(png)
    return old, (y0, y1), later


def hooks_index():
    idx = {}
    for p in glob.glob(os.path.join(ROOT, "factory", "plans", "*.json")):
        if p.endswith("_done.json"):
            continue
        try:
            d = json.load(open(p))
        except Exception:
            continue
        for c in d.get("clips", []):
            idx.setdefault((d.get("brand"), c.get("slug")), c.get("hook"))
    return idx


def slug_of(file):
    brand, name = file.split("/", 1)
    s = re.sub(r"^\d+_", "", name)
    s = re.sub(r"_\d+s\.mp4$", "", s)
    return brand, s


def main():
    if "--local" in sys.argv:
        i = sys.argv.index("--local")
        src, hook = sys.argv[i + 1], sys.argv[i + 2].split("|")
        print(restyle(src, hook, src.replace(".mp4", "_C.mp4")))
        return
    limit = int(os.environ.get("RESTYLE_LIMIT", "30"))
    man = json.load(open(MAN, encoding="utf-8"))
    idx = hooks_index()
    done, skipped = 0, []
    tmp = tempfile.mkdtemp()
    for c in man.get("clips", []):
        if done >= limit:
            break
        if c.get("done") or c.get("style") or c.get("posting"):
            continue
        hook = idx.get(slug_of(c["file"]))
        if not hook:
            skipped.append(f"{c['file']}: no hook on file")
            continue
        asset = c["file"].replace("/", "--")
        src, dst = os.path.join(tmp, asset), os.path.join(tmp, "out_" + asset)
        sh("gh", "release", "download", "media", "-R", REPO, "-p", asset, "-O", src, "--clobber")
        try:
            got = restyle(src, hook, dst)
        except Exception as e:
            skipped.append(f"{c['file']}: {type(e).__name__} {str(e)[:120]}")
            continue
        if not got:
            skipped.append(f"{c['file']}: old hook box not found - left as is")
            c["style"] = "none"
            continue
        os.replace(dst, src)
        sh("gh", "release", "upload", "media", src, "-R", REPO, "--clobber")
        c["style"] = STYLE
        c["bytes"] = os.path.getsize(src)
        done += 1
        print(f"styled {c['file']}  old box y{got[0]}  bar y{got[1]}")
        os.remove(src)
        with open(MAN, "w", encoding="utf-8") as f:     # save as we go
            json.dump(man, f, indent=1, ensure_ascii=False)
    print(f"restyle: {done} clip(s) styled")
    for s in skipped:
        print("  skipped", s)


if __name__ == "__main__":
    main()
