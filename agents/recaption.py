#!/usr/bin/env python3
"""Caption updates for clips already in the queue (runs inside the `post` lock, watch.yml).

1. factory/recaption.json maps a manifest file -> its new caption. A caption is only
   replaced while it still starts with "Ad:" (the old format), so this never undoes
   a later edit.
2. Every queued clip gets ONE line naming the highlight link that fits it
   (agents/offers.py) - once; a caption that already has one is left alone.

Platforms that already posted are untouched; only posts still to go out change.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import offers as O  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP = os.path.join(ROOT, "factory", "recaption.json")
MAN = os.path.join(ROOT, "state", "manifest.json")


def main():
    man = json.load(open(MAN, encoding="utf-8"))
    new = json.load(open(MAP, encoding="utf-8")) if os.path.exists(MAP) else {}
    swapped = pointed = 0
    for c in man.get("clips", []):
        if c.get("done") or c.get("posting"):
            continue
        cap = new.get(c.get("file"))
        if cap and (c.get("caption") or "").lstrip().startswith("Ad:"):
            c["caption"] = cap
            swapped += 1
        if c.get("caption") and not O.has_line(c["caption"]) and not c.get("status"):
            c["caption"] = O.add(c["caption"], O.pick(c.get("file", ""), c["caption"]))
            pointed += 1
    if swapped or pointed:
        with open(MAN, "w", encoding="utf-8") as f:
            json.dump(man, f, indent=1, ensure_ascii=False)
    print(f"recaption: {swapped} caption(s) replaced, {pointed} highlight line(s) added")


if __name__ == "__main__":
    main()
