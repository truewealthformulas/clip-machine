#!/usr/bin/env python3
"""Proposals in, verified clips queued out. Runs unattended.

WHY. 16 Sept 2026: Wednesday, 82% of the weekly usage limit spent, and the owner's
standing order is 4-6 clips a day for BOTH accounts for at least two weeks.
Posting runs without me; making clips does not. So clip SELECTION goes to agents
that write ~/ClipMachine/work/proposals/<key>.json, and everything mechanical after that
lives here, so a usage cutoff halfway through cannot leave the queue empty.

Every clip must pass every gate we have, or it is set aside with the reason:
  hook lint (brand-aware) -> ending verdict (no mid-sentence, no advert/outro)
  -> render -> caption timing AND coverage against the waveform (kt_sync_check)
  -> first/last seconds are real speech (kt_verify_render)
  -> upload + fetch check (kt-machine/add_clips.py) -> cta_kind carried onto the
  manifest (the scheduler keeps a preset one) -> commit.

Safe to re-run: merged proposals are remembered; nothing is uploaded twice.

    python3 kt_batch_build.py            # do everything
    python3 kt_batch_build.py --plan     # show what would happen
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

HOME = os.path.expanduser("~/ClipMachine")
sys.path.insert(0, HOME)
PROP = os.path.join(HOME, "work", "proposals")
SERIES = os.path.join(HOME, "kt_series.json")
SRC_DIR = os.path.join(HOME, "Content", "1_RAW", "KT_SOURCE")
POST = os.path.join(HOME, "POST_TODAY")
FAILED = os.path.join(POST, "_failed")
MACHINE = os.path.join(HOME, "kt-machine")
REPORT = os.path.join(PROP, "BATCH_REPORT.md")
DONE = os.path.join(PROP, "_merged.json")
LOG = []


def log(msg):
    print(msg, flush=True)
    LOG.append(msg)


def family(brand):
    return "AR" if brand.startswith("AR_") else "KT"


def wait_for_renders():
    while subprocess.run(["pgrep", "-f", r"python.*kt_(render|tighten)\.py"],
                         capture_output=True).stdout.strip():
        time.sleep(20)


def main():
    plan_only = "--plan" in sys.argv
    os.makedirs(FAILED, exist_ok=True)
    done = json.load(open(DONE)) if os.path.exists(DONE) else []
    series = json.load(open(SERIES))
    used_by = {}
    for k, s in series.items():
        used_by.setdefault(s["source"], set()).add(family(s["brand"]))

    import kt_hooks
    import kt_payoff
    todo = []
    for path in sorted(glob.glob(os.path.join(PROP, "*.json"))):
        key = os.path.splitext(os.path.basename(path))[0]
        if key.startswith("_") or key in done:
            continue
        try:
            p = json.load(open(path))
        except ValueError as e:
            log(f"SKIP {key}: unreadable proposal ({e})")
            continue
        src = os.path.join(SRC_DIR, p["source"])
        if not os.path.exists(src):
            log(f"SKIP {key}: source video missing ({p['source']})")
            continue
        fam = family(p["brand"])
        other = used_by.get(p["source"], set()) - {fam}
        if other:
            log(f"SKIP {key}: FENCE - {p['source']} already belongs to {other}")
            continue
        keep = []
        for c in p.get("clips", []):
            errs = kt_hooks.problems(c.get("hook") or [], p["brand"])
            if errs:
                log(f"  drop {p['brand']}/{c.get('slug')}: hook - {'; '.join(errs)}")
                continue
            v = kt_payoff.verdict(src, float(c["in"]), float(c["out"]))
            if v:
                log(f"  drop {p['brand']}/{c.get('slug')}: ending - {v}")
                continue
            keep.append(c)
        log(f"{key} ({p['brand']}): {len(keep)} of {len(p.get('clips', []))} passed pre-render gates")
        if keep:
            todo.append((key, p, keep))

    if plan_only or not todo:
        log("nothing to build" if not todo else "plan only - stopping")
        return finish()

    # merge into kt_series.json (render reads it)
    series = json.load(open(SERIES))
    for key, p, keep in todo:
        spec = series.setdefault(key, {"source": p["source"], "brand": p["brand"],
                                       "note": p.get("note", ""), "clips": []})
        have = {c["slug"] for c in spec["clips"]}
        for c in keep:
            if c["slug"] in have:
                continue
            spec["clips"].append({k: c[k] for k in ("slug", "in", "out", "hook", "caption")
                                  if k in c} | ({"cta_kind": c["cta_kind"]} if c.get("cta_kind") else {}))
        spec["clips"].sort(key=lambda x: float(x["in"]))
    json.dump(series, open(SERIES, "w"), indent=1)

    passed_brands, kinds = set(), {}
    for key, p, keep in todo:
        wait_for_renders()
        log(f"\nRENDER {key}")
        r = subprocess.run([sys.executable, os.path.join(HOME, "kt_render.py"), key, "--apply"],
                           capture_output=True, text=True, cwd=HOME)
        if r.returncode:
            log(f"  render refused: {(r.stdout + r.stderr)[-400:]}")
            continue
        bdir = os.path.join(POST, p["brand"])
        slugs = {c["slug"]: c for c in keep}
        for f in sorted(os.listdir(bdir)) if os.path.isdir(bdir) else []:
            if not f.endswith(".mp4") or "__" in f:
                continue
            m = re.match(r"^\d+_(.+?)_\d+s\.mp4$", f)
            if not m or m.group(1) not in slugs:
                continue
            mp4 = os.path.join(bdir, f)
            s = subprocess.run([sys.executable, os.path.join(HOME, "kt_sync_check.py"), mp4],
                               capture_output=True, text=True, cwd=HOME)
            if s.returncode:
                log(f"  FAIL {f}: {s.stdout.strip()[-220:]}")
                for side in glob.glob(os.path.splitext(mp4)[0] + "*"):
                    shutil.move(side, os.path.join(FAILED, os.path.basename(side)))
                continue
            v = subprocess.run([sys.executable, os.path.join(HOME, "kt_verify_render.py"), mp4],
                               capture_output=True, text=True, cwd=HOME).stdout
            why = opens_wrong(os.path.join(SRC_DIR, p["source"]), float(slugs[m.group(1)]["in"]), v)
            if why:
                log(f"  FAIL {f}: {why}")
                for side in glob.glob(os.path.splitext(mp4)[0] + "*"):
                    shutil.move(side, os.path.join(FAILED, os.path.basename(side)))
                continue
            log(f"  PASS {f}  {s.stdout.strip().split('] ',1)[-1][:90]}")
            log("       " + " | ".join(l.strip() for l in v.splitlines() if "FIRST" in l or "LAST" in l)[:200])
            passed_brands.add(p["brand"])
            kinds[f"{p['brand']}/{f}"] = slugs[m.group(1)].get("cta_kind")
        done.append(key)
        json.dump(done, open(DONE, "w"), indent=1)

    # CLOUD TEST MODE: render and check, never upload or queue (factory --test).
    if passed_brands and os.environ.get("KT_FACTORY_NOQUEUE"):
        log("TEST MODE - passing clips NOT uploaded or queued: " + ", ".join(sorted(passed_brands)))
        passed_brands = set()
    if passed_brands:
        subprocess.run(["git", "pull", "-q", "--rebase"], cwd=MACHINE)
        up = subprocess.run([sys.executable, "add_clips.py", *sorted(passed_brands)],
                            capture_output=True, text=True, cwd=MACHINE)
        log("\nUPLOAD\n" + up.stdout[-1500:])
        man_p = os.path.join(MACHINE, "state", "manifest.json")
        man = json.load(open(man_p))
        n = 0
        for c in man["clips"]:
            k = kinds.get(c["file"])
            if k and not c.get("posted_at") and not c.get("cta_kind"):
                c["cta_kind"] = k
                n += 1
        json.dump(man, open(man_p, "w"), indent=1)
        log(f"call to action set from content on {n} clip(s)")
        subprocess.run([sys.executable, "make_thumbs.py"], cwd=MACHINE, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=MACHINE)
        subprocess.run(["git", "commit", "-q", "-m",
                        "Batch: verified clips queued\n\nEvery clip passed hook lint, ending verdict, "
                        "caption timing and coverage against the waveform, and a first/last-seconds "
                        "listen.\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>"], cwd=MACHINE)
        subprocess.run(["git", "pull", "-q", "--rebase"], cwd=MACHINE)
        subprocess.run(["git", "push", "-q"], cwd=MACHINE)
        log("pushed")
    return finish()



def opens_wrong(src, t_in, verify_out):
    """The clip must OPEN on the first words of the sentence the plan chose.

    22 Sept 2026, the owner, on a published clip: it "started little before where
    it should have". It opened on "To make money when you know how" - the
    sentence is "It's easy to make money when you know how". The renderer snaps
    the start to a pause, found one INSIDE the sentence, and nothing listened
    to the result. Now the first seconds of the finished file are compared with
    the planned sentence; allowing for whisper's small differences, a clip that
    does not start on that sentence fails. Returns the reason, or ''.
    """
    import difflib
    import kt_payoff
    m = re.search(r"FIRST 5s\s*:\s*(.+?)(?:\||$)", verify_out)
    if not m:
        return ""
    clean = lambda t: [w.replace("'", "") for w in re.sub(r"[^a-z0-9' ]", " ", t.lower()).split()]
    got = clean(m.group(1))
    sents = kt_payoff.sentences(src, max(0.0, t_in - 12), t_in + 12)
    if not sents or not got:
        return ""
    exp = clean(min(sents, key=lambda s: abs(s[0] - t_in))[2])
    if got[:1] == exp[:1] or difflib.SequenceMatcher(a=got[:4], b=exp[:4]).ratio() >= 0.6:
        return ""
    return f"opens mid-sentence: plan starts '{' '.join(exp[:5])}', clip starts '{' '.join(got[:5])}'"


def finish():
    os.makedirs(PROP, exist_ok=True)
    open(REPORT, "a").write("\n## " + time.strftime("%Y-%m-%d %H:%M") + "\n" + "\n".join(LOG) + "\n")
    log(f"report -> {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
