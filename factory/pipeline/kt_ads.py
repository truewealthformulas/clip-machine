#!/usr/bin/env python3
"""Where Kevin's own advert starts, and refusing to let a clip run into it.

WHY, 13 Sept 2026. the owner watched a posted clip run past its last line straight
into the Your Wish Is Your Command advert. His reasoning is the useful part:

    "if their ad comes afterwords that means the teaching its finished"

The advert is a reliable END MARKER. Every one of these talks closes the
teaching and then runs the same pitch. So the advert's start is a hard ceiling
for any clip cut from that video - and it also tells us where the teaching ends,
which is the thing we have been guessing at.

I had already been told to be precise about ending where the teaching ends, and
a clip still went out ten seconds into the advert. So this stops being judgement
and becomes a gate.

    python3 kt_ads.py            # where the advert starts in every source
    python3 kt_ads.py --check    # list clips that run into one
    python3 kt_ads.py --strict   # exit 1 if any unposted clip does
"""
import json
import os
import re
import sys

HOME = os.path.expanduser("~/ClipMachine")
TRANS = os.path.join(HOME, "transcripts")
SERIES = os.path.join(HOME, "kt_series.json")

# The advert's own opening words. "What is manifesting?" is the usual one.
OPENER = re.compile(
    r"what is manifesting|your wish is your command|"
    r"this book reveals the missing|it was just an awakening|"
    r"my income has doubled", re.I)

# IT MUST BE AT THE END. The first version matched any of these phrases anywhere
# and reported 32 clips broken, most of them nonsense - Kevin says "your wish is
# your command" in the middle of a talk about wishes. The advert is a contiguous
# block that closes the video and runs roughly 40 to 200 seconds.
MIN_TAIL, MAX_TAIL = 40.0, 220.0


def cues(source):
    p = os.path.join(TRANS, os.path.splitext(source)[0] + ".srt")
    if not os.path.exists(p):
        return []

    def _s(t):
        h, m, rest = t.split(":")
        return int(h) * 3600 + int(m) * 60 + float(rest.replace(",", "."))
    raw = open(p, encoding="utf-8", errors="replace").read()
    return [(_s(a), _s(b), " ".join(c.split())) for a, b, c in re.findall(
        r"(\d\d:\d\d:\d\d,\d\d\d) --> (\d\d:\d\d:\d\d,\d\d\d)\n(.*?)(?=\n\n|\Z)",
        raw, re.S)]


# The FIRST words of the advert, used to find the boundary inside a cue.
FIRST_WORDS = re.compile(r"\b(it was just an awakening|what is manifesting|"
                         r"my income has doubled|your wish is your command)\b", re.I)


def ad_start(source, refine=True):
    """When the closing advert begins, or None if this video has none.

    REFINED TO THE WORD, and this is the whole point. 13 Sept 2026 a clip was
    cut at 975.90 and lost its payoff line, because the cue that starts at
    976.50 reads:

        "It will absolutely keep you from it was just an awakening."

    That single cue holds the END of Kevin's teaching ("it will absolutely keep
    you broke") AND the START of the testimonial ("it was just an awakening").
    Trusting the cue's start time put the boundary 3.7 seconds too early and
    threw away the best line in the clip - the owner heard it immediately.

    A subtitle cue is a unit of DISPLAY, not of meaning. So when the opener is
    found mid-cue, re-transcribe that cue word by word and take the moment the
    advert's first word actually begins.
    """
    cs = cues(source)
    if not cs:
        return None
    end = cs[-1][1]
    for s, e, t in cs:
        if not (OPENER.search(t) and MIN_TAIL <= (end - s) <= MAX_TAIL):
            continue
        if not refine:
            return s
        m = FIRST_WORDS.search(t)
        # If the advert's opening words are NOT the first thing in the cue, the
        # boundary is inside it and the cue start is wrong.
        if m and m.start() > 3:
            w = _word_time(source, s, e, m.group(0).split()[0])
            if w is not None:
                return w
        return s
    return None


def _word_time(source, t0, t1, first_word):
    """When `first_word` is actually spoken, from a word-level pass over t0..t1."""
    import subprocess
    src = None
    for root in ("Content/1_RAW/KT_SOURCE",):
        cand = os.path.join(HOME, root, source)
        if os.path.exists(cand):
            src = cand
    if not src:
        return None
    ff = os.path.join(HOME, "bin/ffmpeg")
    wh = os.path.join(HOME, "whisper.cpp/build/bin/whisper-cli")
    mdl = os.path.join(HOME, "whisper.cpp/models/ggml-small.en.bin")
    if not (os.path.exists(wh) and os.path.exists(mdl)):
        return None
    wav = os.path.join(HOME, "work", "_adword.wav")
    pad = 1.0
    r = subprocess.run([ff, "-v", "error", "-y", "-ss", f"{max(0, t0 - pad):.2f}",
                        "-t", f"{(t1 - t0) + 2 * pad:.2f}", "-i", src,
                        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav],
                       capture_output=True)
    if r.returncode:
        return None
    out = subprocess.run([wh, "-m", mdl, "-f", wav, "-ml", "1", "-sow"],
                         capture_output=True, text=True).stdout
    base = max(0.0, t0 - pad)
    want = first_word.lower().strip(".,")
    for mm in re.finditer(r"\[(\d\d):(\d\d):(\d\d)\.(\d\d\d) --> [^\]]+\]\s*(\S+)", out):
        h, mi, sec, ms, word = mm.groups()
        if word.lower().strip(".,") == want:
            t = base + int(h) * 3600 + int(mi) * 60 + int(sec) + int(ms) / 1000
            if t > t0:          # the advert's word, not an earlier coincidence
                return t
    return None


def main():
    d = json.load(open(SERIES))
    check = "--check" in sys.argv or "--strict" in sys.argv
    bad = []
    for k, spec in sorted(d.items()):
        ad = ad_start(spec["source"])
        if not check:
            cs = cues(spec["source"])
            end = cs[-1][1] if cs else 0
            print(f"  {spec['brand']:14} advert at "
                  f"{('%.1fs of %.0fs' % (ad, end)) if ad else 'none found':22}"
                  f" {spec['source'][:44]}")
            continue
        if ad is None:
            continue
        for c in spec.get("clips", []):
            if float(c["out"]) > ad:
                bad.append((spec["brand"], c["slug"], float(c["out"]), ad,
                            bool(c.get("locked"))))
    if not check:
        return
    live = [b for b in bad if b[4]]
    fix = [b for b in bad if not b[4]]
    for brand, slug, out, ad, locked in bad:
        print(f"  {'LIVE ' if locked else 'FIX  '}{brand}/{slug[:32]:34} "
              f"out {out:8.1f}  advert {ad:8.1f}  {out - ad:+.1f}s into it")
    print(f"\n{len(fix)} to fix, {len(live)} already published (cannot be changed)")
    if "--strict" in sys.argv and fix:
        raise SystemExit(f"{len(fix)} clip(s) run into the advert")


if __name__ == "__main__":
    main()
