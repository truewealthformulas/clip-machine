#!/usr/bin/env python3
"""Post the hook variants of ONE clip as Instagram Trial Reels.

WHY THIS FILE EXISTS. 14 Sept 2026, the owner: "what about the 7 clips per day trial
with different hooks?"

It was built on 3 Sept, and it works - Meta's `trial_params` really does create
a trial reel from the API, which I had wrongly told him was app-only until he
pushed back. What did not survive the move off Railway is the way to START it.
It lived behind an HTTP route, `/trial/<slug>`, on a server that is now down, so
since 13 Sept the experiment has had no trigger at all.

Here it is a workflow input instead: Actions -> post -> Run workflow -> trial
slug. Same code path, same safety rule, no server.

DANIEL'S DISCIPLINE, WHICH IS THE ENTIRE VALUE:
  - Seven variants of ONE video, on the SAME DAY.
  - ONLY the hook text differs. Same footage, same cut, same captions. Change
    two things and the result tells you nothing about either.
  - Trial reels are shown to NON-FOLLOWERS, so the account is not spammed and
    the measurement is clean.
  - The winner is graduated by hand, in the app. Which hook won is the thing
    the owner needs to see with his own eyes.

STOPS ON THE FIRST ONE THAT IS NOT A TRIAL. If trial_params silently stopped
working, the remaining variants would publish to his followers - seven
near-identical reels in a day. Losing the experiment costs a re-render; spamming
the account does not get undone.

    python3 trial.py <SLUG>
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "engine"))


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: trial.py <SLUG>")
    slug = sys.argv[1]

    os.environ.setdefault("KT_DATA", os.path.join(HERE, "state"))
    os.environ["KT_MEDIA_REMOTE"] = "1"
    os.makedirs(os.path.join(HERE, "state"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "media"), exist_ok=True)

    import main as engine                                      # noqa: E402
    import poster                                              # noqa: E402
    engine.MANIFEST = os.path.join(HERE, "state", "manifest.json")
    engine.MEDIA = os.path.join(HERE, "media")

    owner = os.environ["GH_REPO"]
    tag = os.environ.get("MEDIA_TAG", "media")

    def media_url(rel):
        return (f"https://github.com/{owner}/releases/download/{tag}/"
                + rel.replace("/", "--"))

    # The variants live in the release beside every other clip. The index is
    # committed by kt_variants.py at render time, because a release has no
    # folders to list and the runner has no copy of the Mac's disk.
    idx = os.path.join(HERE, "state", "variants.json")
    try:
        all_v = json.load(open(idx))
    except (OSError, ValueError):
        raise SystemExit(f"no {idx} - render with kt_variants.py --apply first")
    vids = all_v.get(slug)
    if not vids:
        raise SystemExit(f"no variants listed for {slug}; have: "
                         + ", ".join(sorted(all_v)) or "(none)")

    man = engine.load()
    src = next((c for c in man["clips"] if slug in c["file"]), None)
    if src is None:
        raise SystemExit(f"{slug} is not a clip in the manifest")
    caption = src.get("caption", "")

    if os.environ.get("DRY_RUN") == "1":
        print(f"DRY RUN - would post {len(vids)} trial reel(s) for {slug}:")
        for rel in vids:
            print("   ", rel, "->", media_url(rel))
        return 0

    import urllib.request
    posted = 0
    for rel in vids:
        path = os.path.join(engine.MEDIA, rel)
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            urllib.request.urlretrieve(media_url(rel), path)
        res = poster.instagram(path, caption, media_url(rel), src, trial=True)
        ok = isinstance(res, tuple)
        status = res[0] if ok else res
        print(f"  {rel}: {status}", flush=True)
        posted += 1
        # THE STOP. Never let a failed trial flag turn into seven real posts.
        if not ok or str(status).startswith("PUBLISHED BUT NOT A TRIAL"):
            print(f"STOPPED after {posted}: that one did not publish as a "
                  f"trial. The rest were NOT posted.")
            return 1
    print(f"{posted} trial reel(s) posted for {slug}. "
          f"Open Instagram and graduate the winner by hand.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
