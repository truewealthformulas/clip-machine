#!/usr/bin/env python3
"""THE TIKTOK DESCRIPTION, SENT TO THE OWNER (17 Nov 2026: "how will I know the
description of each one?").

TikTok drafts land in the owner's inbox WITHOUT a description (the app is still
in review), and he pastes it by hand. So every clip that reaches the TikTok
inbox gets a GitHub issue titled with its hook, holding the exact description
in a copy block - GitHub emails it to him and it shows in the GitHub app. The
issue is closed at once (the email still goes out), so nothing piles up.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "engine"))
os.environ.setdefault("KT_DATA", os.path.join(HERE, "state"))


def main():
    import main as engine
    import poster
    engine.MANIFEST = os.path.join(HERE, "state", "manifest.json")
    man = engine.load()
    repo = os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY")
    sent = 0
    for c in man["clips"]:
        st = str((c.get("status") or {}).get("tiktok") or "")
        if c.get("tt_note") or not any(k in st for k in ("inbox", "rocess")):
            continue
        if (c.get("posted_at") or c.get("tt_extra_at") or "") < "2026-11-17":
            c["tt_note"] = "old"          # do not email the whole history
            continue
        cap = poster.caption_for("tiktok", c.get("caption", ""), c["file"].split("/")[0],
                                 c.get("cta_keyword", ""), "", c.get("cta_variant"))
        first = cap.strip().split("\n")[0][:80]
        body = ("New TikTok draft in your inbox. Paste this as the description:\n\n```\n"
                + cap + "\n```\n\n_Clip: " + c["file"] + "_")
        r = subprocess.run(["gh", "issue", "create", "-R", repo, "--title", "TikTok: " + first,
                            "--body", body], capture_output=True, text=True)
        if r.returncode == 0:
            url = r.stdout.strip()
            subprocess.run(["gh", "issue", "close", url, "-R", repo], capture_output=True)
            c["tt_note"] = url
            sent += 1
        else:
            print("tt_notes: issue failed:", r.stderr[:200])
    engine.save(man)
    print(f"tt_notes: {sent} description(s) sent")


if __name__ == "__main__":
    main()
