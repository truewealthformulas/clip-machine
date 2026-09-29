#!/usr/bin/env python3
"""Where the IDEA finishes - not where the audio dips.

WHY THIS EXISTS. 14 Sept 2026. the owner, for the fifth or sixth time: "when you cut
your clips you still are ending them not quite yet there." Every previous fix
measured ACOUSTICS - an adaptive silence threshold, a fine pass, transcript
punctuation choosing which pause is a full stop. All of it works. kt_verify_edges
still reports 30 of 93 clips ending mid-thought, and the ones it passes are often
worse, because a grammatically perfect sentence can still be a SETUP.

Two real endings from his two best videos, both of which the acoustic checks
called clean:

    "...Renee Rifkin had the largest yacht in Sydney Harbor, had a helicopter
     on it. It's really cool. He was my business partner."
        -> a yacht story that never happens. The payoff, 72 seconds later, is
           Kiyosaki saying a home is not an asset, it is a liability.

    "...you want five, no more than this, five pieces of credit on your credit
     report."
        -> he names a number and stops. What the five ARE is the next sentence.

That is the whole complaint, stated exactly: "i felt so fustrated when it
finished because it didnt tought me anything."

THE RULE, SET BY OWNER ON 14 SEPT 2026 (he was asked, in these words):

  1. ALWAYS RUN ON TO THE PAYOFF. If the idea finishes later, the clip goes
     there. He chose this over "only if it is short" and over "re-cut instead".
  2. NO LENGTH CEILING. "Value wins." He chose this over a 3-minute and a
     2-minute cap. A clip is as long as the idea it finishes.
  3. THE LAST LINE IS THE PUNCHLINE - the line the whole passage was built to
     deliver, not the line that sets it up.

HOW IT DECIDES, AND WHY IT IS NOT A WHITELIST. The opening gate taught this
lesson the hard way: a list of GOOD words cannot measure quality - it failed
"Every billionaire's home has one thing in common". So this does not look for
good endings. It looks for DEPENDENCE: an ending is wrong when the sentence
needs the NEXT one to mean anything. That is a property you can actually see in
the text, and it is the property that was broken every single time.

    python3 kt_payoff.py --series debt_trap          # what it would change
    python3 kt_payoff.py --series debt_trap --fix    # write it to kt_series.json
    python3 kt_payoff.py --all                       # every series, report only
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.expanduser("~/ClipMachine"))
import kt_cuts                                              # noqa: E402

HOME = os.path.expanduser("~/ClipMachine")
SERIES = os.path.join(HOME, "kt_series.json")
SRC_DIR = os.path.join(HOME, "Content/1_RAW/KT_SOURCE")

# How far past the current end to look for an idea that finishes. 150s is not a
# ceiling on the CLIP - rule 2 says there is none - it is a ceiling on the
# SEARCH, so a clip whose payoff never arrives does not swallow the rest of the
# video. The furthest real payoff measured across his two priority videos was
# 72 seconds out.
LOOK = 150.0
TAIL = 0.35              # air after the last word, so it does not clip
# How long Kevin has to actually stop for a sentence end to count as the end of
# an IDEA. Measured, not guessed: see the numbers printed by --pauses.
PAUSE_MIN = 0.45

# A sentence that ENDS on one of these is not finished, whatever the punctuation
# says. Whisper puts a full stop wherever Kevin breathes, so "It's outside of."
# and "It was just." both arrive looking like complete sentences.
DANGLING = {
    "a", "an", "the", "of", "to", "in", "on", "at", "for", "with", "from",
    "by", "into", "onto", "about", "and", "or", "but", "so", "because",
    "that", "which", "who", "if", "when", "while", "than", "as", "is",
    "are", "was", "were", "be", "been", "am", "my", "your", "his", "her",
    "its", "our", "their", "this", "these", "those", "just", "very", "not",
    "no", "all", "some", "any", "more", "most", "very", "really", "got",
    "get", "had", "has", "have", "do", "does", "did", "will", "would",
    "can", "could", "should", "may", "might", "must", "like", "up", "out",
}

# The NEXT sentence opening with one of these means the thought is still
# running: it is grammatically bound to the sentence before it. Deliberately a
# tight list - a loose one ("and", "but", "now") would reject half of Kevin's
# real endings and run every clip to the end of the video.
COMPLETER = re.compile(
    r"^\W*(so\s|because\b|which\b|meaning\b|ideally\b|unfortunately\b|"
    r"in\s+other\s+words\b|that'?s\s+(why|how|what|when)\b|"
    # ENUMERATION. "Ideally you have a mortgage and a car payment." reads as a
    # finished sentence and is not a finished ANSWER - the next line is "Then
    # you have three revolving lines of credit", and the viewer asked for five.
    # A list that has not reached its last item is the commonest way a clip
    # ends on a number and teaches nothing.
    r"then\s+you\b|first\b|second(ly)?\b|third(ly)?\b|number\s+(one|two|three)\b|"
    r"after\s+that\b|next\s*,|also\s*,|and\s+the\s+(third|second|last)\b|"
    r"here'?s\s+(what|how|why|the)\b|and\s+then\s+you\b|but\s+when\s+you\b|"
    r"the\s+(reason|point|problem)\s+(is|why)\b)", re.I)

# An ending that INTRODUCES somebody instead of claiming something. This is the
# yacht ending exactly: "He was my business partner." Grammatical, complete,
# and the entire reason the sentence exists is that the next one uses him.
INTRO = re.compile(
    r"^\W*(he|she|they|it|his|her|their|this|that|there)\b[^.!?]*\b"
    r"(was|is|were|are|had|have|has)\b", re.I)

# A sentence carrying one of these is making a CLAIM, so it can stand on its own
# even if the next sentence opens with a completer. This is the brake that stops
# the search running forever - it is not a quality test, it is an independence
# test: a number, a denial, a rule, or a quoted line does not need what follows.
STANDS = re.compile(
    r"(\b\d|\$|percent\b|never\b|nobody\b|nothing\b|no\s+one\b|"
    r"\bis\s+a\s+(lie|scam|racket|myth|liability|trap)\b|"
    r"\bnot\s+an?\s+\w+|\bliability\b|\bslave\b|\bcriminal\b|"
    r"^\W*(you|don'?t|do|never|stop|start|buy|pay|get|go)\b[^.!?]*!|"
    r"[\"“”])", re.I)


def sentences(src, t0=None, t1=None):
    """[(start, end, text)] - real sentences, at WORD resolution.

    NOT cue resolution, and this mattered enormously. A subtitle cue is a unit
    of DISPLAY: whisper packs two or three sentences into one and only the last
    of them lands on the cue's end time. On the re-transcribed mortgage video
    the text carries 368 full stops and just 34 of them sit at a cue boundary,
    so reading sentence ends off cues threw away nine in ten of the places a
    clip could legitimately finish - and then reported the clip as ending
    mid-sentence because the only boundary in reach was a minute away.

    kt_words gives the start and end of every individual word, so a sentence
    ends exactly where its last word does. The window keeps that affordable: a
    clip plus the stretch we are willing to run on into, not five hours of
    interview.
    """
    import kt_words
    if t0 is None:
        cues = kt_cuts._cues(src)
        t0, t1 = (cues[0][0], cues[-1][1]) if cues else (0.0, 0.0)
    # THE WINDOW IS SNAPPED TO A GRID, AND THAT IS NOT AN OPTIMISATION.
    #
    # whisper segments what it is given, so transcribing 100-200 and 110-210
    # returns sentences that break in slightly different places. Asking "does
    # this cut land mid-sentence?" from two different windows could give two
    # different answers for the same cut - which is a check that cannot be
    # trusted, and I nearly shipped decisions taken from one.
    #
    # Quantising both edges to a fixed grid means any question about a stretch
    # of video is answered from the SAME transcription every time. It also makes
    # the cache do real work: a whole series shares a handful of windows instead
    # of one per clip.
    GRID = 60.0
    t0 = max(0.0, (int(t0 // GRID) - 1) * GRID)
    t1 = (int(t1 // GRID) + 2) * GRID
    key = f"PAYOFF/{os.path.basename(src)}"
    # SENTENCES NEED PUNCTUATION AND EXACT TIMES - words_punct gives both. The
    # prompted pass alone compresses timestamps (16 Sept 2026); that is why cut
    # points taken from it were up to 0.6s off and had to be found by ear.
    ws = kt_words.words_punct(src, t0, t1, key)
    out, buf, a = [], [], None
    for rs, re_, w in ws:
        w = (w or "").strip()
        if not w:
            continue
        if a is None:
            a = t0 + rs
        buf.append(w)
        if w.rstrip().endswith((".", "!", "?")):
            out.append((a, t0 + re_, " ".join(buf)))
            buf, a = [], None
    if buf:
        out.append((a, t0 + ws[-1][1], " ".join(buf)))
    return out


def depends(text, nxt):
    """Why this sentence cannot be an ending. Empty tuple means it can.

    Returns the reasons rather than a bool so the report can say WHICH rule
    rejected a clip - a gate nobody can interrogate is a gate people override.
    """
    why = []
    t = (text or "").strip()
    if not t:
        return ("empty",)
    if not t.endswith((".", "!", "?")):
        why.append("fragment")
    last = re.sub(r"[^a-z']", "", t.lower().split()[-1]) if t.split() else ""
    if last in DANGLING:
        why.append(f"ends on '{last}'")
    # A QUOTE THAT NEVER CLOSES. whisper punctuates inside speech - it wrote
    # 'He says, "I know.' as a finished sentence, and the rest of the line ("I'm
    # terrible, but I just love doing it") is the punchline the whole story was
    # built for. An odd number of quote marks means the viewer is left holding
    # an open bracket.
    if (t.count('"') + t.count("\u201c") + t.count("\u201d")) % 2:
        why.append("ends inside a quote")
    stands = bool(STANDS.search(t))
    if INTRO.match(t) and not stands:
        why.append("introduces, does not claim")
    if nxt and COMPLETER.match(nxt) and not stands:
        why.append("next line completes it")
    return tuple(why)


# THE CHANNEL OUTRO. 15 Sept 2026, the owner, about the meditation clip that went
# out today: "the teaching finishes... but instead of stoping our clip there, it
# continues to their own propaganda or kt talking about subscribe if you like it
# give the video a like etc."
#
# He is right and the clip carried FORTY-FIVE SECONDS of it. The teaching ends
# at 3035.5 on "I absolutely will see you all at the top" - Kevin's own sign-off,
# a perfect ending - and the cut ran to 3080.8, through "if you love this
# episode", "hit that subscribe button" and a trailer for the next show.
#
# ad_zones only knew about the TESTIMONIAL advert, which is a reel of different
# voices. An outro is Kevin alone, so nothing caught it. These phrases are
# formulaic in a way the product mentions are not - "subscribe button" never
# appears inside a teaching, whereas Kevin names his own book mid-lesson all the
# time.
OUTRO = re.compile(
    r"(hit that subscribe|subscribe button|smash that|like the video|"
    r"give (the|this) video a like|if you (love|liked|enjoyed) this (episode|video)|"
    r"link in the (description|bio)|check out my (other )?episode|"
    r"show your support|ring the bell|leave a comment below|"
    r"i('ll| will) see you (all )?at the top)", re.I)


def outro_start(src):
    """Where the teaching stops and the channel promo begins. None if never.

    Kevin's sign-off, "I will see you all at the top", is deliberately in the
    list. It is the last line of the teaching, so a clip may END on it - but
    nothing after it is teaching, and the promo always follows it.
    """
    try:
        import kt_ads
    except Exception:
        return None
    cs = kt_ads.cues(os.path.basename(src))
    if not cs:
        return None
    end = cs[-1][1]
    for st, e, t in cs:
        if not OUTRO.search(t):
            continue
        # Only in the last stretch of the video. Kevin says "leave a comment"
        # mid-episode sometimes; an outro is where the episode is ending.
        if end - st > 400:
            continue
        # If the match is his sign-off, the promo starts AFTER it, not at it.
        if re.search(r"i('ll| will) see you (all )?at the top", t, re.I):
            return e
        return st
    return None


def ad_zones(src):
    """Every moment the testimonial advert starts - not just the closing one.

    14 Sept 2026, found while building this. kt_ads.ad_start() only looks in the
    last 40-220 seconds of a video, because the advert it was written for is the
    one bolted to the end. This video has ANOTHER one at 928 seconds, in the
    middle, and KT_DEBT/02 already ends at 929.12 - it contains the advert's
    first second and was live on four platforms.

    A clip may not end inside one and may not run through one, wherever it sits.
    """
    try:
        import kt_ads
    except Exception:
        return []
    cs = kt_ads.cues(os.path.basename(src))
    out = []
    for i, (st, _e, t) in enumerate(cs):
        if not (kt_ads.FIRST_WORDS.search(t) or kt_ads.OPENER.search(t)):
            continue
        # A MENTION IS NOT AN ADVERT, and the first version of this got that
        # wrong. In the mortgage video Kevin says "in Your Wish Is Your Command,
        # that audio program and book" in the MIDDLE OF A LESSON - he is citing
        # his own method, not selling. Blocking there would have cut the clip
        # at the exact moment it starts teaching.
        #
        # What makes the real thing a real thing is that it is a REEL OF
        # DIFFERENT PEOPLE. whisper marks a change of speaker with a leading
        # dash, and the genuine advert at 928s is fourteen of them in a row.
        # Kevin talking about his own book is none.
        win = [c for c in cs[i:i + 22] if c[0] < st + 60]
        voices = sum(1 for _a, _b, x in win if x.lstrip().startswith("-"))
        if voices < 3:
            continue
        if not out or st - out[-1] > 90:          # one zone per advert, not per cue
            out.append(st)
    return out


def _cap(src, t_out):
    """The first thing a clip may not reach: an advert, or the channel outro."""
    z = [t for t in ad_zones(src) if t > t_out - 30]
    o = outro_start(src)
    if o is not None and o > t_out - 30:
        z.append(o)
    return min(z) if z else 1e9


def barriers(src):
    """Everything a clip must not cross, for auditing. [(time, what)]"""
    out = [(t, "testimonial advert") for t in ad_zones(src)]
    o = outro_start(src)
    if o is not None:
        out.append((o, "channel outro"))
    return sorted(out)


def candidates(src, t_in, t_out, look=LOOK, n=6):
    """Every place this clip COULD honestly end, nearest first.

    WHY THIS RETURNS A LIST AND NOT AN ANSWER. Four rounds of tuning on this
    file, and the pattern was always the same: a rule that fixed one clip broke
    another. Requiring a real pause after the last sentence rescued THE FIVE
    PERCENT SCAM ("...I have a car payment on purpose so I can have a good
    credit rating") and ruined THREE CARDS AT ZERO, which had already landed
    on "It's outside of your budget based on your income" and got dragged on to
    "I'm not a financial planner, I'm not a financial manager".

    That is not a threshold that needs more tuning. Whether a line is the one
    the passage was built to deliver is a question about MEANING, and no
    measurement of the waveform or the grammar answers it. The same lesson the
    opening gate taught: stop trying to score quality.

    So the machine does the part it can actually do - throw out every ending
    that is mechanically wrong, and rank what is left - and a person picks. The
    pick is then written into kt_series.json, where it is permanent.
    """
    # The window: a little before the cut, and as far past it as we are willing
    # to run on. Transcribing only this keeps a word-level pass cheap.
    cap = _cap(src, t_out)
    sents = sentences(src, max(0.0, t_out - 25.0), min(t_out + look + 15.0, cap + 5))
    if not sents:
        return []
    i0 = 0
    for i, (a, _e, _t) in enumerate(sents):
        if a <= t_out + 0.6:
            i0 = i
        else:
            break
    out = []
    for j in range(i0, len(sents)):
        a, e, t = sents[j]
        if e > t_out + look or e >= cap:
            break
        if e < t_out - 0.6:
            continue
        nx = sents[j + 1][2] if j + 1 < len(sents) else ""
        why = depends(t, nx)
        if why:
            continue
        sil = [(x, y) for x, y in kt_cuts.silences_fine(src, e - 2.5, e + 4.0)
               if x >= e - 1.2]
        if not sil:
            continue
        a0, b0 = min(sil, key=lambda p: abs(p[0] - e))
        new = a0 + TAIL
        if new >= cap or new <= t_in + 12:
            continue
        out.append({"out": round(new, 2), "grew": round(new - t_out, 1),
                    "pause": round(b0 - a0, 2), "text": t})
        if len(out) >= n:
            break
    return out


def cuts_speech(src, t, edge):
    """Does this cut land in the MIDDLE of a sentence? The rule-2 question.

    Deliberately narrower than verdict(). 15 Sept 2026 I wired rule 2 to
    verdict() and it went on failing seven clips I had just verified word for
    word - because verdict() also reports quality faults ("the next line
    completes it", "introduces, does not claim") which are rule 19, not rule 2.
    A gate that answers a different question than the rule it is named after is
    a gate that gets switched off.

    Starting in a SILENCE before a sentence is fine - that is a clean start with
    a beat of air. Only landing inside speech is a fault.
    """
    for a, b, _t in sentences(src, max(0.0, t - 25), t + 25):
        if edge == "end" and a + 0.25 < t < b - 0.6:
            return True
        if edge == "start" and a + 0.6 < t < b - 0.25:
            return True
    return False


def verdict(src, t_in, t_out):
    """Is the CURRENT ending mechanically wrong? ('' means no.)"""
    sents = sentences(src, max(0.0, t_out - 25.0), t_out + 25.0)
    if not sents:
        return ""
    for t, what in barriers(src):
        if t_in < t < t_out + 1.0:
            return f"runs into the {what} at {t:.0f}s"
    i0 = 0
    for i, (a, _e, _t) in enumerate(sents):
        # The sentence the cut SITS IN is the last one that began before it.
        # 17 Sept 2026: this used `a <= t_out + 0.6`, so when Kevin runs one
        # sentence straight into the next with no pause (whisper gives them
        # touching times), a cut at the exact end of a sentence was judged
        # against the NEXT one - 17 of 19 clean cuts rejected. A next sentence
        # that began 0.15s+ before the cut is still caught: the cut is inside it.
        if a < t_out - 0.15:
            i0 = i
        else:
            break
    if sents[i0][1] - t_out > 0.6:
        return "cuts mid-sentence"
    nx = sents[i0 + 1][2] if i0 + 1 < len(sents) else ""
    why = depends(sents[i0][2], nx)
    return ", ".join(why)


def payoff_end(src, t_in, t_out, look=LOOK):
    """The nearest honest ending, or None when the current one is already fine.

    Kept for callers that want one answer. Prefer candidates() and a human.
    """
    bad = verdict(src, t_in, t_out)
    if not bad:
        return None, "", ()
    c = candidates(src, t_in, t_out, look, n=1)
    if not c:
        return None, "", (bad,)
    return c[0]["out"], c[0]["text"], (bad,)


def run(keys, fix=False):
    d = json.load(open(SERIES))
    total = changed = stuck = 0
    for k in keys:
        spec = d[k]
        src = os.path.join(SRC_DIR, spec["source"])
        if not os.path.exists(src):
            print(f"  {k}: source missing")
            continue
        print(f"\n### {k}  ({spec['brand']})")
        for c in spec["clips"]:
            total += 1
            new, text, bad = payoff_end(src, float(c["in"]), float(c["out"]))
            if not bad:
                print(f"  ok    {c['slug'][:38]:40} ends: ...{text[-58:]}")
                continue
            if new is None:
                stuck += 1
                print(f"  STUCK {c['slug'][:38]:40} {', '.join(bad)}")
                print(f"        no finished idea within {LOOK:.0f}s")
                continue
            grew = new - float(c["out"])
            changed += 1
            print(f"  FIX   {c['slug'][:38]:40} +{grew:.0f}s  ({bad[0]})")
            print(f"        was: ...{(text or '')[:0]}")
            print(f"        now ends: ...{text[-70:]}")
            if fix:
                c["out"] = round(new, 2)
    if fix:
        json.dump(d, open(SERIES, "w"), indent=1)
        print(f"\nwrote kt_series.json")
    print(f"\n{total} clips: {total - changed - stuck} already finish an idea, "
          f"{changed} extended, {stuck} with no payoff in reach")
    return changed


def report(keys):
    """Print every honest ending for every clip, so a person can choose."""
    d = json.load(open(SERIES))
    for k in keys:
        spec = d[k]
        src = os.path.join(SRC_DIR, spec["source"])
        if not os.path.exists(src):
            continue
        print(f"\n{'='*78}\n### {k}  ({spec['brand']})")
        for c in spec["clips"]:
            ti, to = float(c["in"]), float(c["out"])
            bad = verdict(src, ti, to)
            print(f"\n  {c['slug']}   {to - ti:.0f}s"
                  + (f"   <-- {bad}" if bad else "   (ends clean)"))
            for n, o in enumerate(candidates(src, ti, to), 1):
                print(f"    [{n}] {o['out']:8.2f}  {to - ti + o['grew']:4.0f}s "
                      f"({o['grew']:+5.1f}s)  pause {o['pause']:.2f}s")
                print(f"        {o['text'][-150:]}")


def main():
    d = json.load(open(SERIES))
    keys = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--series" in sys.argv:
        keys = [sys.argv[sys.argv.index("--series") + 1]]
    if "--all" in sys.argv:
        keys = list(d)
    if not keys:
        raise SystemExit(__doc__)
    if "--candidates" in sys.argv:
        report(keys)
        return
    run(keys, fix="--fix" in sys.argv)


if __name__ == "__main__":
    main()
