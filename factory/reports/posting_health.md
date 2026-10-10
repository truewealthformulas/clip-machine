# Posting health - Sat 10 Oct 2026 16:58

- Posted today: **4** (target 5)
- Queue: **17** clip(s) = 3.4 days, folders: KT_CREDIT, KT_MINDSET, KT_MINDSET4, KT_MINDSET5, KT_RELATIONSHIPS, KT_WEALTH, KT_WORDS
- Login problems: tiktok, youtube
- Retried once (upload glitches): 0

## Needs you
- [ ] **TIKTOK is not posting** (7 post(s) in 48h). TikTok login expired/invalid. Re-authorize the TikTok developer app (Content Posting API) for @thesuccessclubco, get a NEW refresh token, and paste it into the repo secret TT_REFRESH_TOKEN.
- [ ] **YOUTUBE is not posting** (4 post(s) in 48h). YouTube login expired/revoked. Most common cause: the Google Cloud OAuth consent screen is still in 'Testing' - tokens then die after 7 days. Google Cloud Console -> APIs & Services -> OAuth consent screen -> 'Publish app' (to Production), then create a NEW refresh token and paste it into the repo secret YT_REFRESH_TOKEN.
