#!/usr/bin/env python3
"""Tiny cover images for the captions board, baked into a JSON file.

WHY THEY ARE NOT FETCHED. 14 Sept 2026, the owner: "if you can add the thumbnails or
something visual so we know its the correct one by comparing it would be
awesome." He is matching a clip sitting in his TikTok inbox against a caption on
a web page, and a filename is a poor way to do that.

The board is built on a GitHub runner that has the state file and nothing else -
no videos, no thumbnails. So the pictures are made HERE, on the Mac that has the
clips, shrunk to about the size of a postage stamp, and committed as data URIs.
No upload, no token, no second service, and the board keeps working with the Mac
shut.

    python3 make_thumbs.py            # refresh docs/thumbs.json
"""
import base64
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
POST = os.path.expanduser("~/ClipMachine/POST_TODAY")
FFMPEG = os.path.expanduser("~/ClipMachine/bin/ffmpeg")
OUT = os.path.join(HERE, "docs", "thumbs.json")
STATE = os.path.join(HERE, "state", "manifest.json")
TMP = "/tmp/kt_thumb.jpg"
WIDE = 108              # wide enough to recognise, small enough to inline


def cover_second(mp4):
    """The frame the platforms show. Matches kt_render's own cover probe when
    it left one behind, so the board shows what TikTok shows."""
    side = mp4[:-4] + "__cover_ms.txt"
    if os.path.exists(side):
        try:
            return max(0.0, int(open(side).read().strip()) / 1000.0)
        except (OSError, ValueError):
            pass
    return 1.0


def shrink(mp4):
    at = cover_second(mp4)
    r = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{at:.2f}",
                        "-i", mp4, "-frames:v", "1",
                        "-vf", f"scale={WIDE}:-2", "-q:v", "7", TMP],
                       capture_output=True)
    if r.returncode or not os.path.exists(TMP):
        return None
    with open(TMP, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()


def main():
    want = [c["file"] for c in json.load(open(STATE)).get("clips", [])]
    old = {}
    if os.path.exists(OUT):
        try:
            old = json.load(open(OUT))
        except ValueError:
            pass
    out, made, missing = {}, 0, 0
    for rel in want:
        if rel in old:                       # already have it; a frame never changes
            out[rel] = old[rel]
            continue
        mp4 = os.path.join(POST, rel)
        if not os.path.exists(mp4):
            missing += 1
            continue
        d = shrink(mp4)
        if d:
            out[rel] = d
            made += 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"))
    kb = os.path.getsize(OUT) / 1024
    print(f"{len(out)} thumbnails ({made} new, {missing} clips not on this Mac) "
          f"- {kb:.0f} KB")


if __name__ == "__main__":
    main()
