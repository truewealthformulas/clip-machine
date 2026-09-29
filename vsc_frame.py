#!/usr/bin/env python3
"""Where is Kevin, second by second, and what crop keeps him in a 9:16 frame.

Project 15 / VSC. The brief is explicit that framing must be checked across the
WHOLE clip, not just the opening frame - and this source proves why: Kevin sits
right of centre, and the interview cuts between 2-4 camera angles that are
framed differently. One fixed crop cannot serve all of them.

Deliberately NOT a continuous tracker. The camera is locked off inside a shot,
so a crop that follows the face frame-by-frame would wobble on a still picture,
which reads as amateur. One crop per SHOT is invisible and correct.

Writes <video>.frame.json: [{"start","end","cx","fw"}], cx/fw as fractions.
"""
import cv2, json, os, subprocess, sys, numpy as np

FFMPEG = os.path.expanduser("~/ClipMachine/bin/ffmpeg")
MODEL  = os.path.expanduser("~/ClipMachine/bin/yunet.onnx")
SAMPLE_W = 640          # YuNet is happy well below this; 4K decode is the cost
FPS      = 1.0          # one probe per second


def duration(src):
    out = subprocess.run([FFMPEG, "-i", src], capture_output=True, text=True).stderr
    for line in out.splitlines():
        if "Duration:" in line:
            h, m, s = line.split("Duration:")[1].split(",")[0].strip().split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    raise SystemExit("cannot read duration")


def shot_cuts(src, threshold=6):
    """Times where the picture changes enough to be a different camera."""
    p = subprocess.run([FFMPEG, "-i", src, "-vf", f"scale=320:-2,scdet=threshold={threshold}",
                        "-f", "null", "-"], capture_output=True, text=True).stderr
    cuts = []
    for line in p.splitlines():
        if "lavfi.scd.time:" in line:
            try: cuts.append(float(line.split("lavfi.scd.time:")[1].strip().split()[0]))
            except (IndexError, ValueError): pass
    return sorted(set(cuts))


def face_track(src, dur):
    """cx/fw per sampled second. None where no face was found."""
    tmp = "/tmp/vsc_probe_%05d.jpg"
    subprocess.run([FFMPEG, "-i", src, "-vf", f"fps={FPS},scale={SAMPLE_W}:-2",
                    "-q:v", "4", "-y", tmp, "-loglevel", "error"], check=True)
    det = cv2.FaceDetectorYN_create(MODEL, "", (320, 320), 0.6, 0.3, 5000)
    track, i = [], 1
    while True:
        f = tmp % i
        if not os.path.exists(f): break
        img = cv2.imread(f); h, w = img.shape[:2]
        det.setInputSize((w, h))
        ok, faces = det.detect(img)
        if faces is None or len(faces) == 0:
            track.append(None)
        else:
            b = max(faces, key=lambda r: r[2] * r[3])       # biggest face = Kevin
            track.append((float((b[0] + b[2] / 2) / w), float(b[2] / w), float((b[1] + b[3] / 2) / h)))
        os.remove(f); i += 1
    return track


def smooth(track, k=3):
    """Median-filter the per-second track so one bad detection cannot split a shot."""
    out = []
    for i in range(len(track)):
        win = [t for t in track[max(0, i-k//2):i+k//2+1] if t is not None]
        out.append(None if not win or track[i] is None else
                   tuple(float(np.median([w[j] for w in win])) for j in range(3)))
    return out


def face_breaks(track, dcx=0.10, dfw=0.11):
    """Seconds where the framing jumps - a cut scdet did not score.

    6 Sept: scdet at threshold 6 reported ONE shot from 13.5s to 26.3s, and the
    source actually holds three setups in there - black-and-white close-ups, near
    black cave footage, then colour wides. The transitions are dissolves, which
    frame-difference scoring reads as gradual. But the FACE jumps, and the face
    is the only thing the crop cares about, so segment on that instead.
    """
    t = smooth(track)
    b = []
    for i in range(1, len(t)):
        if (t[i-1] is None) != (t[i] is None):
            b.append(float(i)); continue
        pre  = [x for x in t[max(0,i-3):i]   if x]
        post = [x for x in t[i:i+3]          if x]
        if not pre or not post:
            continue
        # a real cut changes the framing and STAYS changed; a blip does not
        if (abs(np.median([x[0] for x in pre]) - np.median([x[0] for x in post])) > dcx or
            abs(np.median([x[1] for x in pre]) - np.median([x[1] for x in post])) > dfw):
            b.append(float(i))
    return b


def segments(cuts, dur, track):
    # A REAL CAMERA CUT BEATS A ROUNDED ONE. 16 Sept 2026, measured on the YWIYC
    # story: the scene detector put the camera change at 28.03s; the face
    # tracker, which samples once a second, put a break at 27.0; the merge below
    # keeps whichever comes FIRST, so 27.0 won and 28.03 was thrown away. For a
    # full second the crop was aimed for the new camera while the old one was
    # still on screen - Kevin half out of frame. The next change was off by
    # 1.25s the same way, with a phantom one-second "shot" in between.
    #
    # This is the owner's recurring complaint about interview clips not following
    # their camera. Per-shot framing existed; its boundaries were a second late.
    #
    # A face-tracker break now only stands on its own when there is NO scene cut
    # near it - a slow pan or a lean, where the face moves without a hard cut.
    hard = [c for c in cuts if 0 < c < dur]
    soft = [t for t in face_breaks(track) if 0 < t < dur
            and not any(abs(t - c) <= 1.5 for c in hard)]
    bounds = sorted(set([0.0] + hard + soft + [dur]))
    merged = [bounds[0]]
    for t in bounds[1:]:
        if t - merged[-1] >= 1.2: merged.append(t)
    if merged[-1] < dur: merged[-1] = dur
    bounds = merged
    segs = []
    last_cx, last_fw, last_cy = 0.5, 0.25, 0.40
    for a, b in zip(bounds, bounds[1:]):
        if b - a < 0.4: continue
        vals = [track[i] for i in range(int(a), min(int(b) + 1, len(track)))
                if i < len(track) and track[i] is not None]
        if vals:
            cx = float(np.median([v[0] for v in vals]))
            fw = float(np.median([v[1] for v in vals]))
            cy = float(np.median([v[2] for v in vals]))
            last_cx, last_fw, last_cy = cx, fw, cy
        else:                                   # no face in this shot - hold the last known
            cx, fw, cy = last_cx, last_fw, last_cy
        segs.append({"start": round(a, 3), "end": round(b, 3),
                     "cx": round(cx, 4), "cy": round(cy, 4),
                     "fw": round(fw, 4), "faces": len(vals)})
    out = [segs[0]]
    for s2 in segs[1:]:
        p = out[-1]
        same = (abs(p["cx"]-s2["cx"]) < 0.06 and abs(p["fw"]-s2["fw"]) < 0.08)
        if same:                      # one real shot that detection split - put it back
            n1, n2 = p["end"]-p["start"], s2["end"]-s2["start"]
            for k in ("cx", "cy", "fw"):
                p[k] = round((p[k]*n1 + s2[k]*n2)/(n1+n2), 4)
            p["end"] = s2["end"]; p["faces"] += s2["faces"]
        else:
            out.append(s2)
    return out


if __name__ == "__main__":
    src = sys.argv[1]
    dur = duration(src)
    print(f"duration {dur:.1f}s"); sys.stdout.flush()
    cuts = shot_cuts(src); print(f"{len(cuts)} shot cuts"); sys.stdout.flush()
    track = face_track(src, dur)
    found = sum(1 for t in track if t)
    print(f"probed {len(track)}s, face found in {found} ({100*found//max(len(track),1)}%)")
    segs = segments(cuts, dur, track)
    out = os.path.splitext(src)[0] + ".frame.json"
    json.dump({"src": os.path.basename(src), "duration": dur, "segments": segs,
               "track": [list(t) if t else None for t in track]},
              open(out, "w"), indent=1)
    print(f"{len(segs)} shots -> {out}")
