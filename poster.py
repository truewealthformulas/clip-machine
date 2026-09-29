#!/usr/bin/env python3
"""Platform adapters. An adapter returns "posted" only if the platform said so
AND the post was found on the account afterwards.

THE RULE: never report success without confirmation. the owner has already lost
twelve days to seven TikTok posts that a dashboard called Published while they
sat unpublished in an inbox. A wrong "posted" is worse than a loud failure.

24 AUG: the service said `instagram: posted` and nothing was on the account.
The cause was believing the API's 200. Instagram returns a media id from
/media_publish before the Reel is necessarily on the profile, so a 200 is not
evidence. Every adapter now ENDS by asking the platform for the public link and
only then says posted. If the link cannot be found, it says so in those words.

  YouTube    resumable upload -> public immediately. madeForKids MUST be sent
             false or YouTube accepts the request and quietly does not publish.
             Verified by re-reading the video's uploadStatus + privacyStatus.
  Instagram  container -> poll -> publish -> READ BACK the permalink.
  Facebook   Reels API (3-phase). Falls back to a feed video if Reels refuses.
             Needs pages_manage_posts; without it Facebook says (#100).
  TikTok     /inbox/ ONLY. Lands in the creator's drafts, he taps post in the app.
             NEVER /post/publish/video/ (direct post) unaudited: it succeeds and
             publishes SELF_ONLY - permanently private - whatever privacy is sent.

Every adapter returns either "some status string" or ("posted", "<public url>").
"""
import calendar
import json
import math
import os
import re
import time

import requests

T = 120
STORIES_ON = os.environ.get("KT_STORIES", "1") != "0"
CHUNK = 60 * 1024 * 1024          # TikTok caps a chunk at 64MB


# Which brand prefixes may fall back to the UNPREFIXED credentials. Everything
# that was live on 30 Aug 2026 - KT_* and MINDSET_SHIFT - was built before
# prefixes existed and reads the bare IG_ACCESS_TOKEN, so those two keep the
# fallback and nothing about the owner's accounts changes. Any other prefix must
# bring its own variables.
FALLBACK_BRANDS = {p.strip().upper() for p in os.environ.get(
    "KT_FALLBACK_BRANDS", "KT,MINDSET").split(",") if p.strip()}


def cred_prefix(brand):
    """The part of a brand folder that selects its credentials. AR_MIND -> AR."""
    return (brand or "").split("_")[0].upper()


def account_key(brand):
    """WHICH ACCOUNT this brand actually posts to.

    3 Sept 2026: three slots were double-booked - KT_LIES and MINDSET_SHIFT both
    scheduled at 13:30 on the same day, on the SAME Instagram account. The
    planner reserved slots per folder PREFIX, and MINDSET is a different prefix
    from KT. But MINDSET_SHIFT has no MINDSET_IG_* variables, so _cfg falls back
    to the unprefixed ones - the same account KT posts to.

    A slot belongs to an ACCOUNT, not to a folder name. Two brands that resolve
    to the same credentials share one grid; two that resolve to different ones do
    not. This asks the credentials, so a fallback can never split a grid in two.
    """
    (ig,), _ = _cfg("IG_USER_ID", brand=cred_prefix(brand))
    return ig or cred_prefix(brand)


def _cfg(*keys, brand=""):
    """Credentials for one brand. A brand may NOT borrow another brand's.

    MULTI-BRAND, 27 Aug 2026. brand-2 owner wants her own accounts running on this same
    machine. Every adapter already receives the clip, and every clip's file is
    "BRAND/name.mp4", so the brand is already in hand at every call site - the
    only thing missing was letting the credentials vary with it.

    A brand's prefix is the part of its folder before the first underscore, so
    AR_MIND and AR_MONEY both read AR_IG_ACCESS_TOKEN.

    30 AUG: THE UNCONDITIONAL FALLBACK WAS A CROSS-POST WAITING FOR A SLOT.
    AR_YT_* and AR_TT_* were set; AR_IG_* and AR_FB_* were not. So an AR_MIND
    clip would not have failed - it would have read the owner's IG_ACCESS_TOKEN and
    published brand-2's spiritual clip to Kevin's Instagram and Facebook, and the
    board would have said "posted" with a real permalink to prove it. Nothing
    about that is visible in a log.

    So the fallback is now a whitelist. Only FALLBACK_BRANDS may read the bare
    variables. Any other brand missing its own is refused BY NAME, so the board
    says "not configured: AR_IG_USER_ID" instead of quietly posting elsewhere.
    """
    prefix = cred_prefix(brand)
    may_fall_back = not prefix or prefix in FALLBACK_BRANDS
    vals, missing = [], []
    for k in keys:
        v = os.environ.get(prefix + "_" + k, "") if prefix else ""
        if not v and may_fall_back:
            v = os.environ.get(k, "")
        vals.append(v)
        if not v:
            missing.append(k if may_fall_back else prefix + "_" + k)
    return vals, missing


def collides_with_default(brand, *identity_keys):
    """Refuse when a fenced brand resolves to the DEFAULT brand's own account.

    31 Aug 2026, brand-2 owner: "make sure these clips are not posting to owners
    instagram or facebook."

    The FALLBACK_BRANDS whitelist already stops the silent case - a brand with
    no credentials of its own is refused by name rather than borrowing the bare
    ones. But it cannot see a brand that HAS credentials which happen to be
    somebody else's. One mistyped id, or one run of kt_fbtoken.py without
    --brand while her token is in hand, and AR_IG_USER_ID would hold the owner's
    account. The fence would pass it: the variable is set, so nothing looks
    wrong, and her spiritual clips would publish to his feed reporting success
    with a real permalink.

    So the identity is compared as well as the presence. If a fenced brand's
    account id equals the unprefixed one, that is not a configuration, it is a
    mistake, and it fails closed and says which variable to fix.
    """
    prefix = cred_prefix(brand)
    if not prefix or prefix in FALLBACK_BRANDS:
        return None
    for k in identity_keys:
        mine = os.environ.get(prefix + "_" + k, "")
        bare = os.environ.get(k, "")
        if mine and bare and mine == bare:
            return (f"REFUSED: {prefix}_{k} is the same account as the default "
                    f"{k}. A {prefix}_ clip must never post to another brand's "
                    f"account - fix {prefix}_{k}.")
    return None


def brand_of(clip):
    return ((clip or {}).get("file") or "").split("/")[0]


def _j(r):
    try:
        return r.json()
    except Exception:
        return {"_raw": r.text[:300]}


def body_lines(caption):
    """The caption minus the CTA line and the hashtag block.

    The CTA is deliberately identical on every clip (it is the offer), so it is
    useless as a title and, repeated across every upload, looks like spam to
    YouTube. What is left is the actual hook.
    """
    out = []
    for l in (caption or "").split("\n"):
        l = l.strip()
        if not l or l.startswith("#") or l.lower().startswith("comment "):
            continue
        # A LINE WITH A LINK IS NEVER THE HOOK. 10 Sept 2026: two of brand-2's
        # YouTube videos were TITLED with the affiliate URL -
        # "If this one hit you, they're here: https://freeyourwish..." - because
        # this only dropped lines STARTING with "Comment". A CTA phrased any
        # other way survived, and when the real first line was too short for the
        # title window, the link became the title. A bare affiliate URL as a
        # YouTube title reads as spam to the algorithm and to a human.
        if "http://" in l or "https://" in l or "www." in l:
            continue
        # NOR A STOCK QUESTION. Every non-Instagram AR post now ends on the same
        # closing line, and without this it became the YouTube title on all of
        # them - identical titles across a channel read as spam.
        if l in ASK_LINES:
            continue
        out.append(l)
    return out


# THE COMMENT KEYWORD ROTATES. Daniel, 4 Sept 2026, via the owner: each post should
# ask for a DIFFERENT word, cycling and eventually returning to the first, "so it
# gives people the sensation that its something different, a different
# experience."
#
# He is right about the mechanism and it is free. A follower who sees "Comment
# WISH" under five reels in a row is reading an ad they have already read. The
# same follower seeing WISH, then MONEY, then BRAIN is being asked something new
# each time, and a new ask is a new decision instead of a habit to scroll past.
#
# THREE, NOT TEN, AND THE REASON IS MECHANICAL. Meta caps a comment rule at 5
# keywords, and its matching appears to be case-sensitive, so each word costs
# three entries (WISH / Wish / wish). Three words = nine entries = two rules.
# Ten words would be seven rules to maintain by hand, and every keyword that is
# not set up in Meta is a person who comments and gets nothing back.
#
# Assigned in POSTING ORDER by plan(), not by hash: consecutive posts must
# differ, which a hash cannot promise. Frozen onto the clip when it is
# scheduled, so the caption Meta sees never disagrees with the rule that catches
# it.
def keywords_for(brand=""):
    """The keyword rotation for ONE brand.

    Per brand because the words have to match that brand's OWN Meta automation
    rules. the owner's are WISH/KT/FREE/YES; brand-2's account has never heard of KT
    and a caption asking her followers to comment it would send them nowhere.
    Set AR_CTA_KEYWORDS to give her her own.
    """
    prefix = cred_prefix(brand)
    raw = (os.environ.get(prefix + "_CTA_KEYWORDS", "") if prefix else "")
    if not raw:
        # FAIL CLOSED, 9 Sept 2026. This used to fall back to KT_CTA_KEYWORDS
        # for ANY brand, which is how "Comment WISH" - the owner's word, answered
        # only by the owner's automation on the owner's account - ended up on brand-2's
        # live Instagram posts. A fenced brand with no keywords of its own has
        # NO keyword, exactly as it has no offer URL; the caption then simply
        # carries no comment ask. Borrowing another account's keyword is worse
        # than asking for nothing, because it looks like it works.
        if prefix and prefix not in FALLBACK_BRANDS:
            return []
        raw = os.environ.get("KT_CTA_KEYWORDS", "WISH,KT,FREE,YES")
    return [k.strip().upper() for k in raw.split(",") if k.strip()]


KEYWORDS = [k.strip().upper() for k in os.environ.get(
    "KT_CTA_KEYWORDS", "WISH,KT,FREE,YES").split(",") if k.strip()]


# The offer link. Per brand, via _cfg, so AR_OFFER_URL is brand-2's and a brand
# with none gets NO link rather than somebody else's - kt_captions once appended
# Kevin's CTA to her folder and that must not happen through this door.
# THE ASK, IN HER OWN VOICE, ROTATED. brand-2 owner, 9 Sept 2026: "i want to say
# different phrases each post ... when its different it feels less robotic."
#
# One line per variant, picked from a hash of the caption body so a given clip
# always gets the same wording (a re-post must not change the ask) while
# consecutive clips get different ones.
#
# EVERY VARIANT PROMISES EXACTLY WHAT ARRIVES: Kevin's free audios. She floated
# "Kevin's $500 worth seminar for free" - what the automation actually sends is
# the audio set, and a promise bigger than the delivery is the fastest way to
# lose the trust she is building. The wording changes; the offer does not.
AR_ASK_COMMENT = [
    "Comment {kw} and I\u2019ll send you Kevin\u2019s free audios.",
    "If this one hit you, comment {kw} \u2014 I\u2019ll send you his free audios.",
    "Comment {kw} and Kevin\u2019s free audios are in your messages.",
    "Want the audios Kevin gives away? Comment {kw}.",
    "Feel that? Comment {kw} and I\u2019ll send them over.",
    "Comment {kw} \u2014 free audios, no catch, straight to your inbox.",
]
# Offered only when the brand HAS something in its Instagram bio.
AR_ASK_BIO = [
    "Comment {kw}, or tap the link in my bio \u2014 same audios either way.",
    "The audios are in my bio, or comment {kw} and I\u2019ll send them.",
]
AR_ASK_LINK = [
    "Kevin\u2019s free audios, no catch: {url}",
    "The audios are free. Here: {url}",
    "If this one hit you, they\u2019re here: {url}",
    "Free audios from Kevin: {url}",
]


def ar_ask(body_text, kw, url, platform, variant=None):
    """One of the rotating asks.

    `variant` is frozen onto the clip by plan() IN POSTING ORDER, for the same
    reason the keyword is: consecutive posts must differ. A hash of the caption
    gave three identical asks out of five clips - the exact failure the keyword
    rotation comment already warned about. The hash is only the fallback for a
    clip planned before this field existed.
    """
    import hashlib
    h = (int(variant) if variant is not None
         else int(hashlib.sha256((body_text or "").encode()).hexdigest()[:8], 16))
    # INSTAGRAM ONLY FOR THE COMMENT. brand-2 owner, 9 Sept 2026: "comment thing is only
    # for instagram." Her automation is CreatorFlow, which watches Instagram
    # comments - nothing is listening on TikTok, Facebook or YouTube, so asking
    # for a comment there is asking for something that cannot be answered.
    # Everywhere else gets her link.
    # NO AFFILIATE LINK IN ANY POST. 10 Sept 2026, brand-2 owner, after finding her
    # ref link in a YouTube TITLE: "do not do that in any posts that will get us
    # banned. i only put it in the bio or send people messages that is the only
    # way for now."
    #
    # So for AR_* the link NEVER appears in caption, description or title on any
    # platform. It lives in two places only: her bio, and the DM her CreatorFlow
    # automation sends to someone who comments. Instagram keeps the comment ask
    # because that is what feeds the automation; every other platform ends on a
    # question, which earns comments without putting a link anywhere.
    #
    # AR_ASK_LINK is deliberately no longer reachable. Do not wire it back in.
    if platform != "instagram":
        return ASK_LINES[1]
    if platform == "instagram":
        if not kw:
            return ""      # no keyword configured -> no ask at all
        # HER BIO NOW HAS A LINK, 9 Sept 2026. Until today it did not, and
        # pointing her followers at an empty profile was worse than saying
        # nothing - so every ask here was comment-only. She has since put the
        # audios link in the Instagram bio, so a third of the asks offer the
        # tap as well: some people will never comment but will happily tap.
        pool = AR_ASK_COMMENT + (AR_ASK_BIO if url else [])
        return pool[h % len(pool)].format(kw=kw)
    if url:
        pool = AR_ASK_LINK
        return pool[h % len(pool)].format(url=url)
    # No link configured is a configuration error for this brand, not a reason
    # to fall back to somebody else's offer. Say nothing rather than mislead.
    return ""


# Questions that end a post instead of selling it. Deliberately about THEM and
# about the clip they just watched, never about us.
ASK_LINES = [
    "What did you take from this one?",
    "What did you take from this one? Tell me below.",
]


DEFAULT_OFFER = "https://freeyourwish.YOUR_OFFER_URL"


def caption_for(platform, caption, brand="", keyword="", ask="", variant=None):
    """The caption rewritten for ONE platform's link rules.

    3 SEPT 2026, OWNER'S CATCH AND IT IS A REAL ONE. One caption was sent to all
    four platforms, and each has different rules:

      Instagram  links in captions are not clickable -> comment + "link in bio"
      TikTok     no link at all under 1,000 followers -> comment is the ONLY option
      YouTube    the link works in the description -> put the actual link
      Facebook   the link works in the caption -> put the actual link

    We were making people on YouTube and Facebook comment for no reason, on two
    platforms where they could simply have clicked. The comment CTA is not a
    style, it is a workaround for a restriction - and it was being applied to
    platforms that do not have the restriction.

    Instagram keeps the comment CTA on purpose: it feeds the Meta keyword
    automation, so the comment is worth something there.
    """
    cap = (caption or "").strip()
    if not cap:
        return cap
    lines = cap.split("\n")
    asks = {a.lower() for a in ASK_LINES}
    body = [l for l in lines
            if not l.strip().lower().startswith("comment ")
            and l.strip().lower() not in asks
            and not l.strip().lower().startswith("get access here:")]
    tags = [l for l in body if l.strip().startswith("#")]
    body = [l for l in body if not l.strip().startswith("#")]
    while body and not body[-1].strip():
        body.pop()

    (url,), missing = _cfg("OFFER_URL", brand=brand)
    if missing:
        # An unfenced brand falls back to the default; a fenced one gets none.
        url = DEFAULT_OFFER if cred_prefix(brand) in FALLBACK_BRANDS or not brand else ""

    # THE KEYWORD MUST BE ONE THE AUTOMATION CAN ANSWER.
    #
    # 8 Sept 2026. A real viewer commented BRAIN on a live reel within minutes
    # of it posting, and nothing replied - because BRAIN was never in the Meta
    # rule. The rotation default was WISH,MONEY,BRAIN when those clips were
    # SCHEDULED; the keyword is frozen onto the clip at scheduling time; and
    # when the list later became WISH,KT,FREE,YES the already-frozen ones kept
    # their old word. Ten posted clips were asking for words nothing listened
    # for. Every comment on them was a lead hitting silence.
    #
    # Changing a rotation list is not enough - the clips carrying the old word
    # have to be caught. A keyword outside the CURRENT list is never printed;
    # it falls back to one that is, so a stale value can cost a caption's
    # wording but never a lead.
    allowed = keywords_for(brand)
    kw = (keyword or "").upper()
    if not allowed:
        kw = ""          # fenced brand, no keywords configured -> no ask
    elif kw not in {k.upper() for k in allowed}:
        kw = allowed[0].upper()

    # NOT EVERY POST SELLS. 4 Sept 2026, from kevins_apprentice - same material,
    # same offer, 4,609 followers to our 119, and reels at 16K/42K/3.9K likes.
    # TWO OF THREE ended on a QUESTION with no link and no keyword at all.
    #
    # A question earns comments, comments earn reach, reach is the audience for
    # the next post. We attached a CTA to 100% of posts and have been asking a
    # stranger to buy before they have any reason to care. See
    # COMPETITOR_KEVINS_APPRENTICE.md.
    #
    # One offer for every two questions, assigned by plan() in posting order.
    if ask == "question":
        cta = ASK_LINES[0] if platform in ("instagram", "tiktok") else ASK_LINES[1]
        # A VALUE CLIP NEVER LEAVES THE OFFER OUT. 16 Sept 2026, the owner: "what if
        # the value ones get to millions of views for that same reason and nobody
        # comments a key word?" A clip that ends only on a question
        # gives a viral audience no road to the offer. The question stays first
        # (it is what earns saves and shares); one short keyword line follows.
        # Same rules as the offer asks below: Instagram and Facebook TAKE TURNS
        # on the same clip (the owner, 11 Sept), and brand-2 owner asks on Instagram only,
        # in her own words (brand-2 owner, 9 Sept).
        v = variant if isinstance(variant, int) else 0
        if not kw:
            pass
        elif cred_prefix(brand) == "AR":
            if platform == "instagram":
                extra = ar_ask("\n".join(body), kw, url, platform, variant)
                if extra:
                    cta = f"{cta}\n\n{extra}"
        elif platform == "tiktok" or (
                platform in ("instagram", "facebook")
                and (platform == "instagram") == (v % 2 == 0)):
            cta = f"{cta}\n\nComment {kw} to get access."
    elif cred_prefix(brand) == "AR":
        cta = ar_ask("\n".join(body), kw, url, platform, variant)
    elif platform in ("instagram", "facebook"):
        # FACEBOOK ASKS FOR THE COMMENT TOO, AND NEVER CARRIES A RAW LINK.
        # 11 Sept 2026, the owner: "edit the fb descriptions same as IG without a
        # link on it and adding the comment below part." A bare offer link in a
        # Facebook caption reads as spam, and the Meta comment automation is
        # already listening on Messenger - so the comment is worth exactly as
        # much there as it is on Instagram.
        #
        # BUT THE TWO MUST NOT READ IDENTICALLY. His words: "when same clips in
        # IG has comment facebook dosnt, and viseverce." The same clip going out
        # with the same caption on both is also the duplicate-caption pattern
        # that gets accounts flagged. So the ask ALTERNATES: on even variants
        # Instagram carries it and Facebook closes on the question, on odd
        # variants they swap. The variant is frozen per clip at scheduling, so
        # a re-plan never flips a caption that already went out.
        v = variant if isinstance(variant, int) else 0
        mine = (platform == "instagram") == (v % 2 == 0)
        if not mine:
            cta = ASK_LINES[0] if platform == "instagram" else ASK_LINES[1]
        else:
            # "TO GET ACCESS", not "free audios". Their exact framing is
            # `Comment "Reality" to get access.` - the thing has to sound like
            # it is worth having. the owner: "the audios are a privileged, not a
            # free stuff". Only point at the bio if there IS something in it, and
            # only on Instagram - "link in my bio" means nothing on a Facebook
            # page. brand-2's bio has no link at all; she delivers by DM.
            if url and platform == "instagram":
                cta = f"Comment {kw} to get access \u2014 or tap the link in my bio."
            else:
                cta = f"Comment {kw} and I\u2019ll send it to you."
    elif platform == "tiktok":
        cta = f"Comment {kw} to get access."
    elif url:
        cta = f"Get access here: {url}"
    else:
        # NO LINK CONFIGURED -> ASK FOR THE COMMENT, never "link in bio".
        #
        # 5 Sept 2026, the owner: "brand-2 owner does not have anything in her bio, she
        # decided just to do it on comment to send them the link."
        #
        # This branch used to say "Link in bio." and it was worse than useless:
        # it pointed her viewers at a bio that has no link, on the two platforms
        # (YouTube, Facebook) where a real link WOULD have worked. A brand with
        # no OFFER_URL is not a brand with a bio link - it is a brand that
        # delivers by DM, so it must ask for the comment everywhere.
        cta = f"Comment {kw} and I\u2019ll send it to you."
    # WHERE THE ASK SITS. brand-2 owner, 9 Sept 2026: "lets put it at the top instead
    # of bottom." On a phone a caption is truncated after roughly two lines, so
    # an ask at the bottom is an ask almost nobody reads without tapping "more".
    # Her brands lead with it; the owner's keep it at the end, which is his call to
    # change, not mine.
    #
    # A question is NOT moved to the top. It is a closing line - asking "what
    # did you take from this one?" before they have seen anything is nonsense.
    if not (cta or "").strip():
        out = list(body)
    elif (cred_prefix(brand) == "AR" and platform == "instagram"
          and ask != "question" and cta not in ASK_LINES):
        # ONLY THE COMMENT ASK LEADS. A closing question at the top is nonsense
        # ("what did you take from this?" before they have seen it), and on
        # YouTube it also became the TITLE - the same generic line on every
        # video, which is a spam signal. 10 Sept 2026.
        out = [cta, ""] + body
    else:
        out = body + ["", cta]
    if tags:
        out += [""] + tags
    return "\n".join(out).strip()


def title_for(path, caption):
    """A real, distinct YouTube title. Never the CTA, never a filename with
    underscores in it."""
    for l in body_lines(caption):
        if 12 <= len(l) <= 90:
            return l
    name = os.path.basename(path).rsplit(".", 1)[0]
    name = re.sub(r"^\d+_", "", name)
    name = re.sub(r"_\d+s$", "", name)
    return name.replace("-", " ").replace("_", " ").title()[:90]


# --------------------------------------------------------------------- YouTube

def set_cover(vid, cover, tok):
    """Give the Short the cover WE chose, not the frame YouTube liked.

    Verified working on a live Short 30 Aug - I had assumed Shorts could not take
    a custom thumbnail and that the channel was unverified. the owner said otherwise
    and he was right on both counts. Never assume a platform limit; test it.

    Silent on failure. A cover is a nice-to-have and must never turn a published
    video into a failed post.
    """
    if not cover or not os.path.exists(cover):
        return
    try:
        requests.post(
            "https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
            params={"videoId": vid}, timeout=T,
            headers={"Authorization": "Bearer " + tok,
                     "Content-Type": "image/jpeg"},
            data=open(cover, "rb").read())
    except Exception:
        pass


def youtube(path, caption, public_url, clip=None):
    """Uploads the 59-second cut when one exists, otherwise the full clip.

    30 Aug 2026. Three Shorts came back "Blocked - Copyright: the
    copyright-protected content detected is not allowed in Shorts longer than 60
    seconds". Under 60s YouTube licenses the same material; over it, Content ID
    blocks outright. The identical file posts fine to Instagram, Facebook and
    TikTok, so the fix belongs here and nowhere else - one platform, one rule.
    """
    yt = os.path.splitext(path)[0] + "__yt59" + os.path.splitext(path)[1]
    if os.path.exists(yt):
        path = yt
    cover = os.path.splitext(path)[0] + "__thumb.jpg"
    (cid, secret, refresh), missing = _cfg(
        "YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN",
        brand=brand_of(clip))
    if missing:
        return "not configured: " + ", ".join(missing)
    r = requests.post("https://oauth2.googleapis.com/token", timeout=T, data={
        "client_id": cid, "client_secret": secret,
        "refresh_token": refresh, "grant_type": "refresh_token"})
    d = _j(r)
    if "access_token" not in d:
        return f"token refresh failed {r.status_code}: {str(d)[:160]}"
    tok = d["access_token"]
    size = os.path.getsize(path)
    # #Shorts in the title is how a vertical clip is filed as a Short. YouTube
    # also infers it from the aspect ratio and length, but the tag removes the
    # doubt and costs nothing.
    title = (title_for(path, caption) + " #Shorts")[:95]
    body = {"snippet": {"title": title, "description": caption[:4900],
                        "categoryId": "22"},
            "status": {"privacyStatus": "public", "madeForKids": False,
                       "selfDeclaredMadeForKids": False}}
    init = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos",
        params={"uploadType": "resumable", "part": "snippet,status"},
        headers={"Authorization": f"Bearer {tok}",
                 "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Length": str(size),
                 "X-Upload-Content-Type": "video/*"},
        data=json.dumps(body), timeout=T)
    if "location" not in init.headers:
        return f"init failed {init.status_code}: {str(_j(init))[:200]}"
    with open(path, "rb") as fh:
        up = requests.put(init.headers["location"], data=fh, timeout=T * 8,
                          headers={"Content-Length": str(size),
                                   "Content-Type": "video/*"})
    d = _j(up)
    vid = d.get("id")
    if not vid:
        return f"upload failed {up.status_code}: {str(d)[:200]}"
    # Read it back. An upload can be accepted and then rejected for a claim.
    for _ in range(6):
        time.sleep(4)
        s = _j(requests.get("https://www.googleapis.com/youtube/v3/videos",
                            params={"id": vid, "part": "status"},
                            headers={"Authorization": f"Bearer {tok}"}, timeout=T))
        items = s.get("items") or []
        if items:
            st = items[0].get("status", {})
            if st.get("uploadStatus") in ("rejected", "failed"):
                return (f"YouTube rejected it: "
                        f"{st.get('rejectionReason') or st.get('failureReason')}")
            if st.get("uploadStatus") in ("uploaded", "processed"):
                set_cover(vid, cover, tok)
                return "posted", f"https://youtube.com/shorts/{vid}"
    set_cover(vid, cover, tok)
    return "posted", f"https://youtube.com/shorts/{vid}"


# ------------------------------------------------------------------- Instagram
def _ig_permalink(media_id, tok):
    for _ in range(8):
        d = _j(requests.get(f"https://graph.facebook.com/v21.0/{media_id}",
                            params={"fields": "permalink", "access_token": tok},
                            timeout=T))
        if d.get("permalink"):
            return d["permalink"]
        time.sleep(4)
    return None


def instagram(path, caption, public_url, clip=None, trial=False):
    """Publish a Reel. `trial=True` makes it a TRIAL REEL.

    3 SEPT 2026 - AND I HAD THIS WRONG. I told the owner the Trial toggle was
    app-only and that the seven hook variants had to be posted by hand. He
    pushed back ("me posting manually 7 times its a joke") and he was right:
    Meta's content-publishing docs expose `trial_params` on the container, and a
    trial reel created that way behaves exactly like one made in the app.

    I had reasoned from an assumption instead of reading the reference, and the
    conclusion I handed him was seven taps a day he did not owe. Check the
    documentation before telling him a thing cannot be automated.

    A trial reel goes to NON-FOLLOWERS ONLY, which is the whole mechanism -
    seven variants of one video compete for fresh strangers instead of splitting
    the same followers. graduation_strategy MANUAL keeps the winner his call,
    made in the app; SS_PERFORMANCE would let Instagram graduate one on its own,
    and which hook wins is exactly the thing he wants to see for himself.
    """
    (ig, tok), missing = _cfg("IG_USER_ID", "IG_ACCESS_TOKEN",
                              brand=brand_of(clip))
    if missing:
        return "not configured: " + ", ".join(missing)
    clash = collides_with_default(brand_of(clip), "IG_USER_ID")
    if clash:
        return clash
    if not public_url:
        return "no public URL available (KT_BASE_URL unset)"
    body = {"media_type": "REELS", "video_url": public_url,
            "caption": caption[:2100],
            "share_to_feed": "true", "access_token": tok}
    # THE COVER INSTAGRAM SHOWS ON THE GRID. 10 Sept 2026, brand-2 owner: "the thumbnail
    # doesn't look great on the grid ... its using the first scene all the time
    # but its usually when kevin is moving."
    #
    # She was right that it uses the first frame: this container never sent a
    # cover at all, so Instagram chose one, and frame zero of a man mid-sentence
    # is a blur. YouTube has had a chosen cover since 30 Aug; Instagram never
    # did, and the grid is the first thing a stranger sees.
    #
    # kt_render picks the sharpest frame in the hook window and writes the
    # offset beside the clip. thumb_offset is milliseconds into the video.
    #
    # AND IT MUST LAND WHILE THE HOOK IS STILL FULLY ON. 14 Sept 2026, the owner:
    # "make sure the hook its from the moment the clip starts for the
    # thumbnails". It is - the hook is drawn from frame zero - but it begins
    # fading at 2.7s and ends at 3.0s, and two clips carried covers at 2600ms
    # and 2800ms written by an older render whose probe range ran past the
    # fade. Their grid image shows the hook half faded out.
    #
    # The probe range was narrowed to 0.6-2.4s later, so nothing NEW can do
    # this - but the offset is read from a file written at render time, and
    # those files outlive the fix. Clamped here, where it is used, so a stale
    # one cannot reach Instagram.
    HOOK_FULL_MS = 2400
    try:
        ms_file = os.path.splitext(path)[0] + "__cover_ms.txt"
        if os.path.exists(ms_file):
            with open(ms_file) as fh:
                body["thumb_offset"] = str(min(int(fh.read().strip()),
                                               HOOK_FULL_MS))
    except Exception:
        pass                       # a cover is a nice-to-have, never a failure
    if trial:
        # share_to_feed is meaningless for a trial - it has no followers to
        # share to - and sending both is how you get a container that is
        # accepted and then behaves like an ordinary reel.
        body.pop("share_to_feed", None)
        body["trial_params"] = json.dumps({"graduation_strategy": "MANUAL"})
    r = requests.post(f"https://graph.facebook.com/v21.0/{ig}/media", timeout=T,
                      data=body)
    d = _j(r)
    if not d.get("id"):
        return f"container failed {r.status_code}: {str(d)[:200]}"
    cid = d["id"]
    # Instagram downloads the file itself; publishing early returns a 400.
    for _ in range(36):
        time.sleep(5)
        s = _j(requests.get(f"https://graph.facebook.com/v21.0/{cid}", timeout=T,
                            params={"fields": "status_code,status",
                                    "access_token": tok}))
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            return f"could not fetch the video: {str(s.get('status'))[:160]}"
    else:
        return "timed out waiting for Instagram to fetch the video (3 min)"
    p = requests.post(f"https://graph.facebook.com/v21.0/{ig}/media_publish",
                      data={"creation_id": cid, "access_token": tok}, timeout=T)
    d = _j(p)
    mid = d.get("id")
    if not mid:
        return f"publish failed {p.status_code}: {str(d)[:200]}"
    link = _ig_permalink(mid, tok)
    if not link:
        # THE 24 AUG BUG, caught instead of reported as success.
        return (f"Instagram returned media {mid} but the post could not be found "
                f"on the account - NOT confirmed posted")
    if trial:
        # ASK WHETHER IT IS ACTUALLY A TRIAL. A container that accepted
        # trial_params and published an ordinary reel is the worst outcome
        # available: it looks like a passing test and it quietly shows seven
        # near-identical reels to his followers. Instagram exposes is_trial on
        # the media, so there is no reason to guess.
        chk = _j(requests.get(f"https://graph.facebook.com/v21.0/{mid}",
                              params={"fields": "is_trial,media_product_type",
                                      "access_token": tok}, timeout=T))
        if chk.get("is_trial") is False:
            return (f"PUBLISHED BUT NOT A TRIAL - it went to followers. "
                    f"{link} - check trial_params before posting more")
        if "is_trial" not in chk:
            return ("posted (trial NOT verifiable - Instagram did not return "
                    "is_trial; open the app and confirm before posting the rest)",
                    link)
    return "posted", link


def instagram_story(path, public_url, clip=None):
    """Also put the reel in STORIES.

    8 Sept 2026, the owner: "even in the settings the share automatically to my
    stories in ig is on, i think because its API its not working, our reels are
    not geting shared in my stories at the same time."

    He is right. That account setting applies to reels created IN THE APP. A
    reel published through the Content Publishing API bypasses it completely,
    so every clip we have ever posted has skipped stories - and stories reach
    existing followers, which is the one audience an account with 119 of them
    can actually count on.

    This posts the same video as a STORIES media, which is a separate publish
    and not a reshare-with-sticker (the API offers no sticker). The follower
    sees the clip in stories either way, which is the point.

    Failure here is NEVER fatal. The reel is the post; the story is a bonus, and
    a story that does not go out must not make a successful reel look failed.
    """
    (ig, tok), missing = _cfg("IG_USER_ID", "IG_ACCESS_TOKEN",
                              brand=brand_of(clip))
    if missing:
        return "not configured"
    if not public_url:
        return "no public URL"
    # STORIES CAP VIDEO AT 60 SECONDS. 8 Sept 2026: stories were firing on every
    # post and failing on every post - "Instagram could not fetch the video" -
    # because our clips run 130-170s. Instagram was not failing to FETCH it, it
    # was refusing it for length, and the error says the wrong thing.
    #
    # We already cut a 59-second version of every clip for YouTube (Content ID
    # blocks our material in Shorts over 60s). That file is exactly what a story
    # needs. Use it when it exists; a clip already under the cap posts as-is.
    story_url = public_url
    if "__yt59" not in public_url:
        alt = public_url.replace(".mp4", "__yt59.mp4")
        try:
            # FOLLOW THE REDIRECT. 13 Sept 2026, the first bug the move to
            # GitHub introduced: a release download URL answers 302 and points
            # at objects.githubusercontent.com. requests.head() does NOT follow
            # redirects by default, so this saw 302, decided the 59-second cut
            # did not exist, and sent Instagram the full 86-second clip - which
            # it refused, and the story never posted. The file was there the
            # whole time. On Railway the URL was direct, so the bug could not
            # exist until the day the hosting changed.
            if requests.head(alt, timeout=20,
                             allow_redirects=True).status_code == 200:
                story_url = alt
        except Exception:
            pass
    r = _j(requests.post(f"https://graph.facebook.com/v21.0/{ig}/media", timeout=T,
                         data={"media_type": "STORIES", "video_url": story_url,
                               "access_token": tok}))
    cid = r.get("id")
    if not cid:
        return f"story container failed: {str(r)[:140]}"
    for _ in range(30):
        time.sleep(5)
        st = _j(requests.get(f"https://graph.facebook.com/v21.0/{cid}", timeout=T,
                             params={"fields": "status_code", "access_token": tok}))
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") == "ERROR":
            return ("story rejected - likely over the 60s story cap; "
                    "no 59s cut was available for this clip")
    else:
        return "story: timed out waiting for Instagram"
    p2 = _j(requests.post(f"https://graph.facebook.com/v21.0/{ig}/media_publish",
                          data={"creation_id": cid, "access_token": tok}, timeout=T))
    return "story posted" if p2.get("id") else f"story publish failed: {str(p2)[:120]}"


# -------------------------------------------------------------------- Facebook
def _fb_publish_epoch(d):
    """When Facebook says a reel was published, as unix time. None if unknown.

    Buried at status.publishing_phase.publish_time, ISO with a +0000 offset.
    """
    t = (((d.get("status") or {}).get("publishing_phase") or {})
         .get("publish_time"))
    if not t:
        return None
    try:
        return calendar.timegm(time.strptime(t[:19], "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return None


def _fb_feed_video(page, tok, path, caption):
    with open(path, "rb") as fh:
        r = requests.post(f"https://graph.facebook.com/v21.0/{page}/videos",
                          data={"access_token": tok,
                                "description": caption[:4900]},
                          files={"source": (os.path.basename(path), fh, "video/mp4")},
                          timeout=T * 8)
    d = _j(r)
    if not d.get("id"):
        return f"upload failed {r.status_code}: {str(d)[:220]}"
    return "posted", f"https://facebook.com/{d['id']}"


def facebook(path, caption, public_url, clip=None):
    """Publish as a Reel. Falls back to a feed video if Reels is unavailable.

    Reels, not feed video, because a Page feed video reaches almost nobody now
    and Reels is the surface Facebook is pushing. Both need pages_manage_posts;
    if it is missing Facebook answers (#100) and that is said plainly rather
    than dressed up as a network error.
    """
    (page, tok), missing = _cfg("FB_PAGE_ID", "FB_ACCESS_TOKEN",
                                brand=brand_of(clip))
    if missing:
        return "not configured: " + ", ".join(missing)
    clash = collides_with_default(brand_of(clip), "FB_PAGE_ID")
    if clash:
        return clash
    size = os.path.getsize(path)
    t0 = time.time()
    s = _j(requests.post(f"https://graph.facebook.com/v21.0/{page}/video_reels",
                         data={"upload_phase": "start", "access_token": tok},
                         timeout=T))
    vid, up_url = s.get("video_id"), s.get("upload_url")
    if not vid or not up_url:
        err = ((s.get("error") or {}).get("message") or str(s))[:200]
        alt = _fb_feed_video(page, tok, path, caption)
        if isinstance(alt, tuple):
            return alt
        return f"reels start failed: {err} | feed fallback: {alt}"
    with open(path, "rb") as fh:
        u = requests.post(up_url, data=fh, timeout=T * 8,
                          headers={"Authorization": f"OAuth {tok}",
                                   "offset": "0", "file_size": str(size),
                                   "Content-Type": "application/octet-stream"})
    ud = _j(u)
    if not ud.get("success") and u.status_code not in (200, 201):
        return f"reel upload failed {u.status_code}: {str(ud)[:200]}"
    f = _j(requests.post(f"https://graph.facebook.com/v21.0/{page}/video_reels",
                         data={"access_token": tok, "video_id": vid,
                               "upload_phase": "finish",
                               "video_state": "PUBLISHED",
                               "description": caption[:4900]}, timeout=T))
    if not f.get("success"):
        err = ((f.get("error") or {}).get("message") or str(f))[:220]
        return f"reel publish refused: {err}"
    # Read it back, AND CHECK WHEN IT WAS PUBLISHED.
    #
    # 3 Sept 2026. the owner: "the only platform didnt post that clips is FB, is
    # that intentional?" It was not. Four clips that day reported "posted" and
    # none of them appeared on the Page. Every one came back with a real
    # video_id and a real permalink - to a reel published on 26, 27, 28 and 29
    # August. Facebook fingerprints the video, recognises one it already has,
    # and hands back THE ORIGINAL instead of creating a second reel. Success,
    # a permalink, and nothing new on the Page.
    #
    # So a Facebook "success" proves the upload was accepted, not that anything
    # was published. The only thing that distinguishes the two is the publish
    # time, which this code was already asking for inside `status` and throwing
    # away. Compare it to when this run started: a reel older than that existed
    # before we uploaded, and this clip is a REPEAT.
    #
    # That makes Facebook the only honest duplicate detector we have - the
    # other three will publish the same clip again without a word. See
    # duplicate_gate().
    for _ in range(8):
        time.sleep(4)
        d = _j(requests.get(f"https://graph.facebook.com/v21.0/{vid}",
                            params={"fields": "permalink_url,status",
                                    "access_token": tok}, timeout=T))
        if d.get("permalink_url"):
            when = _fb_publish_epoch(d)
            if when and when < t0 - 300:
                day = time.strftime("%d %b", time.localtime(when))
                return (f"DUPLICATE - Facebook already published this on {day}",
                        "https://facebook.com" + d["permalink_url"])
            return "posted", "https://facebook.com" + d["permalink_url"]
    return "posted", f"https://facebook.com/reel/{vid}"


# ---------------------------------------------------------------------- TikTok
def tiktok(path, caption, public_url, clip=None):
    (key, secret, refresh), missing = _cfg(
        "TT_CLIENT_KEY", "TT_CLIENT_SECRET", "TT_REFRESH_TOKEN",
        brand=brand_of(clip))
    if missing:
        return "not configured: " + ", ".join(missing)
    r = requests.post("https://open.tiktokapis.com/v2/oauth/token/", timeout=T,
                      headers={"Content-Type": "application/x-www-form-urlencoded"},
                      data={"client_key": key, "client_secret": secret,
                            "grant_type": "refresh_token", "refresh_token": refresh})
    d = _j(r)
    if "access_token" not in d:
        return f"token refresh failed {r.status_code}: {str(d)[:160]}"
    tok = d["access_token"]
    size = os.path.getsize(path)
    # TIKTOK'S CHUNK ARITHMETIC IS NOT ceil(), 1 Sept 2026. Six clips came back
    # "init failed 400: The total chunk count is invalid", and every one of them
    # was a LARGE file - 133s to 166s. With CHUNK=60MB a 65MB clip gave
    # ceil(65/60) = 2, but TikTok computes floor(video_size / chunk_size) = 1 and
    # rejects any count that disagrees. Its final chunk is allowed to run over
    # chunk_size, which is exactly why the count is a floor and not a ceiling.
    #
    # So: one chunk whenever the file fits under the 64MB ceiling, otherwise
    # split into equal chunks that divide cleanly and let the last one absorb the
    # remainder. This is why the owner got no TikTok draft while the other three
    # platforms posted the same clip fine - the failure was ours, on his longest
    # and best clips only.
    if size <= CHUNK:
        chunk, count = size, 1
    else:
        count = math.ceil(size / CHUNK)
        chunk = size // count
    last = size - chunk * (count - 1)
    init = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/",
        headers={"Authorization": f"Bearer {tok}",
                 "Content-Type": "application/json; charset=UTF-8"},
        data=json.dumps({"source_info": {
            "source": "FILE_UPLOAD", "video_size": size,
            "chunk_size": chunk, "total_chunk_count": count}}), timeout=T)
    d = _j(init)
    url = (d.get("data") or {}).get("upload_url")
    publish_id = (d.get("data") or {}).get("publish_id")
    if not url:
        return f"init failed {init.status_code}: {str(d)[:200]}"
    with open(path, "rb") as fh:
        for i in range(count):
            blob = fh.read(last if i == count - 1 else chunk)
            lo = i * chunk
            up = requests.put(url, data=blob, timeout=T * 8, headers={
                "Content-Type": "video/mp4",
                "Content-Length": str(len(blob)),
                "Content-Range": f"bytes {lo}-{lo + len(blob) - 1}/{size}"})
            if up.status_code not in (200, 201, 206):
                return f"chunk {i+1}/{count} failed {up.status_code}: {up.text[:160]}"

    # ASK TIKTOK WHAT ACTUALLY HAPPENED. 9 Sept 2026, brand-2 owner: "i have not gotten
    # any videos in my notifications on tiktok today" - while the board showed
    # seventeen consecutive successes, five of them hers.
    #
    # This function used to return the success string the instant the last chunk
    # uploaded. But the upload is only the HANDOFF: TikTok then transcodes and
    # delivers asynchronously, and it can fail after a clean 200 - unsupported
    # frame rate, duration limits, a revoked scope, spam heuristics. We were
    # reporting "in your inbox" having never asked whether it arrived. Same
    # shape as every other bug this system has had.
    #
    # init returns a publish_id; /status/fetch/ turns it into the truth.
    # SEND_TO_USER_INBOX is the terminal success for an inbox upload.
    if not publish_id:
        return "uploaded, but TikTok returned no publish_id - cannot confirm"
    import time as _t
    last = {}
    for attempt in range(6):
        _t.sleep(2 + attempt * 2)
        st = requests.post(
            "https://open.tiktokapis.com/v2/post/publish/status/fetch/",
            headers={"Authorization": f"Bearer {tok}",
                     "Content-Type": "application/json; charset=UTF-8"},
            data=json.dumps({"publish_id": publish_id}), timeout=T)
        last = _j(st)
        info = (last.get("data") or {})
        status = info.get("status")
        if status in ("SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"):
            return "in your TikTok inbox - open TikTok and tap post"
        if status == "FAILED":
            reason = info.get("fail_reason") or str(last)[:160]
            return f"TikTok REJECTED it: {reason}"
    return ("uploaded but TikTok still processing after ~40s - "
            f"last status {str((last.get('data') or {}).get('status'))[:60]}")


def already_on_instagram(caption, brand=""):
    """Is a post with this caption ALREADY live on THIS BRAND'S account?

    The board's own done-flags are not trustworthy: they are set by this system,
    and the owner also posts by hand from his phone, so the two drift apart. On
    24 Aug that drift published a clip he had already posted himself. Instagram
    is the only thing that knows what is really on the account, so ask it.

    Matched on the first distinctive line of the caption rather than the whole
    string, because he edits wording on the phone before posting.
    """
    (ig, tok), missing = _cfg("IG_USER_ID", "IG_ACCESS_TOKEN", brand=brand)
    if missing or not caption:
        return None                      # cannot tell - do not claim either way
    lines = body_lines(caption)
    if not lines:
        return None
    needle = lines[0][:45].lower()
    if len(needle) < 12:
        return None
    try:
        for m in recent_instagram(tok, ig):
            if needle in (m.get("caption") or "").lower():
                return m.get("permalink") or "already posted"
    except Exception:
        return None
    return False


def recent_instagram(tok, ig, want=150):
    """The account's own history, paged. 50 was not enough - it is one month of
    posting at 5 a day, and the whole point is to compare against everything."""
    out, url = [], (f"https://graph.facebook.com/v21.0/{ig}/media"
                    f"?fields=caption,permalink,timestamp&limit=100"
                    f"&access_token={tok}")
    while url and len(out) < want:
        d = _j(requests.get(url, timeout=T))
        out += d.get("data", [])
        url = (d.get("paging") or {}).get("next")
    return out


def audit_instagram(clips):
    """Which clips claim Instagram success but are not on their OWN account?

    Returns the indexes. This is the answer to the 24 Aug failure: a clip was
    marked posted, done, and finished, and nothing was ever on the profile. The
    system that publishes cannot also be the system that certifies - so once an
    hour the account itself is asked, and anything that cannot be found is put
    back into the queue with the truth written next to it.

    Uses the same matcher as the pre-post duplicate guard, deliberately. If this
    says a post is missing, that guard will agree, so re-posting cannot produce
    a duplicate: the two can never disagree about what is on the account.

    30 AUG, PER BRAND - AND THIS ONE WOULD HAVE HURT. It asked ONE account about
    EVERY clip. The moment a second brand posts, its clips are not on the
    account being asked, so the audit calls every one of them missing, clears
    done, clears posted_at, clears scheduled_at - and the planner gives it a new
    slot and posts it AGAIN. Once an hour. Forever. The guard that exists to
    stop exactly that (already_on_instagram) was reading the same wrong account,
    so it would have agreed every time. Brand two would have spammed its own
    followers with the same six clips.

    Now each set of credentials is asked about its own clips only, and results
    are cached per (account, token) so twelve KT_* folders still cost one fetch.
    A brand whose credentials are not set is SKIPPED: no account to ask means no
    accusation. Never accuse on silence.
    """
    by_prefix = {}
    for i, c in enumerate(clips):
        if (c.get("status") or {}).get("instagram") != "posted":
            continue
        by_prefix.setdefault(cred_prefix(brand_of(c)), []).append(i)

    cache, bad = {}, []
    for prefix, idxs in by_prefix.items():
        (ig, tok), missing = _cfg("IG_USER_ID", "IG_ACCESS_TOKEN", brand=prefix)
        if missing:
            continue
        if (ig, tok) not in cache:
            try:
                media = recent_instagram(tok, ig)
                cache[(ig, tok)] = (
                    [(m.get("caption") or "").lower() for m in media],
                    {(m.get("permalink") or "").rstrip("/").rsplit("/", 1)[-1]
                     for m in media if m.get("permalink")})
            except Exception:
                cache[(ig, tok)] = None   # cannot tell - never accuse on a timeout
        if not cache[(ig, tok)]:
            continue
        haystack, shortcodes = cache[(ig, tok)]
        if not haystack:
            continue
        for i in idxs:
            c = clips[i]
            # IDENTIFY BY PERMALINK, NOT BY CAPTION. 3 Sept 2026: this audit
            # matched a post by the first line of its caption, and the owner found
            # the same clip published twice - "I was in the room when they built
            # it" and "I worked with the credit card companies" are the SAME
            # video. The cause was mine: I rewrote every caption twice, so the
            # audit went looking for the new first line, could not find it on a
            # post made with the old one, declared it missing and re-queued it.
            #
            # A caption is editable - by me, and by the owner on his phone. A
            # permalink is not. When we recorded one at publish time, that is
            # the identity of the post and the only thing worth checking.
            link = (c.get("links") or {}).get("instagram") or ""
            code = link.rstrip("/").rsplit("/", 1)[-1] if "/reel/" in link \
                or "/p/" in link else ""
            if code:
                if code not in shortcodes:
                    bad.append(i)
                continue
            # No permalink recorded (older posts): fall back to the caption, but
            # only when it is still the caption we posted WITH. caption_at_post
            # is written at publish time and never rewritten afterwards.
            text = c.get("caption_at_post") or c.get("caption", "")
            lines = body_lines(text)
            if not lines:
                continue
            needle = lines[0][:45].lower()
            if len(needle) < 12:
                continue
            if not any(needle in h for h in haystack):
                bad.append(i)
    return sorted(bad)


ADAPTERS = {"tiktok": tiktok, "instagram": instagram,
            "youtube": youtube, "facebook": facebook}
ENABLED = [p.strip() for p in
           os.environ.get("KT_PLATFORMS", "instagram,facebook").split(",")
           if p.strip()]



def backfill_covers(clips, media, limit=5):
    """Give already-published Shorts the cover we chose. A few per run.

    31 Aug 2026. Twenty-four live Shorts were still on YouTube's own auto-picked
    frame - covers reading "AS THE ICE" and "TO BE A CAP" on videos doing a
    thousand views each - because set_cover only existed from the day it shipped
    and everything before that predates it.

    PACED ON PURPOSE. Fixing them in one pass returned 429 "uploaded too many
    thumbnails recently" on 23 of 24. The daily allowance is small and
    undocumented, and spending it in a burst also starves that day's scheduled
    posts, which set their cover at publish time. So: a handful per run, stop
    dead on the first 429, and mark each one so it is never retried.

    Runs on the server precisely so it needs nobody's laptop and nobody's
    attention. the owner does not run commands and should not have to.

    Returns the files it covered.
    """
    (cid, secret, refresh), missing = _cfg(
        "YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")
    if missing:
        return []
    r = requests.post("https://oauth2.googleapis.com/token", timeout=T, data={
        "client_id": cid, "client_secret": secret,
        "refresh_token": refresh, "grant_type": "refresh_token"})
    tok = _j(r).get("access_token")
    if not tok:
        return []
    done = []
    for c in clips:
        if len(done) >= limit:
            break
        if c.get("cover_set") or c.get("file", "").startswith("AR_"):
            continue
        link = (c.get("links") or {}).get("youtube") or ""
        if "/shorts/" not in link:
            continue
        stem = os.path.splitext(c["file"])[0]
        cover = next((os.path.join(media, stem + sfx)
                      for sfx in ("__yt59__thumb.jpg", "__thumb.jpg")
                      if os.path.exists(os.path.join(media, stem + sfx))), None)
        if not cover:
            continue
        try:
            resp = requests.post(
                "https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
                params={"videoId": link.rsplit("/", 1)[-1]}, timeout=T,
                headers={"Authorization": "Bearer " + tok,
                         "Content-Type": "image/jpeg"},
                data=open(cover, "rb").read())
        except Exception:
            break
        if resp.status_code == 429:
            break                      # out of allowance; try again tomorrow
        if resp.status_code < 300:
            c["cover_set"] = True
            done.append(c["file"])
        else:
            c["cover_set"] = True      # a permanent failure must not loop daily
    return done


def publish(clip, path, public_url, only=None):
    """Run every enabled adapter. Returns (status_by_platform, link_by_platform).

    `only` restricts the run to a set of platform names - that is what a retry
    uses so a clip that reached Instagram but not Facebook re-attempts Facebook
    alone, and can never double-post the one that worked.
    """
    out, links = {}, dict(clip.get("links") or {})

    # FACEBOOK GOES FIRST, BECAUSE IT IS THE ONLY ONE THAT CAN SAY "ALREADY".
    #
    # 3 Sept 2026. The board's history begins on 30 August - everything posted
    # before that lost its posted_at, so the planner believed those clips had
    # never gone out and scheduled them all over again. Instagram, YouTube and
    # TikTok published the repeats without complaint. Facebook fingerprinted
    # each one, matched a reel it already had, and returned the ORIGINAL, which
    # is why Facebook looked like the platform that had stopped working when it
    # was the only one telling the truth.
    #
    # Facebook ran LAST, so by the time it noticed, Instagram had already
    # published. Running it first turns that fingerprint into a gate: if
    # Facebook says it already has this video, nothing else posts.
    order = ([p for p in ENABLED if p == "facebook"]
             + [p for p in ENABLED if p != "facebook"])
    for name in order:
        if name != "facebook" and str(out.get("facebook", "")).startswith(
                "DUPLICATE"):
            out[name] = "skipped - already published, see Facebook"
            continue
        if only and name not in only:
            if clip.get("status", {}).get(name):
                out[name] = clip["status"][name]
            continue
        fn = ADAPTERS.get(name)
        if not fn:
            out[name] = "unknown platform"
            continue
        if clip.get("status", {}).get(name) == "posted":
            out[name] = "posted"          # never double-post
            continue
        if name == "instagram":
            live = already_on_instagram(clip.get("caption", ""), brand_of(clip))
            if live:
                out[name] = "posted"
                links[name] = live if str(live).startswith("http") else ""
                continue
        try:
            # EACH PLATFORM GETS ITS OWN CTA. See caption_for: Instagram and
            # TikTok cannot carry a clickable link, YouTube and Facebook can,
            # and we were making people on the latter two comment for nothing.
            cap = caption_for(name, clip.get("caption", ""), brand_of(clip),
                              clip.get("cta_keyword", ""),
                              clip.get("cta_kind", ""),
                              clip.get("cta_variant"))
            res = fn(path, cap, public_url, clip)
        except Exception as e:
            res = f"{type(e).__name__}: {e}"
        if isinstance(res, tuple):
            out[name], links[name] = res[0], res[1]
        else:
            out[name] = res
        # A reel that posted also goes to stories. Bonus, never fatal - wrapped
        # so a story failure cannot turn a good reel into a bad status.
        if name == "instagram" and out.get(name) == "posted" and STORIES_ON:
            try:
                out["instagram_story"] = instagram_story(path, public_url, clip)
            except Exception as e:
                out["instagram_story"] = f"story error: {type(e).__name__}"
    return out, links


def recent_facebook_reels(page, tok, limit=100):
    """Reel ids on a Page, newest first, with when each was published."""
    out, url = {}, f"https://graph.facebook.com/v21.0/{page}/video_reels"
    params = {"fields": "id,created_time", "limit": 50, "access_token": tok}
    while url and len(out) < limit:
        d = _j(requests.get(url, params=params, timeout=T))
        if d.get("error"):
            raise RuntimeError((d["error"].get("message") or "")[:160])
        for m in d.get("data", []):
            out[str(m.get("id"))] = m.get("created_time", "")
        url = ((d.get("paging") or {}).get("next"))
        params = None
    return out


def audit_facebook(clips):
    """Which clips claim Facebook success but are not on the Page?

    3 SEPT 2026 - AND THE NOTE THAT SAID THIS WAS IMPOSSIBLE WAS WRONG.
    It was written after /feed returned "(#10) requires pages_read_engagement",
    and I concluded from that one refusal that Facebook could not be audited at
    all. Facebook was left as the single unverified platform for ten days.
    /feed is refused; /video_reels, /videos and /posts all answer with the token
    we already hold. One failing endpoint is not a closed door, and I should
    have tried the next one before writing it off.

    What that blindness cost: four clips on 3 Sept reported "posted" and none
    reached the Page. Instagram is audited hourly and would have caught the
    equivalent in an hour.

    Same discipline as audit_instagram: identify by the id recorded at publish
    time, never by caption; skip a brand with no credentials; never accuse on a
    network error.
    """
    by_prefix = {}
    for i, c in enumerate(clips):
        if str((c.get("status") or {}).get("facebook", "")) != "posted":
            continue
        by_prefix.setdefault(cred_prefix(brand_of(c)), []).append(i)

    cache, bad = {}, []
    for prefix, idxs in by_prefix.items():
        (page, tok), missing = _cfg("FB_PAGE_ID", "FB_ACCESS_TOKEN",
                                    brand=prefix)
        if missing:
            continue
        if page not in cache:
            try:
                cache[page] = recent_facebook_reels(page, tok)
            except Exception:
                cache[page] = None        # cannot tell - do not accuse
        live = cache[page]
        if not live:
            continue
        for i in idxs:
            link = (clips[i].get("links") or {}).get("facebook") or ""
            m = re.search(r"/reel/(\d+)", link) or re.search(r"/(\d{6,})", link)
            if not m:
                continue                  # no id recorded - nothing to check
            if m.group(1) not in live:
                bad.append(i)
    return bad
