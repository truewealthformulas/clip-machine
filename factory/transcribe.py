"""Transcribe every stocked episode that has no transcript yet (cloud).

Episodes arrive encrypted from the Mac (kt_source_sync.py). This decrypts one,
writes a PUNCTUATED sentence transcript - the kind clip plans are written from
(RULES.md rule 2: at least 8 full stops a minute, else it is useless for edges) -
encrypts it and puts it back beside the episode as <id>.srt.enc.

    python factory/transcribe.py [--max N]
"""
import json, os, re, subprocess, sys

sys.path.insert(0, os.path.expanduser("~/ClipMachine"))
import kt_words  # noqa: E402  (PUNCT_PROMPT - the same prompt the Mac uses)

K = os.path.expanduser("~/ClipMachine")
SRC = os.path.join(K, "Content", "1_RAW", "KT_SOURCE")
TAG, REPO = "sources", os.environ.get("GITHUB_REPOSITORY", "truewealthformulas/clip-machine")
MAX = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 2


def sh(*a, **kw):
    return subprocess.run(list(a), capture_output=True, text=True, **kw)


def crypt(src, dst, decrypt):
    r = sh("openssl", "enc", "-aes-256-cbc", "-pbkdf2", *(["-d"] if decrypt else ["-salt"]),
           "-pass", "env:FACTORY_KEY", "-in", src, "-out", dst)
    if r.returncode:
        raise SystemExit(f"openssl failed on {src}: {r.stderr[-200:]}")


def fetch_source(vid):
    """Decrypted episode at KT_SOURCE/<id>.mp4 (also used by run_plans.py)."""
    mp4 = os.path.join(SRC, f"{vid}.mp4")
    if os.path.exists(mp4):
        return mp4
    r = sh("gh", "release", "download", TAG, "-R", REPO, "-p", f"{vid}.mp4.enc", "-D", "/tmp", "--clobber")
    if r.returncode:
        raise SystemExit(f"download failed for {vid}: {r.stderr[-200:]}")
    crypt(f"/tmp/{vid}.mp4.enc", mp4, decrypt=True)
    os.remove(f"/tmp/{vid}.mp4.enc")
    return mp4


def main():
    sh("gh", "release", "download", TAG, "-R", REPO, "-p", "sources_index.json", "-D", "/tmp", "--clobber")
    idx = json.load(open("/tmp/sources_index.json"))
    todo = [v for v, e in idx.items() if e.get("status") == "stocked" and not e.get("transcript")]
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    if only:
        todo = [only]   # parallel mode: one episode per server; the index is written once, later
    print(f"{len(todo)} episode(s) waiting for a transcript; doing {min(MAX, len(todo))}")
    for vid in todo[:MAX]:
        mp4 = fetch_source(vid)
        wav = f"/tmp/{vid}.wav"
        sh(os.path.join(K, "bin", "ffmpeg"), "-y", "-v", "error", "-i", mp4, "-ar", "16000", "-ac", "1", wav)
        base = f"/tmp/{vid}"
        r = sh(os.path.join(K, "whisper.cpp", "build", "bin", "whisper-cli"),
               "-m", os.path.join(K, "whisper.cpp", "models", "ggml-small.en.bin"),
               "-f", wav, "-t", str(os.cpu_count() or 4), "--prompt", kt_words.PUNCT_PROMPT,
               "-osrt", "-of", base)
        srt = base + ".srt"
        if not os.path.exists(srt):
            print(f"  {vid}: whisper failed: {r.stderr[-300:]}")
            continue
        text = open(srt).read()
        mins = max(1.0, idx[vid].get("duration", 1800) / 60)
        stops = len(re.findall(r"[.!?]", text)) / mins
        crypt(srt, srt + ".enc", decrypt=False)
        u = sh("gh", "release", "upload", TAG, srt + ".enc", "--clobber", "-R", REPO)
        if u.returncode:
            print(f"  {vid}: upload failed {u.stderr[-200:]}")
            continue
        if only:
            print(f"  {vid}: transcribed, {stops:.1f} full stops/min")
            continue
        # Re-read the index right before writing: the Mac may have added episodes.
        sh("gh", "release", "download", TAG, "-R", REPO, "-p", "sources_index.json", "-D", "/tmp", "--clobber")
        idx = json.load(open("/tmp/sources_index.json"))
        idx[vid]["transcript"] = f"{vid}.srt.enc"
        idx[vid]["stops_per_min"] = round(stops, 1)
        json.dump(idx, open("/tmp/sources_index.json", "w"), indent=1)
        sh("gh", "release", "upload", TAG, "/tmp/sources_index.json", "--clobber", "-R", REPO)
        print(f"  {vid}: transcribed, {stops:.1f} full stops/min {'OK' if stops >= 8 else 'LOW - check before planning'}")


if __name__ == "__main__":
    main()
