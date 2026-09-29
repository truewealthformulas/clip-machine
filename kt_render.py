#!/usr/bin/env python3
"""Render a clip end to end in the KT house style: full bleed, no black bars.

WHY THIS REPLACES kt_clips + kt_burn FOR RENDERING.
27 Aug 2026, the owner sent a screen recording of @thekevintrudeau's own Reels tab
with the view counts visible - 1.8M, 165K, 106K, 98.9K - and said our hooks were
"basically garbage comparing it to kts". He was right, and the gap was not only
in the words. Put our frame next to his and three things are wrong with ours:

  1. FIFTY-EIGHT PERCENT OF OUR FRAME IS BLACK. The old letterbox put a 4:3 crop
     at y=555..1365 on a 1920 canvas. Every one of his fills the whole frame. We
     were paying for a billboard and using half of it.
  2. OUR HOOK IS A SERIF IN WHITE BOXES. Georgia Bold, black on white, reads as a
     book jacket. His is a heavy geometric sans, ALL CAPS, straight on the video.
  3. OUR HOOK NEVER LEAVES. It sat there for all 126 seconds. His is gone in ~3
     and the spoken captions take the same spot.

WHAT WAS COPIED, AND FROM WHAT EVIDENCE. Every number below was measured off the
recording he sent, not guessed:
  - Full bleed 9:16. No bars anywhere in his feed.
  - Type sits at ~58-60% of frame height, over the chest, never the bottom edge.
  - White by default, ONE line in yellow. He uses yellow for the payoff line
    ("BEER IS MORE" white / "HYDRATING THAN WATER" yellow, 1.8M views).
  - Heavy drop shadow, no cartoon stroke.
  - Spoken captions are 1-3 words, not a subtitle line. "THE ALPS". "WAITRESS".

FONT. Montserrat Black, fetched to bin/. Do NOT swap in a variable-weight file -
freetype renders the default instance, which is Regular, and the clip ships thin.
That is the same trap Helvetica Neue set in August. Arial Black is the fallback.

    python3 kt_render.py debt_trap                     # plan, renders nothing
    python3 kt_render.py debt_trap --apply
    python3 kt_render.py debt_trap --apply --only WE-OWN-THAT-PERSON
    python3 kt_render.py --all --apply                 # every series
"""
import json
import re
import os
import subprocess
import sys

import kt_burn as burn

HOME = os.path.expanduser("~/ClipMachine")
SERIES = os.path.join(HOME, "kt_series.json")
SRC_DIR = os.path.join(HOME, "Content/1_RAW/KT_SOURCE")
TRANSCRIPTS = os.path.join(HOME, "transcripts")
OUT_ROOT = os.path.join(HOME, "POST_TODAY")
FFMPEG = os.environ.get("WF_FFMPEG", os.path.join(HOME, "bin/ffmpeg"))
# Set KT_OUT to render somewhere else - used to review a new style without
# overwriting clips the cloud already has scheduled.
OUT_DIR = os.environ.get("KT_OUT")

FONT = os.path.join(HOME, "bin/mont_black.ttf")
if not os.path.exists(FONT):                    # never silently ship a thin font
    FONT = "/System/Library/Fonts/Supplemental/Arial Black.ttf"

W, H = 1080, 1920

# --- the type, measured off his feed -----------------------------------------
YELLOW = "#FFE500"
HOOK_SECS = 4.5          # 16 Sept 2026, the owner: hooks "fade away too fast, an average viewer
                         # cannot keep up". 3.0s left ~2.7s at full opacity - not enough to
                         # read a two-line hook while watching a face. Applies to KT, brand-2 owner, VSC.
FADE_OUT = 0.9           # every clip fades out, picture and sound
HOOK_Y1, HOOK_Y2 = 1000, 1116
CAP_Y = 1050             # captions sit here for the whole clip
HOOK_BOTTOM = 930        # the hook's LAST line ends here, clear of CAP_Y
CAP_SIZE = 72
CAP_MAX = 20             # a CEILING, not a target. His own body captions run
                         # 8-15 chars ("THE ALPS", "WITH THIS BROWN") but they
                         # break on MEANING. At 15 the scorer could not fit
                         # "burns that all off" and had to break mid-phrase, so
                         # the ceiling is 20 and nothing rewards filling it.
SHADOW = ":shadowx=0:shadowy=7:shadowcolor=black@0.80:borderw=3:bordercolor=black@0.45"


def esc(t):
    return burn.esc(t)


def font_arg(path):
    return path.replace("\\", "\\\\").replace(":", "\\:").replace(" ", "\\ ")


def source_size(src):
    out = subprocess.run([FFMPEG, "-i", src], capture_output=True, text=True).stderr
    for line in out.splitlines():
        if "Video:" in line:
            for tok in line.split(","):
                tok = tok.strip().split(" ")[0]
                if "x" in tok:
                    a, _, b = tok.partition("x")
                    if a.isdigit() and b.isdigit():
                        return int(a), int(b)
    raise SystemExit(f"cannot read size: {src}")


def _x_expr(sw, cw, shots):
    """A crop-x that CHANGES with the shot, as an ffmpeg expression.

    11 Sept 2026, and this is the owner's catch. He sent a frame of clip 02 showing
    an empty patio and a stranger's arm, and said: an interview cuts between
    setups, and when their camera pulls back to the two-shot a fixed centre crop
    lands on nobody.

    He had told me this before. I looked at ONE frame, saw Kevin right of centre,
    and shipped a single crop for the whole clip. Measured after he complained:

        0.0- 8.0s  cx 0.668   face 16% of width
        8.0-16.0s  cx 0.825   face  8% of width   <- the wide two-shot
       16.0-52.8s  cx 0.621   face 17% of width

    Three setups, one crop, and cx was 0.5 for all of them. Commas are escaped
    because a bare comma ends a filter in a filtergraph.
    """
    def px(cx):
        return max(0, min(int(round(sw * cx - cw / 2)), sw - cw))
    expr = str(px(shots[-1]["cx"]))
    for sh in reversed(shots[:-1]):
        expr = f"if(lt(t\\,{sh['end']:.2f})\\,{px(sh['cx'])}\\,{expr})"
    return expr


def fill_crop(src, cx, zoom=1.0, shots=None):
    """Fill the frame. `zoom` backs the picture off when the source is already tight.

    30 Aug: the owner on a KT_MIND clip - "it got zoomed in too much... the credit
    card clips the zoomed in its perfect". Both used the identical crop, because
    on a 1920x1080 source a full-bleed 9:16 window has exactly ONE possible zoom:
    608 wide by the full 1080 tall. The difference is the SOURCE - Your Thoughts
    Aren't Yours is shot far tighter than the debt interview, so the same maths
    lands on his nose.

    So zoom < 1.0 shrinks the picture and fills what is left with a blurred,
    slightly darkened copy of the same frame. That is not the old black bar - it
    is the frame continuing - and it is the only way to back off on a source that
    has no more width to give.
    """
    sw, sh = source_size(src)
    cw = min(int(round(sh * 9 / 16)), sw)
    x = (_x_expr(sw, cw, shots) if shots
         else max(0, min(int(round(sw * cx - cw / 2)), sw - cw)))
    if zoom >= 0.999:
        return (f"crop={cw}:{sh}:{x}:0,scale={W}:{H}:flags=lanczos,"
                f"setsar=1,fps=30")
    # A WIDER window, not a smaller picture. The first attempt shrank the whole
    # frame and blurred all four sides, which read as a photo in a box - worse
    # than the over-zoom it was fixing. Widening the crop instead keeps the
    # picture edge to edge and leaves blur only above and below, which is what
    # every good vertical edit does with landscape footage.
    cw2 = min(int(round(cw / zoom)) // 2 * 2, sw)
    x2 = max(0, min(int(round(sw * cx - cw2 / 2)), sw - cw2))
    ph = int(round(W * sh / cw2)) // 2 * 2
    return (f"split=2[bg][fg];"
            f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},boxblur=30:2,eq=brightness=-0.12:saturation=0.8[b];"
            f"[fg]crop={cw2}:{sh}:{x2}:0,scale={W}:{ph}:flags=lanczos[f];"
            f"[b][f]overlay=0:(H-h)/2,setsar=1,fps=30")



# TEXT MUST FIT THE PHONE, NOT THE FILE. 31 Aug: the owner's screenshot showed
# "LIVE WITHIN YOUR MEANS" cut off at BOTH edges, yet the same frame pulled from
# our own mp4 fits with room to spare. The file was never wrong - YouTube Shorts
# fills the height of a modern phone, which is TALLER than 9:16, and crops the
# WIDTH to do it. About 10% disappears off each side.
#
# So the usable width is not 1080. Sizing by character count was doubly wrong: it
# measured the wrong thing (letters, not pixels - "MMM" and "III" are nothing
# alike in Montserrat Black) against the wrong target (the file, not the screen).
SAFE_W = 780          # 1080 minus roughly 10% each side, then a real margin.
# 820 WAS TOO CLOSE TO THE EDGE, 3 Sept 2026. the owner, for the second time: "the
# hook its kind of cut off or outside the clips." Measured on an actual rendered
# frame, the three-line hook spanned 140px..938px against a safe zone of
# 130px..950px - inside by TEN PIXELS on one side and twelve on the other.
#
# Technically passing, and useless. Ten pixels is less than the width of one
# stroke of Montserrat Black, so any phone that crops a fraction more than the
# 10% assumed here cuts the text, and the fitter had no reason to shrink because
# the check said it fit. A safe zone with no slack is not a safe zone.
#
# 780 buys ~30px of clearance each side. The only cost is that the longest hooks
# drop one size step, which is invisible; being cut off is not.
try:
    from PIL import ImageFont
    _HAVE_PIL = True
except ImportError:                    # never silently ship oversized text
    _HAVE_PIL = False


def text_w(line, size):
    if not _HAVE_PIL:
        return int(len(line) * size * 0.62)     # crude, deliberately generous
    f = ImageFont.truetype(FONT, size)
    b = f.getbbox(line)
    return b[2] - b[0]


def fit_size(lines, start, floor=44):
    """Largest size at which every line fits inside the phone's safe width."""
    size = start
    while size > floor and any(text_w(l, size) > SAFE_W for l in lines):
        size -= 2
    return size


HOOK_CARD_Y = 500        # middle - high enough clears the captions, low enough
                         # it sits over the background, not over Kevin's face
CARDS = os.path.join(HOME, "work/hookcards")


def hook_scrim(lines, path, width=None, soft=False, max_h=None):
    """brand-2's hook. A gradient, not a box.

    15 Sept 2026. She turned down five: serif airy, band, outline, left rule,
    light pill. Four of those five are a CONTAINER with an edge, and the fifth
    is bare text. A sixth container was never going to land, so this is neither:
    the text sits on a soft vertical wash that fades out at both ends and has no
    edge anywhere. Nothing to read as a box sitting on top of the video.

    It also has to be HERS. the owner's card is a hard dark slab with a yellow rule
    - a headline in a newspaper. Brand 2 is about something surfacing, so
    the hook surfaces out of the frame instead of being stamped on it.

    Same contract as hook_card: returns (path, w, h) and is composited for
    HOOK_SECS from frame zero, so the cover frame always carries it.
    """
    from PIL import Image, ImageDraw, ImageFont
    os.makedirs(CARDS, exist_ok=True)
    lines = [l.upper() for l in lines if l.strip()][:2]
    size = 70
    if max_h:
        while size > 44 and (len(lines) * (size + 20) + 120) > max_h:
            size -= 2
    fo = ImageFont.truetype(FONT, size)
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    while size > 40 and max(probe.textlength(l, font=fo) for l in lines) > SAFE_W - 60:
        size -= 2
        fo = ImageFont.truetype(FONT, size)
    tw = max(probe.textlength(l, font=fo) for l in lines)
    step = size + 20
    # The wash is wider and taller than the words so it never ends where the
    # text ends - an edge that lines up with the text is just a box again.
    cw = min(int(tw) + 170, SAFE_W + 120)
    ch = len(lines) * step + 130
    img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    px = img.load()
    for y in range(ch):
        # Strongest through the middle band where the words are, gone by the
        # top and bottom rows. Squared falloff so it reads as light, not as a
        # rectangle with soft corners.
        f = 1.0 - abs((y - ch / 2) / (ch / 2))
        a = int(208 * (f ** 1.7))
        for x in range(cw):
            g = 1.0 - abs((x - cw / 2) / (cw / 2))
            px[x, y] = (8, 9, 13, int(a * min(1.0, g * 2.2)))
    d = ImageDraw.Draw(img)
    y = 62
    for i, l in enumerate(lines):
        x = (cw - probe.textlength(l, font=fo)) / 2
        # A real shadow under the type, so it holds on a bright frame even
        # where the wash has faded to almost nothing.
        for dx, dy in ((0, 3), (0, 4), (2, 3), (-2, 3)):
            d.text((x + dx, y + dy), l, font=fo, fill=(0, 0, 0, 150))
        d.text((x, y), l, font=fo,
               fill=(247, 231, 198) if i == 0 else (255, 255, 255))
        y += step
    img.save(path)
    return path, cw, ch


def hook_card(lines, path, width=None, soft=False, max_h=None):
    """The hook as a dark card, not bare text. the owner's pick, 11 Sept 2026.

    "I DONT LIKE IT, IT LOOKS JUST LIKE A CAPTION." He was right and the reason
    is mechanical: the hook used the same white block caps as the burned-in
    subtitles, so the eye had nothing to separate them - two different jobs in
    one voice. A panel gives the hook its own surface.

    Chosen from five options rendered on a real frame. Position settled at the
    MIDDLE, y=500, on the owner's call 11 Sept: higher up the card lands on Kevin's
    face in most framings, and a panel over the speaker's face is worse than no
    panel. The very top is out for a different reason - Instagram's own UI and
    TikTok's "Reels" label sit there and crop into it.

    drawtext cannot draw a rounded rectangle, so this is a PNG composited over
    the video for HOOK_SECS.
    """
    from PIL import Image, ImageDraw, ImageFont
    os.makedirs(CARDS, exist_ok=True)
    lines = [l.upper() for l in lines if l.strip()][:2]
    size = 70
    if max_h:
        # Shrink to fit the gap between his chin and the captions. Measured on
        # this library: that gap is often ~170px and a 70px card is ~212px, so
        # a card that refuses to shrink can never sit clear of him. Smaller and
        # clear beats bigger and across his mouth.
        while size > 44 and (len(lines) * (size + 22) + 56) > max_h:
            size -= 2
    fo = ImageFont.truetype(FONT, size)
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    while size > 40 and max(probe.textlength(l, font=fo) for l in lines) > SAFE_W - 80:
        size -= 2
        fo = ImageFont.truetype(FONT, size)
    tw = max(probe.textlength(l, font=fo) for l in lines)
    step = size + 22
    cw, ch = int(tw) + 80, len(lines) * step + 56
    img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # `soft` is for the shots where the card cannot avoid his face - see
    # card_y. Less opaque so his features read through it instead of a slab
    # being dropped on him.
    d.rounded_rectangle([0, 0, cw - 1, ch - 1], 24,
                        fill=(10, 11, 14, 186 if soft else 225))
    d.rounded_rectangle([34, ch - 16, 150, ch - 10], 3, fill=(245, 197, 66))
    y = 28
    for l in lines:
        d.text(((cw - probe.textlength(l, font=fo)) / 2, y), l, font=fo,
               fill=(255, 255, 255))
        y += step
    img.save(path)
    return path, cw, ch


_BANDS = {}


def face_band(src, t_in, seconds=3.0):
    """(top, bottom) of his head in OUTPUT pixels during the hook. Measured.

    The first version ESTIMATED head height as 1.45x the detected face width and
    the estimate was far too generous - the band came out spanning 242 to 1194
    of 1920, which left nowhere for the card and pushed every clip to the same
    extreme. Guessing a number I can measure directly was the mistake.

    YuNet returns a box with a height. This samples the actual frames the hook
    is over and uses it, padded upward for hair, which the box excludes.

    Vertical is safe to map straight across: the 9:16 crop only takes width, so
    a y fraction in the source is the same y fraction in the output.
    """
    key = f"{os.path.basename(src)}@{t_in:.2f}"
    if key in _BANDS:
        return _BANDS[key]
    band = None
    try:
        import cv2
        model = os.path.join(HOME, "bin/yunet.onnx")
        det = cv2.FaceDetectorYN_create(model, "", (320, 320), 0.6, 0.3, 5000)
        tops, bots = [], []
        for off in (0.4, 1.4, 2.4):
            if off > seconds:
                break
            tmp = os.path.join(HOME, "work", f"_fb{os.getpid()}.jpg")
            r = subprocess.run([FFMPEG, "-v", "error", "-y", "-ss",
                                f"{t_in + off:.2f}", "-i", src, "-frames:v", "1",
                                "-vf", "scale=640:-2", tmp], capture_output=True)
            if r.returncode or not os.path.exists(tmp):
                continue
            img = cv2.imread(tmp)
            os.remove(tmp)
            if img is None:
                continue
            h, w = img.shape[:2]
            det.setInputSize((w, h))
            ok, faces = det.detect(img)
            if faces is None or len(faces) == 0:
                continue
            bx = max(faces, key=lambda r_: r_[2] * r_[3])
            fy, fh = float(bx[1]), float(bx[3])
            tops.append((fy - fh * 0.55) / h)      # hair sits above the box
            bots.append((fy + fh * 1.18) / h)      # chin and a little neck
        if tops:
            band = (max(0.0, min(tops)) * H, min(1.0, max(bots)) * H)
    except Exception as e:
        sys.stderr.write(f"  face band unavailable ({e})\n")
    _BANDS[key] = band
    return band


def card_y(src, t_in, card_h):
    """Where the card goes so it does not sit on his face.

    the owner, 11 Sept 2026: "place the card away from his face." The middle is
    right most of the time - it is only wrong when the shot is tight enough that
    his face IS the middle. Prefer the middle, then under the chin, then above
    his head; if nothing is clean, take the least overlap and tell the caller to
    soften the card so his features read through it.
    """
    mid = 500
    band = face_band(src, t_in)
    if not band:
        return mid, False, None
    top, bot = band
    TOP_LIMIT, BOT_LIMIT = 210, CAP_Y - 70
    if bot <= mid or top >= mid + card_h:
        return mid, False
    below = int(bot) + 20
    if below + card_h <= BOT_LIMIT:
        return below, False, None
    gap = BOT_LIMIT - below
    if gap >= 130:
        return below, False, gap             # shrink to fit under his chin
    above = int(top) - card_h - 20
    if above >= TOP_LIMIT:
        return above, False, None
    # NOT ALL OF HIS FACE IS EQUAL. Measured: in a full-bleed 9:16 crop his head
    # runs from the top of the frame to about 55%, and the captions own 1050
    # down. The gap under his chin is 80-150px and a readable card is ~200, so
    # some overlap is unavoidable - there is no clean placement, and pretending
    # otherwise is how this ended up putting the card across his mouth.
    #
    # So minimise WHAT it covers, not how much. The middle of the head - eyes to
    # mouth, where a viewer looks - counts three times. Hair and chin are cheap.
    core_t = top + (bot - top) * 0.22
    core_b = top + (bot - top) * 0.78
    best, worst = mid, None
    for y in range(TOP_LIMIT, max(TOP_LIMIT + 1, BOT_LIMIT - card_h), 10):
        y2 = y + card_h
        core = max(0, min(y2, core_b) - max(y, core_t))
        rest = max(0, min(y2, bot) - max(y, top)) - core
        cost = core * 3 + rest
        if worst is None or cost < worst:
            best, worst = y, cost
    return best, True, None


def hook_chain(hook, persist=False):
    """Two lines, second one yellow, gone after HOOK_SECS.

    Three lines is where his format stops working - none of the reels above 80K
    views carried more than two. If a hook needs three lines it is a sentence,
    not a hook, and the fix is in the words.
    """
    # THREE LINES ALLOWED, 1 Sept. I capped hooks at two lines and then had to
    # shrink every long one to 56px to make it fit - which is how "LIVE WITHIN
    # YOUR MEANS / IS A LIE" ended up small and weak. Kevin's own 84.7K hook,
    # "WHY DISGUST IS THE MOST POWERFUL MOTIVATION", is THREE lines. Three short
    # lines render bigger than two long ones and keep the whole claim intact,
    # which is the thing that actually matters: his losers are the abstract
    # fragments, his winners are complete claims with something concrete in them.
    lines = [l for l in hook if l.strip()][:3]
    if not lines:
        return []
    size = fit_size([l.upper() for l in lines], 92)
    # On the YouTube cut the hook never leaves, and it sits HIGH instead. YouTube
    # picks its own cover frame from anywhere in the video, so a hook that clears
    # after 3 seconds is a hook YouTube will almost never show - which is exactly
    # why the Shorts covers read "AS THE ICE" and "TO BE A CAP". A permanent hook
    # makes every possible frame a correct cover, and needs no verification, no
    # thumbnail API and nothing from the owner.
    step = int(size * 1.26)
    n = len(lines)
    # THE HOOK AND THE CAPTIONS NOW SHARE THE SCREEN, 5 Sept 2026.
    #
    # the owner: "the hook itself without captions while the hook its on its little
    # week... the hook AND CAPTIONS at the same time FROM the BEGINNING its
    # ideal."
    #
    # Before, captions were held back until HOOK_SECS because both were drawn in
    # the same band and would have collided. The cost was that the opening three
    # seconds - the only three that decide anything - carried the hook alone,
    # with Kevin already talking underneath it and nothing on screen tying the
    # two together.
    #
    # So the hook is bottom-aligned to sit ABOVE the caption line rather than on
    # it. The captions keep CAP_Y, which is the position measured off Kevin's
    # own reels and where they sit for the other 95% of the clip - moving THEM
    # to make room would have been the wrong half to move.
    first = HOOK_BOTTOM - (n - 1) * step - size
    ys = [first + i * step for i in range(n)]
    f = font_arg(FONT)
    out = []
    for i, line in enumerate(lines):
        # The LAST line is the yellow one, whether there are two or three.
        # Three-line hooks were shipping with no yellow at all - the accent is
        # copied from Kevin's own reels ("BEER IS MORE" white / "HYDRATING THAN
        # WATER" yellow) and half the hooks were silently missing it.
        colour = YELLOW if i == len(lines) - 1 and len(lines) > 1 else "white"
        out.append(
            f"drawtext=fontfile={f}:text='{esc(line.upper())}':fontsize={size}"
            f":fontcolor={colour}{SHADOW}:x=(w-tw)/2:y={ys[i]}"
            + ("" if persist else f":enable='lt(t,{HOOK_SECS})'"))
    return out


EXTRA_WEAK = {"don", "doesn", "didn", "isn", "aren", "wasn", "won", "can",
              "couldn", "shouldn", "wouldn", "ain", "let", "here", "now",
              "then", "just", "very", "really", "okay", "yeah", "look"}


def accent(text):
    """True when this burst should land in yellow rather than white.

    FIRST ATTEMPT WAS WRONG AND THE RENDER SHOWED IT. The rule was "two words or
    fewer with any content word", and on a real clip that painted THERE'S, OR
    GAWK, DISASTERS, BEING CRITICAL and I DON'T - about two thirds of the whole
    caption track. Yellow everywhere is yellow nowhere, which is the exact thing
    the rule was written to avoid.

    So: a number always (his biggest thumbnails are all numbers), otherwise only
    a SINGLE content word standing alone - "WAITRESS", "WEISSBIER?", the way he
    uses it. never_twice() in caption_chain then stops two landing in a row.
    """
    words = [w for w in text.split() if w.strip()]
    if not words:
        return False
    if any(ch.isdigit() for ch in text) or "$" in text or "%" in text:
        return True
    if len(words) != 1:
        return False
    # A contraction keeps its stem's job: "THERE'S" is still "there", and the
    # apostrophe alone was enough to make _weak call it a content word.
    stem = words[0].replace("\u2019", "'").split("'")[0]
    return not (burn._weak(stem) or burn._weak(words[0]) or stem.lower() in EXTRA_WEAK)


def caption_chain(ps):
    """Spoken bursts, in the spot the hook just left.

    From t=0, alongside the hook. They used to be held back until HOOK_SECS to
    avoid colliding with it; the hook now sits above them (see hook_chain), so
    there is nothing to collide with and the first three seconds carry both.
    """
    f = font_arg(FONT)
    out = []
    last_yellow = [False]
    for a, b, text in ps:
        want = accent(text)
        if want and last_yellow[0]:      # never two in a row - it stops reading
            want = False                 # as emphasis and starts reading as a
        last_yellow[0] = want            # colour scheme
        colour = YELLOW if want else "white"
        size = fit_size([text.upper()], CAP_SIZE)
        out.append(
            f"drawtext=fontfile={f}:text='{esc(text.upper())}':fontsize={size}"
            f":fontcolor={colour}{SHADOW}:x=(w-tw)/2:y={CAP_Y}"
            f":enable='between(t,{a:.2f},{b:.2f})'")
    return out



# ------------------------------------------------------------- the YouTube cut
# 30 Aug 2026. All three blocked Shorts carried the same message: "The
# copyright-protected content detected is not allowed in Shorts longer than 60
# seconds." That is a RULE, not bad luck - under 60s YouTube licenses the same
# material, over 60s Content ID blocks it outright. Our clips run 84-187s, so
# every clip carrying any match dies on the one platform giving us 1K views a
# post while posting fine everywhere else.
#
# So YouTube gets its own cut: the first 59 seconds FROM THE DOOR. Since kt_gold
# that opening is the strongest part of the clip anyway, and a hard 59s ceiling
# makes the rule impossible to trip on any clip, ever.
#
# It still has to END somewhere real - chopping at exactly 59.0 lands mid-word.
# The last silence before the ceiling is the ending.
YT_MAX = 59.0


def yt_window(sil, t_in, t_out):
    """The best SELF-CONTAINED <=59s stretch, not the first 59 seconds.

    Two wrong answers came before this one, both caught by reading what the cut
    actually said out loud:
      1. "last pause before 59s" ended on "You're at 100%." - a setup whose
         payoff is the next line.
      2. "longest pause before 59s" ended at 26s on "what is your credit limit?"
         - a question with no answer.
    Both broke the oldest rule in the pipeline: a clip must contain its own
    payoff. A 3-minute teaching does not have one in its first minute, and no
    amount of choosing a better end point inside that minute will invent one.

    So look at the WHOLE clip for where a point LANDS - the longest pauses, since
    he breathes after finishing a thought and rushes through the middle of one -
    then back up to the last real break within 57 seconds of it. That yields
    setup -> payoff, ending on the beat, wherever in the clip it happens to live.

    Returns (start, end). If nothing self-contained fits, returns None and the
    caller skips the YouTube cut rather than shipping half a thought.
    """
    breaks = [(a, b - a) for a, b in sil if t_in < a < t_out]
    if len(breaks) < 2:
        return None
    lands = sorted(breaks, key=lambda x: -x[1])[:8]      # the biggest breaths
    best = None
    for end, _ in lands:
        if end - t_in < 25:                              # too short to teach
            continue
        starts = [a for a, _ in breaks if end - a <= YT_MAX - 2]
        start = min(starts) if starts else None
        if start is None or end - start < 25:
            continue
        if best is None or (end - start) > (best[1] - best[0]):
            best = (start, end + 0.18)
    return best


def thumb(video):
    """A cover for YouTube, grabbed while the hook is on screen.

    30 Aug: I told the owner custom thumbnails probably do not work on Shorts and
    that his channel was not verified. Both were wrong - he said so, the API
    confirmed longUploadsStatus=allowed, and a test set a thumbnail on a live
    Short successfully. So YouTube's cover is ours to choose after all, and it
    does not have to be whatever frame the algorithm liked.

    Taken at 1.5s, which on the YouTube cut is the hook, full and centred.
    """
    dest = os.path.splitext(video)[0] + "__thumb.jpg"
    # 1280x720, NOT 720x1280. 30 Aug I uploaded portrait thumbnails and YouTube
    # did not letterbox them - it mangled them into a sliver of picture over a
    # flat brown field, which is what the owner saw as a grey tile on the newest
    # Short. YouTube's own auto-cover for a vertical video is the portrait frame
    # centred with a blurred copy filling the sides, so that is what we build,
    # with our hook guaranteed in it instead of whatever frame it picked.
    vf = ("split=2[bg][fg];"
          "[bg]scale=1280:720:force_original_aspect_ratio=increase,"
          "crop=1280:720,boxblur=24:2,eq=brightness=-0.12[b];"
          "[fg]scale=-1:720[f];[b][f]overlay=(W-w)/2:0")
    # PICK THE BEST FRAME, NOT A FIXED ONE. 5 Sept 2026, the owner: "the thumbnail
    # of yt and fb are bad, are not looking good or off like black or not with
    # the hook at front."
    #
    # It grabbed 1.5s every time. The hook is on screen for the first three
    # seconds, but WHICH instant you land on is luck - a blink, a cut, a dark
    # beat, and that is the cover for the life of the video. The hook being
    # present was guaranteed; the picture being good was not.
    #
    # So sample several instants inside the hook window and keep the brightest
    # with the most contrast - a proxy for "his eyes are open and the frame is
    # lit". Cheap, and it removes the coin flip.
    # STILLNESS, NOT BRIGHTNESS. 10 Sept 2026, brand-2 owner: "the thumbnail doesn't
    # look great on the grid ... its using the first scene all the time but its
    # usually when kevin is moving so it doesn't look good."
    #
    # The old score was mean + stddev - lit, and not a flat wash. Both are true
    # of a MOTION-BLURRED frame of a man mid-gesture, which is exactly the
    # picture she is describing. Nothing was measuring movement.
    #
    # Measured on real clips: between adjacent instants the head-and-shoulders
    # region varies about SEVEN-FOLD in motion, and sharpness peaks precisely
    # where motion bottoms out. So pick the stillest instant in the hook window.
    #
    # Why not detect the face: OpenCV 5 dropped CascadeClassifier, which
    # kt_eyes.py already ran into. Motion needs no model and no weights.
    #
    # The crop matters. Scoring the whole frame is useless because the burned-in
    # hook is huge, white and always perfectly sharp - it swamps the signal.
    # This looks ABOVE the hook (which is bottom-aligned to HOOK_BOTTOM) at the
    # head and shoulders only.
    # 0.6s .. 2.4s. NOT 2.8: the hook card starts fading at 2.7s, so a cover
    # taken there catches it half gone - which is the washed-out text the owner saw
    # on the grid.
    PROBES = [0.6 + 0.2 * i for i in range(10)]           # 0.6s .. 2.4s
    LOOK = "crop=iw*0.7:ih*0.34:iw*0.15:ih*0.02"

    def _gray(t, tag):
        q = dest + f".{tag}.png"
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{t:.2f}",
                        "-i", video, "-frames:v", "1", "-vf", LOOK,
                        "-q:v", "2", q], capture_output=True)
        try:
            import cv2
            im = cv2.imread(q, cv2.IMREAD_GRAYSCALE)
        except Exception:
            im = None
        if os.path.exists(q):
            os.remove(q)
        return im

    scored = []
    for t in PROBES:
        a = _gray(t, "a")
        b = _gray(t + 0.07, "b")
        if a is None or b is None:
            continue
        try:
            import cv2
            import numpy as np
            motion = float(np.mean(np.abs(a.astype(np.int16) - b.astype(np.int16))))
            sharp = float(cv2.Laplacian(a, cv2.CV_64F).var())
            lit = float(a.mean())
        except Exception:
            continue
        scored.append({"t": t, "motion": motion, "sharp": sharp, "lit": lit})

    best_t = None
    if scored:
        mm = max(x["motion"] for x in scored) or 1.0
        ms = max(x["sharp"] for x in scored) or 1.0
        for x in scored:
            # stillness leads, detail confirms it, and a frame too dark to read
            # is unusable however still it is
            x["score"] = (0.65 * (1.0 - x["motion"] / mm)
                          + 0.35 * (x["sharp"] / ms)
                          - (0.5 if x["lit"] < 35 else 0.0))
        best_t = max(scored, key=lambda x: x["score"])["t"]

    if best_t is None:
        best_t = 1.5
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{best_t:.2f}",
                    "-i", video, "-frames:v", "1", "-filter_complex", vf,
                    "-q:v", "3", dest], capture_output=True)

    # WHAT INSTAGRAM NEEDS. It picks its own cover unless the container is given
    # thumb_offset in milliseconds - which is why her grid was showing frame
    # zero, mid-gesture. The instant chosen here has to travel with the clip, so
    # it is written beside it and read by poster.instagram.
    try:
        with open(os.path.splitext(video)[0] + "__cover_ms.txt", "w") as fh:
            fh.write(str(int(best_t * 1000)))
    except Exception:
        pass

    if not os.path.exists(dest):        # every probe failed - fall back
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", "1.5",
                        "-i", video, "-frames:v", "1", "-filter_complex", vf,
                        "-q:v", "3", dest], capture_output=True)
    # READ THE ARTIFACT BACK. The portrait bug shipped because every signal said
    # fine: ffmpeg exited 0, the file existed, thumbnails/set returned 200, and
    # the API reported maxresdefault as 1280x720. Only fetching the actual image
    # showed a sliver of picture on a flat field. Three sessions hit this same
    # shape in one night - a check that returns success-looking output while the
    # artifact is wrong - so the rule is: assert a property only the CORRECT
    # version has, measured off the thing itself, not off the status code.
    if os.path.exists(dest):
        got = source_size(dest)
        if got != (1280, 720):
            raise SystemExit(
                f"cover is {got[0]}x{got[1]}, must be 1280x720: {dest}")
    return dest


def yt_path(dest):
    stem, ext = os.path.splitext(dest)
    return stem + "__yt59" + ext



_ONES = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
         "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
         "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
         "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
         "seventy": 70, "eighty": 80, "ninety": 90}
_MAG = {"hundred": 100, "thousand": 1000, "million": 1000000, "billion": 1000000000}


def numbers_to_digits(ws):
    """ "a hundred thousand dollars" -> "$100,000", as ONE caption token.

    16 Sept 2026. the owner on the YWIYC flagship: the captions felt off, and one
    reason was on screen as "I WANT A HUNDRED" / "THOUSAND DOLLARS" - the
    number he is asking for, cut in half across two captions. Whisper spells
    numbers out when it is not primed, and four words will not fit the 20
    character line, so the break scorer had no choice but to split them.

    Digits are also simply how a number reads on a phone: $100,000 is one
    glance, "a hundred thousand dollars" is four words to read while he is
    already on the next sentence. Only converts when there is a MAGNITUDE
    word or "dollars/percent", so "one example" stays words.
    """
    out, i, n = [], 0, len(ws)
    def key(w):
        return re.sub(r"[^a-z]", "", w.lower())
    while i < n:
        # "$450" then "million" -> "$450 million". Whisper often writes the
        # number as digits and the magnitude as a word; converting "million"
        # on its own produced "$450" / "1,000,000" on screen.
        if (i + 1 < n and re.match(r"^\$?[\d,.]+$", ws[i][2].strip())
                and key(ws[i + 1][2]) in ("million", "billion", "thousand")):
            out.append((ws[i][0], ws[i + 1][1], ws[i][2].strip() + " " + ws[i + 1][2].strip()))
            i += 2
            continue
        j, total, cur, seen_mag = i, 0, 0, False
        if key(ws[i][2]) == "a" and i + 1 < n and key(ws[i + 1][2]) in _MAG:
            cur, j = 1, i + 1
        while j < n:
            k = key(ws[j][2])
            if k in _ONES:
                cur += _ONES[k]
            elif k in _TENS:
                cur += _TENS[k]
            elif k in _MAG:
                seen_mag = True
                m = _MAG[k]
                if m == 100:
                    cur = (cur or 1) * 100
                else:
                    total += (cur or 1) * m
                    cur = 0
            elif k == "and" and j > i and j + 1 < n and key(ws[j + 1][2]) in (set(_ONES) | set(_TENS)):
                pass
            else:
                break
            j += 1
        value = total + cur
        unit = key(ws[j][2]) if j < n else ""
        number_words = sum(1 for q in range(i, j) if key(ws[q][2]) in _ONES or key(ws[q][2]) in _TENS
                           or (key(ws[q][2]) == "a" and q + 1 < j))
        if j > i and number_words and (seen_mag or unit in ("dollars", "dollar", "percent")):
            tail = ws[j - 1][2]
            end, last = ws[j - 1][1], j - 1
            text = f"{value:,}"
            if unit in ("dollars", "dollar"):
                text, end, last = "$" + text, ws[j][1], j
                tail = ws[j][2]
            elif unit == "percent":
                text, end, last = text + "%", ws[j][1], j
                tail = ws[j][2]
            punct = re.search(r"[.,!?;:]+$", tail)
            out.append((ws[i][0], end, text + (punct.group(0) if punct else "")))
            i = last + 1
        else:
            out.append(ws[i])
            i += 1
    return out


def phrases_from_words(words):
    """Caption bursts timed to when each word is actually SPOKEN.

    2 Sept 2026. Replaces the character-count guess in kt_burn.phrases(), which
    handed each burst a slice of its cue proportional to how many LETTERS it had.
    "I" takes 90ms and "reveal" takes 560ms, so a burst could sit most of a second
    from the word being said - exactly what the owner saw. A burst now starts when its
    first word starts and ends when its last word ends. No estimate remains.

    WHERE TO BREAK is scored, not greedy. Greedy filling produced "burns that all
    / off and seeds / germinate," - breaks landing mid-phrase because the
    character limit ran out there. Every possible set of breaks is scored instead:
    a real pause between words is nearly free to break on, breaking after
    punctuation is cheap, and breaking BEFORE a word that binds to what follows
    ("and", "of", "that") or AFTER one is expensive. Same idea as kt_burn's line
    scorer, which was right about breaks and wrong about time.
    """
    # NO SPEAKER DASHES ON SCREEN. whisper marks a change of speaker with a
    # leading "- ", and on the YWIYC story it rode into the most important frame
    # of the clip as "- WHAT DO I WANT?". It is transcription markup, never
    # something anyone said.
    ws = [(a, b, w.strip().lstrip("-\u2013\u2014").strip())
          for a, b, w in words if w and w.strip()]
    ws = [x for x in ws if x[2]]
    ws = numbers_to_digits(ws)
    n = len(ws)
    if not n:
        return []
    lens = [len(w[2]) for w in ws]

    def width(i, j):
        return sum(lens[i:j]) + (j - i - 1)

    MIN_HOLD = 0.55       # a burst the eye cannot read is worse than no break
    # NO WORD SITS ON SCREEN WAITING TO BE SAID.
    #
    # 14 Sept 2026, the owner: "the captions in her clips are some words off faster
    # or slower so it looks off." Measured before changing anything: the word
    # TIMINGS are exact - a rendered clip transcribed back word-by-word matches
    # what was burned to a median of 0.00s. So the drift he sees is not timing.
    #
    # It is the burst. A burst appears the moment its FIRST word is spoken and
    # holds until its last word ends, so every other word in it is already on
    # screen before it is said. Across the whole library 4.5% of words were
    # visible more than a second early and 1.3% more than a second and a half.
    # A two-word burst looks perfect and a seven-word burst looks like the
    # captions are running ahead - which is exactly "some faster, some slower",
    # and it was never worse on her clips than on his (AR_SOUND p90 0.91s,
    # KT_BRAIN 0.84s). His have it too.
    #
    # So the span a burst covers is now part of its cost. Past LEAD_MAX the
    # penalty is quadratic, which splits long bursts without shattering short
    # ones.
    LEAD_MAX = 0.90

    def cost(i, j):
        """Cost of making words[i:j] one burst."""
        w = width(i, j)
        c = 0.0
        # A SENTENCE END ENDS THE CAPTION. 16 Sept 2026: "FOR IT. NOW," and
        # "ED BECKLEY. HE'S" - the first word of the next sentence on screen
        # before Kevin has taken the breath and said it. That is the single
        # most "off"-feeling thing a caption can do, and the old scorer allowed
        # it whenever the leftover fragment was too short to stand alone.
        for k in range(i, j - 1):
            if ws[k][2].rstrip().endswith((".", "!", "?")):
                return float("inf")
        # NO STRANDED SCRAPS. "IN." alone, "IT." alone - one short word ending
        # a sentence reads as a glitch. Make it cost enough that the scorer
        # takes it together with the words before it.
        if j - i == 1 and len(ws[i][2].strip(".,!?")) <= 3 and ws[i][2].rstrip().endswith((".", "!", "?", ",")):
            c += 160
        # TIME ON SCREEN IS THE REAL CONSTRAINT, not character count. Scoring on
        # characters alone shattered a clip into flashes - "off" for 0.02s,
        # "which" and "can" for zero, because whisper gives some words identical
        # start and end times. A caption exists to be READ.
        dur = ws[j - 1][1] - ws[i][0]
        if dur < MIN_HOLD:
            c += (MIN_HOLD - dur) ** 2 * 900
        lead = ws[j - 1][0] - ws[i][0]         # how early the LAST word shows
        if lead > LEAD_MAX:
            c += (lead - LEAD_MAX) ** 2 * 260
        if w > CAP_MAX:
            c += (w - CAP_MAX) ** 2 * 12          # never overflow the frame
        # NOTHING rewards filling the line. A push toward the ceiling is what
        # produced "burns that all / off and seeds / germinate," - the break
        # landed where the characters ran out instead of where the phrase ended.
        # A short burst on a clean boundary is always better than a full one on a
        # broken phrase, and short is his house style anyway.
        if j < n:
            prev, nxt = ws[j - 1][2], ws[j][2]
            gap = ws[j][0] - ws[j - 1][1]
            if gap >= 0.30:
                c -= 34                            # he paused here - break here
            elif gap >= 0.15:
                c -= 14
            if prev.rstrip().endswith((".", "!", "?")):
                c -= 45                            # a sentence ended
            elif prev.rstrip().endswith(","):
                c -= 20
            if j - i > 1 and burn._weak(prev):
                c += 34                            # do not end on "and", "of"
            if nxt.lower().strip(".,!?").rstrip("s") in MAGNITUDE_WORDS:
                c += 200                           # never split $25 | BILLION
            # NAMES STAY TOGETHER. 16 Sept 2026: "I WAS IN NEW" / "YORK CITY".
            # Two capitalised words in a row, mid-sentence, are one name - New
            # York, Carnegie Deli, Bobby Singer, Ed Beckley. Never "I", and not
            # when the first one opens a sentence.
            pc, nc = prev.strip("\"'(,"), nxt.strip("\"'(,")
            if (pc[:1].isupper() and nc[:1].isupper() and nc not in ("I", "I'm", "I've", "I'll", "I'd")
                    and not prev.rstrip().endswith((".", "!", "?"))
                    and j - 1 > i and not ws[j - 2][2].rstrip().endswith((".", "!", "?"))):
                c += 140
            # NEVER END ON AN ARTICLE. "WE DID THE" / "SHOW $450 MILLION" - a
            # caption ending on "the" is a sentence with its noun cut off.
            if prev.lower().strip(".,!?\"'") in ("the", "a", "an", "my", "your", "his", "her", "our", "their", "this", "that's"):
                c += 150
            # PAIRS THAT ARE ONE THOUGHT. "COMING" / "IN", "DON'T" / "KNOW".
            # Fluent speech leaves no gap to detect them by, so they are named.
            pair = (prev.lower().strip(".,!?\"'"), nxt.lower().strip(".,!?\"'"))
            if pair in TOGETHER:
                c += 110
            # A NUMBER STAYS WITH WHAT IT IS ABOUT: "I WANT $100,000".
            if re.match(r"^\$?\d", nxt) and not prev.rstrip().endswith((".", ",", "!", "?", ":")):
                c += 60
            # A PHRASE KEEPS ITS TAIL. "A WEEK COMING" / "IN WITHOUT": the short
            # word that CLOSES a phrase ("coming in", "for it", "work for")
            # belongs with it. Spotted by what follows it: punctuation, or a
            # real gap before the next word.
            if j + 1 <= n - 1 or j < n:
                core = nxt.strip(".,!?;:")
                after_gap = (ws[j + 1][0] - ws[j][1]) if j + 1 < n else 1.0
                if len(core) <= 3 and core.lower() not in ("i", "a", "and", "but", "so", "or") and \
                        (nxt.rstrip().endswith((".", ",", "!", "?")) or after_gap >= 0.15):
                    c += 70
        return c

    INF = float("inf")
    best = [0.0] + [INF] * n
    back = [0] * (n + 1)
    for j in range(1, n + 1):
        for i in range(max(0, j - 7), j):
            if best[i] == INF:
                continue
            v = best[i] + cost(i, j)
            if v < best[j]:
                best[j], back[j] = v, i
    cuts, j = [], n
    while j > 0:
        cuts.append((back[j], j))
        j = back[j]
    cuts.reverse()

    # A CAPTION LANDS JUST BEFORE THE WORD, NOT ON IT. Text drawn at the exact
    # instant a word is spoken is read a beat after it - the eye needs about a
    # tenth of a second to register that something changed. Broadcast subtitling
    # has always led the audio slightly for this reason. The lead is clamped to
    # the real gap before the burst so it can never overlap the previous one.
    LEAD_IN = 0.10
    out = []
    for i, j in cuts:
        a0, z0 = ws[i][0], ws[j - 1][1]
        room = a0 - (ws[i - 1][1] if i else 0.0)
        a0 = max(0.0, a0 - min(LEAD_IN, max(0.0, room)))
        if z0 - a0 < 0.18:
            z0 = a0 + 0.18
        out.append((round(a0, 2), round(z0, 2),
                    " ".join(w[2] for w in ws[i:j])))
    # Hold each burst until the next begins, so a pause does not blank the
    # screen. 0.8s, not 0.35s: below that the text vanished and came back inside
    # one sentence, which reads as a glitch rather than as a beat. A gap longer
    # than 0.8s is a real break and is allowed to go dark.
    #
    # 1.5s, not 0.8s. 16 Sept 2026: "WAS OVER $290,000." went dark for 1.2s while
    # Kevin finished the number and paused on it - the biggest figure in the
    # story, gone from the screen at the exact moment he lets it land. He pauses
    # after big numbers on purpose; the caption should stay for the pause.
    for i in range(len(out) - 1):
        if out[i + 1][0] - out[i][1] < 1.5:
            out[i] = (out[i][0], out[i + 1][0], out[i][2])
    return out


TOGETHER = {
    ("coming", "in"), ("come", "in"), ("comes", "in"), ("came", "in"), ("put", "out"),
    ("work", "for"), ("pay", "for"), ("paid", "for"), ("look", "at"), ("looked", "at"),
    ("don't", "know"), ("didn't", "know"), ("doesn't", "know"), ("i", "know"),
    ("find", "out"), ("figure", "out"), ("give", "up"), ("sign", "up"), ("set", "up"),
    ("going", "to"), ("gonna", "happen"), ("have", "to"), ("had", "to"), ("want", "to"),
    ("used", "to"), ("able", "to"), ("new", "york"), ("each", "other"), ("a", "lot"),
}


MAGNITUDE_WORDS = {"billion", "million", "thousand", "hundred", "percent",
                   "dollar", "year", "grand", "k"}


def render(src, dest, t_in, t_out, hook, cues, cx, apply, zoom=1.0,
           hook_y=None, yt_win=None, slug=None, fix=None, shots=None,
           track=None):
    burn.MAX_CHARS = CAP_MAX          # short bursts, not subtitle lines
    # Real word timings when we have them; the old estimate only as a fallback.
    import kt_words
    wkey = os.path.basename(os.path.dirname(dest)) + "/" + slug
    words = kt_words.words_for(src, t_in, t_out, wkey) if slug else []
    # WHISPER MISHEARS THE DOMAIN WORDS. 11 Sept 2026: the caption on a clip
    # ABOUT brainwaves read "AND THEY BROADCAST ON DATA." He says beta. The word
    # whisper gets wrong is reliably the one the clip is about, because it is the
    # rare technical term - so a per-clip correction map is worth more than its
    # size. Set "fix": {"data.": "beta."} on the clip in kt_series.json.
    if fix and words:
        low = {k.lower(): v for k, v in fix.items()}
        words = [(a, b, low.get(w.lower().strip(), w)) for a, b, w in words]
    ps = phrases_from_words(words) if words else burn.phrases(cues, t_in, t_out)
    # KEEP A RECORD OF WHAT WAS BURNED. 16 Sept 2026: captions drifted up to
    # 9.5s ahead of the speech on seven clips, and nothing could see it - the
    # audio checks listen to the edges and a still frame cannot show timing.
    # kt_sync_check.py compares this file against the finished clip's speech.
    if apply:
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            json.dump([[a, b, t] for a, b, t in ps],
                      open(os.path.splitext(dest)[0] + "__caps.json", "w"))
        except OSError:
            pass
    geo = fill_crop(src, cx, zoom, shots)
    caps = caption_chain(ps)
    # THE HOOK IS A CARD, COMPOSITED - see hook_card(). persist=True (the
    # YouTube cut) still uses drawtext, because a card that never leaves would
    # cover a third of the frame for the whole video.
    hlines = [l for l in hook if l.strip()]
    cpath = os.path.join(CARDS, (slug or "hook").replace("/", "_") + ".png")
    _, _cw, _ch = hook_card(hlines, cpath)
    cy_px, soft, fit = card_y(src, t_in, _ch)
    # NO SEE-THROUGH CARD. 13 Sept 2026: on the Instagram grid the softened
    # version read as grey smudge - the owner: "the thumbnail its off, you almost
    # cant see it." The transparency was there to spare his face, and the
    # placement above already does that job. A hook that cannot be read at
    # thumbnail size is not a hook.
    if fit:                        # shrink it into the gap under his chin
        card, _cw, _ch = hook_card(hlines, cpath, max_h=fit)
    else:
        card = cpath
    # EVERY CLIP FADES OUT. the owner, 13 Sept 2026, after watching one run past
    # its last line into Kevin's own advert - which faded - "all of our clips
    # need to end slowly fading away like that one, ALL of our clips for ever
    # because its so bad when it just cuts."
    #
    # Picture and sound together. A hard cut on the last syllable is what makes
    # a clip feel like a fragment somebody sawed off; a fade is the difference
    # between an edit and an accident.
    dur = t_out - t_in
    fs = min(FADE_OUT, max(0.35, dur * 0.12))
    pre = ",".join([geo] + caps)
    fc = (f"[0:v]{pre}[bg];"
          # NO FADE IN. 13 Sept 2026, the owner: "THE HOOK HAS TO START NOT SLOWLY
          # BUT AT ONCE FROM THE VERY BEGINNING SO IF THE THUMBNAIL CHOOSES THE
          # VERY FIRST PART OF THE CLIP IT CATCHES THE HOOK." TikTok and
          # Instagram both grab a cover from the opening instant, and a card
          # easing in over a quarter of a second is half-there when they do.
          f"[1:v]format=rgba,"
          f"fade=out:st={HOOK_SECS - 0.3:.2f}:d=0.3:alpha=1[hk];"
          f"[bg][hk]overlay=x=(W-w)/2:y={cy_px}:"
          f"enable='lt(t,{HOOK_SECS})'[vv];"
          f"[vv]fade=t=out:st={dur - fs:.2f}:d={fs:.2f}[v];"
          f"[0:a]afade=t=out:st={dur - fs:.2f}:d={fs:.2f}[a]")
    vf = ["-filter_complex", fc, "-map", "[v]", "-map", "[a]"]
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-ss", f"{t_in:.2f}",
           "-t", f"{t_out - t_in:.2f}", "-i", src,
           "-loop", "1", "-framerate", "30", "-t", f"{HOOK_SECS:.2f}",
           "-i", card,
           *vf, "-c:v", "libx264", "-preset", "medium", "-crf", "19",
           "-maxrate", "9000k", "-bufsize", "18000k",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
           "-movflags", "+faststart", dest]
    if not apply:
        return len(ps)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    # --yt-only rebuilds the 59s cuts and leaves the full clips untouched, so a
    # hook fix on the YouTube side does not mean re-uploading 1.3GB of clips the
    # cloud already has.
    if "--yt-only" not in sys.argv:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            sys.stderr.write(r.stderr[-1500:] + "\n")
            raise SystemExit(f"render failed: {dest}")

    # EVERY clip gets a cover. Originally thumb() only ran inside the 59s branch,
    # so any clip already under 60 seconds got no cover at all and YouTube picked
    # its own frame - which is the exact problem covers exist to solve. brand-2's
    # 50-second clip was the one that exposed it.
    thumb(dest)

    # The YouTube cut, only when the full clip would break the 60s rule.
    if t_out - t_in > YT_MAX:
        import kt_snap
        # yt_in/yt_out in kt_series.json override the automatic window.
        # 31 Aug 2026: yt_window picks its END from the longest pause, which is
        # usually where a thought lands - but on AR clip 06 the longest pause
        # sat mid-sentence and the cut ended on "feeling good because". Reading
        # it is the only way to see that; the numbers look identical either way.
        # So there is now a manual escape hatch for the cases a human has read
        # and disagrees with, rather than retuning detection for one clip.
        win = yt_win or yt_window(kt_snap.silences(src), t_in, t_out)
        if win:
            ys, ye = win
            # RE-TIME, do not just re-seek. drawtext timings are relative to the
            # start of the render, so reusing the full clip's chain with a later
            # -ss put every caption 37 seconds out of sync. The window gets its
            # own phrases and its own hook, generated from its own start.
            ywords = [(a, b, w) for a, b, w in words if a >= ys - t_in
                      and b <= ye - t_in] if words else []
            ywords = [(a - (ys - t_in), b - (ys - t_in), w) for a, b, w in ywords]
            yps = phrases_from_words(ywords) if ywords else burn.phrases(cues, ys, ye)
            ygeo = fill_crop(src, cx, zoom)
            # The window is often a DIFFERENT teaching from the full clip, so
            # the full clip's hook can promise something this cut never
            # delivers. hook_yt in kt_series.json overrides it where they differ.
            # PERSISTENCE OFF, 31 Aug. I made the YouTube hook stay up for the
            # whole clip so that whatever frame YouTube picked as a cover would
            # carry it. That was a workaround for a problem we then solved
            # properly - set_cover() now uploads the exact cover we choose. With
            # the cover controlled, a permanent hook buys nothing and costs a
            # lot: the owner saw it stacked against YouTube's own auto-captions and
            # our burned captions, three layers of text at once, and said it
            # "looks like we didnt care". He is right. It clears at 3s like the
            # rest.
            ydraws = hook_chain(hook_y or hook) + caption_chain(yps)
            yvf = (["-vf", ",".join([ygeo] + ydraws)] if zoom >= 0.999
                   else ["-filter_complex", ygeo + "," + ",".join(ydraws)])
            yfs = min(FADE_OUT, max(0.35, (ye - ys) * 0.12))
            yvf = (yvf[:-1] + [yvf[-1] + f",fade=t=out:st={ye - ys - yfs:.2f}:"
                               f"d={yfs:.2f}"]) if yvf[0] == "-vf" else yvf
            ycmd = [FFMPEG, "-y", "-loglevel", "error", "-ss", f"{ys:.2f}",
                    "-t", f"{ye - ys:.2f}", "-i", src, *yvf,
                    "-af", f"afade=t=out:st={ye - ys - yfs:.2f}:d={yfs:.2f}",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "19",
           "-maxrate", "9000k", "-bufsize", "18000k",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart", yt_path(dest)]
            ry = subprocess.run(ycmd, capture_output=True, text=True)
            if ry.returncode:
                sys.stderr.write(ry.stderr[-800:] + "\n")
            else:
                print(f"      + youtube cut {ye - ys:.0f}s (+{ys - t_in:.0f}s in)")
                thumb(yt_path(dest))
    return len(ps)


def srt_for(source):
    base = os.path.splitext(source)[0]
    p = os.path.join(TRANSCRIPTS, base + ".srt")
    if not os.path.exists(p):
        raise SystemExit(f"no transcript: {p}")
    return p


FRAMES = os.path.join(HOME, "work/frames")


def shots_for(src, t_in, t_out, slug):
    """Per-shot framing for THIS window. Cached; None if it cannot be measured.

    Kevin does not sit in the same place from one camera to the next, so the
    crop cannot either. See _x_expr for what the owner saw when it did.
    """
    os.makedirs(FRAMES, exist_ok=True)
    tag = f"{slug}@{t_in:.2f}-{t_out:.2f}".replace("/", "_")
    cache = os.path.join(FRAMES, tag + ".json")
    if os.path.exists(cache):
        try:
            j = json.load(open(cache))
            return {"segments": j["segments"], "track": j.get("track") or []}
        except (ValueError, OSError, KeyError):
            pass
    try:
        import vsc_frame as VF
    except Exception as e:
        sys.stderr.write(f"  framing unavailable ({e}); using a fixed crop\n")
        return None
    win = os.path.join(FRAMES, tag + ".mp4")
    r = subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", f"{t_in:.2f}",
                        "-t", f"{t_out - t_in:.2f}", "-i", src, "-an",
                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24",
                        win], capture_output=True, text=True)
    if r.returncode:
        return None
    try:
        dur = VF.duration(win)
        track = VF.face_track(win, dur)
        segs = VF.segments(VF.shot_cuts(win), dur, track)
        # The per-second track is kept as well as the shots. The hook lives for
        # three seconds and a shot can run thirty, so a shot's AVERAGE face
        # position is the wrong number to place the card against - measured on
        # KT_POS/02 the shot average put his face at 29% of frame height while
        # in the first three seconds it was at 13%.
        json.dump({"segments": segs,
                   "track": [list(t) if t else None for t in track]},
                  open(cache, "w"), indent=1)
        return {"segments": segs, "track": track}
    except (Exception, SystemExit) as e:
        # SystemExit DELIBERATELY, and this cost a batch. 15 Sept 2026: the
        # fourth of four clips died on "cannot read duration" and everything
        # after it never rendered, including a whole second series.
        #
        # vsc_frame.duration() raises SystemExit when ffmpeg cannot read the
        # window it just wrote - a transient thing under load. SystemExit comes
        # off BaseException, not Exception, so this handler did not see it and
        # it went all the way out and killed the run.
        #
        # The measurement is optional by design - this function's own docstring
        # says "None if it cannot be measured", and the caller falls back to a
        # fixed crop. An optional measurement must never be able to stop the
        # work it was only meant to improve.
        sys.stderr.write(f"  framing failed ({e}); using a fixed crop\n")
        return None
    finally:
        if os.path.exists(win):
            os.remove(win)


def run_series(key, spec, apply, only):
    src = os.path.join(SRC_DIR, spec["source"])
    if not os.path.exists(src):
        print(f"  SKIP {key}: source missing")
        return 0
    cues = burn.parse_srt(srt_for(spec["source"]))
    cx = float(spec.get("cx", 0.5))
    zoom = float(spec.get("zoom", 1.0))
    brand = spec["brand"]
    n = 0
    for i, c in enumerate(spec["clips"], 1):
        if only and only not in c["slug"]:
            continue
        # A PUBLISHED CLIP IS FINISHED. 11 Sept 2026: a house-style change
        # re-rendered four clips that had gone out that same afternoon. Three of
        # them came back with a DIFFERENT duration in the filename, which the
        # uploader would have sent up as brand new clips - scheduled again,
        # posted again, the same video twice on every platform.
        #
        # Nothing downstream would have caught it: the files were valid, the
        # names were plausible, and the board would have looked normal.
        if c.get("locked"):
            print(f"  skip {brand}/{c['slug'][:34]} - already published")
            continue
        dur = int(round(c["out"] - c["in"]))
        name = f"{i:02d}_{c['slug']}_{dur}s.mp4"
        # Reuse the name already on disk if the slug matches. Rounding here and
        # in the original cutter can differ by a second, and a renamed file is a
        # clip the cloud has scheduled under a name that no longer exists.
        #
        # Only for real rounding drift, though. 10 Sept 2026: re-cutting six
        # clips changed their lengths by 5 to 23 seconds and every one kept its
        # old name, so a 61-second clip went on calling itself 59s. That is not
        # a stale label, it is a wrong one - Stories refuses anything past 60 -
        # and the protection above was never meant to cover a different cut.
        bdir = os.path.join(OUT_ROOT, brand)
        if os.path.isdir(bdir):
            for f in os.listdir(bdir):
                # NEVER match a YouTube cut here. It also contains the slug, so
                # reusing its name produced "..._yt59__yt59.mp4" - a cut of a cut.
                if (f.endswith(".mp4") and c["slug"] in f
                        and "__yt" not in f):
                    m = re.search(r"_(\d+)s\.mp4$", f)
                    if m and abs(int(m.group(1)) - dur) > 2:
                        break          # a different cut: it must be renamed
                    name = f
                    break
        dest = os.path.join(OUT_DIR or bdir, name)
        yt_win = None
        if c.get("yt_in") is not None and c.get("yt_out") is not None:
            yt_win = (float(c["yt_in"]), float(c["yt_out"]))
        frames = shots_for(src, float(c["in"]), float(c["out"]), c["slug"])
        shots = (frames or {}).get("segments") or None
        track = (frames or {}).get("track") or []
        if shots and len(shots) > 1:
            print(f"      {len(shots)} camera setup(s): "
                  + ", ".join(f"{s['cx']:.2f}" for s in shots))
        bursts = render(src, dest, c["in"], c["out"], c["hook"], cues,
                        cx, apply, zoom, c.get("hook_yt"), yt_win,
                        c["slug"], c.get("fix"), shots, track)
        print(f"  {'rendered' if apply else 'plan'} {brand}/{name}  "
              f"{bursts} bursts  hook={' / '.join(c['hook'][:2])}")
        n += 1
    return n


def _lint_hooks(series=None):
    """Refuse to render if any hook breaks the rule. See kt_hooks.py.

    5 Sept 2026: the hooks were rewritten from riddles to plain promises once.
    Once is not a rule. This makes the renderer the place the rule is kept, so
    a clever hook cannot reach a phone without someone deliberately overriding
    it with --no-lint.
    """
    import subprocess
    if "--no-lint" in sys.argv:
        return
    # NOTHING RE-CUTS A PUBLISHED CLIP. Refreshed from the cloud every run,
    # because a flag set by hand goes stale and fifteen live clips were being
    # rewritten by re-renders before anyone noticed.
    try:
        import kt_lock
        n = kt_lock.sync()
        if n:
            print(f"  locked {n} clip(s) the cloud says are already published")
    except Exception as e:
        sys.stderr.write(f"  lock sync failed: {e}\n")
    # SCOPED TO WHAT IS BEING BUILT. 11 Sept 2026 the limit went from three
    # lines to two, and thirty clips in series nobody is rendering - including
    # brand-2's, whose hook rule is deliberately the inverse of the owner's - started
    # blocking every render behind them. A gate that stops unrelated work is a
    # gate people disable.
    cmd = [sys.executable, os.path.join(HOME, "kt_hooks.py"), "--strict"]
    if series:
        cmd += ["--series", series]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(r.stdout[-2000:])
        sys.exit("render refused: a hook breaks the rule (--no-lint to override)")
    # AND NO CLIP RUNS INTO KEVIN'S ADVERT. See kt_ads.py. The advert marks
    # where the teaching ended, so passing it is always wrong.
    r = subprocess.run([sys.executable, os.path.join(HOME, "kt_ads.py"),
                        "--strict"], capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(r.stdout[-1200:])
        sys.exit("render refused: a clip runs past the teaching into the advert")

    # AND NO SOURCE IS CUT FOR TWO PEOPLE. See kt_fence.py.
    r = subprocess.run([sys.executable, os.path.join(HOME, "kt_fence.py"),
                        "--strict"], capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(r.stdout[-1500:])
        sys.exit("render refused: a source video is cut for both people")


def main():
    args = [a for a in sys.argv[1:]]
    _lint_hooks(next((a for a in args if not a.startswith("-")), None))
    apply = "--apply" in args
    only = None
    if "--only" in args:
        only = args[args.index("--only") + 1]
    keys = [a for a in args if not a.startswith("--")
            and (not only or a != only)]
    data = json.load(open(SERIES))
    if "--all" in args:
        keys = list(data)
    if not keys:
        raise SystemExit(__doc__)
    total = 0
    for k in keys:
        if k not in data:
            raise SystemExit(f"no such series: {k}")
        print(f"{k}  ({data[k]['brand']})")
        total += run_series(k, data[k], apply, only)
    print(f"\n{total} clip(s) {'rendered' if apply else 'planned'}"
          f"{'' if apply else ' - add --apply'}")


if __name__ == "__main__":
    main()
