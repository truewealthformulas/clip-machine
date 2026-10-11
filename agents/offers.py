"""Which link in the profile highlights a clip points to.

10 Oct 2026, the owner: the highlights on @thesuccessclubco hold his affiliate
links, and hooks and descriptions should lead to the one that fits the clip:

  wish   Free Your Wish - Kevin's free "Your Wish Is Your Command" training
  book   Your Wish Is Your Command - the book
  gin    Global Information Network - Kevin's members' network
  daily  World's Best Nutritionals - daily whole-food supplement

One plain line, added just above the hashtags. It names the highlight; it never
promises a result. The disclosure (#ad) stays on the hashtag line.

DELIBERATELY NOT HERE: herpescurebook.com. A caption that sends people to a
"cure" for a disease is a medical claim - Meta removes it, the FTC treats the
affiliate as the advertiser, and Kevin's own history is exactly this claim.
No caption, hook or comment ever points to it. The supplement line likewise
names the product only - no health benefit, ever.
"""
import re

LINES = {
    "wish": "Kevin's free training, Your Wish Is Your Command, is in my highlights.",
    "book": "Kevin's book, Your Wish Is Your Command, is in my highlights.",
    "gin": "Kevin's network for money and success thinking (GIN) is in my highlights.",
    "daily": "Kevin's daily nutrition pick is in my highlights.",
}

_PICK = [
    ("gin", r"money|wealth|rich|credit|debt|income|business|boss|deal|budget|cash|financ"),
    ("book", r"love|relationship|marri|partner|soulmate|honest|circle|friend"),
    ("daily", r"nutrition|healthy (habit|living|eating)|\benergy\b|\bfood\b|vitamin"),
]


def pick(*texts):
    t = " ".join(x or "" for x in texts).lower()
    for key, pat in _PICK:
        if re.search(pat, t):
            return key
    return "wish"


def has_line(caption):
    return any(l in (caption or "") for l in LINES.values())


def add(caption, key):
    """Put the highlight line just above the hashtag line (or at the end)."""
    cap = (caption or "").rstrip()
    if not cap or has_line(cap) or key not in LINES:
        return cap
    lines = cap.split("\n")
    if lines[-1].strip().startswith("#"):
        return "\n".join(lines[:-1]).rstrip() + "\n\n" + LINES[key] + "\n\n" + lines[-1].strip()
    return cap + "\n\n" + LINES[key]
