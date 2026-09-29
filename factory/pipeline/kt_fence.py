#!/usr/bin/env python3
"""No source video is ever cut for two different people. Enforced, not assumed.

WHY, 5 Sept 2026. the owner: "please do not mix my videos i give you to brand-2 owners, Do
not mix them... we are seperate when it comes to our accs."

Nothing was mixed when he said it - checked, zero shared sources. But nothing
PREVENTED it either, and every serious failure in this system has had that
shape: a rule that lived in someone's head, held for weeks, and then quietly
broke. The credential fence, the caption fence, the duplicate gate - all of them
started as "we would never do that".

WHAT THIS FORBIDS. One source video, cut by both a KT_/MINDSET_ series and an
AR_ series. They are different people, different accounts, different audiences.
The same footage on both is not efficiency, it is two accounts posting the same
thing - which is the one pattern the platforms punish hardest and the one the owner
has told me about most bluntly.

THE SAME VIDEO ARRIVING TWICE IS FINE. If they both send the same link, that is
not an error - his words: "if she or me happens to send you the same video, its
ok, just know it". It only becomes a problem when CLIPS are cut from it for
both. So this checks the series map, not the download folder.

    python3 kt_fence.py            # report
    python3 kt_fence.py --strict   # exit 1 if crossed (the renderer uses this)
"""
import collections
import json
import os
import sys

SERIES = os.path.join(os.path.expanduser("~/ClipMachine"), "kt_series.json")


def owner(brand):
    """Which person a brand belongs to."""
    return "BRAND2" if (brand or "").startswith("AR_") else "OWNER"


def crossed():
    """[(source, {brands})] for every source cut by more than one person."""
    d = json.load(open(SERIES))
    by = collections.defaultdict(set)
    for _k, s in d.items():
        by[s["source"]].add(s["brand"])
    out = []
    for src, brands in sorted(by.items()):
        if len({owner(b) for b in brands}) > 1:
            out.append((src, brands))
    return out


def main():
    bad = crossed()
    d = json.load(open(SERIES))
    by = collections.defaultdict(set)
    for _k, s in d.items():
        by[s["source"]].add(s["brand"])
    for src, brands in sorted(by.items()):
        who = sorted({owner(b) for b in brands})
        print(f"  [{'/'.join(who):5}] {src[:54]:56} {sorted(brands)}")
    if not bad:
        print(f"\n{len(by)} source(s), none cut for both people. Fence intact.")
        return
    print(f"\n*** {len(bad)} SOURCE(S) CUT FOR BOTH PEOPLE ***")
    for src, brands in bad:
        print(f"    {src}")
        print(f"      {sorted(brands)}")
    print("\nA source belongs to ONE person. Move the clips, or use different")
    print("footage - the same video on both accounts is two accounts posting")
    print("the same thing.")
    if "--strict" in sys.argv:
        sys.exit(1)


if __name__ == "__main__":
    main()
