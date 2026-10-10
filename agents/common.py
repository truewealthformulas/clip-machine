"""Shared plumbing for the three agents.

Everything here runs on GitHub Actions inside the clip-machine repository.
Secrets come from the environment (repo -> Settings -> Secrets -> Actions):
  ANTHROPIC_API_KEY  the agents' brain (pasted by the owner, never committed)
  FACTORY_KEY        already there - decrypts the stored transcripts
"""
import json
import os
import re
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "agents")
PLANS = os.path.join(ROOT, "factory", "plans")
REPORTS = os.path.join(ROOT, "factory", "reports")
MANIFEST = os.path.join(ROOT, os.environ.get("KT_DATA", "state"), "manifest.json")
REPO = os.environ.get("GITHUB_REPOSITORY", "truewealthformulas/clip-machine")
MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-5-5")
WORK = os.environ.get("AGENT_WORK", "/tmp/agents")
os.makedirs(WORK, exist_ok=True)


def sh(*a, **kw):
    return subprocess.run(list(a), capture_output=True, text=True, **kw)


def log(msg):
    print(msg, flush=True)


# ------------------------------------------------------------------ the queue
def manifest():
    if not os.path.exists(MANIFEST):
        return {"clips": []}
    return json.load(open(MANIFEST))


def is_main(c):
    """The owner's account. AR_* is a separate brand the agents never touch."""
    return not c.get("file", "").startswith("AR_")


def queued(man):
    """Clips waiting to post (not posted, not done) on the main account."""
    return [c for c in man.get("clips", [])
            if is_main(c) and not c.get("done") and not c.get("posted_at")]


# ------------------------------------------------------------------ the plans
def plan_files():
    if not os.path.isdir(PLANS):
        return []
    return sorted(f[:-5] for f in os.listdir(PLANS)
                  if f.endswith(".json") and not f.startswith("_"))


def load_plan(key):
    return json.load(open(os.path.join(PLANS, f"{key}.json")))


def done_plans():
    p = os.path.join(PLANS, "_done.json")
    return set(json.load(open(p))) if os.path.exists(p) else set()


def planned_sources():
    out = set()
    for k in plan_files():
        try:
            out.add(load_plan(k).get("source", "")[:-4])
        except Exception:
            pass
    return out


def used_brands():
    out = set()
    for k in plan_files():
        try:
            out.add(load_plan(k).get("brand", ""))
        except Exception:
            pass
    series = os.path.join(ROOT, "factory", "kt_series.json")
    if os.path.exists(series):
        try:
            for s in json.load(open(series)).values():
                out.add(s.get("brand", ""))
        except Exception:
            pass
    for c in manifest().get("clips", []):
        out.add(c.get("file", "").split("/")[0])
    return {b for b in out if b}


def plan_age_hours(key):
    """Hours since the plan file was committed (git), else file mtime."""
    path = os.path.join("factory", "plans", f"{key}.json")
    r = sh("git", "log", "-1", "--format=%ct", "--", path, cwd=ROOT)
    try:
        ts = int(r.stdout.strip())
    except ValueError:
        ts = os.path.getmtime(os.path.join(ROOT, path))
    return (time.time() - ts) / 3600


# ------------------------------------------------------- sources & transcripts
def sources_index():
    dst = os.path.join(WORK, "sources_index.json")
    r = sh("gh", "release", "download", "sources", "-R", REPO, "-p",
           "sources_index.json", "-O", dst, "--clobber")
    if r.returncode or not os.path.exists(dst):
        raise SystemExit(f"could not read the sources index: {r.stderr[-200:]}")
    return json.load(open(dst))


def transcript(vid, entry):
    """Decrypted SRT text for one episode."""
    out = os.path.join(WORK, f"{vid}.srt")
    if os.path.exists(out):
        return open(out, encoding="utf-8", errors="replace").read()
    enc = os.path.join(WORK, entry["transcript"])
    r = sh("gh", "release", "download", "sources", "-R", REPO, "-p",
           entry["transcript"], "-O", enc, "--clobber")
    if r.returncode:
        raise RuntimeError(f"download {entry['transcript']}: {r.stderr[-200:]}")
    d = sh("openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-pass",
           "env:FACTORY_KEY", "-in", enc, "-out", out)
    os.remove(enc)
    if d.returncode:
        raise RuntimeError(f"decrypt {vid}: {d.stderr[-200:]}")
    return open(out, encoding="utf-8", errors="replace").read()


def _secs(t):
    h, m, s = t.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def compact(srt):
    """SRT -> one line per cue, '[start-end] text'. Cheaper for the model and
    keeps the exact seconds the plan needs."""
    lines = []
    for block in re.split(r"\n\s*\n", srt.strip()):
        rows = [r for r in block.splitlines() if r.strip()]
        tm = next((r for r in rows if "-->" in r), None)
        if not tm:
            continue
        a, b = [x.strip() for x in tm.split("-->")]
        text = " ".join(r for r in rows[rows.index(tm) + 1:]).strip()
        if text:
            lines.append(f"[{_secs(a):.1f}-{_secs(b):.1f}] {text}")
    return "\n".join(lines)


def sentences(srt):
    """SRT -> one line per SENTENCE, '[start-end] sentence'.

    Whisper cues are not sentences: a cue often starts mid-thought ("and then
    they...") and the clipper copied those times, so the first real run had 6 of 7
    clips rejected for opening or ending mid-sentence. Here the cue text is
    re-joined and split on . ! ?, and each sentence gets the time of the
    character it starts/ends on (interpolated inside its cue). The factory still
    snaps the final cut to word level; this just puts the plan on a real sentence.
    """
    chars = []                                   # (char, time)
    for line in compact(srt).splitlines():
        m = re.match(r"\[(\d+\.?\d*)-(\d+\.?\d*)\] (.*)", line)
        if not m:
            continue
        a, b, text = float(m[1]), float(m[2]), m[3].strip() + " "
        n = max(1, len(text))
        for i, ch in enumerate(text):
            chars.append((ch, a + (b - a) * i / n))
    out, buf, t0 = [], [], None
    for i, (ch, t) in enumerate(chars):
        if t0 is None:
            if ch.isspace():
                continue
            t0 = t
        buf.append(ch)
        nxt = chars[i + 1][0] if i + 1 < len(chars) else " "
        if ch in ".!?" and nxt.isspace():
            s = "".join(buf).strip()
            if s:
                out.append(f"[{t0:.1f}-{t:.1f}] {s}")
            buf, t0 = [], None
    if buf and t0 is not None:
        out.append(f"[{t0:.1f}-{chars[-1][1]:.1f}] {''.join(buf).strip()}")
    return "\n".join(out)


# ---------------------------------------------------------------- the brain
def ask(system, user, max_tokens=8000, history=None):
    """One call to Claude. Returns the text. `history` = earlier turns, if any."""
    fake = os.environ.get("AGENT_FAKE_REPLY")       # tests only: a folder of replies, used in order
    if fake:
        nxt = sorted(f for f in os.listdir(fake) if not f.startswith("used_"))[0]
        os.rename(os.path.join(fake, nxt), os.path.join(fake, "used_" + nxt))
        return open(os.path.join(fake, "used_" + nxt)).read()
    import anthropic
    client = anthropic.Anthropic()
    messages = (history or []) + [{"role": "user", "content": user}]
    # THINKING COUNTS AGAINST max_tokens. Second live run: every reply stopped at
    # max_tokens with no text at all - the model spent the whole 8,000-token
    # budget thinking about an hour-long transcript. So the ceiling is raised
    # well above what the answer needs, effort is held at "medium", and the call
    # streams (a long non-streamed request can time out).
    max_tokens = max(max_tokens, int(os.environ.get("AGENT_MAX_TOKENS", "32000")))
    extra = {"output_config": {"effort": os.environ.get("AGENT_EFFORT", "medium")}}
    for attempt in range(4):
        try:
            try:
                with client.messages.stream(model=MODEL, max_tokens=max_tokens, system=system,
                                            messages=messages, extra_body=extra) as s:
                    msg = s.get_final_message()
            except anthropic.BadRequestError as e:
                if extra and "output_config" in str(e):
                    log("  effort setting not accepted - retrying without it")
                    extra = {}
                    continue
                raise
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            if not text.strip():
                log(f"  model returned no text (stop_reason={msg.stop_reason})")
            elif msg.stop_reason == "max_tokens":
                log("  model reply was cut off at max_tokens")
            return text
        except Exception as e:                       # rate limit / overload
            log(f"  model call failed ({type(e).__name__}: {str(e)[:120]}), retrying")
            time.sleep(20 * (attempt + 1))
    raise RuntimeError("the model did not answer after 4 tries")


def ask_json(system, user, max_tokens=8000):
    """ask(), parsed as JSON. One repair round if the reply is not JSON.

    First live run: two episodes came back with no JSON object at all, and the
    reply was thrown away unseen. Now the start of a bad reply is logged, and the
    model is asked once more for the JSON alone.
    """
    reply = ask(system, user, max_tokens)
    try:
        return json_from(reply)
    except Exception:
        log(f"  reply was not JSON - first 300 chars: {reply[:300]!r}")
    history = [{"role": "user", "content": user},
               {"role": "assistant", "content": reply.strip() or "(no answer)"}]
    reply = ask(system, "Reply again with ONLY the JSON object in the exact format "
                "requested - no commentary, no questions. If a moment breaks a rule, "
                "leave it out and choose other moments.", max_tokens, history=history)
    return json_from(reply)


def json_from(text):
    """The first JSON object in a reply (models sometimes wrap it in ```)."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        return json.loads(m.group(1))
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b < a:
        raise ValueError("no JSON object in the reply")
    return json.loads(text[a:b + 1])


def read(name):
    p = os.path.join(HERE, name)
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""
