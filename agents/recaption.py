#!/usr/bin/env python3
"""One-off caption swap for clips already in the queue.

factory/recaption.json maps a manifest file -> its new caption. A caption is only
replaced while it still starts with "Ad:" (the old format), so this can run every
time the watchdog runs without ever undoing a later edit. Platforms that already
posted are untouched; only the posts still to go out get the new caption.
Runs inside the `post` concurrency group (watch.yml), so the poster never reads
the manifest half-written.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP = os.path.join(ROOT, "factory", "recaption.json")
MAN = os.path.join(ROOT, "state", "manifest.json")


def main():
    if not os.path.exists(MAP):
        print("recaption: nothing to do")
        return
    new = json.load(open(MAP, encoding="utf-8"))
    man = json.load(open(MAN, encoding="utf-8"))
    n = 0
    for c in man.get("clips", []):
        cap = new.get(c.get("file"))
        if cap and (c.get("caption") or "").lstrip().startswith("Ad:"):
            c["caption"] = cap
            n += 1
    if n:
        with open(MAN, "w", encoding="utf-8") as f:
            json.dump(man, f, indent=1, ensure_ascii=False)
    print(f"recaption: {n} caption(s) replaced")


if __name__ == "__main__":
    main()
