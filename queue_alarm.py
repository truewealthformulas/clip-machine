"""Email the owner when his clips are about to run out.

17 Sept 2026: the queue hit zero and nobody noticed. The calendar feed now shows
the run-out day; this adds an email. It opens a GitHub issue when fewer than
ALARM_DAYS days of clips are left - GitHub emails the repo owner - and closes it
when the queue is refilled. the owner's account only. --dry prints and does nothing.
"""
import datetime, json, os, subprocess, sys

DAYS = int(os.environ.get("ALARM_DAYS", "3"))
PREFIX = "Clips run out"
dry = "--dry" in sys.argv
m = json.load(open(os.path.join(os.environ.get("KT_DATA", "state"), "manifest.json")))["clips"]
left = [c for c in m if not c.get("done") and not c.get("posted_at") and not c["file"].startswith("AR_")]
last = max((c["scheduled_at"][:10] for c in left if c.get("scheduled_at")), default=None)
today = datetime.date.today()
runs_out = datetime.date.fromisoformat(last) + datetime.timedelta(days=1) if last else today
days = (runs_out - today).days
import shutil
GH = shutil.which("gh") or os.path.expanduser("~/ClipMachine/bin/gh")
gh = lambda *a: subprocess.run([GH, *a], capture_output=True, text=True)
found = json.loads(gh("issue", "list", "--state", "open", "--search", f"in:title \"{PREFIX}\"",
                      "--json", "number,title").stdout or "[]")
print(f"{len(left)} clips queued, run out {runs_out} ({days} days); open alarms: {len(found)}")
if days <= DAYS and not found:
    title = f"{PREFIX} on {runs_out:%a %d %b} - {len(left)} clips left"
    body = (f"the owner's queue has {len(left)} clip(s) and the last one posts on {last or 'nothing scheduled'}.\n\n"
            "From that day nothing new goes out on Instagram, Facebook, YouTube or TikTok until more clips are made.\n\n"
            "This closes itself when the queue is refilled.")
    print("OPEN:", title)
    if not dry:
        print(gh("issue", "create", "--title", title, "--body", body).stdout.strip())
elif days > DAYS:
    for i in found:
        print("CLOSE:", i["title"])
        if not dry:
            gh("issue", "close", str(i["number"]), "--comment",
               f"Refilled: {len(left)} clips queued, lasting until {runs_out:%a %d %b}.")
