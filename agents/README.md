# The three agents

| Agent | File | Runs | Job |
|---|---|---|---|
| 1. Clipper | `clipper.py` | after every factory run + daily 08:40 Panama (`agents` workflow) | Reads Kevin's transcripts and writes clip plans (cut times, hook, caption), one folder per episode, until 7 days (35 clips) are queued |
| 2. Rules checker | `reviewer.py` + `AGENT_RULES.md` | inside every clipper run, before anything is saved | Hard checks in code + a Claude review against the rulebook. Fixes or drops clips. Report: `factory/reports/review_<plan>.md` |
| 3. Posting watchdog | `post_watch.py` | every 4 hours (`watch` workflow) | Checks the posts really went out, retries upload glitches once, opens a GitHub issue (emailed to you) when a login breaks or the queue is low. Report: `factory/reports/posting_health.md` |

Posting itself stays in the existing `post` workflow (every 20 min, 5 slots a day).

## Settings (repo -> Settings -> Secrets and variables -> Actions)
- Secret `ANTHROPIC_API_KEY` (required) - from console.anthropic.com. Cost is about $0.10 per episode, roughly $3/month at 5 posts a day.
- Variables (optional): `POSTS_PER_DAY` (5), `TARGET_DAYS` (7), `AGENT_MODEL` (claude-sonnet-5-5).

## Run by hand
Actions -> `agents` -> Run workflow. Tick "Test plans" to render clips for review without posting them.
