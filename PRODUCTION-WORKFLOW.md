# KnockOff Video Production Workflow

Complete workflow from idea to published video.

---

## Phase 1: Planning (Do This First!)

### 1. Copy the Template
```bash
cp templates/video-script-template.md scripts/my-new-video.md
```

### 2. Fill Out Pre-Production Section
- Set title, duration, format
- List what B-roll you need
- List what overlays/graphics you need
- Choose avatar

### 3. Capture Assets
**Avatar Base Video:**
- Record 5-10 seconds of yourself talking
- Face clearly visible, minimal head movement
- Save to `avatars/my-avatar.mp4`

**B-roll Footage:**
- Screen recordings, workspace shots, product demos
- Save to `broll/` folder with clear names
- Keep clips short (under 15 seconds ideal)

**Overlays/Graphics:**
- Create in Canva, Photoshop, or screen capture
- Save to `overlays/` folder
- Can be images (PNG/JPG) or videos (MP4)

---

## Phase 2: Write Script

### Rules for Safe Scripts

**Speech Timing:**
- ~150 words per minute average
- 30s video = ~75 words
- 90s video = ~225 words
- 2min video = ~300 words

**Visual Markers:**
- Keep overlays/B-roll segments under 15 seconds
- Don't place them near 20-second boundaries
- Use sparingly (2-3 per minute max)

**Marker Format:**
```markdown
[BROLL: filename.mp4 | 8s]
[OVERLAY: graphic.png | 5s]
[CTA: Main Text | Subtext below]
[MUSIC: track.mp3 | -12dB]
```

---

## Phase 3: Pre-Flight Check

**ALWAYS run this before generating:**

```bash
cd ~/KnockOff
python tools/preflight_check.py \
  --script scripts/my-video.md \
  --avatar my-avatar
```

This checks:
- ✅ All files exist
- ✅ No chunk boundary issues
- ✅ Avatar video is valid
- ✅ Script syntax is correct

**Fix any errors before proceeding!**

---

## Phase 4: Generate Video

```bash
cd ~/KnockOff
python tools/generate_avatar_video.py \
  --script scripts/my-video.md \
  --avatar my-avatar \
  --format portrait \
  --quality Improved
```

**Watch for:**
- Chunk processing progress
- Any warning messages
- Failed chunks (check logs)

**If it crashes:**
1. Check the log: `~/KnockOff/logs/knockoff_YYYYMMDD.log`
2. Look for ERROR lines
3. Fix the issue and re-run

---

## Phase 5: Review Output

**Output Location:**
- NAS (if mounted): `/Volumes/homes/dmpgh/KnockOff/`
- Local: `~/KnockOff/.tmp/avatar/output/`

**Quality Checks:**
- [ ] Lip sync looks good
- [ ] Audio is clear and properly leveled
- [ ] Overlays/B-roll appear at right times
- [ ] No missing chunks or gaps
- [ ] CTA text is readable

---

## Phase 6: Troubleshooting

### Video has gaps/missing sections
- **Cause:** Chunk failed during processing
- **Fix:** Check log, verify avatar has face in all frames, re-run

### Lip sync is off
- **Cause:** Audio timing issue
- **Fix:** Regenerate with `--quality Enhanced`

### Overlay appears at wrong time
- **Cause:** Script timing estimate was off
- **Fix:** Adjust overlay position in script, regenerate

### Crash during generation
- **Cause:** See log file for details
- **Fix:** Check `~/KnockOff/logs/knockoff_YYYYMMDD.log`

---

## Quick Reference

**File Structure:**
```
~/KnockOff/
├── avatars/           # Your talking head videos
├── broll/            # B-roll footage
├── overlays/         # Graphics and overlays
├── music/            # Background music tracks
├── scripts/          # Your video scripts
├── templates/        # Script templates
├── tools/            # Generation scripts
└── logs/             # Error logs
```

**Common Commands:**
```bash
# List available avatars
python tools/generate_avatar_video.py --list-avatars

# List available voices
python tools/generate_avatar_video.py --list-voices

# Pre-flight check
python tools/preflight_check.py -s scripts/my-video.md -a my-avatar

# Generate video
python tools/generate_avatar_video.py -s scripts/my-video.md -a my-avatar -f portrait

# Check logs
cat logs/knockoff_$(date +%Y%m%d).log | grep ERROR
```

---

## Best Practices

1. **Always run pre-flight check** before generating
2. **Keep visual segments short** (under 15s)
3. **Test with 30s videos first** before making longer content
4. **Save your avatar videos** with descriptive names
5. **Organize B-roll by topic** for reuse
6. **Check logs after every generation** to catch issues early
7. **Back up successful videos** to NAS or cloud storage

---

## Tips for Success

- **Less is more:** Don't overuse overlays/B-roll
- **Plan ahead:** Capture B-roll before writing script
- **Test early:** Generate a short test before full production
- **Learn from logs:** Read error messages to improve workflow
- **Iterate fast:** Small improvements beat perfect first tries
