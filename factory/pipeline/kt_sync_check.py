#!/usr/bin/env python3
"""Are the captions on screen when the words are said? Checked on the FINISHED clip.

WHY THIS EXISTS. 16 Sept 2026. Captions on seven clips drifted progressively
ahead of the speech - 1.6s early by second 4, 9.5s early by second 22 - and two
of them posted. the owner spotted it at a glance: "the captions are completely off
close to the beginning."

Nothing caught it because nothing looked. kt_verify_render listens to the first
and last seconds; a still frame shows the right caption for that instant; an
exit code of 0 says the encode worked. Drift that GROWS is invisible at the
edges and obvious in the middle.

The cause was mine: a punctuation prompt added to the word-timing pass, which
compresses whisper's timestamps. The check below would have failed every one of
those clips on its first run.

How: the renderer writes <clip>__caps.json - exactly what it burned. This
transcribes the finished clip independently, with NO prompt, and compares each
caption's first word against when that word is actually spoken.

    python3 kt_sync_check.py POST_TODAY/KT_LIES/03_THE-DRYER-FUND_57s.mp4 [...]
    exit 1 if any clip fails
"""
import json
import os
import re
import statistics as st
import subprocess
import sys

HOME = os.path.expanduser("~/ClipMachine")
sys.path.insert(0, HOME)
import kt_words                                                  # noqa: E402

FF = f"{HOME}/bin/ffmpeg"
W = f"{HOME}/whisper.cpp/build/bin/whisper-cli"
M = f"{HOME}/whisper.cpp/models/ggml-small.en.bin"
MEDIAN_MAX = 0.30      # a caption's typical lead, including the deliberate 0.1s lead-in
P90_MAX = 0.70         # and the worst tenth - one long burst may start a word early
LEAD_IN = 0.10


def norm(w):
    return re.sub(r"[^a-z0-9]", "", w.lower())


def check(mp4):
    """Grade each caption against the WAVEFORM, not against another transcription.

    FIRST VERSION WAS WRONG, 16 Sept 2026, the same afternoon it was written. It
    compared burned captions against a second whisper pass over the finished
    clip, and FAILED a good clip - THE ECONOMY WAS SLUGGISH, "0.4s early". Graded
    against the real sound over 50 pauses, the burned captions were off by a
    median 0.01s; the checker's own reference was the less accurate of the two.
    Two whisper runs over identical audio disagreed by 0.39s. Whisper cannot
    referee whisper.

    So: after every real pause the next word begins exactly where the sound
    rises - that moment is ground truth. Whisper supplies WHICH word starts
    there (it is reliable about words, not about milliseconds), the waveform
    supplies WHEN, and the caption for that word is graded against it.
    """
    side = os.path.splitext(mp4)[0] + "__caps.json"
    if not os.path.exists(side):
        return None, f"no {os.path.basename(side)} - render it again to get one"
    bursts = json.load(open(side))
    tmp = f"/tmp/kt_sync.{os.getpid()}"   # per process
    subprocess.run([FF, "-y", "-loglevel", "error", "-i", mp4, "-ar", "16000", "-ac", "1",
                    "-c:a", "pcm_s16le", tmp + ".wav"], capture_output=True)
    subprocess.run([W, "-m", M, "-f", tmp + ".wav", "-ml", "1", "-sow", "-osrt", "-of", tmp],
                   capture_output=True)
    heard = kt_words.parse_word_srt(tmp + ".srt")
    r = subprocess.run([FF, "-i", tmp + ".wav", "-af", "silencedetect=noise=-38dB:d=0.25",
                        "-f", "null", "-"], capture_output=True, text=True).stderr
    onsets = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r)]
    # ALIGN BY ORDER, NOT BY NEAREST MATCH. The second version searched forward
    # for the next caption starting with the same word, and "the", "and",
    # "you" matched the wrong occurrence - reporting 16s errors on a clip whose
    # median was 0.10s. A sequence alignment of the two word lists uses word
    # ORDER, so a repeated word maps to the right instance. It still catches
    # real drift: compressed timestamps keep the words in order, only the times
    # are wrong, and the times are what gets graded.
    import difflib
    cap_words = []                       # (normalised word, burst start if it opens one)
    for a, _b, text in bursts:
        for k, w in enumerate(text.split()):
            cap_words.append((norm(w), a if k == 0 else None))
    hn = [norm(w) for _a, _b, w in heard]
    cn = [w for w, _ in cap_words]
    sm = difflib.SequenceMatcher(a=hn, b=cn, autojunk=False)
    h2c = {}
    for tag, i1, i2, j1, _j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                h2c[i1 + k] = j1 + k
    err = []
    for t in onsets:
        idx = [n for n, x in enumerate(heard) if t - 0.6 <= x[0] <= t + 0.6]
        if not idx:
            continue
        hi = min(idx, key=lambda n: abs(heard[n][0] - t))
        ci = h2c.get(hi)
        if ci is None or cap_words[ci][1] is None:
            continue                     # the word at this pause does not open a caption
        err.append((cap_words[ci][1] + LEAD_IN) - t)
    if len(err) < 5:
        return None, f"only {len(err)} pause-anchored captions - too few to judge"
    med = st.median(err)
    p90 = sorted(abs(d) for d in err)[max(0, int(len(err) * 0.9) - 1)]
    ok = abs(med) <= MEDIAN_MAX and p90 <= P90_MAX
    # AND NOTHING SPOKEN GOES UNCAPTIONED. 16 Sept 2026: a rule meant to drop a
    # half-syllable deleted five whole seconds of captions from the YWIYC
    # flagship ("...New York City at the Carnegie Deli") and the timing check
    # still passed - there was nothing left there to be late. Coverage is its
    # own question: speech with no caption over it.
    silent = [(a, b) for a, b in re.findall(r"silence_start: ([\d.]+)[\s\S]*?silence_end: ([\d.]+)", r)]
    quiet = [(float(a), float(b)) for a, b in silent]
    def speaking(t):
        return not any(a <= t <= b for a, b in quiet)
    holes = []
    for k in range(len(bursts) - 1):
        a, b = bursts[k][1], bursts[k + 1][0]
        if b - a > 1.2 and speaking((a + b) / 2):
            holes.append((round(a, 1), round(b, 1)))
    cw = sum(len(t.split()) for _a, _b, t in bursts)
    cover = cw / max(1, len(heard))
    if holes or cover < 0.85:
        ok = False
    return ok, (f"{len(err)} captions vs the sound  median {med:+.2f}s  worst-10% {p90:.2f}s  "
                f"| words captioned {cover:.0%}" + (f"  UNCAPTIONED SPEECH {holes}" if holes else ""))


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    bad = 0
    for mp4 in sys.argv[1:]:
        ok, msg = check(mp4)
        tag = "PASS" if ok else ("????" if ok is None else "FAIL")
        bad += 0 if ok else 1
        print(f"  [{tag}] {os.path.basename(mp4)[:52]:54} {msg}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
