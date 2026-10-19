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
reference fingerprints of Kevin built from 20 posted clips across 8+ sets that
were checked by eye (REF_CLIPS below; built once per run from the media
release, so the list is readable and easy to extend). Tested on 26 posted clips: Kevin scores
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
REF = os.path.expanduser("~/wcache/kevin_faces_v1.npy")
REPO = os.environ.get("GITHUB_REPOSITORY", "truewealthformulas/clip-machine")
# Posted clips that ARE Kevin, checked frame by frame on 19 Oct 2026.
REF_CLIPS = [
    "KT_CREDIT/01_strongcreditfile_47s.mp4",
    "KT_CREDIT/02_belowmeans_33s.mp4",
    "KT_CREDIT/02_chargevscredit_53s.mp4",
    "KT_CREDIT/02_zerobalances_54s.mp4",
    "KT_MINDSET4/02_choosefeel_61s.mp4",
    "KT_MINDSET5/01_caddyrich_52s.mp4",
    "KT_MINDSET5/01_workforself_43s.mp4",
    "KT_MINDSET5/02_houndpain_46s.mp4",
    "KT_WEALTH/01_concernword_49s.mp4",
    "KT_WORDS/01_twowordsiam_56s.mp4",
    "KT_MANIFESTING/01_failurehabits_39s.mp4",
    "KT_MANIFESTING/02_invisiblehill_48s.mp4",
    "KT_MINDSET6/01_choosehappy_44s.mp4",
    "KT_MINDSET6/01_thepause_51s.mp4",
    "KT_MINDSET6/02_controlmind_51s.mp4",
    "KT_PRAYER/01_fearprayer_38s.mp4",
    "KT_MINDSET7/01_createreality_44s.mp4",
    "KT_RELATIONSHIPS/91_yourcircle_30s.mp4",
    "KT_MINDSET/91_fivesecondmiracle_36s.mp4",
    "KT_MINDSET8/02_threerules_45s.mp4",
]
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
        if not os.path.exists(REF):
            _build_ref(det, rec)
        _models = (cv2, det, rec, np.load(REF).astype(np.float32))
    return _models


def _embed(det, rec, img):
    """Unit fingerprint of the biggest face in a 540x960 frame, or None."""
    _, faces = det.detect(img)
    if faces is None:
        return None
    f = max(faces, key=lambda r: r[2] * r[3])
    if f[2] < 40:
        return None
    e = rec.feature(rec.alignCrop(img, f)).reshape(-1)
    return e / (np.linalg.norm(e) or 1)


def _build_ref(det, rec):
    import tempfile
    tmp = tempfile.mkdtemp()
    keep = []
    for name in REF_CLIPS:
        asset = name.replace("/", "--")
        path = os.path.join(tmp, asset)
        if subprocess.run(["gh", "release", "download", "media", "-R", REPO, "-p", asset,
                           "-O", path, "--clobber"], capture_output=True).returncode:
            continue
        dur = _duration(path)
        for i in range(6):
            img = _frame(path, dur * (i + 0.5) / 6) if dur else None
            e = None if img is None else _embed(det, rec, img)
            if e is not None and (not keep or max(float(k @ e) for k in keep) < 0.85):
                keep.append(e)
        os.remove(path)
    if len(keep) < 10:
        raise RuntimeError(f"only {len(keep)} Kevin reference faces could be built")
    os.makedirs(os.path.dirname(REF), exist_ok=True)
    np.save(REF, np.vstack(keep).astype(np.float32))
    print(f"kevin_face: {len(keep)} reference faces from {len(REF_CLIPS)} clips", flush=True)


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
        e = _embed(det, rec, img)
        if e is None:
            continue
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
