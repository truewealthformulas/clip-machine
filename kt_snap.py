#!/usr/bin/env python3
"""Move every clip's in/out to a real sentence boundary.

WHY. 30 Aug 2026, the owner: "most of the clips start cut off or in a worst time for
the clip to start, it starts very off, and also ends off". Measured it before
touching anything: 60 of 81 clips began or ended mid-sentence. He was right, and
it is the single most damaging thing in the whole pipeline - a stranger scrolling
gets half a sentence as the first thing they hear, which reads as broken before
it reads as anything else.

WHY IT HAPPENED. `in`/`out` in kt_series.json were chosen from where a THOUGHT
starts in the transcript, then used as raw seconds. The transcript's own cue
boundaries were never consulted, so the cut landed wherever that second fell -
usually inside a word.

WHAT THIS DOES. For each clip it looks at the subtitle cues around the current
in/out and moves them to the nearest point where a sentence actually ends:
  IN   -> the start of a cue whose PREVIOUS cue ended on . ! or ?
  OUT  -> the end of a cue that itself ends on . ! or ?
Forward is preferred for IN (losing a few seconds of run-up beats opening on a
fragment) and forward for OUT (finish the thought he started).

    python3 kt_snap.py            # show what would move, change nothing
    python3 kt_snap.py --apply
"""
import json
import os
import sys

import kt_burn as burn

HOME = os.path.expanduser("~/ClipMachine")
SERIES = os.path.join(HOME, "kt_series.json")
TRANSCRIPTS = os.path.join(HOME, "transcripts")

END = (".", "!", "?")
WINDOW = 25.0        # how far to look for a boundary before giving up
TAIL = 0.35          # let the last word finish before the cut lands


def ends_sentence(text):
    return text.strip().endswith(END)


def snap_in(cues, t):
    """Nearest sentence START. Prefers moving forward - opening on a fragment is
    worse than losing a little run-up."""
    starts = []
    for i, (a, b, txt) in enumerate(cues):
        if i == 0 or ends_sentence(cues[i - 1][2]):
            starts.append(a)
    if not starts:
        return t
    ahead = [s for s in starts if 0 <= s - t <= WINDOW]
    behind = [s for s in starts if 0 <= t - s <= WINDOW]
    if ahead and behind:
        # forward wins unless backwards is much closer
        return ahead[0] if (ahead[0] - t) <= (t - behind[-1]) * 1.6 else behind[-1]
    if ahead:
        return ahead[0]
    if behind:
        return behind[-1]
    return t


def snap_out(cues, t):
    """Nearest sentence END, preferring to finish the thought he is in."""
    ends = [b for a, b, txt in cues if ends_sentence(txt)]
    if not ends:
        return t
    ahead = [e for e in ends if 0 <= e - t <= WINDOW]
    behind = [e for e in ends if 0 <= t - e <= WINDOW]
    if ahead:
        return ahead[0] + TAIL
    if behind:
        return behind[-1] + TAIL
    return t



# ---------------------------------------------------------------- real silence
# TRANSCRIPTS ARE NOT GOOD ENOUGH AND THE NUMBERS SAY SO. Punctuation-only
# snapping took 60 bad cuts down to 46 and stopped, because the sources disagree
# wildly about what a transcript is: Meditation Myth has ZERO full stops in 436
# cues, and Tough Times has 28 in 559 with no usable gaps either. Snapping to
# punctuation there is snapping to noise.
#
# The audio does not lie. ffmpeg's silencedetect finds where he actually stops
# talking, which is the thing a viewer hears as "this started properly". IN goes
# to the END of a silence (speech begins immediately), OUT to the START of one
# (the thought lands, then quiet). One pass per source, cached.
SIL_CACHE = os.path.join(HOME, "kt_silence.json")
FFMPEG = os.environ.get("WF_FFMPEG", os.path.join(HOME, "bin/ffmpeg"))
NOISE = "-32dB"
MIN_SIL = 0.22

# PER-SOURCE CALIBRATION, 30 Aug 2026. brand-2's session hit a clip whose 69-second
# stretch offered only four break points, so no good cut existed to choose. I
# measured every source here: most of Kevin's give 22-27 breaks a minute, but
# The Secret gives 7.4 and her source gives 10.8 - and those are exactly the two
# places bad cuts survive.
#
# The cause is the recording, not the speech. A source with more room tone never
# drops below -32dB between sentences, so silencedetect sees one long noise.
# Counter-intuitive but load-bearing: a LOWER dB is a STRICTER bar. Going to
# -45dB found 7 breaks in 35 minutes; going UP to -22dB found 809. Measured, not
# reasoned - I had the direction backwards first.
#
# So the threshold is chosen per source: loosen until the density looks like a
# source we already cut well, and never go past -20dB where word gaps start
# counting as sentence breaks.
# THE LADDER IS OFF, AND THE REASON IS THE USEFUL PART.
# I measured density correctly and then drew the wrong conclusion from it. brand-2's
# session ran the loosened setting on a real source and READ all five cuts at both
# thresholds: 1 better, 2 WORSE, 2 unchanged.
#
# Why it backfires: yt_window picks a clip's END from "the biggest breath, since he
# breathes after finishing a thought". That only holds while the detector is finding
# SENTENCE pauses. Loosen it and you also catch comma pauses, breath mid-clause and
# gaps between words - so "biggest break" stops meaning "end of thought" and the
# selection rule quietly loses its basis. More candidates, worse choices.
#
# And the sharp edge: the ladder only fires on THIN sources, because healthy ones
# never leave rung one. Thin sources are exactly where the scorer degrades. So on my
# own numbers it changes behaviour only where it makes things worse, and is a no-op
# everywhere else. That is an argument against shipping it.
#
# The measurement stands and is worth keeping: most sources give 22-27 breaks/min;
# The Secret gives 7.4 and AR_MIND 10.8, and those are the only two places bad cuts
# survive. The fix is to make density a QUALITY signal, not a quantity one - rank
# candidate ends by pause length relative to that source's local median, so a real
# sentence stop still stands out after loosening. UNTESTED. Do not ship it either
# without reading the cuts out loud, which is the only thing that caught this.
TARGET_PER_MIN = 0.0          # 0 = never loosen; the ladder cannot fire
LADDER = [("-32dB", 0.22)]


def silences(src):
    cache = json.load(open(SIL_CACHE)) if os.path.exists(SIL_CACHE) else {}
    key = os.path.basename(src)
    if key in cache:
        return [tuple(x) for x in cache[key]]
    import subprocess
    sys.stderr.write(f"  scanning audio for silence: {key}\n")

    def scan(noise, dur):
        r = subprocess.run(
            [FFMPEG, "-i", src, "-vn", "-af",
             f"silencedetect=noise={noise}:d={dur}", "-f", "null", "-"],
            capture_output=True, text=True)
        got, st = [], None
        for line in r.stderr.splitlines():
            if "silence_start:" in line:
                st = float(line.split("silence_start:")[1].split()[0])
            elif "silence_end:" in line and st is not None:
                got.append((st, float(line.split("silence_end:")[1].split()[0])))
                st = None
        return got

    out = []
    for noise, dur in LADDER:
        out = scan(noise, dur)
        if not out:
            continue
        span = max(b for a, b in out) - min(a for a, b in out)
        if span <= 0:
            break
        per_min = len(out) / (span / 60)
        if per_min >= TARGET_PER_MIN:
            if noise != LADDER[0][0]:
                sys.stderr.write(f"    thin source - loosened to {noise} "
                                 f"({per_min:.1f} breaks/min)\n")
            break
    cache[key] = [list(x) for x in out]
    json.dump(cache, open(SIL_CACHE, "w"))
    return out


def snap_audio_in(sil, t):
    """Start the instant speech resumes after a pause."""
    ends = [e for s, e in sil]
    near = [e for e in ends if abs(e - t) <= WINDOW]
    if not near:
        return t
    ahead = [e for e in near if e >= t]
    behind = [e for e in near if e < t]
    if ahead and behind:
        return ahead[0] if (ahead[0] - t) <= (t - behind[-1]) * 1.6 else behind[-1]
    return (ahead or behind)[0 if ahead else -1]


def snap_audio_out(sil, t):
    """End as he stops, not mid-word. A hair into the silence so the last
    syllable is not clipped."""
    starts = [s for s, e in sil]
    near = [s for s in starts if abs(s - t) <= WINDOW]
    if not near:
        return t
    ahead = [s for s in near if s >= t]
    behind = [s for s in near if s < t]
    if ahead:
        return ahead[0] + 0.18
    return behind[-1] + 0.18


def main():
    apply = "--apply" in sys.argv
    d = json.load(open(SERIES))
    moved = 0
    for key, spec in d.items():
        srt = os.path.join(TRANSCRIPTS,
                           os.path.splitext(spec["source"])[0] + ".srt")
        if not os.path.exists(srt):
            continue
        cues = burn.parse_srt(srt)
        src = os.path.join(HOME, "Content/1_RAW/KT_SOURCE", spec["source"])
        sil = silences(src) if os.path.exists(src) else []
        for c in spec["clips"]:
            i0 = c.get("in_raw", c["in"])          # always snap from the ORIGINAL
            o0 = c.get("out_raw", c["out"])        # so reruns cannot drift
            if sil:
                i1, o1 = snap_audio_in(sil, i0), snap_audio_out(sil, o0)
            else:
                i1, o1 = snap_in(cues, i0), snap_out(cues, o0)
            if o1 - i1 < 15:              # never let a snap collapse a clip
                continue
            if abs(i1 - i0) < 0.05 and abs(o1 - o0) < 0.05:
                continue
            print(f"{spec['brand']}/{c['slug'][:30]:32} "
                  f"in {i0:8.1f} -> {i1:8.1f}   out {o0:8.1f} -> {o1:8.1f}")
            if apply:
                c.setdefault("in_raw", i0)
                c.setdefault("out_raw", o0)
                c["in"], c["out"] = round(i1, 2), round(o1, 2)
            moved += 1
    if apply:
        json.dump(d, open(SERIES, "w"), indent=1, ensure_ascii=False)
    print(f"\n{moved} clip(s) {'snapped' if apply else 'would move'}"
          f"{'' if apply else ' - add --apply'}")


if __name__ == "__main__":
    main()
