#!/usr/bin/env python3
"""AGENT 1 - the clipper.

Keeps the posting queue full. The factory already downloads Kevin's episodes
(HD, encrypted) and transcribes them; the one step that needed a human was
choosing WHICH moments become clips. This agent does that step:

  1. How many clips are queued? Target: TARGET_DAYS x POSTS_PER_DAY (7 x 5 = 35).
  2. Waits if a plan it wrote is still being built (no pile-up, no loop).
  3. Picks transcribed episodes that have no plan yet.
  4. Reads each transcript and asks Claude for 6-9 stand-alone clips
     (hook, caption, exact cut times) following agents/AGENT_RULES.md.
  5. Hands every clip to AGENT 2 (reviewer.py) - only approved clips survive.
  6. Writes factory/plans/<key>.json with ITS OWN brand folder per episode, so
     the scheduler can mix episodes and reach 5 posts a day (max 2 per folder).

The factory then renders, checks edges/captions/1080p, and queues the clips.

    python agents/clipper.py [--dry] [--max-episodes N]
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C      # noqa: E402
import reviewer as R    # noqa: E402

POSTS_PER_DAY = int(os.environ.get("POSTS_PER_DAY", "5"))
TARGET_DAYS = int(os.environ.get("TARGET_DAYS", "7"))
MAX_EPISODES = int(sys.argv[sys.argv.index("--max-episodes") + 1]) if "--max-episodes" in sys.argv \
    else int(os.environ.get("MAX_EPISODES_PER_RUN", "3"))
PENDING_GRACE_H = 30          # a plan not built after this long no longer blocks
CLIPS_PER_EPISODE = 7         # what we expect on average, for the deficit maths
DRY = "--dry" in sys.argv
# TEST MODE: plans are rendered and checked but never posted (CLAUDE.md step 5).
# Turned on for the first run so the owner can watch the clips before they go live.
TEST = os.environ.get("AGENT_TEST_PLANS", "0") == "1" or "--test" in sys.argv

SYSTEM = """You are the clip editor for The Success Club, a channel that shares Kevin
Trudeau's teaching (with his permission) as short vertical videos. You read a full
episode transcript and choose the moments that will perform as stand-alone Shorts/Reels.

Follow the rulebook exactly. Above all:
- the transcript is ONE SENTENCE PER LINE: "[start-end] sentence". A clip is a run
  of consecutive lines. "in" MUST be the start time of its first line and "out" MUST
  be the end time of its last line - copy them exactly, never invent times.
- each clip STANDS ALONE: the first line sets up the idea (never a line starting
  with And / But / So / Because / That / Which / It / This that depends on what came
  before), and the last line is the payoff (the punchline / the lesson). Never end
  on a setup, a list in progress, or a question that is answered later.
- 30 to 58 seconds each. Prefer methods, stories, step-by-step teaching, memorable lines.
- skip ads, product pitches, phone numbers, calls to buy, intros/outros, and anything
  whose main point is health/medical, or a promise of money to the viewer.
- hooks: max 6 words, max 2 lines, Title Case, start with How/Why/What/When/The/A/a
  number. No full stop. Never a riddle.
- captions: start with "Ad: ", 300-700 characters, 3-5 short paragraphs separated by
  blank lines, end with ONE question to the viewer, then optionally a final line with
  2-4 hashtags. No links, no @handles, no "comment X", no money amounts.

Reply with JSON only, no commentary:
{"topic": "ONE_WORD_TOPIC_IN_CAPS",
 "clips": [{"slug": "lowercaseletters", "in": 123.4, "out": 170.2,
            "hook": ["Line One", "Line Two"],
            "caption": "Ad: ...", "cta_kind": "offer" or "question"}]}
Give 6 to 9 clips. Alternate cta_kind: about one "offer" for every two "question"."""


def want_clips(man):
    return TARGET_DAYS * POSTS_PER_DAY - len(C.queued(man))


def pending_plans():
    done = C.done_plans()
    return [k for k in C.plan_files() if k not in done and C.plan_age_hours(k) < PENDING_GRACE_H]


def candidates(idx):
    planned = C.planned_sources()
    out = []
    for vid, e in idx.items():
        if e.get("status") != "stocked" or e.get("test") or not e.get("transcript"):
            continue
        if vid in planned:
            continue
        if e.get("height", 1080) < 1080:
            continue
        out.append((vid, e))
    # Best transcripts first (punctuation density decides how clean the edges are),
    # then the newest uploads.
    out.sort(key=lambda ve: (float(ve[1].get("stops_per_min") or 0) >= 8,
                             ve[1].get("uploaded", "")), reverse=True)
    return out


def brand_for(topic, taken):
    base = "KT_" + (re.sub(r"[^A-Z0-9]", "", (topic or "").upper())[:14] or "EP")
    name, n = base, 2
    while name in taken:
        name, n = f"{base}{n}", n + 1
    return name


def key_for(vid, topic):
    base = re.sub(r"[^a-z0-9]", "", (topic or "ep").lower())[:16] or "ep"
    key = f"{base}_{vid}"
    return key


def write_plan(vid, entry, taken_brands):
    text = C.sentences(C.transcript(vid, entry))
    if len(text) < 2000:
        C.log(f"  {vid}: transcript too short ({len(text)} chars) - skipped")
        return None
    user = (C.read("AGENT_RULES.md") +
            f"\n\n## Episode\nTitle: {entry.get('title', '')}\n"
            f"Duration: {float(entry.get('duration', 0)) / 60:.0f} min\n\n"
            f"## Transcript (one sentence per line: [start-end seconds] sentence)\n{text}")
    try:
        got = C.ask_json(SYSTEM, user, max_tokens=8000)
    except Exception as e:
        C.log(f"  {vid}: unreadable reply ({e}) - skipped")
        return None
    topic = got.get("topic", "")
    brand = brand_for(topic, taken_brands)
    clips = []
    for c in got.get("clips", []):
        try:
            clips.append({"slug": re.sub(r"[^a-z0-9]", "", str(c["slug"]).lower())[:24],
                          "in": round(float(c["in"]), 2), "out": round(float(c["out"]), 2),
                          "hook": [str(h).strip() for h in c["hook"]][:3],
                          "caption": str(c["caption"]).strip(),
                          "cta_kind": c.get("cta_kind") if c.get("cta_kind") in ("offer", "question") else "question"})
        except (KeyError, TypeError, ValueError):
            continue
    plan = {"source": f"{vid}.mp4", "brand": brand, "test": TEST, "clips": clips}
    # AGENT 2: nothing reaches the factory without passing the rules check.
    plan, report = R.review_plan(plan, transcript_text=text,
                                 use_model=not os.environ.get("AGENT_NO_REVIEW_MODEL"))
    return key_for(vid, topic), plan, report


def main():
    man = C.manifest()
    need = want_clips(man)
    q = len(C.queued(man))
    C.log(f"queue: {q} clip(s) waiting; target {TARGET_DAYS} days x {POSTS_PER_DAY}/day "
          f"= {TARGET_DAYS * POSTS_PER_DAY}; need {max(need, 0)}")
    if need <= 0:
        C.log("queue is full enough - nothing to do")
        return 0
    pend = pending_plans()
    if pend:
        C.log(f"waiting for the factory to build {pend} - not planning more yet")
        return 0
    idx = C.sources_index()
    cands = candidates(idx)
    C.log(f"{len(cands)} transcribed episode(s) without a plan")
    if not cands:
        C.log("NO EPISODES LEFT TO PLAN - the factory needs to stock more (rumble_stock)")
        return 0
    n_eps = min(MAX_EPISODES, max(1, -(-need // CLIPS_PER_EPISODE)), len(cands))
    taken = C.used_brands()
    written = 0
    for vid, entry in cands[:n_eps]:
        C.log(f"- {vid}: {entry.get('title', '')[:70]}")
        try:
            res = write_plan(vid, entry, taken)
        except Exception as e:
            C.log(f"  {vid}: failed ({type(e).__name__}: {str(e)[:160]})")
            continue
        if not res:
            continue
        key, plan, report = res
        C.log("  " + "\n  ".join(report))
        if len(plan["clips"]) < 2:
            C.log(f"  {vid}: only {len(plan['clips'])} clip(s) approved - not worth a folder, skipped")
            continue
        taken.add(plan["brand"])
        C.log(f"  -> {key}.json  brand {plan['brand']}  {len(plan['clips'])} clip(s) approved")
        if DRY:
            print(json.dumps(plan, indent=1, ensure_ascii=False))
            continue
        os.makedirs(C.PLANS, exist_ok=True)
        with open(os.path.join(C.PLANS, f"{key}.json"), "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=1, ensure_ascii=False)
        R.write_report(key, report, plan)
        written += 1
    C.log(f"wrote {written} plan(s)")
    # Tell the workflow whether to start the factory.
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"written={written}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
