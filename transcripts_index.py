"""Two jobs around parallel transcription (one writer for sources_index.json).

    python factory/transcripts_index.py list    # matrix of stocked episodes with no transcript yet
    python factory/transcripts_index.py mark    # record every transcript that now exists
"""
import json, os, subprocess, sys
R = os.environ.get("GITHUB_REPOSITORY", "truewealthformulas/clip-machine")
sh = lambda *a: subprocess.run(list(a), capture_output=True, text=True)
sh("gh", "release", "download", "sources", "-R", R, "-p", "sources_index.json", "-D", "/tmp", "--clobber")
idx = json.load(open("/tmp/sources_index.json"))
assets = {a["name"] for a in json.loads(sh("gh", "release", "view", "sources", "-R", R, "--json", "assets").stdout)["assets"]}
if sys.argv[1] == "list":
    todo = [v for v, e in idx.items() if e.get("status") == "stocked" and f"{v}.srt.enc" not in assets and not e.get("test")]
    print("to transcribe:", todo)
    with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as fh:
        fh.write(f"matrix={json.dumps(todo)}\ncount={len(todo)}\n")
else:
    n = 0
    for v, e in idx.items():
        if f"{v}.srt.enc" in assets and not e.get("transcript"):
            e["transcript"] = f"{v}.srt.enc"; n += 1
    json.dump(idx, open("/tmp/sources_index.json", "w"), indent=1)
    sh("gh", "release", "upload", "sources", "/tmp/sources_index.json", "--clobber", "-R", R)
    print(f"marked {n} new transcript(s)")
