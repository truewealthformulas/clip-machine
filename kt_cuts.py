#!/usr/bin/env python3
"""Where a clip may start and end, measured from the WAVEFORM.

WHY THIS EXISTS, 8 Sept 2026, after four failed attempts at the same bug.

the owner, repeatedly: clips "finish in the middle of a story, teaching, data, or
speach." Four fixes, four times the verification said it was still broken, and
the reason turned out to have nothing to do with the logic.

**Whisper's word timestamps are not reproducible.** Transcribe 321.7->374.6 and
transcribe 321.7->378.6, and the SAME word lands at a different time:

    fixer's transcription:    last word 'guy'      ends 54.24
    verifier's transcription: last word 'another'  ends 52.63

Same audio. So the fixer optimised against one set of numbers and the checker
graded against another, and they could never agree. Every "fixed" claim I made
was an artefact of that disagreement.

**Silence in the waveform is not a model output. It is a measurement.** ffmpeg's
silencedetect returns the same answer every time, so a fixer and a checker
reading it cannot disagree:

    silence 373.51 -> 374.04   (0.53s)
    silence 376.69 -> 377.25   (0.56s)

A clip should END just after the last word before a silence, and START just
after a silence ends. Both are exact.

Whisper is still the right tool for CAPTIONS - it is the words that matter there
and a tenth of a second does not. It is the wrong tool for CUTS.

**10 Sept 2026: the threshold cannot be a constant.** Six new clips came out cut
mid-sentence at BOTH edges and the snapper had silently declined to move any of
them. It had found no silence to snap to - not one pause in a six-minute stretch
of a man talking. The threshold was pinned at -30dB, and measuring the file
showed why that is not a number you can pin:

    190-580s   noise floor  -32.1 dB     -> nothing is ever below -30
    810-920s   noise floor -897.0 dB     -> true digital silence

Same file. One remastered stretch sits on a hiss floor, the next is clean. A
fixed threshold is deaf to the first and fine on the second, and the failure is
SILENT: best_end returns None, the clip is skipped, and it ships cut mid-word.

So the threshold is now measured per 60-second block, from that block's own RMS.
The block grid is what makes it safe to do: a point's threshold depends only on
which 60s block it falls in, never on the window a caller happened to ask for,
so the fixer and the checker still read identical numbers - which is the entire
reason this module stopped using whisper.
"""
import json
import os
import re
import subprocess

HOME = os.path.expanduser("~/ClipMachine")
FFMPEG = os.path.join(HOME, "bin/ffmpeg")
CACHE = os.path.join(HOME, "kt_silence_map_v3.json")

MIN_SIL = 0.28       # a clear break in speech
FINE_SIL = 0.12      # the smaller dip at a full stop in fast speech
TAIL = 0.25          # keep this much of the silence after the last word
LEAD = 0.12          # start this far before the first word

GRID = 60.0          # threshold is measured per 60s block, on a fixed grid
PAD = 2.0            # analyse a little past the block so a pause on the seam survives
BELOW_RMS = (12.0, 9.0, 6.0)   # try this far under the block's RMS, in order
FLOOR, CEIL = -38.0, -16.0     # never go outside this, whatever the RMS says
WANT = 14.0          # a block with no pause per 14s has not been heard properly
NEAR = 1.5           # how close a pause must sit to a full stop to count as one


def _load():
    if not os.path.exists(CACHE):
        return {}
    try:
        with open(CACHE) as fh:
            return json.load(fh)
    except (ValueError, OSError):
        return {}


def _save(cache):
    tmp = f"{CACHE}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w") as fh:
            json.dump(cache, fh)
        os.replace(tmp, CACHE)
    except OSError:
        pass


def _rms_db(src, t0, dur):
    """Loudness of this stretch. The threshold is set relative to it."""
    r = subprocess.run(
        [FFMPEG, "-ss", f"{t0:.2f}", "-t", f"{dur:.2f}", "-i", src,
         "-af", "astats=metadata=1:reset=0", "-f", "null", "-"],
        capture_output=True, text=True)
    m = re.findall(r"RMS level dB: ([-\d.]+)", r.stderr)
    return float(m[-1]) if m else -20.0


def _detect(src, t0, dur, db, d):
    """Raw silencedetect at one threshold, in absolute source seconds."""
    r = subprocess.run(
        [FFMPEG, "-ss", f"{t0:.2f}", "-t", f"{dur:.2f}", "-i", src,
         "-af", f"silencedetect=noise={db:.1f}dB:d={d}", "-f", "null", "-"],
        capture_output=True, text=True)
    out, start = [], None
    for line in r.stderr.splitlines():
        m = re.search(r"silence_start: ([-\d.]+)", line)
        if m:
            start = t0 + float(m.group(1))
        n = re.search(r"silence_end: ([-\d.]+)", line)
        if n and start is not None:
            out.append((start, t0 + float(n.group(1))))
            start = None
    return out


def _block(src, b):
    """Pauses starting inside 60s block b, at two resolutions.

    A point's answer depends only on its block, so two callers asking about the
    same moment through different windows get identical numbers. That property is
    the whole point - it is what whisper could not give us.

    Two resolutions because a full stop does not always come with a real break.
    Measured 10 Sept: between 244s and 259s the man ends four sentences and never
    once pauses for a quarter-second. Asking only for clear breaks left fifteen
    seconds with nowhere to cut, and the clip shipped cut mid-word instead. The
    fine pass finds the smaller dip; the transcript decides if it is a full stop.
    """
    key = f"{os.path.basename(src)}#{b}"
    cache = _load()
    if key in cache and isinstance(cache[key], dict):
        return {k: [tuple(x) for x in v] for k, v in cache[key].items()}

    lo = b * GRID
    t0 = max(0.0, lo - PAD)
    dur = (lo + GRID + PAD) - t0
    rms = _rms_db(src, t0, dur)

    long_ = []
    db = min(CEIL, max(FLOOR, rms - BELOW_RMS[0]))
    for under in BELOW_RMS:
        db = min(CEIL, max(FLOOR, rms - under))
        long_ = _detect(src, t0, dur, db, MIN_SIL)
        if len(long_) >= (GRID / WANT):
            break
    fine = _detect(src, t0, dur, db, FINE_SIL)

    # Keep only pauses beginning in the block itself, so the pads never
    # double-count a pause that two neighbouring blocks both saw.
    out = {"long": [(s, e) for s, e in long_ if lo <= s < lo + GRID],
           "fine": [(s, e) for s, e in fine if lo <= s < lo + GRID]}
    cache[key] = {k: [list(x) for x in v] for k, v in out.items()}
    _save(cache)
    return out


def _span(src, t0, t1, kind):
    out = []
    for b in range(int(max(0.0, t0) // GRID), int(t1 // GRID) + 1):
        out += _block(src, b)[kind]
    return sorted(set(out))


def silences(src, t0, t1):
    """[(start, end)] clear breaks in speech, absolute source seconds."""
    return _span(src, t0, t1, "long")


def silences_fine(src, t0, t1):
    """[(start, end)] every dip, including the small ones at a full stop."""
    return _span(src, t0, t1, "fine")


TRANS = os.path.join(HOME, "transcripts")
_CUES = {}


def _cues(src):
    """[(start, end, text)] from the transcript beside this source."""
    name = os.path.splitext(os.path.basename(src))[0]
    if name in _CUES:
        return _CUES[name]
    path = os.path.join(TRANS, name + ".srt")
    out = []
    if os.path.exists(path):
        def _s(t):
            h, m, rest = t.split(":")
            return int(h) * 3600 + int(m) * 60 + float(rest.replace(",", "."))
        raw = open(path, encoding="utf-8", errors="replace").read()
        for a, b, txt in re.findall(
                r"(\d\d:\d\d:\d\d,\d\d\d) --> "
                r"(\d\d:\d\d:\d\d,\d\d\d)\n(.*?)(?=\n\n|\Z)", raw, re.S):
            out.append((_s(a), _s(b), " ".join(txt.split())))
    _CUES[name] = out
    return out


def full_stops(src):
    """Times where a sentence FINISHES, from the transcript's punctuation.

    Silence says where the audio dips. It cannot tell a breath from a full stop,
    and that difference is the whole complaint: a clip that ends on a breath ends
    mid-thought. So silence supplies the exact times and the transcript decides
    which of them is the end of something.

    Segment ends are stable in a way word times are not, and they are only ever
    used to CHOOSE between measured silences - never as the cut itself.
    """
    return [e for _s, e, t in _cues(src) if t.rstrip().endswith((".", "!", "?"))]


def sentence_starts(src):
    """Times a new sentence BEGINS - the cue after one that ended in a stop."""
    cues = _cues(src)
    out = [cues[0][0]] if cues else []
    for i in range(1, len(cues)):
        if cues[i - 1][2].rstrip().endswith((".", "!", "?")):
            out.append(cues[i][0])
    return out


def _beside(cands, marks, before):
    """Candidates sitting beside a sentence mark. Empty if none do.

    before=True  - the mark comes just BEFORE the candidate (a clip's end)
    before=False - the mark comes just AFTER  the candidate (a clip's start)
    """
    slack = 0.45                      # the same fraction is_clean_* allows
    if before:
        return [c for c in cands if any(-slack <= (c - m) <= NEAR for m in marks)]
    return [c for c in cands if any(-slack <= (m - c) <= NEAR for m in marks)]


def best_end(src, t_in, t_out, back=9.0, fwd=26.0):
    """Where this clip should really end. None if nothing better is in reach.

    Ends just AFTER the last word - at the start of a silence plus a small tail,
    not at the end of the silence, which would leave dead air.
    """
    lo, hi = t_out - back, t_out + fwd
    stops = full_stops(src)
    clear = [s for s, _e in silences(src, lo - 2, hi + 2) if lo <= s <= hi]
    pick = _beside(clear, stops, True)
    if not pick:
        fine = [s for s, _e in silences_fine(src, lo - 2, hi + 2) if lo <= s <= hi]
        pick = _beside(fine, stops, True)
    if not pick:
        pick = clear                      # last resort: a break, if not a stop
    if not pick:
        return None
    new = min(pick, key=lambda s: abs(s - t_out)) + TAIL
    if new <= t_in + 12.0:
        return None                       # would leave nothing worth posting
    return None if abs(new - t_out) < 0.10 else new


def best_start(src, t_in, t_out, back=9.0, fwd=6.0):
    """Where this clip should really start - just after a silence ENDS."""
    lo, hi = t_in - back, t_in + fwd
    starts = sentence_starts(src)
    clear = [e for _s, e in silences(src, lo - 2, hi + 2) if lo <= e <= hi]
    pick = _beside(clear, starts, False)
    if not pick:
        fine = [e for _s, e in silences_fine(src, lo - 2, hi + 2) if lo <= e <= hi]
        pick = _beside(fine, starts, False)
    if not pick:
        pick = clear
    if not pick:
        return None
    new = max(0.0, min(pick, key=lambda e: abs(e - t_in)) - LEAD)
    if t_out - new < 12.0:
        return None
    return None if abs(new - t_in) < 0.10 else new


def is_clean_end(src, t_out, tol=0.45):
    """Does this end land on a dip that finishes a sentence?"""
    if not any(s - tol <= t_out <= e + tol
               for s, e in silences_fine(src, max(0.0, t_out - 4), t_out + 4)):
        return False
    stops = full_stops(src)
    # SLACK ON BOTH SIDES. 11 Sept 2026 this read `0 <= t_out - m`, so a cut
    # landing 0.06s BEFORE a transcript full stop was called mid-sentence -
    # and the clip in question ended on "...or a cart bench." Perfect.
    # Transcript cue times are quantised to the second; the waveform is not, so
    # the exact cut sits either side of the stop by a fraction. A one-sided
    # window turned that fraction into a failure and reported 43 good clips as
    # broken. Acting on that would have made every one of them worse.
    return not stops or any(-tol <= (t_out - m) <= NEAR + tol for m in stops)


def is_clean_start(src, t_in, tol=0.45):
    """Does this start land on a dip that a sentence begins after?"""
    if not any(s - tol <= t_in <= e + tol
               for s, e in silences_fine(src, max(0.0, t_in - 4), t_in + 4)):
        return False
    starts = sentence_starts(src)
    return not starts or any(-tol <= (m - t_in) <= NEAR + tol for m in starts)
