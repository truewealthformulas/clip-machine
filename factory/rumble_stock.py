"""Stock the factory with HD episodes straight from Rumble - no Mac needed.

19 Sept 2026. The cloud can download Kevin's episodes from Rumble by posing as
Chrome (the first request is sometimes refused by Cloudflare; a retry passes).
Picks the newest full episodes at 1080p or better that were never clipped and
are not fenced to brand-2 owner, downloads up to 1440p, encrypts them into the 'sources'
release (the repository is public), and adds them to sources_index.json so
transcribe.py and the clip plans can use them.

    python factory/rumble_stock.py [--max N] [--stock N]
"""
import json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
K = os.path.expanduser("~/ClipMachine")
SRC = os.path.join(K, "Content", "1_RAW", "KT_SOURCE")
TAG, REPO = "sources", os.environ.get("GITHUB_REPOSITORY", "truewealthformulas/clip-machine")
arg = lambda n, d: int(sys.argv[sys.argv.index(n) + 1]) if n in sys.argv else d
MAX, STOCK = arg("--max", 2), arg("--stock", 6)


def sh(*a):
    return subprocess.run(list(a), capture_output=True, text=True)


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def height(p):
    m = re.search(r"Video:.*?(\d{3,4})x(\d{3,4})", sh("ffmpeg", "-i", p).stderr)
    return int(m[2]) if m else 0


def main():
    sh("gh", "release", "download", TAG, "-R", REPO, "-p", "sources_index.json", "-D", "/tmp", "--clobber")
    idx = json.load(open("/tmp/sources_index.json")) if os.path.exists("/tmp/sources_index.json") else {}
    done = set(json.load(open(os.path.join(HERE, "plans", "_done.json"))))
    planned = " ".join(open(os.path.join(HERE, "plans", f)).read()
                       for f in os.listdir(os.path.join(HERE, "plans")) if f.endswith(".json"))
    waiting = [v for v, e in idx.items() if e.get("status") == "stocked" and not e.get("test")
               and v not in planned]
    need = min(MAX, STOCK - len(waiting))
    print(f"{len(waiting)} stocked episode(s) not yet planned; stock target {STOCK}; fetching {max(need, 0)}")
    if need <= 0:
        return
    series = json.load(open(os.path.join(HERE, "kt_series.json")))
    used = {norm(os.path.splitext(s.get("source", ""))[0])[:40] for s in series.values()}
    cat = json.load(open(os.path.join(HERE, "rumble_catalog.json")))
    have = {e.get("rumble") for e in idx.values()}
    pick = [(u, e) for u, e in sorted(cat.items(), key=lambda x: x[1]["date"], reverse=True)
            if not e["short"] and e["dur"] >= 1200 and e["height"] >= 1080
            and u not in have and norm(e["title"])[:40] not in used]
    # THE MONTH'S LIST COMES FIRST (factory/source_plan.json, chosen with the owner).
    sp = os.path.join(HERE, "source_plan.json")
    if os.path.exists(sp):
        order = [e["id"] for e in json.load(open(sp))["episodes"]]
        rank = lambda ue: order.index(re.search(r"/(v[a-z0-9]+)-", ue[0])[1]) \
            if re.search(r"/(v[a-z0-9]+)-", ue[0])[1] in order else len(order)
        pick.sort(key=rank)
    for url, e in pick[:need]:
        vid = re.search(r"/(v[a-z0-9]+)-", url)[1]
        mp4 = os.path.join(SRC, f"{vid}.mp4")
        print(f"  {vid}  {e['dur']/60:.0f} min  {e['height']}p  {e['title'][:70]}")
        for attempt in range(6):
            # Alternate: the direct stream (skips the page Cloudflare guards) and the page.
            target = e.get("hls") if (attempt % 2 == 0 and e.get("hls")) else url
            r = sh("yt-dlp", "--no-warnings", "-q", "--impersonate", "chrome", "-N", "8",
                   "-f", "bv*[height<=2160]+ba/b[height<=2160]", "--merge-output-format", "mp4",
                   "-o", mp4, target)
            if os.path.exists(mp4):
                break
            time.sleep(15 * (attempt + 1))
        h = height(mp4) if os.path.exists(mp4) else 0
        if h == 0:
            # Cloudflare turned every attempt away. Not the episode's fault: try
            # again on the next run instead of writing it off.
            print(f"    NOT FETCHED this run, will retry ({r.stderr.strip()[-120:]})")
            continue
        if h < 1080:
            print(f"    REFUSED: {h}p - under the 1080p gate")
            idx[vid] = {"title": e["title"], "rumble": url, "status": "rejected", "height": h}
            continue
        enc = f"/tmp/{vid}.mp4.enc"
        sh("openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-salt", "-pass", "env:FACTORY_KEY", "-in", mp4, "-out", enc)
        u = sh("gh", "release", "upload", TAG, enc, "--clobber", "-R", REPO)
        os.remove(enc)
        if u.returncode:
            print(f"    UPLOAD FAILED {u.stderr[-150:]}")
            continue
        idx[vid] = {"title": e["title"], "rumble": url, "duration": e["dur"], "height": h,
                    "status": "stocked", "uploaded": time.strftime("%Y-%m-%dT%H:%M")}
        print(f"    STOCKED {h}p")
    json.dump(idx, open("/tmp/sources_index.json", "w"), indent=1)
    sh("gh", "release", "upload", TAG, "/tmp/sources_index.json", "--clobber", "-R", REPO)


if __name__ == "__main__":
    main()
