"""Collect every shard's passing clips and queue them ONCE (cloud).

Shards render in parallel (build_shard.py); this is the single place that
touches the posting queue: merge each plan into kt_series.json (captions live
there), put the clips where add_clips.py expects them, upload + queue, carry
the call-to-action kind onto the manifest, record the plan as built, commit.
Test plans are reported and marked built but never queued.

    python factory/queue.py /tmp/shards
"""
import glob, json, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MACHINE = os.path.dirname(HERE)
K = os.path.expanduser("~/ClipMachine")
SERIES = os.path.join(K, "kt_series.json")
root = sys.argv[1]

results = [json.load(open(f)) for f in glob.glob(os.path.join(root, "*", "result.json"))]
by_plan = {}
for r in results:
    by_plan.setdefault(r["plan"], []).append(r)
sys.path.insert(0, K)
import kt_lock  # noqa: E402  (mark published clips before anything re-renders)
sys.path.insert(0, HERE)
import kevin_face  # noqa: E402  (is it Kevin on screen?)
print("locked now published:", kt_lock.sync())
series = json.load(open(SERIES))
done = json.load(open(os.path.join(HERE, "plans", "_done.json")))
brands, kinds, report = set(), {}, []
for plan, rs in sorted(by_plan.items()):
    p = json.load(open(os.path.join(HERE, "plans", f"{plan}.json")))
    passed = [c for r in sorted(rs, key=lambda r: r["shard"]) for c in r["clips"]]
    built = bool(passed)
    # KEVIN MUST BE THE FACE ON SCREEN (factory/kevin_face.py, 19 Oct 2026): six
    # posted clips named Kevin over another man. A clip that fails is dropped
    # here, before it can be uploaded or queued.
    not_him = set()
    for r in rs:
        for f in r["files"]:
            if not f.endswith(".mp4") or "__" in f:
                continue
            c = next((c for c in passed if f"_{c['slug']}_" in f), None)
            if not c:
                continue
            ok, why = kevin_face.check(os.path.join(root, f"shard-{plan}-{r['shard']}", f))
            print(f"face check {plan}/{f}: {'Kevin' if ok else 'NOT KEVIN'} - {why}", flush=True)
            if not ok:
                not_him.add(c["slug"])
                report.append(f"- dropped {f}: not Kevin on screen ({why})")
    passed = [c for c in passed if c["slug"] not in not_him]
    report.append(f"## {plan}: {len(passed)} of {len(p['clips'])} clip(s) passed every gate"
                  + (f" ({len(not_him)} dropped: not Kevin on screen)" if not_him else "")
                  + (" (TEST - not queued)" if p.get("test") else ""))
    for r in rs:
        rep = os.path.join(root, f"shard-{plan}-{r['shard']}", "report.md")
        if os.path.exists(rep):
            report.append(open(rep).read()[-3000:])
    # ONLY a plan that actually produced a clip (or a test) counts as built.
    # 19 Sept: an infrastructure failure marked all 8 clips done and they were
    # silently lost. A plan that yields nothing stays pending and is retried.
    # A plan whose clips rendered but were all someone else is finished too -
    # rebuilding it would only find the same faces again.
    if built or p.get("test"):
        done.append(plan)
    if p.get("test") or not passed:
        continue
    spec = series.setdefault(plan, {"source": p["source"], "brand": p["brand"],
                                    "note": p.get("note", ""), "clips": []})
    have = {c["slug"] for c in spec["clips"]}
    spec["clips"] += [{k: c[k] for k in ("slug", "in", "out", "hook", "caption", "cta_kind") if k in c}
                      for c in passed if c["slug"] not in have]
    bdir = os.path.join(K, "POST_TODAY", p["brand"])
    os.makedirs(bdir, exist_ok=True)
    for r in rs:
        for f in r["files"]:
            if any(f"_{s}_" in f for s in not_him):
                continue
            shutil.copy(os.path.join(root, f"shard-{plan}-{r['shard']}", f), bdir)
            if f.endswith(".mp4") and "__" not in f and "cta_kind" in str(passed):
                slug = next((c for c in passed if f"_{c['slug']}_" in f), {})
                if slug.get("cta_kind"):
                    kinds[f"{p['brand']}/{f}"] = slug["cta_kind"]
    brands.add(p["brand"])
json.dump(series, open(SERIES, "w"), indent=1, ensure_ascii=False)
shutil.copy(SERIES, os.path.join(HERE, "kt_series.json"))
json.dump(sorted(set(done)), open(os.path.join(HERE, "plans", "_done.json"), "w"), indent=1)
if brands:
    subprocess.run(["git", "pull", "-q", "--rebase"], cwd=MACHINE)
    up = subprocess.run([sys.executable, "add_clips.py", *sorted(brands)], cwd=MACHINE,
                        capture_output=True, text=True)
    report.append("## UPLOAD\n" + up.stdout[-2500:] + up.stderr[-500:])
    man_p = os.path.join(MACHINE, "state", "manifest.json")
    man = json.load(open(man_p))
    for c in man["clips"]:
        if kinds.get(c["file"]) and not c.get("posted_at") and not c.get("cta_kind"):
            c["cta_kind"] = kinds[c["file"]]
    json.dump(man, open(man_p, "w"), indent=1)
    subprocess.run([sys.executable, "make_thumbs.py"], cwd=MACHINE, capture_output=True)
os.makedirs(os.path.join(HERE, "reports"), exist_ok=True)
open(os.path.join(HERE, "reports", "latest.md"), "w").write("\n\n".join(report))
print("\n\n".join(report)[-4000:])
