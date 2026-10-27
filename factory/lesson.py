#!/usr/bin/env python3
"""SUCCESS CLUB LESSON VIDEOS - no Kevin footage, nothing to match as a duplicate.

26 Oct 2026. Instagram flagged reels cut from Kevin's interviews as "duplicate
content or content you don't have the rights to" (several pages post the same
moments). The owner: "lets find another option, continue posting videos".

A lesson video teaches ONE of Kevin's principles in our own words: big navy and
gold text, one line at a time, read by a neural narrator voice (edge-tts), then
the closing question card and the follow line. 20-35 s. The caption carries
"AI voice" so the narration is disclosed.

    python factory/lesson.py preview          # renders the preview lessons below
    python factory/lesson.py render FILE.json # {"lines": [...], "question": "...", "out": "x.mp4"}
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HERE)        # appended: factory/queue.py must not shadow stdlib queue
import restyle as R  # noqa: E402  (fonts, colours, outro card)

W, H = 1080, 1920
VOICE = os.environ.get("LESSON_VOICE", "en-US-AndrewNeural")
RATE = os.environ.get("LESSON_RATE", "+4%")
FONT = R.FONT

PREVIEW = [
    {"label": "THE SUCCESS CLUB · LESSON",
     "lines": ["Most people chase money.",
               "Kevin Trudeau says that's exactly why they never catch it.",
               "Money follows a person who solves problems for others.",
               "So stop asking, how do I get rich?",
               "Start asking, whose problem can I solve today?"],
     "question": "Whose problem could you solve this week?",
     "out": "lesson_preview_1.mp4"},
    {"label": "THE SUCCESS CLUB · LESSON",
     "lines": ["Kevin Trudeau says the words I am are the most powerful words you speak.",
               "Whatever follows them, your mind starts working to make true.",
               "I am broke. I am tired. I am not good enough.",
               "Your brain hears every one of those as an instruction.",
               "Change the sentence, and you start changing the result."],
     "question": "What do you say after the words I am?",
     "out": "lesson_preview_2.mp4"},
]


def sh(*a):
    subprocess.run(a, check=True)


def dur(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", path], capture_output=True, text=True,
                                check=True).stdout.strip())


def background(out):
    """Navy with a soft gold glow low on the frame, and a faint vignette."""
    top, bot = R.INK, (20, 34, 78)
    im = Image.new("RGB", (W, H))
    px = ImageDraw.Draw(im)
    for y in range(H):
        t = y / (H - 1)
        px.line((0, y, W, y), fill=tuple(int(top[k] + (bot[k] - top[k]) * t) for k in range(3)))
    glow = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(glow)
    d.ellipse((140, 1500, W - 140, 2300), fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(200))
    gold = Image.new("RGB", (W, H), (120, 96, 20))
    im = Image.composite(gold, im, glow)
    im.save(out)


def wrap(d, text, f, maxw):
    out, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= maxw or not cur:
            cur = t
        else:
            out.append(cur)
            cur = w
    return out + ([cur] if cur else [])


def frame(bg, label, text, idx, total, out):
    """One line of the lesson: label on top, the line big in the middle, progress dots."""
    im = Image.open(bg).convert("RGB")
    d = ImageDraw.Draw(im)
    lf = ImageFont.truetype(FONT, 34)
    lw = d.textlength(label, font=lf)
    d.text(((W - lw) / 2, 230), label, font=lf, fill=R.GOLD)
    d.line((90, 250, (W - lw) / 2 - 24, 250), fill=R.GOLD, width=2)
    d.line(((W + lw) / 2 + 24, 250, W - 90, 250), fill=R.GOLD, width=2)
    text = text.upper()
    for size in range(104, 56, -4):
        f = ImageFont.truetype(FONT, size)
        lines = wrap(d, text, f, W - 150)
        if len(lines) <= 5:
            break
    lh = int(f.size * 1.2)
    y = (H - lh * len(lines)) // 2 - 40
    # the key word of the last line in gold, the rest white
    for i, l in enumerate(lines):
        w = d.textlength(l, font=f)
        d.text(((W - w) / 2, y), l, font=f, fill=R.GOLD if (i == len(lines) - 1 and idx == total - 1) else R.WHITE)
        y += lh
    cx = W // 2 - (total - 1) * 18
    for k in range(total):
        r = 8
        x = cx + k * 36
        d.ellipse((x - r, 1600 - r, x + r, 1600 + r), fill=R.GOLD if k <= idx else (70, 80, 110))
    cf = ImageFont.truetype(FONT, 28)
    credit = "A PRINCIPLE BY KEVIN TRUDEAU · AI VOICE"
    cw = d.textlength(credit, font=cf)
    d.text(((W - cw) / 2, 1700), credit, font=cf, fill=(170, 178, 200))
    im.save(out)


async def _tts(text, out):
    import edge_tts
    await edge_tts.Communicate(text, VOICE, rate=RATE).save(out)


def render(spec, outdir):
    tmp = tempfile.mkdtemp()
    bg = os.path.join(tmp, "bg.png")
    background(bg)
    lines = spec["lines"]
    segs = []
    for i, line in enumerate(lines):
        mp3 = os.path.join(tmp, f"l{i}.mp3")
        asyncio.run(_tts(line, mp3))
        png = os.path.join(tmp, f"l{i}.png")
        frame(bg, spec.get("label", "THE SUCCESS CLUB"), line, i, len(lines), png)
        seg = os.path.join(tmp, f"s{i}.mp4")
        t = dur(mp3) + 0.35
        # slow push-in on each card so the frame is never static
        sh("ffmpeg", "-loglevel", "error", "-y", "-loop", "1", "-framerate", "30", "-i", png, "-i", mp3,
           "-filter_complex",
           f"[0:v]scale=1188:2112,zoompan=z='min(1+0.0009*on,1.06)':x='iw/2-(iw/zoom/2)':"
           f"y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps=30,fade=t=in:st=0:d=0.18,format=yuv420p[v];"
           f"[1:a]aresample=48000,aformat=channel_layouts=stereo,apad=pad_dur=0.35[a]",
           "-map", "[v]", "-map", "[a]", "-t", f"{t:.2f}", "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "20", "-c:a", "aac", "-b:a", "160k", seg)
        segs.append(seg)
    card = os.path.join(tmp, "outro.png")
    R.outro_png(spec.get("question", ""), card)
    qmp3 = os.path.join(tmp, "q.mp3")
    asyncio.run(_tts(spec.get("question") or "Follow for a new success principle every day.", qmp3))
    oseg = os.path.join(tmp, "outro.mp4")
    sh("ffmpeg", "-loglevel", "error", "-y", "-loop", "1", "-framerate", "30", "-i", card, "-i", qmp3,
       "-filter_complex", "[0:v]fade=t=in:st=0:d=0.25,format=yuv420p[v];"
       "[1:a]aresample=48000,aformat=channel_layouts=stereo,apad=pad_dur=1.6[a]",
       "-map", "[v]", "-map", "[a]", "-t", f"{dur(qmp3) + 1.6:.2f}", "-c:v", "libx264",
       "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", oseg)
    segs.append(oseg)
    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as fh:
        fh.writelines(f"file '{s}'\n" for s in segs)
    out = os.path.join(outdir, spec["out"])
    sh("ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
       "-c", "copy", "-movflags", "+faststart", out)
    print(f"rendered {out} ({dur(out):.1f}s)", flush=True)
    return out


if __name__ == "__main__":
    od = os.environ.get("LESSON_OUT", ".")
    os.makedirs(od, exist_ok=True)
    if len(sys.argv) > 1 and sys.argv[1] == "render":
        render(json.load(open(sys.argv[2])), od)
    else:
        for s in PREVIEW:
            render(s, od)
