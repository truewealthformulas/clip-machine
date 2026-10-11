#!/usr/bin/env python3
"""Daily offer story cards (1080x1920), the Success Club look.

Two kinds per offer:
  auto_*    posted by the machine every day - ends on "Reply <KEYWORD>"; the
            owner's DM auto-reply sends the link (the API cannot add link stickers)
  sticker_* for the owner to post from the app with a LINK STICKER in the
            marked space (the only way a story link can be added)
Each in two looks: photo (a still of Kevin) and text.

Rules (agents/AGENT_RULES.md): small "Ad · affiliate" label on every card; the
nutrition card names the product, never a health benefit; no herpes book.

    python factory/make_story_cards.py <frames_dir> <out_dir>    (frames: kev_suit/kev_hat/kev_blue.png)
"""
import os
import sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(ROOT, "factory", "assets", "mont_black.ttf")
W, H = 1080, 1920
GOLD, INK, WHITE, GREY = (245, 197, 24), (12, 12, 14), (255, 255, 255), (150, 150, 150)

OFFERS = {
    "training": {"kicker": "FREE TRAINING", "title": ["KEVIN'S FREE", "TRAINING"],
                 "sub": "Your Wish Is Your Command", "kw": "TRAINING", "photo": "kev_suit.png"},
    "gin": {"kicker": "GLOBAL INFORMATION NETWORK", "title": ["THINK LIKE", "THE SUCCESSFUL"],
            "sub": "Kevin's network for money & success thinking", "kw": "GIN", "photo": "kev_hat.png"},
    "book": {"kicker": "THE BOOK", "title": ["YOUR WISH IS", "YOUR COMMAND"],
             "sub": "The book behind Kevin's teaching", "kw": "BOOK", "photo": "kev_blue.png"},
    "daily": {"kicker": "DAILY NUTRITION", "title": ["KEVIN'S DAILY", "NUTRITION PICK"],
              "sub": "World's Best Nutritionals", "kw": "DAILY", "photo": "kev_suit.png"},
}


def f(size):
    return ImageFont.truetype(FONT, size)


def fit(d, text, size, maxw):
    while size > 30 and d.textlength(text, font=f(size)) > maxw:
        size -= 2
    return f(size)


def center(d, y, text, font, fill):
    d.text(((W - d.textlength(text, font=font)) / 2, y), text, font=font, fill=fill)


def base(photo):
    im = Image.new("RGB", (W, H), INK)
    if photo:
        src = Image.open(photo).convert("RGB")
        top = src.crop((0, 120, W, 900))            # his face, above the burned captions
        im.paste(top, (0, 200))
        # fade the photo into the black below it
        fade = Image.new("L", (W, 330))
        fd = ImageDraw.Draw(fade)
        for y in range(330):
            fd.line((0, y, W, y), fill=int(255 * y / 330))
        im.paste(Image.new("RGB", (W, 330), INK), (0, 650), fade)
        im.paste(Image.new("RGB", (W, H - 980), INK), (0, 980))
        im.paste(Image.new("RGB", (W, 200), INK), (0, 0))
    return im


def card(key, kind, photo_dir):
    o = OFFERS[key]
    im = base(os.path.join(photo_dir, o["photo"]) if photo_dir else None)
    d = ImageDraw.Draw(im)
    y = 860 if photo_dir else 560
    k = f(34)
    center(d, y, o["kicker"], k, GOLD)
    d.rectangle((W / 2 - 70, y + 58, W / 2 + 70, y + 66), fill=GOLD)
    y += 100
    tf = min((fit(d, t, 104, W - 110) for t in o["title"]), key=lambda x: x.size)
    for i, t in enumerate(o["title"]):
        center(d, y, t, tf, WHITE if i == 0 else GOLD)
        y += int(tf.size * 1.15)
    center(d, y + 20, o["sub"], fit(d, o["sub"], 40, W - 140), GREY)
    y += 120
    if kind == "auto":
        box_h = 190
        d.rounded_rectangle((90, y, W - 90, y + box_h), radius=30, outline=GOLD, width=5)
        center(d, y + 32, "REPLY", f(40), WHITE)
        center(d, y + 86, o["kw"], fit(d, o["kw"], 80, W - 260), GOLD)
        center(d, y + box_h + 30, "and I'll send you the link", f(38), WHITE)
    else:
        center(d, y + 10, "TAP THE LINK BELOW", f(46), WHITE)
        ax = W // 2
        d.polygon([(ax - 40, y + 90), (ax + 40, y + 90), (ax, y + 150)], fill=GOLD)
        # the empty space here is where the owner drops the link sticker
    center(d, 1760, "Ad · affiliate link · The Success Club", f(26), GREY)
    return im


def main():
    frames, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for key in OFFERS:
        for kind in ("auto", "sticker"):
            for look in ("photo", "text"):
                # JPEG: Instagram's API only accepts JPEG for image stories
                card(key, kind, frames if look == "photo" else None).save(
                    os.path.join(out, f"{kind}_{key}_{look}.jpg"), quality=88, optimize=True)
    print(sorted(os.listdir(out)))


if __name__ == "__main__":
    main()
