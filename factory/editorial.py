"""THE EDITORIAL LOOK (14 Nov 2026, the owner, after a reel from @kevins_apprentice:
"Choose to have clips like this HD" ... "Like it, let's change them all").

A pass over the finished strip (BW x BH, Kevin + cutaways), before it goes on the
black 9:16 canvas:

  * Kevin's words sit INSIDE the picture, on the side away from him, a few lines
    at a time, each word appearing as he says it. Mixed type: bold capitals, thin
    lowercase, and one word per card in cream italic.
  * Once or twice a clip, a giant word fills the frame BEHIND Kevin: the person
    is cut out (u2net human segmentation, onnxruntime) and laid back on top.
  * No title box, no caption bar under the strip.

phrases are clip-relative (a, b, text), the same ones the old captions used.
"""
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SANS = os.path.join(HERE, "assets", "Montserrat.ttf")
SERIF = os.path.join(HERE, "assets", "PlayfairDisplay-Italic.ttf")
SERIF_R = os.path.join(HERE, "assets", "PlayfairDisplay.ttf")
BLACK = os.path.join(HERE, "assets", "mont_black.ttf")
CREAM = (244, 232, 205)
WHITE = (250, 250, 250)
SEG_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net_human_seg.onnx"
SEG_PATH = os.environ.get("SEG_MODEL", "/tmp/u2net_human_seg.onnx")
BIG_MAX = int(os.environ.get("EDIT_BIG", "2"))         # giant words per clip

_F = {}


def _font(kind, size, w=700):
    k = (kind, size, w)
    if k not in _F:
        f = ImageFont.truetype({"sans": SANS, "serif": SERIF, "black": BLACK, "roman": SERIF_R}[kind], size)
        if kind in ("sans", "roman"):
            try:
                f.set_variation_by_axes([w])
            except Exception:
                pass
        _F[k] = f
    return _F[k]


def _ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


_SESS = []


def _seg():
    if _SESS:
        return _SESS[0]
    try:
        import onnxruntime as ort
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "onnxruntime"], check=False)
        import onnxruntime as ort
    if not os.path.exists(SEG_PATH):
        subprocess.run(["curl", "-sSL", "--retry", "3", "-o", SEG_PATH, SEG_URL], check=True)
    _SESS.append(ort.InferenceSession(SEG_PATH, providers=["CPUExecutionProvider"]))
    return _SESS[0]


def person_mask(img):
    s = _seg()
    x = np.asarray(img.convert("RGB").resize((320, 320)), dtype=np.float32) / 255.0
    x = (x - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
    x = x.transpose(2, 0, 1)[None].astype(np.float32)
    o = s.run(None, {s.get_inputs()[0].name: x})[0][0, 0]
    o = (o - o.min()) / (o.max() - o.min() + 1e-6)
    m = Image.fromarray((o * 255).astype(np.uint8)).resize(img.size, Image.BILINEAR)
    return m.filter(ImageFilter.GaussianBlur(1.5))


def cards(phrases, emphasis):
    """Group phrases into on-screen cards: 1-3 lines, closed at a sentence end."""
    out, cur = [], []
    for p in phrases:
        cur.append(p)
        words = sum(len(t.split()) for _, _, t in cur)
        if p[2].rstrip().endswith((".", "?", "!")) or len(cur) >= 3 or words >= 9:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    res = []
    for i, c in enumerate(out):
        allw = [w for _, _, t in c for w in t.split()]
        e = emphasis(allw)
        nxt = out[i + 1][0][0] if i + 1 < len(out) else None
        end = c[-1][1] + 0.5
        if nxt is not None:
            end = min(end, nxt)
        res.append({"a": c[0][0], "end": max(end, c[-1][1]), "lines": c, "emph": e})
    return res


def big_moments(phrases, segs, body, emphasis, n=BIG_MAX):
    """Short punchy phrases while Kevin is on screen -> giant words behind him."""
    def on_kevin(a, b):
        return any(k == "K" and sa <= a and b <= sb for sa, sb, k, _ in segs)
    cand = []
    for a, b, t in phrases:
        ws = [w.strip(",.!?").upper() for w in t.split()]
        ws = [w for w in ws if w]
        if not ws or a < 3.2 or b > body - 1.5 or b - a < 0.9 or not on_kevin(a, b):
            continue
        if len(ws) <= 2 and all(len(w) <= 10 and emphasis([w]) is not None for w in ws):
            words = ws
        else:
            e = emphasis(t.split())
            if e is None or len(ws[e]) > 10:
                continue
            words = [ws[e]]
        score = sum(len(w) for w in words) + (5 if len(words) == 1 else 0)
        cand.append((score, a, min(b + 0.3, body - 1.5), words))
    cand.sort(reverse=True)
    picked = []
    for c in cand:
        if all(abs(c[1] - p[1]) > 6 for p in picked):
            picked.append(c)
        if len(picked) >= n:
            break
    return [(a, b, w) for _, a, b, w in sorted(picked, key=lambda x: x[1])]


def _draw_card(base, t, card, side, BW, BH):
    lay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    lines, k = [], 0
    for li, (a, b, txt) in enumerate(card["lines"]):
        ws = txt.split()
        toks = []
        for j, w in enumerate(ws):
            ta = a + j * min(0.22, max(0.08, (b - a) / max(1, len(ws))))
            if card["emph"] is not None and k == card["emph"]:
                toks.append((w.lower().strip(",."), _font("serif", 66), CREAM, ta))
            elif li % 2 == 0:
                toks.append((w.upper(), _font("sans", 38, 700), WHITE, ta))
            else:
                toks.append((w.lower(), _font("sans", 36, 300), WHITE, ta))
            k += 1
        lines.append(toks)
    maxw = BW * 0.40
    # wrap any line that is too wide for the side
    wrapped = []
    for toks in lines:
        row, x = [], 0
        for tk in toks:
            tw = d.textlength(tk[0] + " ", font=tk[1])
            if row and x + tw > maxw:
                wrapped.append(row)
                row, x = [], 0
            row.append(tk)
            x += tw
        if row:
            wrapped.append(row)
    hts = [max(tk[1].size for tk in r) * 1.22 for r in wrapped]
    y = BH * 0.5 - sum(hts) / 2
    out = _ease((card["end"] - t) / 0.2)
    for row, hh in zip(wrapped, hts):
        rw = sum(d.textlength(tk[0] + " ", font=tk[1]) for tk in row)
        x = 48 if side == "L" else BW - 48 - rw
        for w, f, c, ta in row:
            a = _ease((t - ta) / 0.25)
            if a > 0:
                al = int(255 * a * out)
                d.text((x, y + (1 - a) * 14 + (hh - f.size * 1.22)), w, font=f, fill=c + (al,))
            x += d.textlength(w + " ", font=f)
        y += hh
    sh = lay.split()[3].filter(ImageFilter.GaussianBlur(6)).point(lambda v: int(v * 0.6))
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 255))
    shadow.putalpha(sh)
    base.alpha_composite(shadow)
    base.alpha_composite(lay)


def _draw_big(base, t, mom, frame, BW, BH):
    a, b, words = mom
    p, out = _ease((t - a) / 0.25), _ease((b - t) / 0.2)
    lay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    sc = 1.12 - 0.12 * p
    n = len(words)
    size = int((250 if n > 1 else 300) * sc)
    rows = []
    for w in words:
        f = _font("black", size)
        tw = d.textlength(w, font=f)
        if tw > BW - 40:
            f = _font("black", max(60, int(size * (BW - 40) / tw)))
            tw = d.textlength(w, font=f)
        rows.append((w, f, tw))
    total = sum(f.size * 1.0 for _, f, _ in rows)
    y = (BH - total) / 2 - 20
    for w, f, tw in rows:
        d.text(((BW - tw) / 2, y), w, font=f, fill=(255, 255, 255, int(255 * p * out)))
        y += f.size * 1.0
    base.alpha_composite(lay)
    person = frame.convert("RGBA")
    person.putalpha(person_mask(frame))
    base.alpha_composite(person)


def side_for(strip, segs, BW, BH):
    """(side, (cx, face_y)): text goes away from where Kevin's body sits."""
    geo = (BW * 0.55, BH * 0.35)
    ks = [(a, b) for a, b, k, _ in segs if k == "K"]
    if not ks:
        return "L", geo
    a, b = max(ks, key=lambda x: x[1] - x[0])
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{(a + b) / 2:.2f}", "-i", strip,
                          "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{BW}x{BH}", "-"],
                         capture_output=True).stdout
    if len(raw) < BW * BH * 3:
        return "L", geo
    try:
        m = np.asarray(person_mask(Image.frombytes("RGB", (BW, BH), raw)), dtype=np.float32) / 255.0
        cols = m.sum(axis=0)
        cx = float((cols * np.arange(BW)).sum() / max(1.0, cols.sum()))
        rows = np.where(m.sum(axis=1) > BW * 0.03)[0]
        top = float(rows[0]) if len(rows) else BH * 0.1
        band = m[int(top):int(min(BH, top + BH * 0.3))]
        bc = band.sum(axis=0)
        fx = float((bc * np.arange(BW)).sum() / max(1.0, bc.sum())) if bc.sum() > 0 else cx
        geo = (fx, min(BH * 0.6, top + BH * 0.17))
        return ("L" if cx >= BW * 0.45 else "R"), geo
    except Exception as e:
        print(f"  editorial: side check failed ({e}); text on the left", flush=True)
        return "L", geo


def _zoom(fr, z, ax, ay, BW, BH):
    """Zoom by z keeping the anchor point (Kevin's face) where it is on screen."""
    if z <= 1.001:
        return fr
    w, h = BW / z, BH / z
    l = min(max(ax - ax / z, 0), BW - w)
    t = min(max(ay - ay / z, 0), BH - h)
    return fr.resize((BW, BH), Image.BICUBIC, box=(l, t, l + w, t + h))


def _hook_card(base, t, hook, side, BW, BH, HOOK_T):
    """Doc opening: the title in big mixed type beside the close-up."""
    txt = " ".join(hook) if isinstance(hook, (list, tuple)) else str(hook)
    words = txt.split()
    lay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    rows, row, x = [], [], 0
    maxw = BW * 0.46
    for i, w in enumerate(words):
        em = w.startswith("*") and w.rstrip(",.!?").endswith("*")
        clean = w.strip("*")
        f = _font("serif", 92) if em else _font("black", 50)
        tok = (clean.lower() if em else clean.upper(), f, CREAM if em else WHITE, 0.15 + i * 0.12)
        tw = d.textlength(tok[0] + " ", font=f)
        if row and (x + tw > maxw or em):
            rows.append(row)
            row, x = [], 0
        row.append(tok)
        x += tw
        if em:
            rows.append(row)
            row, x = [], 0
    if row:
        rows.append(row)
    hts = [max(tk[1].size for tk in r) * 1.15 for r in rows]
    y = BH * 0.5 - sum(hts) / 2
    out = _ease((HOOK_T - t) / 0.25)
    for r, hh in zip(rows, hts):
        rw = sum(d.textlength(tk[0] + " ", font=tk[1]) for tk in r)
        x = 56 if side == "L" else BW - 56 - rw
        for w, f, c, ta in r:
            a = _ease((t - ta) / 0.3)
            if a > 0:
                d.text((x, y + (1 - a) * 16 + (hh - f.size * 1.15)), w, font=f, fill=c + (int(255 * a * out),))
            x += d.textlength(w + " ", font=f)
        y += hh
    sh = lay.split()[3].filter(ImageFilter.GaussianBlur(8)).point(lambda v: int(v * 0.7))
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 255))
    shadow.putalpha(sh)
    base.alpha_composite(shadow)
    base.alpha_composite(lay)


DOC_HOOK = 2.8


def apply(strip, out, phrases, segs, body, emphasis, BW, BH, FPS, mode="editorial", hook=None):
    """strip.mp4 (no audio) -> out.mp4 with the editorial text burned in.

    mode "doc" (14 Nov 2026, the documentary reference): opens on a tight
    close-up of Kevin with the title beside him, then slow push-ins and punch-in
    cuts on his shots, and the footage cutaways in dark black and white.
    """
    side, (fx, fy) = side_for(strip, segs, BW, BH)
    doc = mode == "doc"
    cs = cards(phrases, emphasis)
    try:
        bigs = big_moments(phrases, segs, body, emphasis)
        if bigs:
            _seg()
    except Exception as e:
        print(f"  editorial: no giant words ({e})", flush=True)
        bigs = []
    g = Image.linear_gradient("L").rotate(90 if side == "R" else -90).resize((BW, BH))
    g = g.point(lambda v: int(max(0, v - 110) * 0.9))
    shade = Image.new("RGBA", (BW, BH), (0, 0, 0, 255))
    shade.putalpha(g)
    dec = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", strip, "-vf", f"fps={FPS}",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{BW}x{BH}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
                            "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", out],
                           stdin=subprocess.PIPE)
    n, sz = 0, BW * BH * 3
    while True:
        raw = dec.stdout.read(sz)
        if len(raw) < sz:
            break
        t = n / FPS
        n += 1
        fr = Image.frombytes("RGB", (BW, BH), raw)
        if doc:
            si = next((i for i, sg in enumerate(segs) if sg[0] <= t < sg[1]), None)
            sg = segs[si] if si is not None else None
            if t < DOC_HOOK and (sg is None or sg[2] == "K"):
                z = 1.75 + 0.08 * (t / DOC_HOOK)
                fr = _zoom(fr, z, fx, fy, BW, BH)
            elif sg is not None and sg[2] == "K":
                kn = sum(1 for x in segs[:si] if x[2] == "K")
                prog = (t - sg[0]) / max(0.1, sg[1] - sg[0])
                z = (1.0 if kn % 2 == 0 else 1.25) + 0.06 * prog
                fr = _zoom(fr, z, fx, fy, BW, BH)
            elif sg is not None:
                g = fr.convert("L").point(lambda v: int(max(0, min(255, (v - 128) * 1.25 + 112))))
                fr = g.convert("RGB")
        st = fr.convert("RGBA")
        st.alpha_composite(shade)
        mom = next((m for m in bigs if m[0] <= t < m[1]), None)
        if doc and t < DOC_HOOK and hook:
            _hook_card(st, t, hook, side, BW, BH, DOC_HOOK)
        elif mom:
            try:
                _draw_big(st, t, mom, fr, BW, BH)
            except Exception as e:
                print(f"  editorial: giant word dropped ({e})", flush=True)
                bigs = []
        else:
            for c in cs:
                if c["a"] <= t < c["end"]:
                    _draw_card(st, t, c, side, BW, BH)
        enc.stdin.write(st.convert("RGB").tobytes())
    enc.stdin.close()
    enc.wait()
    dec.wait()
    print(f"  editorial: {n} frames, text {side}, giant words {[' '.join(w) for _, _, w in bigs]}", flush=True)
    return out


# ------------------------------------------------------------------ covers
# 15 Nov 2026, the owner: "take away from the videos the blue label" (the navy
# band of the old T5 cover) and, with the @kevins_apprentice grid: "let's do
# something like this". Two full-bleed covers, no band, no box:
#   "word"  - Kevin close, filling the frame, one or two words low in the frame
#             (bold caps + the key word in cream italic), like their "Secret".
#   "giant" - the key word huge BEHIND Kevin, like their "PURPOSE IN LIFE".
# Everything that matters sits inside the 3:4 the profile grid shows.

def kevin_pos(img):
    """(x of Kevin's face centre, top of his head) in a full-resolution frame, or None.

    16 Nov 2026: on two-person podcast sets (host left, Kevin right) the person
    mask picked the middle of the two, and the TikTok crop showed a shoulder and
    the gap between the panels. Now every face is fingerprinted (YuNet + SFace,
    factory/kevin_face.py) and the crop goes to the one that is Kevin."""
    try:
        import kevin_face as KF
        cv2, det, rec, ref = KF._load()
        w, h = img.size
        sc = 960.0 / w
        small = np.asarray(img.convert("RGB").resize((960, int(h * sc))))[:, :, ::-1].copy()
        det.setInputSize((small.shape[1], small.shape[0]))
        _, faces = det.detect(small)
        if faces is None or not len(faces):
            return None
        best, bs = None, -1.0
        for f in faces:
            if f[2] < 24:
                continue
            e = rec.feature(rec.alignCrop(small, f)).reshape(-1)
            e = e / (np.linalg.norm(e) or 1)
            sim = float(np.max(ref @ e))
            if sim > bs:
                best, bs = f, sim
        if best is None:
            return None
        if bs < 0.30:                      # nobody recognisable: the biggest face
            best = max(faces, key=lambda r: r[2] * r[3])
        x, y, fw, fh = [float(v) / sc for v in best[:4]]
        return x + fw / 2, max(0.0, y - fh * 0.45)
    except Exception as e:
        print(f"  kevin_pos: {type(e).__name__}: {e}", flush=True)
        return None


def _hook_parts(hook):
    txt = " ".join(hook) if isinstance(hook, (list, tuple)) else str(hook)
    words = txt.replace("/", " ").split()
    emph = [i for i, w in enumerate(words) if w.startswith("*")]
    clean = [w.strip("*") for w in words]
    return clean, (emph[0] if emph else None)


def _portrait(src, t, W=1080, H=1920):
    """A 9:16 frame from the source around Kevin, at full source resolution."""
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0", src], capture_output=True, text=True)
    sw, shh = [int(x) for x in probe.stdout.strip().split(",")[:2]]
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", src, "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    fr = Image.frombytes("RGB", (sw, shh), raw)
    kp = kevin_pos(fr)
    if kp:
        fx, top = kp[0], int(kp[1])
    else:
        m = np.asarray(person_mask(fr), dtype=np.float32) / 255.0
        rows = np.where(m.sum(axis=1) > sw * 0.03)[0]
        top = int(rows[0]) if len(rows) else int(shh * 0.1)
        band = m[top:int(min(shh, top + shh * 0.3))]
        bc = band.sum(axis=0)
        fx = float((bc * np.arange(sw)).sum() / max(1.0, bc.sum())) if bc.sum() > 0 else sw / 2
    ch = int(shh * 0.92)                      # a little tighter than the full height
    cw = int(ch * W / H)
    l = int(min(max(fx - cw / 2, 0), sw - cw))
    t0 = int(min(max(top - ch * 0.10, 0), shh - ch))
    im = fr.crop((l, t0, l + cw, t0 + ch)).resize((W, H), Image.LANCZOS)
    im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))
    return im


def _split_hook(words):
    """'How a $2 billion app happened' -> ('HOW A $2', 'Billion app happened.')"""
    n = len(words)
    if n <= 2:
        return " ".join(words).upper(), ""
    k = max(2, min(4, (n + 1) // 2))
    head = " ".join(words[:k]).upper()
    sub = " ".join(words[k:]).rstrip(",;:")
    sub = sub[:1].upper() + sub[1:]
    if sub and sub[-1] not in ".!?":
        sub += "."
    return head, sub


def student_cover(im, words, out):
    """18 Nov 2026, the owner, showing @kevin_trudeau_student ("he is doing it
    and having results"): Kevin in black and white, a small spaced KEVIN TRUDEAU,
    a thin red bar, the headline in heavy white capitals and the rest of the
    line in italic serif under it - low on the frame, inside the 3:4 the grid shows."""
    from PIL import ImageEnhance, ImageOps
    W, H = im.size
    g = ImageOps.grayscale(im.convert("RGB"))
    g = ImageEnhance.Contrast(g).enhance(1.18)
    g = ImageEnhance.Brightness(g).enhance(0.92)
    base = Image.merge("RGB", (g, g, g)).convert("RGBA")
    shade = Image.new("L", (1, H))
    for y in range(H):                                # dark from the middle down
        v = 0 if y < H * 0.50 else int(215 * min(1.0, (y - H * 0.50) / (H * 0.30)))
        shade.putpixel((0, y), v)
    blk = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    blk.putalpha(shade.resize((W, H)))
    base.alpha_composite(blk)
    d = ImageDraw.Draw(base)
    head, sub = _split_hook(words)
    x0, maxw = int(W * 0.115), int(W * 0.80)
    # the headline: up to two lines, as big as fits
    for size in (104, 96, 88, 80, 72, 64, 58):
        f = _font("black", size)
        ws, lines, cur = head.split(), [], ""
        for w in ws:
            if cur and d.textlength(cur + " " + w, font=f) > maxw:
                lines.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        lines.append(cur)
        if len(lines) <= 2 and all(d.textlength(l, font=f) <= maxw for l in lines):
            break
    fs = _font("serif", 58)
    sl, cur = [], ""
    for w in sub.split():
        if cur and d.textlength(cur + " " + w, font=fs) > maxw:
            sl.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        sl.append(cur)
    sl = sl[:2]
    lh, slh = int(f.size * 1.02), int(fs.size * 1.22)
    block = lh * len(lines) + (14 + slh * len(sl) if sl else 0)
    y = int(H * 0.745) - block // 2
    fl = _font("sans", 26, 600)
    lab, lx = "KEVIN TRUDEAU", x0
    for ch in lab:                                    # letter-spaced label
        d.text((lx, y - 62), ch, font=fl, fill=(235, 235, 235, 255))
        lx += d.textlength(ch, font=fl) + 7
    d.rectangle((x0 - 30, y + 6, x0 - 22, y + block - 4), fill=(200, 30, 36, 255))
    for ln in lines:
        d.text((x0, y), ln, font=f, fill=(255, 255, 255, 255))
        y += lh
    y += 14
    for ln in sl:
        d.text((x0, y), ln, font=fs, fill=(240, 236, 228, 255))
        y += slh
    base.convert("RGB").save(out, quality=92)
    return out


def make_cover(src, t, hook, out, kind="word", emphasis=None):
    W, H = 1080, 1920
    im = _portrait(src, t, W, H).convert("RGBA")
    words, ei = _hook_parts(hook)
    if ei is None and emphasis:
        ei = emphasis(words)
    key = words[ei] if ei is not None else max(words, key=len)
    key = key.strip(",.!?:;\"'")
    d = ImageDraw.Draw(im)
    if kind == "student":
        return student_cover(im, words, out)
    if kind == "headline":
        # @kevin_trudeau_student (15 Nov 2026): Kevin full-frame, the hook in
        # white serif capitals across the middle, soft shadow, nothing else.
        im = im.convert("RGB")
        from PIL import ImageEnhance
        im = ImageEnhance.Brightness(im).enhance(0.88).convert("RGBA")
        txt = " ".join(words).upper().split()
        f = _font("roman", 74, 650)
        best = None                      # balanced lines, like their two-line titles
        for n in (1, 2, 3):
            if n > len(txt):
                break
            import itertools
            for cuts in itertools.combinations(range(1, len(txt)), n - 1):
                ls = [" ".join(txt[i:j]) for i, j in zip((0,) + cuts, cuts + (len(txt),))]
                wmax = max(d.textlength(x, font=f) for x in ls)
                if wmax <= W * 0.86 and (best is None or (n, wmax) < (best[0], best[1])):
                    best = (n, wmax, ls)
            if best:
                break
        lines = best[2] if best else [" ".join(txt)]
        if not best:
            f = _font("roman", 54, 650)
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dl = ImageDraw.Draw(lay)
        lh = int(f.size * 1.18)
        y = int(H * 0.60) - lh * len(lines) // 2
        for ln in lines:
            dl.text(((W - dl.textlength(ln, font=f)) / 2, y), ln, font=f, fill=(255, 255, 255, 255))
            y += lh
        sh = lay.split()[3].filter(ImageFilter.GaussianBlur(10)).point(lambda v: int(v * 0.85))
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        shadow.putalpha(sh)
        im.alpha_composite(shadow)
        im.alpha_composite(lay)
    elif kind == "giant":
        # the wide shot on black, the word huge behind Kevin (their "PURPOSE IN LIFE")
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", src, "-frames:v", "1",
                              "-vf", "scale=1080:608", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
        strip = Image.frombytes("RGB", (1080, 608), raw)
        sw, sh_ = 1080, 608
        sc = 1.25                              # a touch closer than the video
        strip = strip.resize((int(sw * sc), int(sh_ * sc)), Image.LANCZOS)
        strip = strip.crop(((strip.width - 1080) // 2, 0, (strip.width - 1080) // 2 + 1080, strip.height))
        strip = strip.filter(ImageFilter.UnsharpMask(radius=2, percent=50, threshold=2))
        im = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        y0 = (H - strip.height) // 2
        im.paste(strip, (0, y0))
        person = strip.convert("RGBA")
        person.putalpha(person_mask(strip))
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dl = ImageDraw.Draw(lay)
        txt = [w.upper() for w in key.split()] if " " in key else [key.upper()]
        rest = [w for i, w in enumerate(words) if i != ei]
        # two lines when the key word is short and a neighbour helps: "PURPOSE / IN LIFE"
        lines = txt
        y = y0 + strip.height * 0.06
        for ln in lines:
            f = _font("black", 300)
            tw = dl.textlength(ln, font=f)
            if tw > W - 40:
                f = _font("black", max(120, int(300 * (W - 40) / tw)))
                tw = dl.textlength(ln, font=f)
            dl.text(((W - tw) / 2, y), ln, font=f, fill=(255, 255, 255, 255))
            y += f.size * 0.95
        im.alpha_composite(lay)
        im.alpha_composite(person, (0, y0))
        sub = " ".join(rest[:7]).upper()
        if sub:
            fs = _font("sans", 40, 800)
            d2 = ImageDraw.Draw(im)
            ly, line, out_l = y0 + strip.height + 50, "", []
            for w in sub.split():
                if line and d2.textlength(line + " " + w, font=fs) > W * 0.8:
                    out_l.append(line)
                    line = w
                else:
                    line = (line + " " + w).strip()
            out_l.append(line)
            for ln in out_l:
                d2.text(((W - d2.textlength(ln, font=fs)) / 2, ly), ln, font=fs, fill=WHITE)
                ly += 54
    else:
        g = Image.linear_gradient("L").resize((W, H)).point(lambda v: int(max(0, v - 120) * 1.6))
        shade = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        shade.putalpha(g)
        im.alpha_composite(shade)
        d = ImageDraw.Draw(im)
        rest = [w for i, w in enumerate(words) if i != ei][:6]
        small = " ".join(rest).upper()
        fs = _font("sans", 44, 800)
        lines, line = [], ""
        for w in small.split():
            if line and d.textlength(line + " " + w, font=fs) > W * 0.78:
                lines.append(line)
                line = w
            else:
                line = (line + " " + w).strip()
        if line:
            lines.append(line)
        fe = _font("serif", 170)
        while d.textlength(key.lower(), font=fe) > W * 0.86 and fe.size > 90:
            fe = _font("serif", fe.size - 10)
        y = 1660 - fe.size * 1.1 - len(lines) * 56
        for ln in lines:
            d.text(((W - d.textlength(ln, font=fs)) / 2, y), ln, font=fs, fill=WHITE)
            y += 56
        d.text(((W - d.textlength(key.lower(), font=fe)) / 2, y), key.lower(), font=fe, fill=CREAM)
    im.convert("RGB").save(out, quality=92)
    return out
