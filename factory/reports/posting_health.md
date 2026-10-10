# Posting health - Sat 10 Oct 2026 09:01

- Posted today: **2** (target 5)
- Queue: **6** clip(s) = 1.2 days, folders: KT_MIND, KT_MINDSET, KT_RELATIONSHIPS
- Login problems: tiktok, youtube
- Retried once (upload glitches): 0

## Needs you
- [ ] **TIKTOK is not posting** (5 post(s) in 48h). TikTok login expired/invalid. Re-authorize the TikTok developer app (Content Posting API) for @thesuccessclubco, get a NEW refresh token, and paste it into the repo secret TT_REFRESH_TOKEN.
- [ ] **YOUTUBE is not posting** (4 post(s) in 48h). YouTube login expired/revoked. Most common cause: the Google Cloud OAuth consent screen is still in 'Testing' - tokens then die after 7 days. Google Cloud Console -> APIs & Services -> OAuth consent screen -> 'Publish app' (to Production), then create a NEW refresh token and paste it into the repo secret YT_REFRESH_TOKEN.
- [ ] **Queue low:** 6 clip(s) = 1.2 days. The clipper agent runs daily; if this stays low check the `agents` workflow log.
