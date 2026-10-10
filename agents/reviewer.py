#!/usr/bin/env python3
"""AGENT 2 - the rules checker.

Every clip the clipper proposes passes through here BEFORE it is rendered or
posted. Two layers:

  1. HARD CHECKS in code (cannot be talked around): hook length/shape, clip
     length, the "Ad:" disclosure, no links/handles/manual CTAs, hashtag count,
     banned claim words (income promises, health/medical, conspiracy bait,
     engagement bait, fake urgency).
  2. A REVIEW by Claude against agents/AGENT_RULES.md, which reads the actual
     words of the clip as well as the caption, so a clip whose MAIN POINT is a
     health claim is dropped even if its caption is clean. It may rewrite a
     hook/caption; the rewrite then goes through the hard checks again.

Anything still failing is dropped, never shipped. A report is written to
factory/reports/review_<plan>.md so the owner can see every decision.

    python agents/reviewer.py factory/plans/<key>.json [--no-model]   # review one plan in place
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

MAX_WORDS, MAX_LINES = 6, 2
MIN_SECS, MAX_SECS = 20.0, 59.0
CAP_MIN, CAP_MAX = 250, 1200
MAX_TAGS = 5

DIRECT = re.compile(r"^(how|why|what|when|where|which|the|a|an|one|two|three|four|"
                    r"five|six|seven|eight|nine|ten)\b", re.I)
NUMBER = re.compile(r"[\d$%]")
RIDDLE = re.compile(r"^(some|there('s| is| are)|nobody|everyone|no one|this is what|"
                    r"it (is|was)|he|she|they|i)\b", re.I)

BANNED = [
    # income / results promises
    (r"\bguarantee", "guarantee claim"),
    (r"\bget rich\b|\brich quick\b|\bfast money\b|\beasy money\b", "get-rich claim"),
    (r"\$\s?\d|\d\s?(k|m)\b|\b\d[\d,.]*\s*(dollars|million|thousand|grand)\b", "money figure (no amounts in our text)"),
    (r"\bdouble your (income|money)\b|\bpassive income\b", "income promise"),
    (r"\bfinancial freedom in\b|\bquit your job\b|\bretire (early|at)\b", "income promise"),
    (r"\byou (will|'ll) (become|be) (a )?(millionaire|rich|wealthy)\b", "income promise"),
    # health / medical
    (r"\bcure[sd]?\b|\bheal(s|ed|ing)?\b|\bdisease|\bcancer\b|\bdiabet|\btumou?r", "health claim"),
    (r"\bdepression\b|\banxiety\b|\bweight loss\b|\blose weight\b|\bdetox|\bnever get sick\b", "health claim"),
    (r"\bpharma|\bdoctors? (lie|won't|don't want)|\bmedication|\bprescription", "medical claim"),
    # conspiracy / fear bait
    (r"they don'?t want you to know|\bsecret societ|\bbrotherhood\b|\bthe elite\b|\billuminati", "conspiracy bait"),
    (r"\bbanned\b|\bcensored\b|\bthe government\b", "fear bait"),
    # urgency / engagement bait
    (r"\blast chance\b|\bonly today\b|\bbefore it'?s (deleted|gone|removed)\b|\bact now\b", "fake urgency"),
    (r"\blike if\b|\bshare (this )?(to|if)\b|\btag (\d|a|three|two|your)\b|\bfollow for (part|more)\b", "engagement bait"),
    # personal attributes (Meta)
    (r"\bare you (broke|poor|depressed|fat|overweight|in debt|lonely)\b", "personal-attribute targeting"),
]
MANUAL_CTA = re.compile(r"https?://|www\.|\.com\b|@\w|link in (my )?bio|\bcomment\s+[A-Z\"']|"
                        r"\bDM me\b|\bclick (the )?link\b", re.I)


def hook_problems(hook):
    out = []
    if not isinstance(hook, list) or not hook or not all(isinstance(h, str) and h.strip() for h in hook):
        return ["hook missing"]
    if len(hook) > MAX_LINES:
        out.append(f"hook has {len(hook)} lines (max {MAX_LINES})")
    words = sum(len(h.split()) for h in hook)
    if words > MAX_WORDS:
        out.append(f"hook has {words} words (max {MAX_WORDS})")
    first = hook[0].strip()
    if RIDDLE.match(first) and not NUMBER.search(first):
        out.append(f'hook opens on a riddle/pronoun: "{first}"')
    elif not DIRECT.match(first) and not NUMBER.search(first):
        out.append(f'hook is not a direct promise: "{first}"')
    if hook[-1].strip().endswith((".", "!")):
        out.append("hook ends with punctuation - a hook is a headline")
    for pat, why in BANNED:
        if re.search(pat, " ".join(hook), re.I):
            out.append(f"hook: {why}")
    return out


def caption_problems(cap, hook=None):
    out = []
    if not isinstance(cap, str) or not cap.strip():
        return ["caption missing"]
    if not cap.startswith("Ad: "):
        out.append('caption must start with "Ad: " (affiliate disclosure)')
    if not CAP_MIN <= len(cap) <= CAP_MAX:
        out.append(f"caption is {len(cap)} chars (want {CAP_MIN}-{CAP_MAX})")
    tags = re.findall(r"(?<!\w)#\w+", cap)
    if len(tags) > MAX_TAGS:
        out.append(f"{len(tags)} hashtags (max {MAX_TAGS})")
    if MANUAL_CTA.search(cap):
        out.append("caption has a link/handle/manual call to action - the machine adds the CTA")
    body = re.sub(r"(?<!\w)#\w+", "", cap)
    if "?" not in body:
        out.append("caption must end on a question to the viewer")
    first = cap[4:].split("\n")[0].strip()
    if not 20 <= len(first) <= 200:
        out.append("first line must be 20-200 chars (it becomes the YouTube title)")
    for pat, why in BANNED:
        if re.search(pat, cap, re.I):
            out.append(f"caption: {why}")
    if hook and " ".join(hook).lower() in cap.lower()[:120]:
        out.append("caption repeats the hook word for word")
    return out


def clip_problems(c, seen_slugs=()):
    out = []
    slug = c.get("slug", "")
    if not re.fullmatch(r"[a-z0-9]{3,24}", str(slug)):
        out.append(f'slug "{slug}" must be 3-24 lowercase letters/digits')
    elif slug in seen_slugs:
        out.append(f'slug "{slug}" used twice')
    try:
        a, b = float(c["in"]), float(c["out"])
        if not MIN_SECS <= b - a <= MAX_SECS:
            out.append(f"length {b - a:.1f}s (want {MIN_SECS:.0f}-{MAX_SECS:.0f}s)")
        if a < 0:
            out.append("negative start")
    except (KeyError, TypeError, ValueError):
        out.append("in/out times missing")
    out += hook_problems(c.get("hook"))
    out += caption_problems(c.get("caption"), c.get("hook"))
    return out


def excerpt(transcript_text, a, b):
    """The transcript lines inside one clip, so the reviewer judges the WORDS."""
    keep = []
    for line in (transcript_text or "").splitlines():
        m = re.match(r"\[(\d+\.?\d*)-(\d+\.?\d*)\]", line)
        if m and float(m[2]) > a - 0.5 and float(m[1]) < b + 0.5:
            keep.append(line)
    return "\n".join(keep)


SYSTEM = """You are the compliance and quality reviewer for a short-video channel
that posts Kevin Trudeau clips (with his permission) as an affiliate. You are strict:
an account ban or an FTC problem costs everything. Apply the rulebook exactly.
For each clip return one verdict:
  "ok"   - ships as is
  "fix"  - ships after your rewrite of hook and/or caption (keep the meaning, follow every rule)
  "drop" - must not ship (main point is a health/medical claim, an income promise,
           conspiracy content, an ad/sales segment, starts or ends mid-thought, or cannot be fixed)
Reply with JSON only:
{"clips":[{"slug":"...","verdict":"ok|fix|drop","reason":"short","hook":["..",".."],"caption":"..."}]}
Include hook and caption only for "fix"."""


def review_plan(plan, transcript_text="", use_model=True):
    """Returns (kept_plan, report_lines)."""
    report = []
    clips = plan.get("clips", [])
    # 1. model review
    verdicts = {}
    if use_model and clips:
        items = []
        for c in clips:
            items.append({"slug": c.get("slug"), "seconds": round(float(c["out"]) - float(c["in"]), 1),
                          "hook": c.get("hook"), "caption": c.get("caption"),
                          "spoken_words": excerpt(transcript_text, float(c["in"]), float(c["out"]))})
        user = (C.read("AGENT_RULES.md") + "\n\n## Clips to review\n" +
                json.dumps(items, ensure_ascii=False, indent=1))
        try:
            got = C.ask_json(SYSTEM, user, max_tokens=6000)
            verdicts = {v.get("slug"): v for v in got.get("clips", [])}
        except Exception as e:
            report.append(f"- model review unavailable ({type(e).__name__}); hard checks only, unclear clips dropped")
    # 2. apply verdicts + hard checks
    kept, seen = [], set()
    for c in clips:
        v = verdicts.get(c.get("slug"), {"verdict": "ok" if not use_model else "missing"})
        verdict = v.get("verdict", "missing")
        if use_model and verdict == "missing":
            report.append(f"- DROP `{c.get('slug')}`: reviewer gave no verdict")
            continue
        if verdict == "drop":
            report.append(f"- DROP `{c.get('slug')}`: {v.get('reason', '')}")
            continue
        if verdict == "fix":
            before = (c.get("hook"), c.get("caption"))
            if v.get("hook"):
                c["hook"] = v["hook"]
            if v.get("caption"):
                c["caption"] = v["caption"]
            report.append(f"- FIXED `{c.get('slug')}`: {v.get('reason', '')} "
                          f"(hook was {' / '.join(before[0] or [])!r})")
        probs = clip_problems(c, seen)
        if probs:
            report.append(f"- DROP `{c.get('slug')}`: " + "; ".join(probs))
            continue
        seen.add(c["slug"])
        kept.append(c)
        if verdict == "ok":
            report.append(f"- OK `{c['slug']}`: {' / '.join(c['hook'])}")
    plan = dict(plan, clips=kept)
    return plan, report


def write_report(key, report, plan):
    os.makedirs(C.REPORTS, exist_ok=True)
    with open(os.path.join(C.REPORTS, f"review_{key}.md"), "w", encoding="utf-8") as f:
        f.write(f"# Rules review: {key} ({plan.get('brand')}, source {plan.get('source')})\n\n")
        f.write(f"{len(plan.get('clips', []))} clip(s) approved.\n\n")
        f.write("\n".join(report) + "\n")


def main():
    path = sys.argv[1]
    key = os.path.basename(path)[:-5]
    plan = json.load(open(path))
    plan, report = review_plan(plan, use_model="--no-model" not in sys.argv)
    json.dump(plan, open(path, "w"), indent=1, ensure_ascii=False)
    write_report(key, report, plan)
    print("\n".join(report))


if __name__ == "__main__":
    main()
