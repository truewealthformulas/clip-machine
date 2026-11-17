"""THE TIKTOK CUT (16 Nov 2026, the owner: "Change it so we can have 600 views").

His own October TikToks (400-643 views) were full-screen close-ups of Kevin
with big bold captions in the middle and a yellow key word; the clip machine's
black-with-a-strip copies stopped at 150-200. So TikTok gets its own cut:

  * 9:16 FULL SCREEN, cropped on Kevin's face (u2net person mask), alternating
    a normal and a punched-in framing shot to shot, footage cutaways full screen;
  * BIG captions, 1-3 words at a time, white with a heavy black outline, the key
    word yellow, popping in as he says them, at about 60% of the height;
  * the hook big at the top for the first 2.2 s;
  * no end card: the video loops straight back into the hook (watch time).
"""
import os
import subprocess
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import editorial as ED

W, H, FPS = 1080, 1920, 30
YELLOW = (255, 214, 0)
HOOK_T = 2.2


def _sh(*a):
    subprocess.run(a, check=True)


def _frame(src, t, sw, shh):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", src, "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return Image.frombytes("RGB", (sw, shh), raw)


def _face_x(img):
    """x of Kevin's face and the top of his head: his fingerprinted face first,
    the person mask only when no face is found."""
    kp = ED.kevin_pos(img)
    if kp:
        return kp
    m = np.asarray(ED.person_mask(img), dtype=np.float32) / 255.0
    w, h = img.size
    rows = np.where(m.sum(axis=1) > w * 0.03)[0]
    if not len(rows):
        return w / 2, h * 0.15
    top = int(rows[0])
    band = m[top:int(min(h, top + h * 0.25))]
    bc = band.sum(axis=0)
    fx = float((bc * np.arange(w)).sum() / max(1.0, bc.sum())) if bc.sum() > 0 else w / 2
    return fx, top


def _size(src):
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height", "-of", "csv=p=0", src], capture_output=True, text=True)
    return [int(x) for x in p.stdout.strip().split(",")[:2]]


def _chunks(phrases, emphasis):
    """(a, b, [words], key_index) - 1-3 words each, timed inside their phrase."""
    out = []
    for a, b, t in phrases:
        ws = t.split()
        if not ws:
            continue
        n = len(ws)
        groups, i = [], 0
        while i < n:
            k = 3 if n - i > 4 else (2 if n - i > 1 else 1)
            if n - i == 4:
                k = 2
            groups.append(ws[i:i + k])
            i += k
        step = (b - a) / max(1, n)
        j = 0
        for g in groups:
            ga = a + j * step
            gb = a + (j + len(g)) * step
            e = emphasis(g)
            out.append((ga, gb, g, e))
            j += len(g)
    # each chunk stays until the next one starts (no flicker)
    res = []
    for i, (a, b, g, e) in enumerate(out):
        nb = out[i + 1][0] if i + 1 < len(out) else b + 0.4
        res.append((a, max(b, min(nb, b + 0.6)), g, e))
    return res


def _draw_words(base, words, key, t, a, y_mid, size, maxw):
    d = ImageDraw.Draw(base)
    f = ED._font("black", size)
    txt = [w.upper() for w in words]
    # wrap to two lines if needed
    lines, line = [], []
    for i, w in enumerate(txt):
        trial = " ".join([x for x, _ in line] + [w])
        if line and d.textlength(trial, font=f) > maxw:
            lines.append(line)
            line = []
        line.append((w, i == key))
    if line:
        lines.append(line)
    p = min(1.0, max(0.0, (t - a) / 0.12))
    sc = 0.82 + 0.18 * p                     # pop in
    f = ED._font("black", max(20, int(size * sc)))
    lh = int(f.size * 1.08)
    y = y_mid - lh * len(lines) / 2
    for ln in lines:
        lw = sum(d.textlength(w + " ", font=f) for w, _ in ln) - d.textlength(" ", font=f)
        x = (W - lw) / 2
        for w, k in ln:
            d.text((x + 4, y + 6), w, font=f, fill=(0, 0, 0, 160), stroke_width=10, stroke_fill=(0, 0, 0, 160))
            d.text((x, y), w, font=f, fill=YELLOW if k else (255, 255, 255),
                   stroke_width=9, stroke_fill=(0, 0, 0))
            x += d.textlength(w + " ", font=f)
        y += lh


def render_tt(src, t_in, t_out, hook, phrases, segs, dst, emphasis):
    tmp = tempfile.mkdtemp()
    body = t_out - t_in
    sw, shh = _size(src)
    ch = shh
    cw = int(round(ch * W / H / 2) * 2)
    parts, kn = [], 0
    for i, (a, b, kind, ph) in enumerate(segs):
        d = b - a
        n = max(1, int(round(d * FPS)))
        out = os.path.join(tmp, f"t{i:02d}.mp4")
        if kind == "K":
            fx, top = _face_x(_frame(src, t_in + (a + b) / 2, sw, shh))
            z = 1.0 if kn % 2 == 0 else 1.22
            kn += 1
            zw, zh = int(cw / z) // 2 * 2, int(ch / z) // 2 * 2
            x = int(min(max(fx - zw / 2, 0), sw - zw))
            y = int(min(max(top - zh * 0.08, 0), shh - zh)) if z > 1 else 0
            vf = (f"crop={zw}:{zh}:{x}:{y},scale={W}:{H}:flags=lanczos,unsharp=5:5:0.5,"
                  f"eq=contrast=1.05:saturation=1.05,setsar=1,fps={FPS},format=yuv420p")
            _sh("ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t_in + a:.3f}", "-t", f"{d:.3f}", "-i", src,
                "-an", "-vf", vf, "-frames:v", str(n), "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", out)
        elif ph and ph.endswith(".mp4"):
            _sh("ffmpeg", "-loglevel", "error", "-y", "-stream_loop", "-1", "-i", ph, "-t", f"{d:.3f}", "-an",
                "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                f"eq=contrast=1.06:saturation=0.95,setsar=1,fps={FPS},format=yuv420p",
                "-frames:v", str(n), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", out)
        else:
            _sh("ffmpeg", "-loglevel", "error", "-y", "-loop", "1", "-i", ph, "-vf",
                f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
                f"zoompan=z='1+0.10*on/{n}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n}:s={W}x{H}:fps={FPS},"
                "setsar=1,format=yuv420p", "-frames:v", str(n), "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "18", out)
        parts.append(out)
    lst = os.path.join(tmp, "p.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    full = os.path.join(tmp, "full.mp4")
    _sh("ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", full)

    chunks = _chunks([(max(0.0, a), min(b, body), t) for a, b, t in phrases if b > 0 and a < body], emphasis)
    hw, hi = ED._hook_parts(hook)
    dec = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", full, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    vid = os.path.join(tmp, "v.mp4")
    enc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                            "-crf", "18", "-pix_fmt", "yuv420p", vid], stdin=subprocess.PIPE)
    sz, k = W * H * 3, 0
    while True:
        raw = dec.stdout.read(sz)
        if len(raw) < sz:
            break
        t = k / FPS
        k += 1
        im = Image.frombytes("RGB", (W, H), raw)
        if t < HOOK_T and hw:
            _draw_words(im, hw, hi, t, 0.0, 420, 104, W * 0.86)
        c = next((c for c in chunks if c[0] <= t < c[1]), None)
        if c:
            _draw_words(im, c[2], c[3], t, c[0], 1180, 112, W * 0.84)
        enc.stdin.write(im.tobytes())
    enc.stdin.close()
    enc.wait()
    dec.wait()
    joined = os.path.join(tmp, "j.mp4")
    _sh("ffmpeg", "-loglevel", "error", "-y", "-i", vid, "-ss", f"{t_in:.3f}", "-t", f"{body:.3f}", "-i", src,
        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", joined)
    jumpcut(joined, phrases, body, dst)
    subprocess.run(["rm", "-rf", tmp])
    return dst


def jumpcut(src, phrases, body, dst, max_gap=float(os.environ.get("TT_MAX_GAP", "0.3"))):
    """NO DEAD AIR (17 Nov 2026, TikTok stuck under 185 views). Every pause
    longer than max_gap between Kevin's phrases is cut down to it - the pace of
    the edits that do well on TikTok. Captions are already burned in, so they
    move with the picture."""
    ph = sorted((max(0.0, a), min(b, body)) for a, b, _ in phrases if b > a)
    keep, cur = [], [0.0, 0.0]
    for a, b in ph:
        if a - cur[1] > max_gap:
            keep.append((cur[0], cur[1] + max_gap / 2))
            cur = [a - max_gap / 2, b]
        else:
            cur[1] = max(cur[1], b)
    keep.append((cur[0], min(body, cur[1] + 0.4)))
    keep = [(max(0.0, a), b) for a, b in keep if b - a > 0.05]
    cut = body - sum(b - a for a, b in keep)
    if cut < 0.5 or len(keep) > 120:
        os.replace(src, dst)
        return dst
    sel = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in keep)
    _sh("ffmpeg", "-loglevel", "error", "-y", "-i", src,
        "-vf", f"select='{sel}',setpts=N/FRAME_RATE/TB",
        "-af", f"aselect='{sel}',asetpts=N/SR/TB",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart", dst)
    print(f"  jump cuts: {cut:.1f}s of pauses removed ({len(keep)} pieces)", flush=True)
    return dst
