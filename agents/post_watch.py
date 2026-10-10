#!/usr/bin/env python3
"""AGENT 3 - the posting watchdog.

The posting itself is done by the existing `post` workflow (every 20 minutes,
5 slots a day, all four platforms). This agent makes sure it is REALLY working,
because "success" has lied before (LESSONS.md):

  - reads every post of the last 48 hours, platform by platform
  - a broken login (expired/invalid token) can't be fixed by a robot: it opens
    ONE GitHub issue - GitHub emails the owner - naming the platform and the fix
  - any other failure (upload/processing hiccup) is retried ONCE, only on the
    platform that failed, through the machine's own `retry_only` mechanism
    (never re-posts to a platform that already has it)
  - checks the day's count against the 5-a-day target and the queue length
  - writes factory/reports/posting_health.md and closes the issue when healthy

    python agents/post_watch.py [--dry]
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

DRY = "--dry" in sys.argv
POSTS_PER_DAY = int(os.environ.get("POSTS_PER_DAY", "5"))
WINDOW_H = 48
ISSUE_TITLE = "Posting health: action needed"
OK_WORDS = ("posted", "in your tiktok inbox", "inbox", "duplicate", "story posted")
LOGIN_WORDS = ("token", "oauth", "expired", "revoked", "invalid_grant", "unauthorized",
               "401", "permission", "not configured", "access_token", "session has been invalidated")
SKIP_PLATFORMS = ("instagram_story",)       # a story failure never counts against a post

FIX = {
    "tiktok": ("TikTok login expired/invalid. Re-authorize the TikTok developer app "
               "(Content Posting API) for @thesuccessclubco, get a NEW refresh token, and "
               "paste it into the repo secret TT_REFRESH_TOKEN."),
    "youtube": ("YouTube login expired/revoked. Most common cause: the Google Cloud OAuth "
                "consent screen is still in 'Testing' - tokens then die after 7 days. "
                "Google Cloud Console -> APIs & Services -> OAuth consent screen -> "
                "'Publish app' (to Production), then create a NEW refresh token and paste "
                "it into the repo secret YT_REFRESH_TOKEN."),
    "instagram": ("Instagram token problem. Generate a new long-lived token in the Meta "
                  "developer app (instagram_content_publish + instagram_manage_insights) "
                  "and paste it into IG_ACCESS_TOKEN."),
    "facebook": ("Facebook Page token problem. Generate a new Page access token in the Meta "
                 "developer app and paste it into FB_ACCESS_TOKEN."),
}


def parse(ts):
    try:
        return dt.datetime.strptime(ts[:16], "%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        return None


def classify(msg):
    m = str(msg or "").lower()
    if not m:
        return "none"
    if any(m.startswith(w) or w in m[:40] for w in OK_WORDS):
        return "ok"
    if any(w in m for w in LOGIN_WORDS):
        return "login"
    return "glitch"


def now_local():
    try:
        from zoneinfo import ZoneInfo
        z = ZoneInfo(os.environ.get("KT_TZ", "America/New_York"))
        return dt.datetime.now(dt.timezone.utc).astimezone(z).replace(tzinfo=None)
    except Exception:
        return dt.datetime.utcnow()


def gh(*a):
    exe = shutil.which("gh")
    if not exe:
        return subprocess.CompletedProcess(a, 1, "", "no gh")
    return subprocess.run([exe, *a], capture_output=True, text=True)


def main():
    man = C.manifest()
    clips = man.get("clips", [])
    now = now_local()
    since = now - dt.timedelta(hours=WINDOW_H)
    login, retried, glitches = {}, [], []
    posted_today = 0
    changed = False

    for c in clips:
        if not C.is_main(c):
            continue
        pa = parse(c.get("posted_at"))
        if not pa or pa < since:
            continue
        if pa.date() == now.date():
            posted_today += 1
        status = c.get("status") or {}
        failed = []
        for plat, msg in status.items():
            if plat in SKIP_PLATFORMS:
                continue
            kind = classify(msg)
            if kind == "login":
                login.setdefault(plat, []).append(c["file"])
            elif kind == "glitch":
                failed.append(plat)
                glitches.append(f"{c['file']} on {plat}: {str(msg)[:110]}")
        # ONE retry per clip per platform, never for a login problem (it would
        # just fail again), never while the clip is mid-post.
        already = set(c.get("agent_retried") or [])
        todo = [p for p in failed if p not in already]
        if todo and not c.get("posting") and not c.get("retry_only"):
            retried.append(f"{c['file']} -> {', '.join(todo)}")
            if not DRY:
                for p in todo:
                    status.pop(p, None)
                c["status"] = status
                c["retry_only"] = todo
                c["done"] = False
                c["agent_retried"] = sorted(already | set(todo))
                changed = True

    q = C.queued(man)
    days_left = len(q) / POSTS_PER_DAY if POSTS_PER_DAY else 0
    folders_waiting = sorted({c["file"].split("/")[0] for c in q})
    problems = []
    for plat, files in sorted(login.items()):
        problems.append(f"- [ ] **{plat.upper()} is not posting** ({len(files)} post(s) in 48h). "
                        f"{FIX.get(plat, 'Re-connect this platform and update its secret.')}")
    if days_left < 2:
        problems.append(f"- [ ] **Queue low:** {len(q)} clip(s) = {days_left:.1f} days. The clipper agent "
                        "runs daily; if this stays low check the `agents` workflow log.")
    if len(folders_waiting) < 3 and q:
        problems.append(f"- [ ] Only {len(folders_waiting)} episode folder(s) queued ({', '.join(folders_waiting)}). "
                        "With max 2 posts per folder per day, 5/day needs 3+ folders.")

    lines = [f"# Posting health - {now:%a %d %b %Y %H:%M}", "",
             f"- Posted today: **{posted_today}** (target {POSTS_PER_DAY})",
             f"- Queue: **{len(q)}** clip(s) = {days_left:.1f} days, folders: {', '.join(folders_waiting) or 'none'}",
             f"- Login problems: {', '.join(sorted(login)) or 'none'}",
             f"- Retried once (upload glitches): {len(retried)}"]
    lines += [f"  - {r}" for r in retried]
    if glitches:
        lines += ["", "## Glitches seen (48h)"] + [f"- {g}" for g in glitches]
    if problems:
        lines += ["", "## Needs you"] + problems
    report = "\n".join(lines) + "\n"
    print(report)

    if DRY:
        return 0
    os.makedirs(C.REPORTS, exist_ok=True)
    with open(os.path.join(C.REPORTS, "posting_health.md"), "w", encoding="utf-8") as f:
        f.write(report)
    if changed:
        json.dump(man, open(C.MANIFEST, "w"), indent=1, ensure_ascii=False)

    # One issue, updated in place; GitHub emails the owner when it opens.
    found = json.loads(gh("issue", "list", "--state", "open", "--search", f'in:title "{ISSUE_TITLE}"',
                          "--json", "number").stdout or "[]")
    if problems:
        body = report + "\n_Written by the posting watchdog (agents/post_watch.py). Closes itself when fixed._"
        if found:
            gh("issue", "edit", str(found[0]["number"]), "--body", body)
        else:
            gh("issue", "create", "--title", ISSUE_TITLE, "--body", body)
    else:
        for i in found:
            gh("issue", "close", str(i["number"]), "--comment", "All platforms posting, queue healthy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
