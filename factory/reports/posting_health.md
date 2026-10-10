# Posting health - Sat 10 Oct 2026 01:00

- Posted today: **0** (target 5)
- Queue: **7** clip(s) = 1.4 days, folders: KT_MIND, KT_MINDSET, KT_RELATIONSHIPS
- Login problems: tiktok, youtube
- Retried once (upload glitches): 1
  - KT_MIND/01_inprocess_36s.mp4 -> facebook

## Glitches seen (48h)
- KT_MIND/01_inprocess_36s.mp4 on facebook: reel upload failed 400: {'debug_info': {'retriable': False, 'type': 'ProcessingFailedError', 'message': 'Reque

## Needs you
- [ ] **TIKTOK is not posting** (4 post(s) in 48h). TikTok login expired/invalid. Re-authorize the TikTok developer app (Content Posting API) for @thesuccessclubco, get a NEW refresh token, and paste it into the repo secret TT_REFRESH_TOKEN.
- [ ] **YOUTUBE is not posting** (3 post(s) in 48h). YouTube login expired/revoked. Most common cause: the Google Cloud OAuth consent screen is still in 'Testing' - tokens then die after 7 days. Google Cloud Console -> APIs & Services -> OAuth consent screen -> 'Publish app' (to Production), then create a NEW refresh token and paste it into the repo secret YT_REFRESH_TOKEN.
- [ ] **Queue low:** 7 clip(s) = 1.4 days. The clipper agent runs daily; if this stays low check the `agents` workflow log.
