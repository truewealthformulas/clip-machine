"""Re-cut queued clips from the original HD episode in the WIDE frame.

6 Nov 2026, the owner, with a screenshot of the full YouTube frame: "this is what
i am talking ... cut them again". The queued clips were cut as a full-height 9:16
slice of the 16:9 recording - tight on Kevin's body - and that slice has no room
left to zoom out into. So each one is rendered again from the episode with the
same in/out, hook and captions, at KT_ZOOM 0.3 (the whole 16:9 frame edge to
edge, blur above and below), then restyled (Kevin's best 3 s + hook + CTA).

    python factory/recut.py list            # matrix of queued clips -> $GITHUB_OUTPUT
    python factory/recut.py one <file>      # render one clip into /tmp/recut_out
    python factory/recut.py commit <dir>    # upload + reset style in the manifest
"""
import glob, json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAN = os.path.join(ROOT, "state", "manifest.json")
K = os.path.expanduser("~/ClipMachine")
REPO = os.environ.get("GITHUB_REPOSITORY", "truewealthformulas/clip-machine")
RECUT_V = 2   # 2: again, without the face-scale box
OUT = "/tmp/recut_out"


def slug_of(f):
    return re.match(r"\d+_(.+)_\d+s\.mp4$", f.split("/")[-1]).group(1)


def queued(man):
    return [c for c in man["clips"]
            if not c.get("done") and not c.get("posting") and not c.get("posted_at")
            and not any("posted" in str(v) for v in (c.get("status") or {}).values())
            and (c.get("recut_v") or 0) < RECUT_V]


def find(series, f):
    brand, slug = f.split("/")[0], slug_of(f)
    for key, spec in series.items():
        if spec["brand"] == brand:
            for c in spec["clips"]:
                if c["slug"] == slug:
                    return key, spec, c
    return None, None, None


def cmd_list():
    man = json.load(open(MAN))
    series = json.load(open(os.path.join(HERE, "kt_series.json")))
    files = [c["file"] for c in queued(man) if find(series, c["file"])[0]]
    print(f"{len(files)} clip(s) to re-cut: {files}")
    with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as fh:
        fh.write(f"matrix={json.dumps(files)}\ncount={len(files)}\n")


def cmd_one(f):
    os.environ["KT_OUT"] = OUT
    os.environ.setdefault("KT_ZOOM", "0.3")
    os.makedirs(OUT, exist_ok=True)
    sys.path.insert(0, HERE)
    sys.path.insert(0, K)
    from transcribe import fetch_source, crypt  # noqa: F401
    series = json.load(open(os.path.join(K, "kt_series.json")))
    key, spec, clip = find(series, f)
    if not key:
        raise SystemExit(f"{f}: not in kt_series.json")
    vid = spec["source"][:-4]
    fetch_source(vid)
    srt = os.path.join(K, "transcripts", f"{vid}.srt")
    if not os.path.exists(srt):
        subprocess.run(["gh", "release", "download", "sources", "-R", REPO, "-p", f"{vid}.srt.enc",
                        "-D", "/tmp", "--clobber"], check=True)
        subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-pass", "env:FACTORY_KEY",
                        "-in", f"/tmp/{vid}.srt.enc", "-out", srt], check=True)
    import kt_render
    # Same cut, same hook - only the framing changes. A reposted slug is locked
    # (its first version went out); this re-cut is the queued copy, so unlock it here.
    one = dict(clip, locked=False)
    sub = dict(spec, clips=[one])
    sub.pop("zoom", None)
    kt_render.run_series(key, sub, True, clip["slug"])
    hits = [p for p in glob.glob(os.path.join(OUT, f"*_{clip['slug']}_*s.mp4")) if "__" not in os.path.basename(p)]
    if not hits:
        raise SystemExit(f"{f}: render produced nothing")
    asset = f.replace("/", "--")
    shutil.move(hits[0], os.path.join(OUT, "RECUT__" + asset))
    for p in glob.glob(os.path.join(OUT, "*")):
        if not os.path.basename(p).startswith("RECUT__"):
            os.remove(p)
    print("re-cut", f)


def cmd_commit(d):
    man = json.load(open(MAN))
    by = {c["file"]: c for c in queued(man)}
    n = 0
    for p in sorted(glob.glob(os.path.join(d, "**", "RECUT__*.mp4"), recursive=True)):
        asset = os.path.basename(p)[len("RECUT__"):]
        f = asset.replace("--", "/", 1)
        c = by.get(f)
        if not c:
            print("skip (posted or gone):", f)
            continue
        up = os.path.join("/tmp", asset)
        shutil.copy(p, up)
        subprocess.run(["gh", "release", "upload", "media", up, "-R", REPO, "--clobber"], check=True)
        os.remove(up)
        for k in ("style", "t5_v", "t5_best", "t5_from", "t5_zoom", "cover", "cover_v", "broll"):
            c.pop(k, None)
        c["bytes"], c["recut_v"] = os.path.getsize(p), RECUT_V
        n += 1
        print("replaced", f)
        json.dump(man, open(MAN, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"{n} clip(s) replaced with the wide cut; restyle next")


if __name__ == "__main__":
    a = sys.argv[1:]
    {"list": lambda: cmd_list(), "one": lambda: cmd_one(a[1]), "commit": lambda: cmd_commit(a[1])}[a[0]]()
