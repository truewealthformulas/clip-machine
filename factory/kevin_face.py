#!/usr/bin/env python3
"""IS IT KEVIN ON SCREEN? Checked on every clip before it is queued.

19 Oct 2026. Six posted clips captioned "Kevin Trudeau says..." showed somebody
else the whole time: a podcast host (KT_MINDSET9, episode v71ktjy) and a younger
man in a black t-shirt (KT_SUCCESS, v76l9y0). Some episodes on Kevin's channel
are other people teaching his material, and the transcript cannot tell who is
talking. A caption naming Kevin over another man's face misleads the viewer, so
no clip reaches the queue unless Kevin is the face on screen.

How: 8 frames across the clip, the biggest face in each (YuNet, already in
factory/assets), turned into a face fingerprint (OpenCV SFace) and compared with
58 reference fingerprints of Kevin taken from 20 posted clips across 8+ sets
(factory/assets/kevin_faces.npy). Tested on 26 posted clips: Kevin scores
0.72-0.92, the two other men 0.15-0.21. The line is 0.40, and Kevin has to be
the face in at least 60% of the frames where a face is found.

Fails CLOSED: if the model cannot be loaded, nothing is queued, because the
damage of a wrong face is a public post and the damage of a skipped run is a day.

    python factory/kevin_face.py clip.mp4 [clip2.mp4 ...]
"""
import os
import subprocess
import sys
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
REF = os.path.join(ASSETS, "kevin_faces.npy")
YUNET = os.path.join(ASSETS, "yunet.onnx")
SFACE = os.path.expanduser("~/wcache/sface_2021dec.onnx")
SFACE_URL = ("https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
             "face_recognition_sface/face_recognition_sface_2021dec.onnx")
THRESHOLD = 0.40       # cosine similarity to the nearest Kevin reference
NEED = 0.60            # share of face frames that must be Kevin
FRAMES = 8

_models = None


def _load():
    global _models
    if _models is None:
        import cv2
        if not os.path.exists(SFACE) or os.path.getsize(SFACE) < 10_000_000:
            os.makedirs(os.path.dirname(SFACE), exist_ok=True)
            urllib.request.urlretrieve(SFACE_URL, SFACE)
        det = cv2.FaceDetectorYN.create(YUNET, "", (540, 960), 0.8)
        rec = cv2.FaceRecognizerSF.create(SFACE, "")
        _models = (cv2, det, rec, np.load(REF).astype(np.float32))
    return _models


def _duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _frame(path, t):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", path,
                          "-frames:v", "1", "-vf", "scale=540:960", "-f", "rawvideo",
                          "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
    if len(raw) != 540 * 960 * 3:
        return None
    return np.frombuffer(raw, np.uint8).reshape(960, 540, 3).copy()


def check(path):
    """(is_kevin, detail) for one rendered clip."""
    cv2, det, rec, ref = _load()
    dur = _duration(path)
    if dur <= 0:
        return False, "unreadable video"
    scores = []
    for i in range(FRAMES):
        img = _frame(path, dur * (i + 0.5) / FRAMES)
        if img is None:
            continue
        _, faces = det.detect(img)
        if faces is None:
            continue
        f = max(faces, key=lambda r: r[2] * r[3])
        if f[2] < 40:
            continue
        e = rec.feature(rec.alignCrop(img, f)).reshape(-1)
        e = e / (np.linalg.norm(e) or 1)
        scores.append(float((ref @ e).max()))
    if len(scores) < 3:
        return False, f"face found in only {len(scores)} of {FRAMES} frames"
    share = sum(s >= THRESHOLD for s in scores) / len(scores)
    detail = f"Kevin in {share:.0%} of face frames (median match {np.median(scores):.2f})"
    return share >= NEED, detail


if __name__ == "__main__":
    for p in sys.argv[1:]:
        ok, d = check(p)
        print(("KEVIN   " if ok else "NOT HIM ") + os.path.basename(p) + "  " + d)
