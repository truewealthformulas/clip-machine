#!/usr/bin/env python3
"""Transcribe the FIRST and LAST seconds of a FINISHED clip. The honest check.

WHY THIS IS A PERMANENT FILE. 15 Sept 2026 it lived in /tmp and was gone the
next morning. In one session it caught six defects that no log, exit code, file
size or edge verifier reported:

  - a clip opening on "People live below their means" with "Wealthy" clipped
  - a clip carrying the co-host's "Okay" from the previous line
  - two files corrupted by two renders writing at once, which every status
    check called fine

Every other check reads the TRANSCRIPT or the CUT POINTS and infers what the
viewer hears. This listens to what they actually hear. The transcript lies
about cut points; the rendered file cannot.

    python3 kt_verify_render.py POST_TODAY/KT_LIES/03_THE-DRYER-FUND_57s.mp4 [...]
"""
import os
import re
import subprocess
import sys

HOME = os.path.expanduser("~/ClipMachine")
FF = f"{HOME}/bin/ffmpeg"
W = f"{HOME}/whisper.cpp/build/bin/whisper-cli"
M = f"{HOME}/whisper.cpp/models/ggml-small.en.bin"
# Primed to punctuate - see project_transcript_punctuation. Without it the
# check hears words but not sentences, and cannot tell a finished line from a
# fragment.
P = ("Hello, everyone. Today, we are going to talk about money, health, and "
     "success. It is important, isn't it?")
TMP = f"/tmp/kt_verify_render.{os.getpid()}.wav"   # per process


def say(mp4, ss, dur):
    subprocess.run([FF, "-y", "-loglevel", "error", "-ss", str(ss), "-t", str(dur),
                    "-i", mp4, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                    TMP], capture_output=True)
    r = subprocess.run([W, "-m", M, "-f", TMP, "--prompt", P, "-nt"],
                       capture_output=True, text=True)
    return " ".join(r.stdout.split())


def length(mp4):
    d = subprocess.run([FF, "-hide_banner", "-i", mp4],
                       capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", d)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    for mp4 in sys.argv[1:]:
        L = length(mp4)
        print(f"\n=== {os.path.basename(mp4)}  ({L:.0f}s)")
        if L < 1:
            print("  UNREADABLE - the file is empty, truncated, or still being written")
            continue
        print(f"  FIRST 5s : {say(mp4, 0, 5)[:160]}")
        print(f"  LAST  8s : {say(mp4, max(0, L - 8), 8)[:160]}")


if __name__ == "__main__":
    main()
