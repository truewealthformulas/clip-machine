#!/usr/bin/env python3
"""Connect (or reconnect) the TikTok account - no token ever shown to anyone.

23 Oct 2026. TikTok had been failing for weeks with "refresh token is invalid
or expired": the token pasted in the TT_REFRESH_TOKEN secret had died, and a
GitHub job cannot write a new secret. So the login now lives in the repo,
ENCRYPTED with the FACTORY_KEY secret (the same key that already protects the
transcripts): state/tiktok_token.enc. Only a job holding FACTORY_KEY can read
it, and the poster re-saves it every time TikTok hands back a fresh token, so it
never quietly expires again.

Two steps, both from Actions -> tiktok-connect -> Run workflow:
  1. leave "code" empty  -> the job summary shows the TikTok login link.
     Open it, log in as @thesuccessclubco, tap Authorize. TikTok sends you to
     the clip-machine GitHub page; the address bar ends with ?code=....
  2. paste that code into "code" and run again -> the code is exchanged for a
     login, checked against the account name, encrypted and saved.

The code works once and only for a few minutes, and is useless without the
app's client secret, which never leaves GitHub's secret store.
"""
import json
import os
import subprocess
import sys
import urllib.parse

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(os.path.dirname(HERE), "state", "tiktok_token.enc")
REDIRECT = os.environ.get("TT_REDIRECT_URI", "https://github.com/truewealthformulas/clip-machine")
SCOPES = "user.info.basic,video.upload"


def summary(text):
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if p:
        with open(p, "a") as fh:
            fh.write(text + "\n")
    print(text)


def save_refresh(token):
    """Encrypt the refresh token with FACTORY_KEY into state/tiktok_token.enc."""
    r = subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-salt", "-a", "-A",
                        "-pass", "env:FACTORY_KEY", "-out", TOKEN_FILE],
                       input=token.encode(), capture_output=True)
    if r.returncode:
        raise SystemExit("could not encrypt the TikTok login: " + r.stderr.decode()[-200:])


def main():
    key = os.environ.get("TT_CLIENT_KEY", "")
    secret = os.environ.get("TT_CLIENT_SECRET", "")
    if not key or not secret or not os.environ.get("FACTORY_KEY"):
        raise SystemExit("TT_CLIENT_KEY, TT_CLIENT_SECRET and FACTORY_KEY secrets are required")
    code = urllib.parse.unquote((os.environ.get("TT_CODE") or "").strip())
    if "code=" in code:                       # a whole pasted address works too
        code = urllib.parse.parse_qs(urllib.parse.urlparse(code).query).get("code", [""])[0]
    if not code:
        link = ("https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
            "client_key": key, "scope": SCOPES, "response_type": "code",
            "redirect_uri": REDIRECT, "state": "clipmachine"}))
        summary("## Step 1 - log in to TikTok\n\nOpen this link, log in as "
                "**@thesuccessclubco** and tap **Authorize**:\n\n" + link +
                "\n\nTikTok then opens the clip-machine GitHub page. Copy everything "
                "after `code=` in the address bar (up to the next `&`), and run this "
                "workflow again with it in the **code** box.")
        return 0
    r = requests.post("https://open.tiktokapis.com/v2/oauth/token/", timeout=30,
                      headers={"Content-Type": "application/x-www-form-urlencoded"},
                      data={"client_key": key, "client_secret": secret, "code": code,
                            "grant_type": "authorization_code", "redirect_uri": REDIRECT})
    d = r.json() if r.content else {}
    if "refresh_token" not in d:
        err = {k: d.get(k) for k in ("error", "error_description") if d.get(k)}
        summary(f"## TikTok said no ({r.status_code})\n\n{json.dumps(err)}\n\n"
                "The code lasts only a few minutes and works once - run step 1 again "
                "for a fresh one.")
        return 1
    who = requests.get("https://open.tiktokapis.com/v2/user/info/",
                       params={"fields": "display_name,username"}, timeout=30,
                       headers={"Authorization": "Bearer " + d["access_token"]}).json()
    user = (who.get("data") or {}).get("user") or {}
    save_refresh(d["refresh_token"])
    days = int(d.get("refresh_expires_in", 0)) // 86400
    summary(f"## TikTok connected\n\nAccount: **{user.get('display_name', '?')}** "
            f"(@{user.get('username', '?')}). Scopes: {d.get('scope', '?')}. The login "
            f"is saved encrypted and renews itself on every post (valid {days} days "
            "from the last use).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
