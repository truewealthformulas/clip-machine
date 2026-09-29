#!/usr/bin/env python3
"""Burn spoken captions into an already-cut clip.

WHY THIS EXISTS. The pipeline said since July: "NEVER burn captions. the owner adds
those natively on his phone." That was right while he posted by hand. The moment
posting became automatic that step vanished, and the first API-published Reel went
out with no captions on it. Automating away a manual step means absorbing the work
it was doing.

STYLE, as of 25 Aug 2026: bold CAPS, white, a soft dark edge and a drop shadow,
centred, sitting low over the video - under Kevin's face, above the frame edge.

This replaces the original "plain white, no outline" style, which was copied from
his own phone-made posts. That was the right call while he was matching his own
feed by hand; it stopped being right the moment the clips had to look like a
channel rather than a phone. His words, 25 Aug: "it looks not expensive or
professional". Six variants were rendered against a real frame and compared
before changing anything - see the note by the constants.

    python3 kt_burn.py mindset_shift            # plan
    python3 kt_burn.py mindset_shift --apply
    python3 kt_burn.py mindset_shift --apply --only WHO-IS-THE-FOOL
"""
import json
import os
import re
import subprocess
import sys

HOME = os.path.expanduser("~/ClipMachine")
DROP = os.path.join(HOME, "POST_TODAY")
SERIES = os.path.join(HOME, "kt_series.json")
TRANSCRIPTS = os.path.join(HOME, "transcripts")
FFMPEG = os.environ.get("WF_FFMPEG", os.path.join(HOME, "bin/ffmpeg"))
FONT = os.path.join(HOME, "bin/arial_bold.ttf")

# The canvas is 1080x1920 with the video occupying y 555-1365 (see
# build_clips_v2). Captions sit at CAP_Y, which is inside the picture and low -
# matching where his own captions land - and a long way clear of the bottom of
# the frame where the platform puts its own controls.
CAP_Y = 1176
CAP_SIZE = 56
MAX_CHARS = 22          # SHORT bursts. Caps run wider than sentence case, and a
                        # 26-char line at this size touches both edges of the
                        # frame. Shorter also hits harder - the words land as
                        # beats rather than as a subtitle you read.
MIN_HOLD = 0.55         # never flash a phrase too fast to read
LEAD = 0.10             # show each phrase a beat EARLY. A caption that arrives
                        # with the word reads as late, because the eye needs a
                        # moment to land on it before the ear confirms it.

# 25 AUG: the owner - "the captions look not expensive or professional". They were
# plain white with no edge, and over a light shirt or a bright studio wall they
# half-vanished. Rendered six variants against a real frame and looked at them:
# thin white lost every time, Helvetica Neue resolved to its LIGHT weight through
# fontconfig, and bold caps with a soft dark edge plus a drop shadow read clean
# on every background without turning into a cartoon outline.
CAP_CAPS = True
BORDER_W, BORDER_C = 3, "black@0.45"    # soft edge, NOT a hard stroke
SHADOW_Y, SHADOW_C = 5, "black@0.55"    # depth, which is what reads as expensive


def parse_srt(path):
    cues, t0, t1 = [], None, None
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.strip()
        m = re.match(r"(\d\d):(\d\d):(\d\d),(\d+)\s*-->\s*(\d\d):(\d\d):(\d\d),(\d+)", line)
        if m:
            g = [int(x) for x in m.groups()]
            t0 = g[0]*3600 + g[1]*60 + g[2] + g[3]/1000
            t1 = g[4]*3600 + g[5]*60 + g[6] + g[7]/1000
        elif line and not line.isdigit() and t0 is not None:
            cues.append((t0, t1, line))
            t0 = None
    return cues


def esc(t):
    """drawtext eats a bare apostrophe inside text='…' - "don't" becomes "dont".
    The typographic quote is the correct glyph anyway."""
    return (t.replace("\\", "\\\\").replace("'", "’")
             .replace(":", "\\:").replace("%", "\\%"))


# Words no line should END on. Breaking after "in", "a" or "that" is the single
# thing that made the first caps pass look amateur - the eye stops on a dangling
# preposition and the sentence stalls. the owner, 25 Aug: it has to read professional.
WEAK = {
    "a", "an", "the", "and", "but", "or", "nor", "so", "if", "as", "at", "by",
    "for", "from", "in", "into", "of", "off", "on", "onto", "out", "over", "to",
    "up", "with", "is", "are", "was", "were", "be", "been", "am", "do", "does",
    "did", "have", "has", "had", "will", "would", "can", "could", "should",
    "my", "your", "his", "her", "its", "our", "their", "this", "that", "these",
    "those", "it", "he", "she", "they", "we", "you", "i", "there", "what",
    "when", "where", "who", "how", "why", "no", "not",
}


def _weak(word):
    return word.lower().strip(".,!?;:\u2019'\"").strip() in WEAK


# A number must never be parted from its magnitude: "$25" on one line and
# "BILLION" on the next throws away the whole point of the sentence.
MAGNITUDE = {"billion", "million", "thousand", "hundred", "percent", "dollars",
             "years", "grand", "k"}


def split_phrase(words):
    """Break a line into chunks that read like speech, not like a text wrap.

    Greedy filling puts the break wherever the character count runs out, which
    is how the first caps pass produced "OVER $25 BILLION IN" and "I DIDN'T COME
    FROM A". So instead every possible set of breaks is scored and the cheapest
    wins - overflow is expensive, ending on a weak word is expensive, and
    separating a number from its magnitude is nearly forbidden. Lines are short
    enough that the search is trivial.
    """
    n = len(words)
    if n == 0:
        return []
    lens = [len(w) for w in words]

    def width(i, j):                      # words[i:j] joined with spaces
        return sum(lens[i:j]) + (j - i - 1)

    def cost(i, j):
        w = width(i, j)
        c = 0.0
        if w > MAX_CHARS:
            c += (w - MAX_CHARS) ** 2 * 12      # never quietly overflow the frame
        else:
            # QUADRATIC, not linear. A linear pull let the weak-word penalty win
            # every argument and the result was a stack of orphans - "I used",
            # "So using", "How". A short line is its own kind of ugly.
            c += (MAX_CHARS - w) ** 2 * 0.09
        if j < n:                               # this chunk has a line after it
            if j - i > 1 and _weak(words[j - 1]):
                c += 16                         # do not end on "in", "a", "that"
            if words[j].lower().strip(".,!?;:") in MAGNITUDE:
                c += 200                        # "$25" | "BILLION" - never
        return c

    INF = float("inf")
    best = [0.0] + [INF] * n
    back = [0] * (n + 1)
    for j in range(1, n + 1):
        for i in range(max(0, j - 12), j):
            if best[i] == INF:
                continue
            c = best[i] + cost(i, j)
            if c < best[j]:
                best[j] = c
                back[j] = i
    out, j = [], n
    while j > 0:
        i = back[j]
        out.append(" ".join(words[i:j]))
        j = i
    return [c for c in reversed(out) if c.strip()]


def phrases(cues, t_in, t_out):
    """Cues inside the clip, split into short bursts, timed clip-relative."""
    out = []
    for a, b, text in cues:
        if b <= t_in or a >= t_out:
            continue
        a, b = max(a, t_in), min(b, t_out)
        words = text.split()
        if not words:
            continue
        chunks = split_phrase(words)
        a, b = max(a - LEAD, 0.0), max(b - LEAD, 0.05)
        span = max(b - a, 0.3)
        total = sum(len(c) for c in chunks) or 1
        t = a
        for c in chunks:
            d = max(span * len(c) / total, MIN_HOLD)
            out.append((round(t - t_in, 2), round(min(t + d, b) - t_in, 2), c))
            t += d
    # never let two phrases overlap - drawtext would draw them on top of each other
    for i in range(len(out) - 1):
        if out[i][1] > out[i + 1][0]:
            out[i] = (out[i][0], out[i + 1][0], out[i][2])
    return [p for p in out if p[1] > p[0]]


def chain(ps):
    f = FONT.replace("\\", "\\\\").replace(":", "\\:").replace(" ", "\\ ")
    parts = []
    for a, b, text in ps:
        if CAP_CAPS:
            text = text.upper()
        parts.append(
            f"drawtext=fontfile={f}:text='{esc(text)}':fontsize={CAP_SIZE}"
            f":fontcolor=white"
            f":borderw={BORDER_W}:bordercolor={BORDER_C}"
            f":shadowcolor={SHADOW_C}:shadowx=0:shadowy={SHADOW_Y}"
            f":x=(w-tw)/2:y={CAP_Y}"
            f":enable='between(t,{a},{b})'")
    return ",".join(parts)


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    name = sys.argv[1]
    apply_changes = "--apply" in sys.argv
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None

    series = json.load(open(SERIES))[name]
    srt = os.path.join(TRANSCRIPTS, series["source"].rsplit(".", 1)[0] + ".srt")
    cues = parse_srt(srt)
    bdir = os.path.join(DROP, series["brand"])
    files = sorted(f for f in os.listdir(bdir) if f.endswith(".mp4"))
    # _cuts.json holds where the file ACTUALLY starts and ends. kt_series.json
    # holds where the cut was requested, and the two differ by up to a couple of
    # seconds because the in-point is snapped into a pause and then moved onto a
    # strong opening frame. Timing captions off the requested numbers puts every
    # word of the clip late.
    cuts = {}
    cpath = os.path.join(bdir, "_cuts.json")
    if os.path.exists(cpath):
        cuts = json.load(open(cpath))

    for clip, fname in zip(series["clips"], files):
        if only and only not in clip["slug"]:
            continue
        real = cuts.get(fname) or {}
        t_in = real.get("in", clip["in"])
        t_out = real.get("out", clip["out"])
        ps = phrases(cues, t_in, t_out)
        src = os.path.join(bdir, fname)
        print(f"  {fname}  {len(ps)} caption(s)")
        if ps[:3]:
            for a, b, t in ps[:3]:
                print(f"      {a:5.1f}-{b:5.1f}  {t}")
        if not apply_changes or not ps:
            continue
        tmp = src + ".cap.mp4"
        subprocess.run(
            [FFMPEG, "-y", "-loglevel", "error", "-i", src, "-vf", chain(ps),
             "-c:v", "libx264", "-preset", "medium", "-b:v", "4M",
             "-maxrate", "4M", "-bufsize", "8M", "-pix_fmt", "yuv420p",
             "-c:a", "copy", "-movflags", "+faststart", tmp], check=True)
        os.replace(tmp, src)
        print(f"      -> captions burned in")

    if not apply_changes:
        print("\n  plan only. --apply to burn them in.")


if __name__ == "__main__":
    main()
