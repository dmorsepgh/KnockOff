# Video Script Template

**Title:** [Your video title]
**Duration Target:** [30s / 60s / 90s / 2min]
**Format:** [portrait / landscape / square]
**Avatar:** [name of avatar file]

---

## Pre-Production Checklist

- [ ] Avatar video recorded and in `avatars/` folder
- [ ] All B-roll footage captured
- [ ] All overlays/graphics created
- [ ] Music track selected (optional)
- [ ] Script reviewed for chunk boundaries (overlays within 20s segments)

---

## Shot List

**Avatar Base:**
- Filename: `[avatar-name].mp4`
- Duration: 5-10 seconds minimum
- Notes: Face clearly visible, minimal head movement

**B-roll Needed:**
- [ ] [Description of B-roll shot 1] → `broll/[filename].mp4`
- [ ] [Description of B-roll shot 2] → `broll/[filename].mp4`

**Overlays/Graphics:**
- [ ] [Description of overlay 1] → `overlays/[filename].png`
- [ ] [Description of overlay 2] → `overlays/[filename].mp4`

**Background Music:** (optional)
- [ ] Track: `music/[filename].mp3`
- [ ] Volume: -12dB (adjust as needed)

---

## Script with Markers

> **IMPORTANT:** Keep overlays/B-roll segments SHORT (under 15s) to avoid chunk boundary issues.
> Videos process in 20-second chunks - plan accordingly.

Your opening hook goes here. Make it punchy and attention-grabbing.

[OVERLAY: graphic-intro.png | 5s]

Now explain the main concept. Voice continues over the overlay.

More narration about your topic. This is pure avatar talking.

[BROLL: screen-demo.mp4 | 8s]

Explain what they're seeing in the B-roll. Keep it under 15 seconds.

Continue with more avatar narration. Build to your conclusion.

[CTA: Subscribe | Hit that follow button]

Final thought here. End strong.

[MUSIC: background-track.mp3 | -12dB]

---

## Generation Command

```bash
cd ~/KnockOff
python tools/generate_avatar_video.py \
  --script "scripts/[this-script-name].md" \
  --avatar [avatar-name] \
  --format [portrait/landscape/square] \
  --quality Improved
```

---

## Post-Production

- [ ] Review output for sync issues
- [ ] Check for missing chunks (watch for gaps)
- [ ] Verify audio levels
- [ ] Upload to target platform
