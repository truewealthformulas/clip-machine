# kt-machine

Posts Kevin Trudeau clips to Instagram, Facebook, YouTube and TikTok on a
schedule, for two separate accounts, without a server and without a bill.

## Why it looks like this

It used to run on Railway as a service awake 24 hours a day so it could be
useful for the few seconds a day something was actually due. That cost real
money — $13.79 against a $15 cap, heading for $28. GitHub Actions is free
without limit on a public repository, so the same work became a cron job.

Two consequences, both good:

- **It costs nothing.** No server, no volume, no egress.
- **It does not need a Mac.** The machine no longer stops when a laptop closes.

## How it runs

`.github/workflows/post.yml` fires every 20 minutes. Each run:

1. Reads `state/manifest.json` — the record of every clip and what has happened
   to it.
2. Schedules anything unscheduled onto that account's own slot grid.
3. Publishes anything whose slot has arrived.
4. Commits the state back, so the next run knows what the last one did.

Concurrency is locked to one run at a time. Two overlapping passes would each
see the same clip as due and publish it twice.

## Where the videos are

In a GitHub Release tagged `media`, not in the repository. A release asset has
a public URL, which is the whole reason a server was needed in the first place:
Instagram's API will not accept bytes, it fetches from a URL.

`run_once.py` downloads only the single clip it is about to publish. A checkout
carrying three gigabytes of video on every scheduled run would be its own kind
of waste.

## What must never be broken

- **The two accounts never mix.** `AR_*` is Brand 2, everything else is
  Kevin Trudeau Wisdom. Separate credentials, separate slot grids, separate
  keywords. `poster` refuses to post a clip to an account that is not its own.
- **A published clip is never re-cut.** `posted_at` is the record; nothing
  rewrites a video that is already live on four platforms.
- **One source video per day, at most twice, never twice in a row.** Four clips
  from one interview in one day reads as one video sawn up, because it is.
- **At least 45 minutes between two posts by the same account.** A backlog is
  trickled out, never emptied at once.

## Layout

```
run_once.py                 one scheduling pass, then exit
engine/main.py              scheduling, slots, spacing, state
engine/poster.py            the four platforms, and the fence between accounts
engine/pages.py             the read-only board
engine/metrics.py           engagement sampling
state/manifest.json         every clip and what happened to it
.github/workflows/post.yml  the cron
```

## Secrets

Set in the repository's Actions secrets — never in the repository. One set per
account: Instagram, Facebook, YouTube and TikTok credentials, the posting slot
grid, and the comment keywords that Meta's automation listens for.
