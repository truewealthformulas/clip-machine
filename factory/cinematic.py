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
# SPANISH (14 Nov 2026, the owner: a second account, "Éxito Diario"-style, in
# Spanish). CINE_LANG=es: the footage is chosen from Kevin's English words as
# always, but the words on screen, the title and the end card are Spanish.
LANG = os.environ.get("CINE_LANG", "en").strip().lower() or "en"
# 13 Nov 2026: Pexels paused new API keys the day we asked. MIXKIT instead: free
# stock video, no key, licensed for use in videos. factory/assets/broll/videos.txt
# lists hand-picked clips per theme; Pexels (if a key ever exists) is tried first.
MIXKIT_LIST = os.path.join(HERE, "assets", "broll", "videos.txt")
CINE_V = 15   # 15: TikTok copy keeps the opening (context), 35-65 s.
CINE_V_14 = 14     # 14: @kevin_trudeau_student covers (B&W, red bar, caps + italic).
CINE_V_13 = 13   # 13: TikTok copy 20-40 s + jump cuts.
CINE_V_12 = 12   # 12: clips start where the thought starts, end where the sentence ends.
CINE_V_PREV = 11   # 11: cutaways chosen by Claude to match the words. 10: 10: TikTok full-screen cut. 9: 9: covers under a versioned name (the clobbered upload kept failing). 7: designed full-bleed covers, no navy band. 6: the clip ends where Kevin's story ends (finish_thought)
# 14 Nov 2026, the owner: "Like it, let's change them all" - the editorial look
# (factory/editorial.py). CINE_STYLE=classic gives back the title + caption bar.
STYLE = os.environ.get("CINE_STYLE", "editorial").strip().lower()
# The owner prefers the editorial ("HD") look for everything (14 Nov 2026).
# "auto": the documentary look when Kevin is telling his own story (lots of
# I / my / me), the editorial look otherwise. "doc" forces the documentary one.


FORCE_LOOK = [None]
# TIKTOK KEEPS THE BLACK-AND-TITLE LOOK (15 Nov 2026, the owner: "For TikTok
# let's continue doing this style black with the title"). Every clip is cut a
# second time in the classic look (title above the strip, words under Kevin);
# that copy is uploaded as <asset>__tt.mp4 and poster.tiktok() posts it.
TT_CLASSIC = os.environ.get("CINE_TT_CLASSIC", "1") == "1"


def look_for(phrases):
    if FORCE_LOOK[0]:
        return FORCE_LOOK[0]
    if STYLE in ("editorial", "doc", "classic"):
        return STYLE
    ws = [re.sub(r"[^a-z']", "", w.lower()) for _, _, t in phrases for w in t.split()]
    ws = [w for w in ws if w]
    first = sum(1 for w in ws if w in ("i", "i'm", "i've", "i'd", "i'll", "my", "me", "myself", "we", "our"))
    return "doc" if ws and first / len(ws) >= 0.07 else "editorial"


def music_bed(seconds, out, seed="x"):
    """A quiet, generated documentary pad (no licence questions): a slow minor
    chord that breathes, low-passed, with a little echo."""
    h = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    roots = [110.0, 98.0, 87.31, 116.54]
    r = roots[h % len(roots)]
    ex = (f"0.16*sin(2*PI*{r}*t)*(0.6+0.4*sin(2*PI*0.07*t))"
          f"+0.10*sin(2*PI*{r * 1.2:.3f}*t)*(0.6+0.4*sin(2*PI*0.05*t+1))"
          f"+0.09*sin(2*PI*{r * 1.5:.3f}*t)*(0.6+0.4*sin(2*PI*0.09*t+2))"
          f"+0.05*sin(2*PI*{r * 2:.3f}*t)*(0.5+0.5*sin(2*PI*0.11*t+3))")
    sh("ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
       f"aevalsrc={ex}:s=48000:d={seconds:.2f}",
       "-af", "lowpass=f=900,aecho=0.8:0.7:120|260:0.25|0.15,afade=t=in:d=1.5,"
       f"afade=t=out:st={max(0.0, seconds - 2):.2f}:d=2", "-ac", "2", out)
    return out
# NO TEASER (14 Nov 2026, the owner: "the first 3 seconds say something then they
# start from another point of the conversation"). The opening used to be Kevin's
# loudest 3 s lifted from later in the clip, then the clip from its start: the
# viewer hears a line out of order. Now the clip simply plays from its start,
# title on from frame one. CINE_TEASE=1 brings the old opening back.
TEASE = os.environ.get("CINE_TEASE", "0") == "1"
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


STOP_ES = set("el la los las un una unos unas y o pero de del a al en con por para que qu\u00e9 se su sus "
              "es son fue era ser estar est\u00e1 est\u00e1n lo le les me te nos mi mis tu tus muy m\u00e1s menos "
              "como c\u00f3mo cuando cu\u00e1ndo donde d\u00f3nde porque si s\u00ed no ya hay este esta esto ese esa eso "
              "aqu\u00ed all\u00ed tambi\u00e9n solo s\u00f3lo cada todo todos toda todas nada algo alguien \u00e9l ella "
              "ellos ellas usted ustedes yo t\u00fa nosotros entonces bueno tener tiene tengo hacer hace "
              "decir dice dijo puede pueden poder sobre entre hasta desde muy bien".split())


def translate_es(phrases, hook):
    """Phrases (a, b, text) and the hook, in natural Spanish; same count, same timing."""
    sys.path.insert(0, os.path.join(ROOT, "agents"))
    import common as AC
    texts = [t for _, _, t in phrases]
    hook_txt = " / ".join(hook) if isinstance(hook, (list, tuple)) else str(hook)
    sysmsg = ("You translate on-screen captions of a motivational talk into natural Latin American "
              "Spanish. Keep each caption short, spoken and punchy; keep the meaning; never add "
              "claims. Return JSON only.")
    user = ("Translate each caption in order (same number of items). Also translate the title; "
            "keep any word wrapped in *asterisks* wrapped in asterisks, and keep ' / ' line breaks.\n"
            + json.dumps({"title": hook_txt, "captions": texts}, ensure_ascii=False)
            + '\nReply: {"title": "...", "captions": ["...", ...]}')
    out = AC.ask_json(sysmsg, user, max_tokens=4000)
    caps = out.get("captions") or []
    if len(caps) != len(texts):
        raise RuntimeError(f"translation returned {len(caps)} captions for {len(texts)}")
    title = [x.strip() for x in str(out.get("title") or hook_txt).split(" / ") if x.strip()]
    return [(a, b, c) for (a, b, _), c in zip(phrases, caps)], title


def emphasis(words):
    """Index of the word to set in gold script: a theme word, else the longest real word."""
    best, score = None, 0
    for i, w in enumerate(words):
        c = _clean(w)
        th = theme_of(c)[0]
        if LANG == "es":
            c = re.sub(r"[^a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1\u00fc']", "", w.lower())
            th = None
            if not c or c in STOP_ES or len(c) < 5:
                continue
        elif not c or c in STOP or (len(c) < 5 and not th):
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


_MK_BAD = set()


def _fetch(url, dst, deadline_s=40):
    """Download with a WHOLE-FILE deadline. 15 Nov 2026: four cuts hung 50+
    minutes - urlopen's timeout is per socket read, so a server trickling bytes
    never trips it. Now a download that is not done in deadline_s is dropped."""
    import time
    import urllib.request
    t0 = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 clip-machine"})
    with urllib.request.urlopen(req, timeout=15) as r, open(dst, "wb") as fh:
        while True:
            b = r.read(1 << 16)
            if not b:
                break
            fh.write(b)
            if time.time() - t0 > deadline_s:
                raise TimeoutError(f"download over {deadline_s}s")


def mixkit_file(mid):
    """Download one Mixkit clip (largest size it has), cached per runner."""
    n = mid[2:]
    p = os.path.join(PEX_DIR, f"v_{mid}.mp4")
    if os.path.exists(p):
        return p
    if mid in _MK_BAD:
        raise RuntimeError(f"mixkit {n}: failed earlier in this run")
    os.makedirs(PEX_DIR, exist_ok=True)
    import urllib.request
    for size in ("1080", "720", "360"):
        url = f"https://assets.mixkit.co/videos/{n}/{n}-{size}.mp4"
        try:
            _fetch(url, p + ".part")
            if os.path.getsize(p + ".part") > 50000:
                os.replace(p + ".part", p)
                return p
        except Exception:
            continue
    _MK_BAD.add(mid)
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


# FOOTAGE THAT MATCHES THE WORDS (16 Nov 2026, the owner: "It shows a city and
# he is talking about a pad of paper"). The old picker matched a dozen broad
# themes and filled the rest with generic city/sunrise shots. Now Claude reads
# the phrases and names only the moments with something concrete to show
# ("pad of paper" -> "hand writing on a notepad"), Mixkit is searched for exactly
# that, and every other moment stays on Kevin. No match = no cutaway.
SMART = os.environ.get("CINE_SMART", "1") == "1"


def smart_picks(phrases, lo, hi):
    """{phrase index: search query} for literal, showable moments, or None if Claude is unavailable."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "agents"))
        import common as AC
    except Exception:
        return None
    lines = "\n".join(f"[{i}] {a:.1f}s: {t}" for i, (a, b, t) in enumerate(phrases) if a >= lo and b <= hi)
    if not lines:
        return {}
    try:
        out = AC.ask_json(
            "You pick stock-footage cutaways for a talking-head clip. A cutaway must SHOW LITERALLY "
            "what the speaker is saying at that moment (an object, an action, a place he names). "
            "Never pick a cutaway for abstract talk. Return JSON only.",
            "Kevin's words, numbered, with start times:\n" + lines + "\n\n"
            "Choose at most 5 moments, at least 6 seconds apart, where a short stock video would show "
            "exactly what he says (e.g. 'pad of paper' -> 'hand writing on notepad', 'phone calls' -> "
            "'phone ringing on desk', 'open the mail' -> 'opening envelope', 'gold' -> 'gold bars'). "
            "For each give a 2-4 word stock-video search query in English. Skip anything abstract. "
            'Reply: {"picks": [{"i": N, "query": "..."}]}', max_tokens=800)
        res = {}
        for p in out.get("picks") or []:
            i, q = int(p.get("i")), str(p.get("query") or "").strip()
            if q and 0 <= i < len(phrases):
                res[i] = q
        print(f"  cutaways: {res}", flush=True)
        return res
    except Exception as e:
        print(f"  cutaway picks unavailable ({type(e).__name__}: {e})", flush=True)
        return None


def mixkit_search(query, seed=""):
    """Download the best Mixkit video for a search query (search page -> mp4)."""
    import urllib.request
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
    key = "mks_" + slug
    p = os.path.join(PEX_DIR, f"v_{key}.mp4")
    if os.path.exists(p):
        return p
    os.makedirs(PEX_DIR, exist_ok=True)
    req = urllib.request.Request(f"https://mixkit.co/free-stock-video/{slug}/",
                                 headers={"User-Agent": "Mozilla/5.0 clip-machine"})
    with urllib.request.urlopen(req, timeout=20) as r:
        html = r.read(3_000_000).decode("utf-8", "ignore")
    urls = []
    for u in re.findall(r"https://assets\.mixkit\.co/[^\"'\s]+?-360\.mp4", html):
        if u not in urls:
            urls.append(u)
    for u in urls[:4]:
        for size in ("720", "1080", "360"):
            try:
                _fetch(u[:-len("360.mp4")] + size + ".mp4", p + ".part")
                if os.path.getsize(p + ".part") > 50000:
                    os.replace(p + ".part", p)
                    return p
            except Exception:
                continue
    raise RuntimeError(f"mixkit search '{query}': nothing downloadable")


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
    smart = smart_picks(phrases, lo, hi) if SMART else None
    if smart is not None:
        cuts = []
        for i in sorted(smart):
            a, b, _ = phrases[i]
            a2, b2 = a, min(max(b, a + 2.4), a + 4.0, hi)
            if b2 - a2 < 2.0 or any(not (b2 + 2.0 <= x or a2 >= y + 2.0) for x, y, _ in cuts):
                continue
            try:
                cuts.append((a2, b2, mixkit_search(smart[i], seed)))
            except Exception as e:
                print(f"  cutaway '{smart[i]}': {type(e).__name__}: {e}", flush=True)
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
            continue              # 16 Nov 2026: no unrelated filler footage
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


LAST_LOOK = ["classic"]


def render(src, t_in, t_out, hook, phrases, dst, seed, cover=None):
    """One cinematic clip from the HD episode. phrases are clip-relative (a, b, text)."""
    tmp = tempfile.mkdtemp()
    body = t_out - t_in
    segs = plan(phrases, body, seed)          # footage is matched on Kevin's own (English) words
    cta_kind = "youtube"
    if LANG == "es":
        phrases, hook = translate_es(phrases, hook)
        cta_kind = "youtube_es"
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
    look = look_for(phrases)
    LAST_LOOK[0] = look
    if look in ("editorial", "doc"):
        import editorial as ED
        ed = os.path.join(tmp, "strip_ed.mp4")
        ED.apply(strip, ed, [(max(0.0, a), min(b, body), t) for a, b, t in phrases if b > 0 and a < body],
                 segs, body, emphasis, BW, BH, FPS, mode=look, hook=hook)
        strip = ed
        title = os.path.join(tmp, "blank.png")
        Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(title)
        caps = caption_frames([], body, tdir, title)
    else:
        caps = caption_frames(phrases, body, tdir, title)
    # 3. the opening: Kevin's strongest 3 s, title above
    ca = os.path.join(tmp, "a.wav")
    sh("ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t_in:.3f}", "-t", f"{body:.3f}", "-i", src,
       "-vn", "-ac", "1", "-ar", "8000", ca)
    bw = t_in + (R.best_window(ca, 0.0, max(R.T5_HOOK + 0.1, body - 2.5)) if TEASE else 0.0)
    bw = min(max(bw, t_in), t_out - R.T5_HOOK)
    # 4. the end card
    still = os.path.join(tmp, "still.png")
    sh("ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t_in + body / 2:.2f}", "-i", src, "-frames:v", "1", still)
    cta = os.path.join(tmp, "cta.png")
    R.t5_cta_png(still, cta, cta_kind)
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
    if not TEASE:                                    # straight from the start, no lifted opening
        fc = fc.split(f"color=c=black:s={W}x{H}:r={FPS}:d={body:.3f}[bg1];", 1)[1]
        fc = f"color=c=black:s={W}x{H}:r={FPS}:d={body:.3f}[bg1];" + fc
        fc = fc.replace("[hv][ha][bv][ba][cv][ca]concat=n=3", "[bv][ba][cv][ca]concat=n=2")
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
    if LAST_LOOK[0] == "doc":                 # the documentary music bed under Kevin's voice
        bed = music_bed(dur(dst), os.path.join(tmp, "bed.wav"), seed=str(seed))
        mixed = dst + ".m.mp4"
        sh("ffmpeg", "-loglevel", "error", "-y", "-i", dst, "-i", bed, "-filter_complex",
           "[1:a]volume=0.22[m];[0:a][m]amix=inputs=2:duration=first:normalize=0[a]",
           "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
           "-movflags", "+faststart", mixed)
        os.replace(mixed, dst)
    if cover:
        made = False
        if LAST_LOOK[0] in ("editorial", "doc"):
            # 15 Nov 2026: full-bleed covers, no navy band (editorial.make_cover)
            try:
                import editorial as ED
                ks = [(a, b) for a, b, k, _ in segs if k == "K" and b - a > 1.0]
                a, b = (ks[len(ks) // 2] if ks else (1.0, 2.0))
                kinds = [k for k in os.environ.get("CINE_COVERS", "student").split(",") if k]
                kind = kinds[int(hashlib.md5(str(seed).encode()).hexdigest(), 16) % len(kinds)]
                ED.make_cover(src, t_in + (a + b) / 2, hook, cover, kind=kind, emphasis=emphasis)
                made = True
                print(f"  cover: {kind}", flush=True)
            except Exception as e:
                print(f"  cover: designed cover failed ({type(e).__name__}: {e}); using a frame", flush=True)
        if not made:
            sh("ffmpeg", "-loglevel", "error", "-y", "-ss", f"{(hk - 0.4) if TEASE else 1.2:.2f}", "-i", dst,
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


# TIKTOK x2 (17 Nov 2026, the owner: "Let's make 5 more posts on TikTok per day
# so in total 10"). Instagram's queue only feeds 5 a day, so the extra five come
# from the BACKLOG: clips already posted elsewhere that never reached TikTok (63
# of them died on the October token failure). CINE_TT_ONLY=1 cuts just their
# TikTok version (full screen, the one-clear-point check included);
# tiktok_extra.py posts them in the extra TikTok slots.
TT_ONLY = os.environ.get("CINE_TT_ONLY") == "1"
TT_BATCH = int(os.environ.get("CINE_TT_BATCH", "6"))


def tt_backlog(man, series):
    out = []
    for c in man["clips"]:
        t = str((c.get("status") or {}).get("tiktok") or "")
        if (c.get("posted_at") and not c.get("tt_extra") and not c.get("dropped")
                and not any(k in t for k in ("inbox", "posted", "rocess"))
                and find(series, c["file"])[0]):
            out.append(c["file"])
    return out


def cmd_list():
    man = json.load(open(MAN))
    series = json.load(open(os.path.join(HERE, "kt_series.json")))
    if TT_ONLY:
        files = tt_backlog(man, series)[:TT_BATCH]
    else:
        files = [c["file"] for c in queued(man) if find(series, c["file"])[0]]
    print(f"{len(files)} clip(s) to cut cinematic: {files}")
    with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as fh:
        fh.write(f"matrix={json.dumps(files)}\ncount={len(files)}\n")


MAX_LEN = float(os.environ.get("CINE_MAX_LEN", "90"))


def finish_thought(srt, t_in, t_out):
    """FINISH THE STORY (14 Nov 2026, the owner: "Why cut it? Finish the last
    story in the clip"). The friends-and-money clip ended on "When I was..." -
    Kevin starting a story the clip never told. Read the episode transcript
    around the cut and move the end to where the sentence or story that is
    running at the cut actually concludes (the clip stays under MAX_LEN).
    Claude decides where the story ends; without it, at least the sentence is
    finished."""
    import kt_render
    cues = [c for c in kt_render.burn.parse_srt(srt) if c[1] > t_out - 20 and c[0] < t_out + 70]
    limit = min(t_in + MAX_LEN - R.T5_CTA, t_out + 60)
    after = [c for c in cues if c[0] >= t_out - 0.5 and c[1] <= limit]
    if not after:
        return t_out
    new = t_out
    try:
        sys.path.insert(0, os.path.join(ROOT, "agents"))
        import common as AC
        lines = "\n".join(f"[{i}] {a:.1f}-{b:.1f}s: {t}" for i, (a, b, t) in enumerate(cues) if b <= limit)
        out = AC.ask_json(
            "You edit short video clips of a speaker. A clip must never end in the middle of a "
            "sentence or in the middle of a story. Return JSON only.",
            f"The clip currently ends at {t_out:.1f}s. Transcript lines around that point:\n{lines}\n\n"
            "If a sentence, point or story is still unfinished at the cut, give the index of the line "
            "where it naturally concludes (the punchline or lesson of the story included). If the clip "
            "already ends cleanly, give the index of the line ending at or just before the cut. "
            'Reply: {"end_index": N, "why": "..."}', max_tokens=600)
        i = int(out.get("end_index"))
        if 0 <= i < len(cues) and cues[i][1] <= limit:
            # 16 Nov 2026 (the owner: "the last video is missing information"):
            # a transcript line can stop mid-sentence ("...your goals and dreams
            # in"), so keep going to the line that closes the sentence.
            while (i + 1 < len(cues) and not cues[i][2].rstrip().endswith((".", "?", "!"))
                   and cues[i + 1][1] <= limit):
                i += 1
            new = max(t_out, cues[i][1] + 0.35)
            print(f"  end: {t_out:.1f}s -> {new:.1f}s ({str(out.get('why'))[:100]})", flush=True)
            return new
    except Exception as e:
        print(f"  end check by Claude unavailable ({type(e).__name__}: {e}); finishing the sentence", flush=True)
    for a, b, t in after:                       # fallback: through the end of the running sentence
        new = b + 0.35
        if t.rstrip().endswith((".", "?", "!")):
            break
    return max(t_out, new)


def start_thought(srt, t_in, t_out):
    """THE BEGINNING TOO (16 Nov 2026). A clip opening on "...when your attitude
    is right" has lost the setup. Claude reads the lines before the cut and moves
    the start back to where the point begins (at most 25 s, and the clip stays
    under MAX_LEN); without Claude, at least to the start of the sentence."""
    import kt_render
    cues = [c for c in kt_render.burn.parse_srt(srt) if c[1] > t_in - 30 and c[0] < t_in + 12]
    if not cues:
        return t_in
    floor = max(0.0, t_in - 25, t_out + R.T5_CTA - MAX_LEN)
    try:
        sys.path.insert(0, os.path.join(ROOT, "agents"))
        import common as AC
        lines = "\n".join(f"[{i}] {a:.1f}-{b:.1f}s: {t}" for i, (a, b, t) in enumerate(cues) if a >= floor)
        idx = [i for i, (a, b, t) in enumerate(cues) if a >= floor]
        out = AC.ask_json(
            "You edit short video clips of a speaker. A clip must start where a thought starts, never "
            "in the middle of a sentence or after the setup of the point. Return JSON only.",
            f"The clip currently starts at {t_in:.1f}s. Transcript lines around that point:\n{lines}\n\n"
            "Give the index of the line where the thought that is running at the start actually begins "
            "(its setup included). If the clip already starts cleanly, give the index of the line that "
            'starts at the cut. Reply: {"start_index": N, "why": "..."}', max_tokens=600)
        i = int(out.get("start_index"))
        if i in idx:
            new = min(t_in, max(floor, cues[i][0] - 0.15))
            if new < t_in - 0.3:
                print(f"  start: {t_in:.1f}s -> {new:.1f}s ({str(out.get('why'))[:100]})", flush=True)
            return new
    except Exception as e:
        print(f"  start check by Claude unavailable ({type(e).__name__}: {e})", flush=True)
    before = [c for c in cues if c[0] < t_in and c[0] >= floor]
    for k in range(len(before) - 1, -1, -1):        # back to the start of the running sentence
        if k == 0 or before[k - 1][2].rstrip().endswith((".", "?", "!")):
            return min(t_in, before[k][0] - 0.15)
    return t_in


POINT_MIN = int(os.environ.get("CINE_POINT_MIN", "7"))


def point_window(srt, t_in, t_out):
    """ONE CLEAR POINT OR NOTHING (16 Nov 2026, the owner on the gut-feeling clip:
    "That video makes no point or sense... says nothing").

    Claude reads the transcript from 40 s before the clip to 60 s after it and
    picks the window (setup -> point -> payoff, whole sentences, 25-85 s) that a
    stranger would understand on its own, and scores it 1-10. Returns
    (t_in, t_out, score, why); score None when Claude is unavailable."""
    import kt_render
    cues = [c for c in kt_render.burn.parse_srt(srt) if c[1] > t_in - 40 and c[0] < t_out + 60]
    if not cues:
        return t_in, t_out, None, ""
    sys.path.insert(0, os.path.join(ROOT, "agents"))
    import common as AC
    lines = "\n".join(f"[{i}] {a:.1f}-{b:.1f}s: {t}" for i, (a, b, t) in enumerate(cues))
    out = AC.ask_json(
        "You are a strict editor of short social clips of a speaker (Kevin Trudeau). Every clip must make "
        "ONE clear, complete point that a stranger understands with no context: the setup, the point "
        "itself and its payoff or lesson, in whole sentences. Never start or end mid-sentence. Return JSON only.",
        f"The clip is currently {t_in:.1f}s-{t_out:.1f}s. Transcript lines around it:\n{lines}\n\n"
        f"Choose the best window (start line index, end line index) between {PW_MIN:.0f} and {PW_MAX:.0f} seconds long that "
        "makes one clear point on its own, staying close to the current clip. Then score that window 1-10: "
        "10 = a stranger gets a clear, valuable point; 5 = vague or depends on missing context; "
        "1 = says nothing. Be honest; vague motivational talk without a concrete point scores 5 or less. "
        'Reply: {"start": N, "end": M, "score": S, "point": "the point in one sentence", "why": "..."}',
        max_tokens=800)
    a, b = int(out.get("start")), int(out.get("end"))
    sc = int(out.get("score"))
    if not (0 <= a <= b < len(cues)):
        raise ValueError(f"bad window {a}-{b}")
    while b + 1 < len(cues) and not cues[b][2].rstrip().endswith((".", "?", "!")):
        b += 1
    # Facebook (18 Nov 2026): "post more reels over 60 seconds - views up 50%".
    # Too short -> carry on to the end of the next whole sentences.
    while cues[b][1] - cues[a][0] < PW_MIN and b + 1 < len(cues) and cues[b + 1][1] - cues[a][0] <= PW_MAX:
        b += 1
        while b + 1 < len(cues) and not cues[b][2].rstrip().endswith((".", "?", "!")):
            b += 1
    new_in, new_out = cues[a][0] - 0.15, cues[b][1] + 0.35
    if new_out - new_in > MAX_LEN - R.T5_CTA:
        new_out = new_in + MAX_LEN - R.T5_CTA
    print(f"  point ({sc}/10): {str(out.get('point'))[:120]} | {t_in:.1f}-{t_out:.1f}s -> "
          f"{new_in:.1f}-{new_out:.1f}s", flush=True)
    return new_in, new_out, sc, str(out.get("point") or "")


# 22 Nov 2026, the owner: "the last 3 TikTok videos have no context, are too
# short and miss what Kevin is previously talking about". The TikTok copy now
# KEEPS THE OPENING (the setup the full clip was chosen to start on) and only
# ends earlier, at the first place the point is complete - 35 to 65 s.
TT_MAX = float(os.environ.get("TT_MAX_LEN", "65"))
TT_MIN = float(os.environ.get("TT_MIN_LEN", "35"))
# 18 Nov 2026, the owner: "Facebook mention 1 min videos". The full story (YouTube,
# Instagram, Facebook) runs 62-85 s; TikTok keeps its own 20-40 s copy.
PW_MIN = float(os.environ.get("POINT_MIN_S", "62"))
PW_MAX = float(os.environ.get("POINT_MAX_S", "85"))


def tt_short(phrases):
    """SHORT FOR TIKTOK (17 Nov 2026: TikTok stuck under 185 views since the
    clips grew to 55-75 s). TikTok pushes what people watch to the end, so its
    copy keeps only the strongest 20-40 s that still make the point - Claude
    picks the phrases; the other platforms keep the full story.
    Returns (first, last) phrase indexes, or None to keep everything."""
    if not phrases or phrases[-1][1] - phrases[0][0] <= TT_MAX:
        return None
    try:
        sys.path.insert(0, os.path.join(ROOT, "agents"))
        import common as AC
        lines = "\n".join(f"[{i}] {a:.1f}-{b:.1f}s: {t}" for i, (a, b, t) in enumerate(phrases))
        out = AC.ask_json(
            "You shorten a speaker's clip for TikTok. The clip ALWAYS starts at phrase 0 - that is where "
            "he sets up what he is talking about, and a stranger needs it. You only choose where it ENDS: "
            "the earliest phrase where his point is complete and lands (the payoff line), so nothing "
            "important is cut. Whole sentences only. Return JSON only.",
            f"Phrases of the clip:\n{lines}\n\nPick the last phrase so the clip runs {TT_MIN:.0f}-{TT_MAX:.0f} s "
            'from phrase 0 and ends on the payoff. Reply: {"last": M, "why": "..."}', max_tokens=500)
        a, b = 0, int(out["last"])
        while b + 1 < len(phrases) and not phrases[b][2].rstrip().endswith((".", "?", "!")) \
                and phrases[b + 1][1] - phrases[a][0] <= TT_MAX + 8:
            b += 1
        if 0 <= a <= b < len(phrases) and TT_MIN - 8 <= phrases[b][1] - phrases[a][0] <= TT_MAX + 8:
            print(f"  tiktok window: phrases {a}-{b} ({phrases[b][1] - phrases[a][0]:.1f}s) {out.get('why', '')[:90]}",
                  flush=True)
            return a, b
    except Exception as e:
        print(f"  tiktok window unavailable ({type(e).__name__}: {e})", flush=True)
    return None


def render_tiktok(src, t_in, t_out, hook, phrases, segs, dst, seed):
    import tiktok_cut as TC
    w = tt_short(phrases)
    if w:
        a, b = w
        s0, s1 = max(0.0, phrases[a][0] - 0.15), phrases[b][1] + 0.35
        ph2 = [(x - s0, y - s0, t) for x, y, t in phrases[a:b + 1]]
        segs2 = plan(ph2, s1 - s0, seed)
        return TC.render_tt(src, t_in + s0, t_in + s1, hook, ph2, segs2, dst, emphasis)
    return TC.render_tt(src, t_in, t_out, hook, phrases, segs, dst, emphasis)


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
    if os.environ.get("CINE_FINISH", "1") == "1":
        score = None
        try:
            t_in, t_out, score, _ = point_window(srt, t_in, t_out)
        except Exception as e:
            print(f"  point check unavailable ({type(e).__name__}: {e}); trimming to whole thoughts", flush=True)
            t_in = start_thought(srt, t_in, t_out)
            t_out = finish_thought(srt, t_in, t_out)
        if score is not None and score < POINT_MIN:
            # not worth posting: tell the swap to take it out of the queue
            os.makedirs(OUT, exist_ok=True)
            with open(os.path.join(OUT, ("DROPTT__" if TT_ONLY else "DROP__") + f.replace("/", "--") + ".json"), "w") as fh:
                json.dump({"file": f, "score": score}, fh)
            print(f"cinematic {f}: DROPPED - no clear point (score {score}/10)", flush=True)
            return
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
    if TT_ONLY:
        segs = plan(phrases, t_out - t_in, clip["slug"])
        render_tiktok(src, t_in, t_out, hook, phrases, segs, os.path.join(OUT, "TTX__" + asset), clip["slug"])
        print(f"tiktok backlog {f}: cut ({t_out - t_in:.1f}s)", flush=True)
        return
    dst = os.path.join(OUT, "CINE__" + asset)
    cover = os.path.join(OUT, "CINE__" + asset.replace(".mp4", "__cover.jpg"))
    segs = render(src, t_in, t_out, hook, phrases, dst, clip["slug"], cover)
    if TT_CLASSIC:
        # 16 Nov 2026: TikTok gets the full-screen cut (factory/tiktok_cut.py);
        # CINE_TT=classic gives back the black-and-title copy.
        try:
            if os.environ.get("CINE_TT", "full") == "classic":
                FORCE_LOOK[0] = "classic"
                render(src, t_in, t_out, hook, phrases, os.path.join(OUT, "CINETT__" + asset), clip["slug"], None)
            else:
                render_tiktok(src, t_in, t_out, hook, phrases, segs, os.path.join(OUT, "CINETT__" + asset), clip["slug"])
            print(f"  tiktok copy: {os.environ.get('CINE_TT', 'full')}", flush=True)
        except Exception as e:
            print(f"  tiktok copy failed ({type(e).__name__}: {e})", flush=True)
        finally:
            FORCE_LOOK[0] = None
    b = sum(y - x for x, y, k, _ in segs if k == "B")
    print(f"cinematic {f}: {len(segs)} shots, footage {b:.1f}s of {t_out - t_in:.1f}s")


def _drops(d, m):
    """Clips Claude scored as saying nothing: out of the queue, never posted."""
    n = 0
    for p in glob.glob(os.path.join(d, "**", "DROP__*.json"), recursive=True):
        info = json.load(open(p))
        for c in m.get("clips", []):
            if c.get("file") == info["file"] and not c.get("posted_at") and not c.get("done"):
                c["done"] = True
                c["dropped"] = f"no clear point ({info['score']}/10)"
                n += 1
    return n


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
        # THE REAL COVER BUG (16 Nov 2026): the artifact folder is named after the
        # clip ("cine-KT_X-01_y.mp4/"), so p.replace(".mp4", ...) rewrote the
        # FOLDER too and the cover was never found - every queue kept the old
        # navy-band cover. Only the file name is changed now.
        cv = os.path.join(os.path.dirname(p), os.path.basename(p)[:-4] + "__cover.jpg")
        print(f"  cover file {'found' if os.path.exists(cv) else 'MISSING'}: {os.path.basename(cv)}", flush=True)
        if os.path.exists(cv):
            # A NEW NAME, NOT --clobber (15 Nov 2026). The queue kept the old
            # navy-band covers: re-uploading a small file over a same-named asset
            # right after --clobber deleted it fails ("already exists") while the
            # big mp4 got through. A versioned name never collides; retried too.
            cname = asset.replace(".mp4", f"__cover{CINE_V}.jpg")
            cup = os.path.join("/tmp", cname)
            shutil.copy(cv, cup)
            ok = False
            for i in range(3):
                r = subprocess.run(["gh", "release", "upload", "media", cup, "-R", REPO, "--clobber"],
                                   capture_output=True, text=True)
                if r.returncode == 0:
                    ok = True
                    break
                print(f"  cover upload try {i + 1}: {r.stderr.strip()[:200]}", flush=True)
                import time
                time.sleep(8)
            os.remove(cup)
            if ok:
                c["cover"], c["cover_v"] = cname, R.COVER_V
                c["cine_cover"] = CINE_V
            else:
                print("  cover upload FAILED:", cname, flush=True)
        tt = os.path.join(os.path.dirname(p), "CINETT__" + asset)
        if os.path.exists(tt):
            tname = asset.replace(".mp4", "__tt.mp4")
            tup = os.path.join("/tmp", tname)
            shutil.copy(tt, tup)
            if subprocess.run(["gh", "release", "upload", "media", tup, "-R", REPO, "--clobber"]).returncode == 0:
                c["tiktok_file"] = tname
            os.remove(tup)
        # restyle must leave it alone: it is finished in its own style
        c["style"], c["t5_v"], c["cine_v"] = R.STYLE, R.T5_V, CINE_V
        c["bytes"] = os.path.getsize(p)
        n += 1
        print("cinematic in:", f)
        json.dump(man, open(MAN, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    for p in sorted(glob.glob(os.path.join(d, "**", "TTX__*.mp4"), recursive=True)):
        asset = os.path.basename(p)[len("TTX__"):]
        f = asset.replace("--", "/", 1)
        c = next((x for x in man["clips"] if x["file"] == f), None)
        if not c:
            continue
        tname = asset.replace(".mp4", "__tt.mp4")
        tup = os.path.join("/tmp", tname)
        shutil.copy(p, tup)
        if subprocess.run(["gh", "release", "upload", "media", tup, "-R", REPO, "--clobber"]).returncode == 0:
            c["tiktok_file"], c["tt_extra"] = tname, "ready"
            print("tiktok backlog ready:", f)
        os.remove(tup)
    for p in glob.glob(os.path.join(d, "**", "DROPTT__*.json"), recursive=True):
        info = json.load(open(p))
        c = next((x for x in man["clips"] if x["file"] == info["file"]), None)
        if c:
            c["tt_extra"] = f"dropped - no clear point ({info['score']}/10)"
    json.dump(man, open(MAN, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    dn = _drops(d, man)
    if dn:
        json.dump(man, open(MAN, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        print(f"{dn} clip(s) dropped: no clear point")
    print(f"{n} clip(s) now cinematic")


if __name__ == "__main__":
    a = sys.argv[1:]
    {"list": lambda: cmd_list(), "one": lambda: cmd_one(a[1]), "commit": lambda: cmd_commit(a[1])}[a[0]]()
