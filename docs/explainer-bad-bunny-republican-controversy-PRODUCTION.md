# Production Plan - explainer-bad-bunny-republican-controversy

**Generated:** 2026-02-02 10:59 PM
**Total Duration:** ~60 seconds
**Structure:** Avatar Intro (20s) → B-roll Middle (20s) → Avatar Outro (20s)

---

## Timing Breakdown

- **Intro:** 20.0s (Target: 20s) - Avatar with lip sync
- **Middle:** 20.0s (Target: 20s) - B-roll with voiceover
- **Outro:** 20.0s (Target: 20s) - Avatar with lip sync
- **Total:** 60.0s

---

## Production Structure

### [0-20s] INTRO - Avatar (Lip Sync Chunk 1)

So here's what happened. Bad Bunny, one of the biggest music artists in the world right now, just won Album of the Year at the Grammys. He's the first Latin artist ever to win that major category. During his acceptance speech, he said two simple words: I.C.E. out. And Republicans

**Shot:** Avatar talking directly to camera
**Audio:** Lip-synced to avatar video

---

### [20-40s] MIDDLE - B-roll (Continuous Voiceover)

completely lost it. Now, to understand why this matters, you need to know that Bad Bunny was already announced as the halftime show performer for the 2026 Super Bowl. And that announcement alone had already caused a meltdown. President Trump called it absolutely ridiculous and said he's going to boycott

**Shot:** B-roll footage, screen recordings, or text overlays
**Audio:** Continuous voiceover (NO lip sync needed)

**B-roll Needed:**
- [ ] Screen recording or demo → `broll/demo-20260202.mp4`
- [ ] Text overlay with key points → `overlays/text-20260202.png`

---

### [40-60s] OUTRO - Avatar (Lip Sync Chunk 2)

the Super Bowl. Alabama Senator Tommy Tuberville started calling it the Woke Bowl and kept referring to Bad Bunny as Bad Rabbit. Conservative commentator Tomi Lahren questioned whether he's even an American artist, which is interesting because he's Puerto Rican, and Puerto Rico is, you know, part of America. House

**Shot:** Avatar talking directly to camera
**Audio:** Lip-synced to avatar video

[CTA: Follow for more | Daily AI tips at dmpgh.com]

---

## Audio Production Notes

**IMPORTANT:** Generate ONE continuous 60-second audio file with TTS.
- Audio runs continuously underneath entire video
- Intro section [0-20s] → lip sync to avatar
- Middle section [20-40s] → play over B-roll (no lip sync)
- Outro section [40-60s] → lip sync to avatar

Only the intro and outro portions need lip syncing (40s total).
Middle 20s is pure voiceover - much faster to process!

---

## Pre-Production Checklist

- [ ] Avatar base video recorded (5-10s minimum) → `avatars/[name].mp4`
- [ ] B-roll footage captured

---

## Generation Commands

**1. Pre-flight Check:**
```bash
python tools/preflight_check.py -s scripts/[script-name].md -a [avatar-name]
```

**2. Generate Video:**
```bash
python tools/generate_avatar_video.py -s scripts/[script-name].md -a [avatar-name] -f portrait
```

---

## Warnings
- ✅ No warnings - script timing looks good
