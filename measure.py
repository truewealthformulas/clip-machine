#!/usr/bin/env python3
"""Sample how every published clip is doing. One pass, then exit.

WHY THIS FILE EXISTS. 15 Sept 2026. engine/metrics.py came across in the
migration and nothing ever called it, so the measurement loop stopped on 13
Sept and nobody noticed - there is no metrics.json in the repository at all.

That matters more than it sounds. the owner decides what to make from these
numbers: the question-CTA finding (157.7 average engagement against 19.1 for an
offer) and the format rebuild that took median YouTube views from 2 to 984 both
came out of this file. He is currently reasoning about a clip he says is past
170,000 views on Instagram, and the system cannot see it.

Runs from the same cron as the posting pass, but only when the last sample is
more than SAMPLE_EVERY old, so it costs one API round per platform every six
hours rather than one every twenty minutes.

    python3 measure.py          # sample if due
    python3 measure.py --force  # sample now
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "engine"))

STATE = os.path.join(HERE, "state", "manifest.json")
METRICS = os.path.join(HERE, "state", "metrics.json")
SAMPLE_EVERY = 6 * 3600


def due():
    if not os.path.exists(METRICS):
        return True
    try:
        hist = json.load(open(METRICS))
    except (OSError, ValueError):
        return True
    if not hist:
        return True
    last = hist[-1].get("at", "")
    try:
        t = time.mktime(time.strptime(last[:16], "%Y-%m-%dT%H:%M"))
    except ValueError:
        return True
    return (time.time() - t) > SAMPLE_EVERY


def main():
    os.environ.setdefault("KT_DATA", os.path.join(HERE, "state"))
    if not ("--force" in sys.argv or due()):
        print("measured recently - skipping")
        return 0
    import metrics                                            # noqa: E402
    clips = json.load(open(STATE)).get("clips", [])
    n = metrics.collect(clips, METRICS)
    print(f"sampled {n} clip(s)")
    # SAY WHEN A PLATFORM ANSWERED WITH NOTHING. A silent zero here is how a
    # dead token looks, and a dead token looks exactly like a quiet week.
    try:
        hist = json.load(open(METRICS))
        last = [r for r in hist if r.get("at") == hist[-1]["at"]]
        for plat in ("instagram", "youtube", "facebook"):
            got = sum(1 for r in last if r.get(plat))
            print(f"  {plat}: {got} of {len(last)}"
                  + ("   <-- NOTHING CAME BACK" if not got else ""))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
