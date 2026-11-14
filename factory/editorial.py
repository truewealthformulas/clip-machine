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
        f = ImageFont.truetype({"sans": SANS, "serif": SERIF, "black": BLACK}[kind], size)
        if kind == "sans":
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
