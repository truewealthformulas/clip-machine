"""Short lines from Kevin's audiobook "Your Wish Is Your Command" for the captions.

20 Nov 2026, the owner: "take a phrase from the audio book and put it in the
descriptions and photo descriptions". The owner's own BookFunnel copy.

This repository is PUBLIC, so the book never lands in it: the chapter links
(signed, short-lived) arrive ENCRYPTED to a key made inside this run, the audio
and the transcript live only on this server, and only the short quotes -
checked word for word against the transcript - are committed.
"""
import base64, json, os, re, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as AC  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding, rsa  # noqa: E402
from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "agents", "book_quotes.json")
REPO = os.environ.get("GITHUB_REPOSITORY", "truewealthformulas/clip-machine")
W = os.path.expanduser("~/wcache")
BOOK = "Your Wish Is Your Command"


def gh(*a):
    return subprocess.run(["gh", *a], capture_output=True, text=True)


def receive(key, since, issue):
    """Wait (up to 40 min) for a comment 'BOOKBLOB:<json>' on the issue."""
    for _ in range(240):
        r = gh("api", f"repos/{REPO}/issues/{issue}/comments?since={since}&per_page=50")
        try:
            cs = json.loads(r.stdout or "[]")
        except Exception:
            cs = []
        for c in cs:
            m = re.search(r"BOOKBLOB:(\{.*\})", c.get("body", ""), re.S)
            if not m:
                continue
            b = json.loads(m.group(1))
            k = key.decrypt(base64.b64decode(b["k"]), padding.OAEP(
                mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
            pt = AESGCM(k).decrypt(base64.b64decode(b["iv"]), base64.b64decode(b["ct"]), None)
            gh("api", "-X", "DELETE", f"repos/{REPO}/issues/comments/{c['id']}")
            return json.loads(pt)
        time.sleep(10)
    raise SystemExit("no chapter links arrived")


def transcribe(url, i):
    mp3, wav = f"/tmp/b{i}.mp3", f"/tmp/b{i}.wav"
    subprocess.run(["curl", "-sSL", "--retry", "3", "-o", mp3, url], check=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", mp3, "-ar", "16000", "-ac", "1", wav], check=True)
    subprocess.run([os.path.join(W, "whisper-cli"), "-m", os.path.join(W, "ggml-small.en.bin"),
                    "-t", str(os.cpu_count() or 4), "-nt", "-otxt", "-of", f"/tmp/b{i}", wav],
                   check=True, capture_output=True)
    os.remove(mp3)
    os.remove(wav)
    return re.sub(r"\s+", " ", open(f"/tmp/b{i}.txt").read()).strip()


def _norm(t):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]+", " ", t.lower().replace("’", "'"))).strip()


def pick(text, title):
    sysmsg = ("You pick short lines from Kevin Trudeau's audiobook for social captions. Copy each line "
              "EXACTLY from the transcript (only fix capitalisation and end punctuation). No lines that "
              "promise money or income results, nothing about health, disease, medicine, conspiracies or "
              "secret societies. Return JSON only.")
    out = []
    for s in range(0, len(text), 15000):
        chunk = text[s:s + 15000]
        c = AC.ask_json(sysmsg, "Transcript excerpt:\n" + chunk + "\n\nPick up to 6 powerful, self-contained "
                        "sentences about success, wishes and goals, money mindset, discipline or thinking - "
                        "8 to 24 words each, quoted exactly.\nReply: {\"quotes\": [\"\"]}", max_tokens=1500)
        nt = _norm(chunk)
        for q in c.get("quotes") or []:
            q = q.strip().strip('"“”')
            if 8 <= len(q.split()) <= 26 and _norm(q) in nt:
                out.append({"q": q, "ch": title})
    return out


def main():
    issue = os.environ["BOOK_ISSUE"]
    since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 60))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = key.public_key().public_bytes(serialization.Encoding.DER,
                                        serialization.PublicFormat.SubjectPublicKeyInfo)
    print("BOOKKEY:" + base64.b64encode(pub).decode(), flush=True)
    data = receive(key, since, issue)
    for u in data["urls"]:
        print(f"::add-mask::{u}", flush=True)
    have = json.load(open(OUT)) if os.path.exists(OUT) else {"book": BOOK, "quotes": []}
    seen = {_norm(q["q"]) for q in have["quotes"]}
    for i, (u, t) in enumerate(zip(data["urls"], data["titles"])):
        try:
            text = transcribe(u, i)
        except Exception as e:
            AC.log(f"{t}: could not transcribe ({type(e).__name__})")
            continue
        got = [q for q in pick(text, t) if _norm(q["q"]) not in seen]
        seen |= {_norm(q["q"]) for q in got}
        have["quotes"] += got
        AC.log(f"{t}: {len(text.split())} words, {len(got)} quote(s) kept")
        json.dump(have, open(OUT, "w"), indent=1, ensure_ascii=False)
    AC.log(f"{len(have['quotes'])} quotes in {OUT}")


if __name__ == "__main__":
    main()
