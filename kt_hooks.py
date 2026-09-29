#!/usr/bin/env python3
"""The hook rule, enforced in code so it cannot quietly rot.

WHY THIS IS A LINT AND NOT A STYLE NOTE. 5 Sept 2026 all 75 hooks were rewritten
from riddles to plain benefit statements, because the owner sent a reel with one view
and said: "the hook is weak, it should be straight like HOW TO
INCREASE YOUR CREDIT SCORE."

A one-time rewrite decays. The next batch of clips gets hooks written from
memory, one of them is clever, then three are, and in a month we are back to
"Some seeds only open in a forest fire" with nobody able to say when it slipped.
A rule that lives only in a conversation is not a rule. This one fails the
render.

WHAT IT ENFORCES, and each line of it was paid for:

  DIRECT OPENING   Must begin with a promise word - How / Why / What / When /
                   The / N things - or lead with a number. These are the shapes
                   that tell a stranger what they GET before they decide to
                   scroll. A hook that opens on a pronoun or a scene ("He paid
                   it off in full...") is describing, not promising.

  NO RIDDLE VERBS  Banned openers that announce a mystery instead of naming a
                   benefit: "Some", "There is", "Nobody", "Everyone", "This is
                   what". They read as clever and convert as nothing.

  FITS THE PHONE   Measured in PIXELS against SAFE_W, not characters. Phones
                   crop ~10% off each side; a hook that fits the file and not
                   the screen is cut in half on the only device anyone watches
                   it on. See kt_render.SAFE_W.

  AT MOST 3 LINES  Four lines of Montserrat Black covers the speaker's face.

  NOT A SENTENCE   No full stop at the end. A hook is a headline.

    python3 kt_hooks.py            # check every hook
    python3 kt_hooks.py --strict   # exit 1 if any fail (used by the render)
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.expanduser("~/ClipMachine"))
import kt_render as R                                   # noqa: E402

SERIES = os.path.join(os.path.expanduser("~/ClipMachine"), "kt_series.json")

# Spelled-out counts are a direct promise too - "Two habits that grow the money
# part of your brain" tells a stranger exactly what they get. The first version
# of this lint only looked for DIGITS and failed that hook, which was correct
# English and correct strategy. Lint the rule, not the wording.
DIRECT = re.compile(r"^(how|why|what|when|where|which|the|a |an |"
                    r"one|two|three|four|five|six|seven|eight|nine|ten)\b", re.I)
NUMBER = re.compile(r"[\d$%]")
RIDDLE = re.compile(r"^(some|there('s| is| are)|nobody|everyone|no one|"
                    r"this is what|it (is|was)|he |she |they |i )", re.I)


# THE ANNOUNCER WORDS. 8 Sept 2026 - and this is the exact inversion of the
# rule above, on purpose, for one brand only.
#
# brand-2 owner, on her own account: "i want the hooks to be more stabbing. in terms of
# when people read it its like BAM. controversial and sharp." Measured, 23 of
# her 24 hooks opened with Why/How/What - 96%, a template. The words that make
# a hook a DIRECT PROMISE for the owner are the same words that make it a TOPIC
# LABEL for her: "Why bad luck is still your doing" announces that an
# explanation is coming. "A drunk hit your car. That was you." accuses.
#
# Both rules are correct for their own account and they cannot both be one
# rule, so the lint asks who owns the clip. the owner's brands keep the promise
# rule his one-view reel paid for; AR_* gets the stab rule.
ANNOUNCER = re.compile(r"^(how|why|what|when|where|which)\b", re.I)


def problems(hook, brand=""):
    """Every reason this hook is not shippable. Empty list means good."""
    out = []
    if not hook:
        return ["empty hook"]
    if len(hook) > 2:
        out.append(f"{len(hook)} lines (max 2)")
    first = hook[0].strip()
    stab = str(brand).upper().startswith("AR")
    if stab:
        if ANNOUNCER.match(first):
            out.append(f'announces a topic instead of making a claim: '
                       f'"{first}" - cut the first word')
        if RIDDLE.match(first) and not NUMBER.search(first) \
                and not re.match(r"^(he|she|they|i|we|it)\b", first, re.I):
            out.append(f'opens on a vague riddle: "{first}"')
        if "?" in " ".join(hook):
            out.append("a question is not a stab - make it a statement")
        # A terminal full stop is ALLOWED here. "That was you." lands because
        # of the stop, not in spite of it.
    else:
        if RIDDLE.match(first) and not NUMBER.search(first):
            out.append(f'opens on a riddle/scene: "{first}"')
        elif not DIRECT.match(first) and not NUMBER.search(first):
            out.append(f'not a direct promise: "{first}"')
        if hook[-1].strip().endswith("."):
            out.append("ends in a full stop - a hook is a headline, "
                       "not a sentence")
    lines = [l.upper() for l in hook]
    size = R.fit_size(lines, 92)
    widest = max(R.text_w(l, size) for l in lines)
    if widest > R.SAFE_W:
        out.append(f"{widest}px wide at {size}px - over the {R.SAFE_W}px "
                   f"safe zone, will be cut off on a phone")
    return out


def main():
    strict = "--strict" in sys.argv
    d = json.load(open(SERIES))
    bad = ok = 0
    want = None
    if "--series" in sys.argv:
        want = sys.argv[sys.argv.index("--series") + 1]
    for k, spec in sorted(d.items()):
        if want and k != want:
            continue
        # EVERY BRAND, not just the owner's. 8 Sept 2026: his 75 hooks were
        # rewritten from riddles to plain promises on 5 Sept and the lint was
        # scoped to KT_/MINDSET only - so brand-2's twenty-four went on shipping
        # as riddles ("LUCK IS A COMBINATION LOCK", "PICTURE NEVER GETTING IT")
        # for three days with nothing complaining. A rule that only covers the
        # brand you were looking at is not a rule.
        if spec.get("brand") is None:
            continue
        for c in spec.get("clips", []):
            # A published clip's hook is history. 11 Sept 2026 the line limit
            # went from three to two and 62 clips that are already live on four
            # platforms started failing a rule they cannot be brought into -
            # which would have blocked every render behind them.
            if c.get("locked"):
                continue
            errs = problems(c.get("hook") or [], spec.get("brand"))
            if errs:
                bad += 1
                print(f"{spec['brand']}/{c['slug']}")
                print(f"   {' / '.join(c.get('hook') or [])}")
                for e in errs:
                    print(f"   FAIL: {e}")
            else:
                ok += 1
    print(f"\n{ok} hook(s) pass, {bad} fail.")
    if bad and strict:
        print("Refusing to render. Fix the hooks above - see the rule in this "
              "file's docstring.")
        sys.exit(1)



MAX_WORDS = 6
_problems_base = problems


def problems(hook, brand=""):
    """Every brand: a hook is at most MAX_WORDS words.

    16 Sept 2026, the owner: "the hooks are too long... a average viewer cannot keep
    up and read long and fast, it must be short hook fewer phrases." The best
    hook this account ever had - 180,796 views - was 6 words: "How rich people /
    actually buy houses". The flagship's "The secret formula he used / to
    manifest $100K a week" was 9.
    """
    errs = list(_problems_base(hook, brand))
    n = sum(len(l.split()) for l in (hook or []) if l.strip())
    if n > MAX_WORDS:
        errs.append(f"{n} words - max {MAX_WORDS}, it cannot be read before it fades")
    return errs


if __name__ == "__main__":
    main()
