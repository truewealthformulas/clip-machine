#!/usr/bin/env python3
"""Word-level timings, so a caption appears exactly when the word is spoken.

WHY, 2 Sept 2026. the owner: "i saw the captions of the clip not being in sync with
kts voice". He was right and the cause was not the cut - the audio and the seek
are perfectly aligned, verified by transcribing a rendered clip and comparing it
to the source transcript.

The drift was INSIDE the caption timing. `kt_burn.phrases()` splits one subtitle
cue into short bursts and then hands each burst a slice of the cue's duration
**proportional to its CHARACTER COUNT**:

    d = span * len(chunk) / total

Speech is not proportional to letters. "I" takes 90ms and "reveal" takes 560ms,
and a three-burst cue over 3.6 seconds could put a burst most of a second away
from the word being said. Every clip had this; it is invisible in code and
obvious the moment you watch one.

whisper.cpp will give real word times with `-ml 1 -sow` (one word per segment).
This generates them per clip window - not per whole source, which would be hours
of audio - and caches them, so a re-render costs nothing.

    python3 kt_words.py debt_trap          # build timings for one video
    python3 kt_words.py --all              # every video
"""
import json
import os
import re
import subprocess
import sys

HOME = os.path.expanduser("~/ClipMachine")
SERIES = os.path.join(HOME, "kt_series.json")
SRC_DIR = os.path.join(HOME, "Content/1_RAW/KT_SOURCE")
CACHE = os.path.join(HOME, "kt_words.json")
FFMPEG = os.path.join(HOME, "bin/ffmpeg")
WHISPER = os.path.join(HOME, "whisper.cpp/build/bin/whisper-cli")
MODEL = os.path.join(HOME, "whisper.cpp/models/ggml-small.en.bin")
# ONE FOLDER PER PROCESS. 16 Sept 2026: three transcriptions ran at once and
# all wrote /tmp/kt_words_tmp/p.wav and read p.json back - whichever finished
# last could hand its words to the others, and the cache keeps them for good.
TMP = f"/tmp/kt_words_tmp/{os.getpid()}"
PUNCT_PROMPT = ("Hello, everyone. Today, we are going to talk about money, "
                "health, and success. It is important, isn't it?")


def parse_word_srt(path):
    """[(start, end, word)] from a one-word-per-cue SRT."""
    out, t0, t1 = [], None, None
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\n")
        m = re.match(r"(\d\d):(\d\d):(\d\d),(\d+)\s*-->\s*(\d\d):(\d\d):(\d\d),(\d+)",
                     line.strip())
        if m:
            g = [int(x) for x in m.groups()]
            t0 = g[0]*3600 + g[1]*60 + g[2] + g[3]/1000
            t1 = g[4]*3600 + g[5]*60 + g[6] + g[7]/1000
        elif not line.strip():
            t0 = None            # an empty-text cue must not swallow the next index
        # A WORD MAY BE ALL DIGITS. 17 Sept 2026: this used to skip digit-only
        # lines as cue numbers - but one word per cue means "40", "28", "1969"
        # are whole cues, and every one of them vanished from the captions.
        # The index line is already skipped: it arrives while t0 is None.
        elif t0 is not None:
            w = line.strip()
            if w:
                out.append((t0, t1, w))
            t0 = None
    return out


def _load_cache():
    """The cache, or an empty one. NEVER raises.

    3 Sept 2026. A render died on `JSONDecodeError: Expecting ',' delimiter` at
    character 24571 of kt_words.json, and the clip it was rendering fell through
    to the character-proportional fallback - the very drift this module exists
    to remove - with nothing on screen to say so.

    The file was not damaged. It was being READ while another render was WRITING
    it: `json.dump(cache, open(CACHE, "w"))` truncates first and writes second,
    so for a moment the file on disk is a valid path to half a JSON document.
    Three sessions share this Mac and renders run in parallel, so that moment
    comes round often.

    Two changes, and both are needed. Reads never raise, because a cold cache
    costs a re-transcribe and a raised exception costs the clip. Writes are
    atomic (see _save_cache), because a reader must never see a half-written
    file in the first place.
    """
    if not os.path.exists(CACHE):
        return {}
    try:
        with open(CACHE) as fh:
            return json.load(fh)
    except (ValueError, OSError) as e:
        sys.stderr.write(f"  kt_words: cache unreadable ({e}); "
                         "continuing without it\n")
        return {}


def _save_cache(key, value):
    """Add one entry. Written to a temp file and renamed, so a reader sees
    either the old cache or the new one and never a half of either.

    Re-read immediately before writing rather than trusting the copy this
    process loaded, so two parallel renders do not each save a cache missing
    the other's work.
    """
    cache = _load_cache()
    cache[key] = value
    tmp = f"{CACHE}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w") as fh:
            json.dump(cache, fh)
        os.replace(tmp, CACHE)            # atomic on the same filesystem
    except OSError as e:
        sys.stderr.write(f"  kt_words: could not save cache: {e}\n")
        if os.path.exists(tmp):
            os.remove(tmp)


def words_for(src, t_in, t_out, key):
    """Word timings for one clip window, clip-relative. Cached by key."""
    # THE WINDOW IS PART OF THE IDENTITY. 3 Sept: the book clip was recut to
    # start 31 seconds later, the video was correct, and the captions were still
    # the OLD ones - because the cache key was the clip's NAME. Same name, new
    # in/out, stale timings returned. A cache keyed on less than what the value
    # depends on is a cache that lies.
    # "#t2": timings from an UNPROMPTED pass. Every entry written before this
    # tag may carry prompt-compressed times and must never be reused.
    key = f"{key}@{t_in:.2f}-{t_out:.2f}" + ("#t2" if key.startswith("PAYOFF") else "#t3")  # t3: digits kept
    cache = _load_cache()
    if key in cache:
        return [tuple(x) for x in cache[key]]
    os.makedirs(TMP, exist_ok=True)
    wav = os.path.join(TMP, "w.wav")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{t_in:.2f}",
                    "-t", f"{t_out - t_in:.2f}", "-i", src, "-ar", "16000",
                    "-ac", "1", "-c:a", "pcm_s16le", wav], capture_output=True)
    base = os.path.join(TMP, "w")
    # NO PROMPT ON THE TIMING PASS - AND THIS COST TWO DAYS OF CAPTIONS.
    #
    # 14 Sept 2026 I added the punctuation prompt here, to give caption breaks
    # real full stops. It did that - and it silently COMPRESSED every word
    # timestamp in one-word-per-segment mode. Measured 16 Sept on the same 28s
    # of audio: "universe" at 22.36s unprompted, 13.06s prompted. Burned
    # captions ran 1.6s early by second 4 and 9.5s early by second 22. the owner
    # saw it immediately: "the captions are completely off close to the
    # beginning". Seven clips were timed this way; two had already posted.
    #
    # So timing and punctuation are separate passes. This one is unprompted and
    # its times are exact. words_punct() below adds punctuation from a prompted
    # pass WITHOUT taking its times.
    r = subprocess.run([WHISPER, "-m", MODEL, "-f", wav, "-ml", "1", "-sow",
                        "-osrt", "-of", base], capture_output=True, text=True)
    if not os.path.exists(base + ".srt"):
        sys.stderr.write(f"  whisper failed for {key}: {r.stderr[-200:]}\n")
        return []
    got = parse_word_srt(base + ".srt")
    _save_cache(key, [list(x) for x in got])
    return got


def words_punct(src, t_in, t_out, key):
    """Exact times (unprompted pass) carrying punctuation (prompted pass).

    For anything that needs SENTENCES - kt_payoff finding where an idea ends.
    Captions do not need this and must not pay for it: use words_for().

    The two passes are lined up by their normalised words and only the trailing
    punctuation is carried across. A word the passes disagree on keeps the timed
    pass's text. No time from the prompted pass is ever used.
    """
    import difflib
    timed = words_for(src, t_in, t_out, key)
    pkey = f"PUNCT/{key}@{t_in:.2f}-{t_out:.2f}" + ("#t2" if key.startswith("PAYOFF") else "#t3")
    cache = _load_cache()
    if pkey in cache:
        return [tuple(x) for x in cache[pkey]]
    os.makedirs(TMP, exist_ok=True)
    wav = os.path.join(TMP, "p.wav")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{t_in:.2f}",
                    "-t", f"{t_out - t_in:.2f}", "-i", src, "-ar", "16000",
                    "-ac", "1", "-c:a", "pcm_s16le", wav], capture_output=True)
    base = os.path.join(TMP, "p")
    subprocess.run([WHISPER, "-m", MODEL, "-f", wav, "-ml", "1", "-sow",
                    "--prompt", PUNCT_PROMPT, "-osrt", "-of", base],
                   capture_output=True, text=True)
    if not os.path.exists(base + ".srt"):
        return timed
    punct = [w for _a, _b, w in parse_word_srt(base + ".srt")]
    norm = lambda w: re.sub(r"[^a-z0-9]", "", w.lower())
    a_ = [norm(w) for _x, _y, w in timed]
    b_ = [norm(w) for w in punct]
    out = [list(x) for x in timed]
    sm = difflib.SequenceMatcher(a=a_, b=b_, autojunk=False)
    for tag, i1, i2, j1, _j2 in sm.get_opcodes():
        if tag != "equal":
            continue
        for k in range(i2 - i1):
            src_w, dst_w = punct[j1 + k], out[i1 + k][2]
            tail = re.search(r"[.!?,;:\"\u201d]+$", src_w)
            core = re.sub(r"[.!?,;:\"\u201d]+$", "", dst_w)
            out[i1 + k][2] = core + (tail.group(0) if tail else "")
    _save_cache(pkey, out)
    return [tuple(x) for x in out]


def main():
    d = json.load(open(SERIES))
    keys = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--all" in sys.argv:
        keys = list(d)
    if not keys:
        raise SystemExit(__doc__)
    for k in keys:
        spec = d[k]
        src = os.path.join(SRC_DIR, spec["source"])
        if not os.path.exists(src):
            print(f"  {k}: source missing")
            continue
        print(f"{k} ({spec['brand']})")
        for c in spec["clips"]:
            key = f"{spec['brand']}/{c['slug']}"
            w = words_for(src, c["in"], c["out"], key)
            print(f"   {c['slug'][:34]:36} {len(w)} words")


if __name__ == "__main__":
    main()
