#!/usr/bin/env python3
"""Put newly rendered clips into the machine: release asset + manifest entry.

WHY THIS EXISTS. 15 Sept 2026. `kt_push.py` uploads to KT Cloud on Railway,
which has been down since the machine moved to GitHub on 13 Sept. So for two
days there has been no route at all from the Mac that RENDERS clips to the
thing that POSTS them - you could cut and render all day and nothing could ever
reach an account. the owner's queue running dry was the visible end of that.

Two destinations, because the machine keeps them apart on purpose:

  the bytes    -> a GitHub Release asset, which has a public URL. Instagram's
                  API will not accept bytes; it fetches from a URL. A release
                  has no folders, so "KT_LIES/01_X.mp4" is uploaded as
                  "KT_LIES--01_X.mp4" - the same scheme run_once.py resolves.
  the record   -> state/manifest.json, committed. The caption comes from
                  kt_series.json, which is where captions are written and
                  reviewed.

NEVER TOUCHES A CLIP THAT IS ALREADY IN THE MANIFEST. Re-adding one would give
it a fresh slot and post it a second time on four platforms - the duplicate
failure this project has already paid for.

    python3 add_clips.py --dry              # what it would add
    python3 add_clips.py KT_LIES KT_DEBT    # add those folders
    python3 add_clips.py --all
    python3 add_clips.py --captions         # refresh captions, upload nothing
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~/ClipMachine")
POST = os.path.join(HOME, "POST_TODAY")
SERIES = os.path.join(HOME, "kt_series.json")
STATE = os.path.join(HERE, "state", "manifest.json")
GH = os.path.join(HOME, "bin", "gh")
REPO = "truewealthformulas/clip-machine"
TAG = "media"


def captions():
    """slug -> (caption, brand), from kt_series.json."""
    out = {}
    for spec in json.load(open(SERIES)).values():
        for c in spec.get("clips", []):
            if c.get("caption"):
                out[(spec["brand"], c["slug"])] = c["caption"]
    return out


def candidates(folders):
    man = json.load(open(STATE))
    known = {c["file"] for c in man["clips"]}
    caps = captions()
    found = []
    for brand in sorted(folders):
        bdir = os.path.join(POST, brand)
        if not os.path.isdir(bdir):
            continue
        for f in sorted(os.listdir(bdir)):
            if not f.endswith(".mp4") or "__yt" in f or "__st" in f:
                continue
            rel = f"{brand}/{f}"
            if rel in known:
                continue
            m = re.match(r"^\d+_(?:\d+_)?(.+?)_\d+s\.mp4$", f)
            slug = m.group(1) if m else None
            cap = caps.get((brand, slug))
            if not cap:
                print(f"  SKIP {rel}: no caption in kt_series.json for "
                      f"{brand}/{slug}")
                continue
            found.append((rel, os.path.join(bdir, f), cap))
    return man, found


def refresh_captions(dry=False):
    """Push edited captions to the machine without touching a single video.

    Replaces kt_caption_push.py, which sent them to Railway. Same reason it
    existed: a caption is text, and re-uploading a hundred megabytes of video to
    change a sentence is absurd. A published clip keeps the caption it went out
    with - caption_at_post is frozen at posting time and never edited, because
    the audit identifies a post by its text and a rewritten caption once made it
    re-queue everything.
    """
    man = json.load(open(STATE))
    caps = captions()
    changed = []
    for c in man["clips"]:
        # A PUBLISHED CLIP KEEPS THE CAPTION IT WENT OUT WITH. Two reasons, and
        # the second one nearly bit on the first run of this.
        #
        # 1. The audit identifies a post by its TEXT. Rewriting captions once
        #    made it decide every post was missing and re-queue the lot.
        # 2. kt_series.json still carries the "Comment RISE..." line baked into
        #    the body, while the live captions have it stripped - poster adds
        #    the right CTA per platform at posting time. Copying the series
        #    version over a live one injects a SECOND ask into the caption. The
        #    dry run flagged 13 clips in exactly this state, all published.
        if c.get("posted_at") or c.get("links") or c.get("caption_at_post"):
            continue
        brand = c["file"].split("/")[0]
        m = re.match(r"^\d+_(?:\d+_)?(.+?)_\d+s\.mp4$", c["file"].split("/")[-1])
        if not m:
            continue
        new = caps.get((brand, m.group(1)))
        if new and new != c.get("caption"):
            changed.append(c["file"])
            if not dry:
                c["caption"] = new
    if not changed:
        print("every caption already matches kt_series.json")
        return 0
    print(f"{len(changed)} caption(s) {'would change' if dry else 'updated'}:")
    for f in changed:
        print("   ", f)
    if not dry:
        json.dump(man, open(STATE, "w"), indent=1)
        print("commit and push state/manifest.json")
    return 0


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry" in sys.argv
    if "--captions" in sys.argv:
        return refresh_captions(dry)
    folders = args or ([d for d in os.listdir(POST)
                        if os.path.isdir(os.path.join(POST, d))
                        and not d.startswith("_")] if "--all" in sys.argv else [])
    if not folders:
        raise SystemExit(__doc__)

    man, found = candidates(folders)
    if not found:
        print("nothing new to add")
        return 0
    print(f"{len(found)} clip(s) to add:")
    for rel, path, _ in found:
        print(f"   {rel}  ({os.path.getsize(path) / 1e6:.0f} MB)")
    if dry:
        return 0

    for rel, path, cap in found:
        asset = rel.replace("/", "--")
        tmp = os.path.join("/tmp", asset)
        subprocess.run(["cp", path, tmp], check=True)
        r = subprocess.run([GH, "release", "upload", TAG, tmp, "--clobber",
                            "-R", REPO], capture_output=True, text=True)
        os.remove(tmp)
        if r.returncode:
            print(f"   UPLOAD FAILED {rel}: {r.stderr[-200:]}")
            continue
        # READ IT BACK. An upload that returns 0 and a URL that 404s is the
        # exact shape of failure this project keeps paying for, and here it
        # would mean a scheduled clip whose media cannot be fetched.
        url = f"https://github.com/{REPO}/releases/download/{TAG}/{asset}"
        chk = subprocess.run(["curl", "-sIL", "-o", "/dev/null",
                              "-w", "%{http_code}", url],
                             capture_output=True, text=True)
        if chk.stdout.strip() != "200":
            print(f"   UPLOADED BUT NOT FETCHABLE {rel}: HTTP {chk.stdout}")
            continue
        man["clips"].append({"file": rel, "caption": cap,
                             "bytes": os.path.getsize(path),
                             "done": False, "status": {}})
        print(f"   added {rel}")
    json.dump(man, open(STATE, "w"), indent=1)
    print(f"\nmanifest now holds {len(man['clips'])} clips")
    print("commit and push state/manifest.json to let the machine see them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
