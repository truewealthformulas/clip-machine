"""Render and check ONE shard of a clip plan (a couple of clips) on this server.

Every gate runs exactly as on the Mac (kt_batch_build in no-queue mode): hook
lint, ending verdict, render, caption sync against the waveform, first/last
seconds - plus the 1080p source gate and word-level edge snapping (run_plans).
Clips that pass are handed to factory/queue.py as an artifact; nothing is
queued from here, so parallel shards never fight over the manifest.

    python factory/build_shard.py <plan> <shard>
"""
import glob, json, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.expanduser("~/ClipMachine"))
import run_plans as R  # noqa: E402
from shard import SIZE  # noqa: E402

plan, shard = sys.argv[1], int(sys.argv[2])
p = json.load(open(os.path.join(R.PLANS, f"{plan}.json")))
key = f"{plan}__s{shard}"
sub = dict(p, clips=p["clips"][shard * SIZE:(shard + 1) * SIZE])
json.dump(sub, open(os.path.join(R.PLANS, f"{key}.json"), "w"), indent=1, ensure_ascii=False)

vid = p["source"][:-4]
mp4 = R.fetch_source(vid)
# The renderer reads the episode's transcript from disk, and the lock has to be
# up to date or it refuses to render at all (19 Sept: both stopped every clip).
srt = os.path.join(R.K, "transcripts", f"{vid}.srt")
if not os.path.exists(srt):
    R.sh("gh", "release", "download", "sources", "-R", os.environ.get("GITHUB_REPOSITORY", "truewealthformulas/clip-machine"),
         "-p", f"{vid}.srt.enc", "-D", "/tmp", "--clobber")
    R.sh("openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-pass", "env:FACTORY_KEY",
         "-in", f"/tmp/{vid}.srt.enc", "-out", srt)
    print("transcript:", os.path.exists(srt), srt)
import kt_lock
print("locked now published:", kt_lock.sync())
h = R.height(mp4)
out = "/tmp/shard_out"
os.makedirs(out, exist_ok=True)
result = {"plan": plan, "shard": shard, "brand": p["brand"], "source": p["source"],
          "test": bool(p.get("test")), "height": h, "clips": [], "files": []}
if h < 1080:
    print(f"REFUSED: source is {h}p, the gate is 1080p")
else:
    R.fix_edges(key)
    fixed = json.load(open(os.path.join(R.PLANS, f"{key}.json")))["clips"]
    R.batch([key], test=True)                       # render + check, never queue here
    bdir = os.path.join(R.K, "POST_TODAY", p["brand"])
    for c in fixed:
        hits = [f for f in glob.glob(os.path.join(bdir, f"*_{c['slug']}_*s.mp4")) if "__" not in os.path.basename(f)]
        if not hits:
            continue                                # failed a gate (moved to _failed) or dropped
        result["clips"].append(c)
        for f in glob.glob(os.path.join(bdir, os.path.basename(hits[0])[:-4] + "*")):
            shutil.copy(f, out)
            result["files"].append(os.path.basename(f))
rep = os.path.join(R.K, "work", "proposals", "BATCH_REPORT.md")
if os.path.exists(rep):
    shutil.copy(rep, os.path.join(out, "report.md"))
json.dump(result, open(os.path.join(out, "result.json"), "w"), indent=1, ensure_ascii=False)
print(f"shard {key}: {len(result['clips'])} of {len(sub['clips'])} clip(s) passed every gate")
