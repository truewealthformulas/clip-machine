"""STYLE CINE - the cinematic cut (13 Nov 2026).

The owner sent a reel (@growthcodefiles) and said "maybe this way works", then
"yes" to the preview. Instagram had flagged the account: "Es posible que este
contenido no sea originalmente tuyo" - every reel of Kevin full screen, with our
text on top, read as a re-upload. Instagram's own help page says what counts as
a substantial edit: new footage, text that adds something, an edit that tells
the story. So this cut:

  * keeps Kevin's VOICE the whole way through,
  * shows Kevin only about half the time - the rest is footage that matches what
    he is saying at that moment ("tomorrow" -> a sunrise, "focus" -> chess),
  * lays the words in one at a time, the key word of each phrase in gold script,
  * sits in a 16:9 cinema strip on black, the hook as a title above it the whole
    time (the Oct 21-22 lesson: the topic on screen all the way through),
  * opens on Kevin's strongest 3 seconds and ends on the YouTube end card.

Rendered from the HD episode (so Kevin is sharp and has no burned captions).

    python factory/cinematic.py list          # queued clips not yet cinematic -> $GITHUB_OUTPUT
    python factory/cinematic.py one <file>    # render one into /tmp/cine_out
    python factory/cinematic.py commit <dir>  # swap the assets in, mark them
"""
import glob, hashlib, json, os, re, shutil, subprocess, sys, tempfile

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import restyle as R  # noqa: E402

MAN = os.path.join(ROOT, "state", "manifest.json")
K = os.path.expanduser("~/ClipMachine")
REPO = os.environ.get("GITHUB_REPOSITORY", "truewealthformulas/clip-machine")
# REAL VIDEO FOOTAGE (13 Nov 2026, the owner: "ok lets do it!"). With a free
# Pexels key in the PEXELS_API_KEY secret, the cutaways are real video clips
# found for each theme; without it, the 36 still photos. Adding the key bumps the
# version, so the queue is cut again with video on the next run.
PEXELS = os.environ.get("PEXELS_API_KEY", "").strip()
# 13 Nov 2026: Pexels paused new API keys the day we asked. MIXKIT instead: free
# stock video, no key, licensed for use in videos. factory/assets/broll/videos.txt
# lists hand-picked clips per theme; Pexels (if a key ever exists) is tried first.
MIXKIT_LIST = os.path.join(HERE, "assets", "broll", "videos.txt")
CINE_V = 3
OUT = "/tmp/cine_out"
BROLL_DIR = "/tmp/broll"
W, H, FPS = 1080, 1920, 30
BW, BH = 1080, 608                    # the cinema strip
BY = (H - BH) // 2 - 40               # a little above centre: room for the title above
SHARE = float(os.environ.get("CINE_BROLL_SHARE", "0.5"))   # target share of footage
GOLD, WHITE = (232, 190, 92), (255, 255, 255)

# What Kevin says -> what we show. Themes are the BROLL--<theme>_<id>.jpg photos
# in the media release (factory/assets/broll/list.txt). First match wins.
THEMES = [
    ("money", r"money|cash|dollar|rich|wealth|wealthy|million|billion|income|pay|paid|debt|bank|afford"),
    ("gold", r"gold|treasure|value|valuable|worth|reward|prize|gift"),
    ("wallst", r"business|market|stock|invest|investment|company|deal|sell|sales|buy|trade|economy"),
    ("city", r"work|job|office|career|busy|phone|call|calls|mail|interrupt|interruptions|people|world|society"),
    ("chess", r"focus|think|thinking|strategy|decide|decision|choose|choice|plan|mind|brain|attention|priority|first"),
    ("library", r"read|reading|book|books|learn|learning|knowledge|study|write|wrote|list|paper|pad|school|teacher|wisdom"),
    ("summit", r"success|successful|goal|goals|achieve|accomplish|accomplished|finish|finished|win|winner|top|conclusion|done|complete|climb"),
    ("sunrise", r"tomorrow|morning|today|day|new|begin|start|future|hope|dream|dreams|wake|light|life"),
    ("road", r"until|journey|path|way|road|step|steps|keep|forward|habit|habits|daily|cycle|long|time"),
    ("jet", r"freedom|free|travel|fly|flying|fast|speed|vacation|escape"),
    ("ocean", r"peace|calm|feel|feeling|emotion|emotions|happy|happiness|love|meditat\w*|relax|nature|breathe"),
    ("car", r"drive|driving|car|ferrari|luxury|lifestyle"),
]
FALLBACK = ["sunrise", "road", "summit", "ocean", "city"]
# What to search Pexels for, per theme (several, so clips do not repeat).
QUERIES = {
    "money": ["counting money", "cash dollars", "wealth luxury", "business success money"],
    "gold": ["gold bars", "golden light", "treasure gold"],
    "wallst": ["stock market screen", "business meeting", "city business district", "handshake deal"],
    "city": ["city night timelapse", "busy office people", "phone call business", "busy street people"],
    "chess": ["chess game", "man thinking", "focus work desk", "strategy planning"],
    "library": ["writing notebook", "reading book", "library books", "student studying"],
    "summit": ["mountain summit hiker", "climbing mountain", "man on mountain top", "finish line"],
    "sunrise": ["sunrise timelapse", "morning light", "new day sunrise", "dawn sky"],
    "road": ["road trip drone", "walking path", "running road", "highway sunset"],
    "jet": ["private jet", "airplane flying", "travel freedom"],
    "ocean": ["ocean waves calm", "peaceful nature", "meditation sunrise", "forest light"],
    "car": ["luxury car driving", "sports car", "driving car road"],
}
PEX_DIR = "/tmp/pexels"
STOP = set("the a an and or but of to in on at for with from into that this these those it its is are was "
           "were be been being i you he she we they them his her our your their my me us do does did "
           "dont don't not no so if then than just very really there here what when where who why how "
           "can could would should will shall have has had get got going gonna want about because "
           "it's that's there's here's you're i'm we're they're what's let's isn't aren't wasn't "
           "doesn't didn't can't won't wouldn't couldn't shouldn't i've you've we've i'll you'll "
           "it'll i'd you'd he's she's thing things something anything everything someone "
           "going really actually basically maybe little other another every always never "
           "said says say tell told know knew think thought make made take took give gave "
           "come came look looked like just only even still also".split())


def sh(*a, **k):
    return subprocess.run(a, check=True, **k)


def dur(p):
    return R.duration(p)


def font(path, size, wght):
    f = ImageFont.truetype(path, size)
    try:
        f.set_variation_by_axes([wght])
    except Exception:
        pass
    return f


SANS = os.path.join(HERE, "assets", "Montserrat.ttf")
SCRIPT = os.path.join(HERE, "assets", "PlayfairDisplay-Italic.ttf")


def _clean(w):
    return re.sub(r"[^a-z']", "", w.lower())


def theme_of(text):
    ws = [_clean(w) for w in text.split()]
    for theme, rx in THEMES:
        for w in ws:
            if w and re.fullmatch(rx, w):
                return theme, w
    return None, None


def emphasis(words):
    """Index of the word to set in gold script: a theme word, else the longest real word."""
    best, score = None, 0
    for i, w in enumerate(words):
        c = _clean(w)
        th = theme_of(c)[0]
        if not c or c in STOP or (len(c) < 5 and not th):
            continue
        s = len(c) + (10 if th else 0)
        if s > score:
            best, score = i, s
    return best


def photos():
    """{theme: [paths]} from the media release (downloaded once per runner)."""
    if not glob.glob(os.path.join(BROLL_DIR, "BROLL--*.jpg")):
        os.makedirs(BROLL_DIR, exist_ok=True)
        subprocess.run(["gh", "release", "download", "media", "-R", REPO, "-p", "BROLL--*.jpg",
                        "-D", BROLL_DIR, "--clobber"], check=False)
    out = {}
    for p in sorted(glob.glob(os.path.join(BROLL_DIR, "BROLL--*.jpg"))):
        m = re.match(r"BROLL--([a-z]+)_", os.path.basename(p))
        if m:
            out.setdefault(m.group(1), []).append(p)
    return out


def _http_json(url):
    import urllib.request
    req = urllib.request.Request(url, headers={"Authorization": PEXELS, "User-Agent": "clip-machine"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def pexels_videos(theme):
    """[(id, duration, link)] landscape HD clips for a theme, cached per runner."""
    if not PEXELS:
        return []
    os.makedirs(PEX_DIR, exist_ok=True)
    cache = os.path.join(PEX_DIR, f"q_{theme}.json")
    if os.path.exists(cache):
        return json.load(open(cache))
    out = []
    from urllib.parse import quote
    for q in QUERIES.get(theme, [theme]):
        try:
            d = _http_json("https://api.pexels.com/videos/search?query=" + quote(q)
                           + "&orientation=landscape&size=medium&per_page=12")
        except Exception as e:
            print(f"  pexels '{q}': {type(e).__name__}")
            continue
        for v in d.get("videos", []):
            files = [f for f in v.get("video_files", [])
                     if (f.get("width") or 0) >= 1280 and (f.get("width") or 0) <= 1920
                     and (f.get("width") or 0) > (f.get("height") or 0) and f.get("link")]
            if not files or (v.get("duration") or 0) < 5:
                continue
            f = max(files, key=lambda x: x["width"])
            out.append((v["id"], v["duration"], f["link"]))
    json.dump(out, open(cache, "w"))
    return out


def mixkit_videos(theme):
    """[(id, None, None)] for a theme from videos.txt."""
    out = []
    if os.path.exists(MIXKIT_LIST):
        for ln in open(MIXKIT_LIST):
            ps = ln.split()
            if len(ps) >= 2 and not ln.startswith("#") and ps[0] == theme:
                out.append(("mk" + ps[1], None, None))
    return out


def mixkit_file(mid):
    """Download one Mixkit clip (largest size it has), cached per runner."""
    n = mid[2:]
    p = os.path.join(PEX_DIR, f"v_{mid}.mp4")
    if os.path.exists(p):
        return p
    os.makedirs(PEX_DIR, exist_ok=True)
    import urllib.request
    for size in ("1080", "720", "360"):
        url = f"https://assets.mixkit.co/videos/{n}/{n}-{size}.mp4"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 clip-machine"})
            with urllib.request.urlopen(req, timeout=120) as r, open(p + ".part", "wb") as fh:
                shutil.copyfileobj(r, fh)
            if os.path.getsize(p + ".part") > 50000:
                os.replace(p + ".part", p)
                return p
        except Exception:
            continue
    raise RuntimeError(f"mixkit {n}: no downloadable size")


def pexels_file(vid, link):
    p = os.path.join(PEX_DIR, f"v_{vid}.mp4")
    if not os.path.exists(p):
        import urllib.request
        req = urllib.request.Request(link, headers={"User-Agent": "clip-machine"})
        with urllib.request.urlopen(req, timeout=120) as r, open(p + ".part", "wb") as fh:
            shutil.copyfileobj(r, fh)
        os.replace(p + ".part", p)
    return p


def plan(phrases, body, seed):
    """[(a, b, kind, photo)] covering 0..body. kind 'K' (Kevin) or 'B' (footage)."""
    lib = photos()
    used, cuts = set(), []

    def pick(theme):
        vids = [v for v in (pexels_videos(theme) or mixkit_videos(theme)) if ("v", v[0]) not in used]
        start = int(hashlib.md5((seed + theme).encode()).hexdigest(), 16)
        for k in range(min(3, len(vids))):          # a dead link falls through to the next clip
            v = vids[(start + k) % len(vids)]
            try:
                p = mixkit_file(v[0]) if str(v[0]).startswith("mk") else pexels_file(v[0], v[2])
                used.add(("v", v[0]))
                return p
            except Exception as e:
                print(f"  video {v[0]}: {type(e).__name__}")
                used.add(("v", v[0]))
        cands = lib.get(theme) or []
        cands = [p for p in cands if p not in used] or cands
        if not cands:
            return None
        p = cands[int(hashlib.md5((seed + theme).encode()).hexdigest(), 16) % len(cands)]
        used.add(p)
        return p

    lo, hi = 3.0, body - 2.5          # Kevin opens and closes the body
    budget = SHARE * body
    cand = []
    for a, b, text in phrases:
        if a < lo or b > hi:
            continue
        th, _ = theme_of(text)
        cand.append((0 if th else 1, a, b, th))
    # themed phrases first, in time order; generic fill only if short of the target
    cand.sort(key=lambda x: (x[0], x[1]))
    taken = 0.0
    gi = 0
    for pri, a, b, th in cand:
        if taken >= budget:
            break
        a2, b2 = a, max(b, a + 2.4)
        b2 = min(b2, a2 + 4.5, hi)
        if b2 - a2 < 2.0:
            continue
        # keep at least 2 s of Kevin between two footage shots
        if any(not (b2 + 2.0 <= x or a2 >= y + 2.0) for x, y, _ in cuts):
            continue
        if th is None:
            th = FALLBACK[gi % len(FALLBACK)]
            gi += 1
        ph = pick(th)
        if not ph:
            continue
        cuts.append((a2, b2, ph))
        taken += b2 - a2
    cuts.sort()
    segs, t = [], 0.0
    for a, b, ph in cuts:
        if a > t:
            segs.append((t, a, "K", None))
        segs.append((a, b, "B", ph))
        t = b
    if t < body:
        segs.append((t, body, "K", None))
    return segs


def title_png(hook, out):
    """The hook as a title in the black above the strip (no box, no name)."""
    words, _ = R._t5_layout(R.t5_lines(hook), H * 0.3)
    big = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    for wd, f, col, x, y in words:
        d.text((x, y), wd, font=f, fill=col + (255,))
    box = big.getbbox()
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if box:
        txt = big.crop(box)
        sc = min(1.0, 940 / txt.width, (BY - 120) / txt.height, 0.8)
        txt = txt.resize((int(txt.width * sc), int(txt.height * sc)), Image.LANCZOS)
        im.alpha_composite(txt, ((W - txt.width) // 2, BY - 50 - txt.height))
    im.save(out)
    return out


def caption_frames(phrases, body, tdir, title):
    """PNG sequence (concat list) of the word-by-word captions over the strip."""
    base = Image.open(title).convert("RGBA")
    seq = []

    def frame(ws, n):
        im = base.copy()
        if not ws:
            return im
        d = ImageDraw.Draw(im)
        e = emphasis(ws)
        size_s, size_e = 46, 96
        while True:
            fs, fe = font(SANS, size_s, 700), font(SCRIPT, size_e, 700)
            toks = [((w.lower().strip(",.") if i == e else w.upper()), fe if i == e else fs,
                     GOLD if i == e else WHITE, i == e) for i, w in enumerate(ws)]
            tw = sum(d.textlength(t, font=f) for t, f, _, _ in toks) + 18 * (len(toks) - 1)
            if tw <= W - 80 or size_s <= 30:
                break
            size_s, size_e = size_s - 4, size_e - 8
        x, base_y = (W - tw) / 2, BY + BH - 80
        for i, (t, f, c, emph) in enumerate(toks):
            if i >= n:
                break
            y = base_y - (size_e if emph else size_s + 6)
            d.text((x + 3, y + 4), t, font=f, fill=(0, 0, 0, 180))
            d.text((x, y), t, font=f, fill=c + (255,))
            x += d.textlength(t, font=f) + 18
        return im

    def add(im, d):
        p = os.path.join(tdir, f"{len(seq):04d}.png")
        im.save(p)
        seq.append((p, max(d, 1.0 / FPS)))

    t = 0.0
    for i, (a, b, text) in enumerate(phrases):
        a, b = max(a, 0.0), min(b, body)
        if b <= t:
            continue
        if a > t:
            add(frame([], 0), a - t)
            t = a
        ws = text.split()
        nxt = phrases[i + 1][0] if i + 1 < len(phrases) else body
        end = min(max(b, min(nxt, b + 0.6)), body)
        step = min(0.2, (end - t) / (len(ws) + 1))
        for n in range(1, len(ws) + 1):
            d = step if n < len(ws) else end - t - step * (len(ws) - 1)
            add(frame(ws, n), d)
        t = end
    if t < body:
        add(frame([], 0), body - t)
    lst = os.path.join(tdir, "list.txt")
    with open(lst, "w") as fh:
        for p, d in seq:
            fh.write(f"file '{p}'\nduration {d:.3f}\n")
        fh.write(f"file '{seq[-1][0]}'\n")
    return lst


def strip_filter():
    # the full 16:9 picture, exactly the strip size
    return (f"scale={BW}:{BH}:force_original_aspect_ratio=increase,crop={BW}:{BH},"
            f"setsar=1,fps={FPS},format=yuv420p")


def render(src, t_in, t_out, hook, phrases, dst, seed, cover=None):
    """One cinematic clip from the HD episode. phrases are clip-relative (a, b, text)."""
    tmp = tempfile.mkdtemp()
    body = t_out - t_in
    segs = plan(phrases, body, seed)
    # 1. the strip: Kevin and footage, cut on the phrases
    parts = []
    for i, (a, b, kind, ph) in enumerate(segs):
        out = os.path.join(tmp, f"s{i:02d}.mp4")
        d = b - a
        n = max(1, int(round(d * FPS)))
        if kind == "K":
            sh("ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t_in + a:.3f}", "-t", f"{d:.3f}", "-i", src,
               "-an", "-vf", strip_filter(), "-frames:v", str(n),
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", out)
        elif ph.endswith(".mp4"):
            # a real video cutaway: a stretch from its middle, graded like the photos
            try:
                vd = dur(ph)
            except Exception:
                vd = d + 1
            off = max(0.0, min(vd * 0.3, vd - d - 0.2))
            sh("ffmpeg", "-loglevel", "error", "-y", "-ss", f"{off:.2f}", "-t", f"{d:.3f}", "-i", ph, "-an",
               "-vf", strip_filter().replace(",format=yuv420p", "")
               + ",eq=contrast=1.06:saturation=0.9:brightness=-0.03,vignette=PI/5,format=yuv420p",
               "-frames:v", str(n), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", out)
            if dur(out) < d - 0.3:                     # clip shorter than asked: hold its last frame
                sh("ffmpeg", "-loglevel", "error", "-y", "-i", out, "-vf",
                   f"tpad=stop_mode=clone:stop_duration={d:.2f}", "-frames:v", str(n),
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", out + ".p.mp4")
                os.replace(out + ".p.mp4", out)
        else:
            sh("ffmpeg", "-loglevel", "error", "-y", "-loop", "1", "-i", ph, "-vf",
               f"scale=2160:-2,crop=2160:1216,zoompan=z='1+0.10*on/{n}':x='iw/2-(iw/zoom/2)+40*on/{n}'"
               f":y='ih/2-(ih/zoom/2)':d={n}:s={BW}x{BH}:fps={FPS},"
               f"eq=contrast=1.08:saturation=0.9:brightness=-0.04,vignette=PI/5,setsar=1,format=yuv420p",
               "-frames:v", str(n), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", out)
        parts.append(out)
    lst = os.path.join(tmp, "parts.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    strip = os.path.join(tmp, "strip.mp4")
    sh("ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", strip)
    # 2. the words and the title
    title = title_png(hook, os.path.join(tmp, "title.png"))
    tdir = os.path.join(tmp, "tx")
    os.makedirs(tdir)
    caps = caption_frames(phrases, body, tdir, title)
    # 3. the opening: Kevin's strongest 3 s, title above
    ca = os.path.join(tmp, "a.wav")
    sh("ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t_in:.3f}", "-t", f"{body:.3f}", "-i", src,
       "-vn", "-ac", "1", "-ar", "8000", ca)
    bw = t_in + R.best_window(ca, 0.0, max(R.T5_HOOK + 0.1, body - 2.5))
    bw = min(max(bw, t_in), t_out - R.T5_HOOK)
    # 4. the end card
    still = os.path.join(tmp, "still.png")
    sh("ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t_in + body / 2:.2f}", "-i", src, "-frames:v", "1", still)
    cta = os.path.join(tmp, "cta.png")
    R.t5_cta_png(still, cta, "youtube")
    fo = min(0.6, body * 0.1)
    hk = R.T5_HOOK
    fc = (
        f"color=c=black:s={W}x{H}:r={FPS}:d={hk}[bg0];"
        f"[0:v]trim={bw - t_in:.3f}:{bw - t_in + hk:.3f},setpts=PTS-STARTPTS,{strip_filter()}[hs];"
        f"[bg0][hs]overlay=0:{BY}[h0];[h0][5:v]overlay=0:0,format=yuv420p[hv];"
        f"[0:a]atrim={bw - t_in:.3f}:{bw - t_in + hk:.3f},asetpts=PTS-STARTPTS,"
        f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[ha];"
        f"color=c=black:s={W}x{H}:r={FPS}:d={body:.3f}[bg1];"
        f"[bg1][1:v]overlay=0:{BY}:shortest=1[b0];[2:v]fps={FPS},format=rgba[tx];"
        f"[b0][tx]overlay=0:0:eof_action=repeat,trim=0:{body:.3f},setpts=PTS-STARTPTS,"
        f"fade=t=out:st={body - fo:.3f}:d={fo:.3f},format=yuv420p[bv];"
        f"[0:a]atrim=0:{body:.3f},asetpts=PTS-STARTPTS,afade=t=out:st={body - fo:.3f}:d={fo:.3f},"
        f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[ba];"
        f"[3:v]scale={W}:{H},setsar=1,fps={FPS},format=yuv420p,fade=t=in:st=0:d=0.35[cv];"
        f"[4:a]aformat=sample_fmts=fltp:channel_layouts=stereo[ca];"
        f"[hv][ha][bv][ba][cv][ca]concat=n=3:v=1:a=1[v][a]")
    sh("ffmpeg", "-loglevel", "error", "-y",
       "-ss", f"{t_in:.3f}", "-t", f"{body:.3f}", "-i", src,
       "-i", strip,
       "-f", "concat", "-safe", "0", "-i", caps,
       "-loop", "1", "-framerate", str(FPS), "-t", str(R.T5_CTA), "-i", cta,
       "-f", "lavfi", "-t", str(R.T5_CTA), "-i", "anullsrc=r=48000:cl=stereo",
       "-i", title,
       "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
       "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-maxrate", "9000k", "-bufsize", "18000k",
       "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", dst)
    if cover:
        sh("ffmpeg", "-loglevel", "error", "-y", "-ss", f"{hk - 0.4:.2f}", "-i", dst,
           "-frames:v", "1", "-q:v", "2", cover)
    shutil.rmtree(tmp, ignore_errors=True)
    return segs


# ---------------------------------------------------------------- the jobs

def queued(man):
    return [c for c in man["clips"]
            if not c.get("done") and not c.get("posting") and not c.get("posted_at")
            and not any("posted" in str(v) for v in (c.get("status") or {}).values())
            and (c.get("cine_v") or 0) < CINE_V]


def find(series, f):
    brand, slug = R.slug_of(f)
    for key, spec in series.items():
        if spec["brand"] == brand:
            for c in spec["clips"]:
                if c["slug"] == slug:
                    return key, spec, c
    return None, None, None


def cmd_list():
    man = json.load(open(MAN))
    series = json.load(open(os.path.join(HERE, "kt_series.json")))
    files = [c["file"] for c in queued(man) if find(series, c["file"])[0]]
    print(f"{len(files)} clip(s) to cut cinematic: {files}")
    with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as fh:
        fh.write(f"matrix={json.dumps(files)}\ncount={len(files)}\n")


def cmd_one(f):
    os.makedirs(OUT, exist_ok=True)
    sys.path.insert(0, K)
    from transcribe import fetch_source  # noqa
    series = json.load(open(os.path.join(K, "kt_series.json")))
    key, spec, clip = find(series, f)
    if not key:
        raise SystemExit(f"{f}: not in kt_series.json")
    vid = spec["source"][:-4]
    src = fetch_source(vid)
    srt = os.path.join(K, "transcripts", f"{vid}.srt")
    if not os.path.exists(srt):
        subprocess.run(["gh", "release", "download", "sources", "-R", REPO, "-p", f"{vid}.srt.enc",
                        "-D", "/tmp", "--clobber"], check=True)
        subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-pass", "env:FACTORY_KEY",
                        "-in", f"/tmp/{vid}.srt.enc", "-out", srt], check=True)
    import kt_render
    t_in, t_out = float(clip["in"]), float(clip["out"])
    phrases = []
    try:
        import kt_words
        words = kt_words.words_for(src, t_in, t_out, f"{spec['brand']}/{clip['slug']}")
        fix = clip.get("fix")
        if fix and words:
            low = {k.lower(): v for k, v in fix.items()}
            words = [(a, b, low.get(w.lower().strip(), w)) for a, b, w in words]
        phrases = kt_render.phrases_from_words(words) if words else []
    except Exception as e:
        print(f"  word timings unavailable ({type(e).__name__}: {e}); using the transcript")
    if not phrases:
        cues = kt_render.burn.parse_srt(srt)
        phrases = kt_render.burn.phrases(cues, t_in, t_out)
    phrases = [(float(a), float(b), re.sub(r"[{}<>*_]", "", str(t))) for a, b, t in phrases]
    idx, _ = R.hooks_index()
    hook = idx.get(R.slug_of(f)) or clip.get("hook") or [clip["slug"]]
    asset = f.replace("/", "--")
    dst = os.path.join(OUT, "CINE__" + asset)
    cover = os.path.join(OUT, "CINE__" + asset.replace(".mp4", "__cover.jpg"))
    segs = render(src, t_in, t_out, hook, phrases, dst, clip["slug"], cover)
    b = sum(y - x for x, y, k, _ in segs if k == "B")
    print(f"cinematic {f}: {len(segs)} shots, footage {b:.1f}s of {t_out - t_in:.1f}s")


def cmd_commit(d):
    man = json.load(open(MAN))
    by = {c["file"]: c for c in queued(man)}
    n = 0
    for p in sorted(glob.glob(os.path.join(d, "**", "CINE__*.mp4"), recursive=True)):
        asset = os.path.basename(p)[len("CINE__"):]
        f = asset.replace("--", "/", 1)
        c = by.get(f)
        if not c:
            print("skip (posted or gone):", f)
            continue
        up = os.path.join("/tmp", asset)
        shutil.copy(p, up)
        subprocess.run(["gh", "release", "upload", "media", up, "-R", REPO, "--clobber"], check=True)
        os.remove(up)
        cv = p.replace(".mp4", "__cover.jpg")
        if os.path.exists(cv):
            cname = asset.replace(".mp4", "__cover.jpg")
            cup = os.path.join("/tmp", cname)
            shutil.copy(cv, cup)
            subprocess.run(["gh", "release", "upload", "media", cup, "-R", REPO, "--clobber"], check=False)
            os.remove(cup)
            c["cover"], c["cover_v"] = cname, R.COVER_V
        # restyle must leave it alone: it is finished in its own style
        c["style"], c["t5_v"], c["cine_v"] = R.STYLE, R.T5_V, CINE_V
        c["bytes"] = os.path.getsize(p)
        n += 1
        print("cinematic in:", f)
        json.dump(man, open(MAN, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"{n} clip(s) now cinematic")


if __name__ == "__main__":
    a = sys.argv[1:]
    {"list": lambda: cmd_list(), "one": lambda: cmd_one(a[1]), "commit": lambda: cmd_commit(a[1])}[a[0]]()
