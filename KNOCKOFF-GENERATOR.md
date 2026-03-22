# KnockOff Video Generator

**Local AI video generation system - A self-hosted HeyGen/Synthesia alternative**

> Build professional talking-head videos with AI lip-sync, B-roll, overlays, and music - entirely on your Mac. No subscriptions, no API costs, complete control.

---

## What Is KnockOff?

KnockOff transforms text scripts into polished video content using:
- **Local TTS** (Piper) - Natural voice synthesis
- **AI Lip Sync** (Wav2Lip) - Matches mouth movements to audio
- **Automated Editing** - B-roll insertion, overlays, music mixing
- **No Cloud Required** - Runs 100% on your machine

**Perfect for:** YouTube explainers, course content, social media, product demos

---

## System Architecture

```
┌─────────────┐
│ Text Script │
│  (.md file) │
└──────┬──────┘
       │
       ├──→ [Parse Script] → Extract speech + visual markers
       │
       ├──→ [Piper TTS] → Generate audio from text
       │         │
       │         ↓
       ├──→ [Wav2Lip] → Lip-sync avatar to audio
       │         │
       │         ↓
       └──→ [Video Assembly]
              ├─ Insert B-roll clips
              ├─ Add overlay graphics
              ├─ Mix background music
              └─ Render final video
                     ↓
            ┌────────────────┐
            │  Final Video   │
            │ Ready to Upload│
            └────────────────┘
```

---

## Core Components

### 1. Text-to-Speech (Piper)
- **Engine:** Piper TTS (local neural TTS)
- **Voices:** Joe (male), Lessac (female)
- **Quality:** Near-human natural speech
- **Speed:** ~150 words/minute
- **Location:** `models/piper/`

### 2. Lip Sync (Wav2Lip)
- **Engine:** Easy-Wav2Lip
- **Quality Levels:**
  - `Fast` - Quick preview (lower quality)
  - `Improved` - Production quality (recommended)
  - `Enhanced` - Maximum quality (slower)
- **Location:** `~/Easy-Wav2Lip/`

### 3. Video Assembly (MoviePy)
- Combines all elements into final video
- Handles timing, transitions, audio mixing
- Supports multiple formats (portrait, landscape, square)

---

## Directory Structure

```
~/KnockOff/
├── avatars/           # Your talking head source videos
│   ├── vg-host.mp4
│   └── my-avatar.mp4
├── broll/             # B-roll footage clips
│   ├── demo.mp4
│   └── workspace.mp4
├── overlays/          # Graphics and image overlays
│   ├── product.png
│   └── cta-subscribe.png
├── music/             # Background music tracks
│   ├── upbeat.mp3
│   └── calm.mp3
├── scripts/           # Your video scripts (.md files)
│   ├── video-01.md
│   └── tutorial.md
├── templates/         # Script templates
│   └── video-script-template.md
├── tools/             # Python generation scripts
│   ├── generate_avatar_video.py  # Main generator
│   ├── preflight_check.py        # Validation tool
│   ├── parse_script.py           # Script parser
│   └── tts_xtts.py               # TTS engine
├── logs/              # Generation logs
├── comparisons/       # Quality comparisons vs HeyGen
└── .tmp/              # Temporary processing files
```

---

## Complete Workflow

### Phase 1: Preparation

**1. Create Your Avatar Video**
```bash
# Requirements:
# - 5-30 seconds long
# - Face clearly visible in all frames
# - Minimal head movement
# - Good lighting
# - No text overlays or PIP elements
# - H.264 MP4 format

# Save to:
~/KnockOff/avatars/my-avatar.mp4
```

**2. Gather Assets**
```bash
# B-roll clips (screen recordings, demos, etc.)
~/KnockOff/broll/

# Overlay graphics (created in Canva, screenshots, etc.)
~/KnockOff/overlays/

# Background music (royalty-free tracks)
~/KnockOff/music/
```

**3. Copy Script Template**
```bash
cd ~/KnockOff
cp templates/video-script-template.md scripts/my-video.md
```

---

### Phase 2: Write Your Script

Edit `scripts/my-video.md`:

```markdown
---
Title: My Video Title
Duration: 90s
Format: portrait
Avatar: my-avatar
Voice: joe
---

# My Video Title

This is the opening line. Keep it conversational and natural.

[OVERLAY: product-demo.png | 5s]

Continue speaking here. The overlay appears during this section.

More speech content that gets converted to audio.

[BROLL: workspace.mp4 | 8s]

This section plays over the B-roll footage.

Final thoughts and call to action.

[CTA: Subscribe Now | Hit the bell for notifications]

[MUSIC: upbeat.mp3 | -12dB]
```

**Script Markers:**

| Marker | Purpose | Example |
|--------|---------|---------|
| `[BROLL: file \| duration]` | Full-screen B-roll cut | `[BROLL: demo.mp4 \| 8s]` |
| `[OVERLAY: file \| duration]` | Overlay graphic/video | `[OVERLAY: graph.png \| 5s]` |
| `[CTA: text \| subtext]` | Call-to-action text | `[CTA: Subscribe \| Links below]` |
| `[MUSIC: file \| volume]` | Background music | `[MUSIC: calm.mp3 \| -15dB]` |

**Timing Guidelines:**
- ~150 words per minute
- 30s video = ~75 words
- 90s video = ~225 words
- 2min video = ~300 words

---

### Phase 3: Pre-Flight Check

**ALWAYS run this before generating:**

```bash
cd ~/KnockOff
python tools/preflight_check.py \
  --script scripts/my-video.md \
  --avatar my-avatar
```

**Checks performed:**
- ✅ Avatar video exists and is valid
- ✅ All B-roll files exist
- ✅ All overlay files exist
- ✅ Music files exist
- ✅ Script syntax is correct
- ✅ No chunk boundary issues (Wav2Lip limitation)
- ✅ File formats are compatible

**Fix any errors before proceeding!**

---

### Phase 4: Generate Video

```bash
cd ~/KnockOff
source .venv/bin/activate

python tools/generate_avatar_video.py \
  --script scripts/my-video.md \
  --avatar my-avatar \
  --format portrait \
  --quality Improved
```

**Options:**

```bash
--script PATH          # Path to .md script file
--avatar NAME          # Avatar name (from avatars/ folder)
--voice NAME           # Voice: joe (male), lessac (female)
--format FORMAT        # portrait, landscape, square
--quality LEVEL        # Fast, Improved, Enhanced
--captions             # Burn in closed captions
--output PATH          # Custom output location
```

**Quality Levels:**
- `Fast` - Quick preview, lower quality (~2-3 min)
- `Improved` - Production quality (recommended, ~5-7 min)
- `Enhanced` - Maximum quality, slower (~10-15 min)

---

### Phase 5: Review & Iterate

**Output Location:**
- Primary: `/Volumes/homes/dmpgh/KnockOff/` (NAS)
- Fallback: `~/.tmp/avatar/output/`

**Quality Checklist:**
- [ ] Lip sync looks natural
- [ ] Audio is clear and properly leveled
- [ ] B-roll/overlays appear at correct times
- [ ] No gaps or missing chunks
- [ ] CTA text is readable and well-positioned
- [ ] Background music level is appropriate
- [ ] Overall pacing feels right

**If issues found:**
1. Check logs: `~/KnockOff/logs/knockoff_YYYYMMDD.log`
2. Adjust script
3. Re-run generation

---

## Common Commands

```bash
# List available avatars
python tools/generate_avatar_video.py --list-avatars

# List available voices
python tools/generate_avatar_video.py --list-voices

# Generate with captions
python tools/generate_avatar_video.py \
  -s scripts/my-video.md \
  -a my-avatar \
  --captions

# Quick preview (Fast quality)
python tools/generate_avatar_video.py \
  -s scripts/test.md \
  -a my-avatar \
  --quality Fast

# Check today's logs for errors
cat logs/knockoff_$(date +%Y%m%d).log | grep ERROR

# Monitor generation in real-time
tail -f logs/knockoff_$(date +%Y%m%d).log
```

---

## Auto-Processing Queue

KnockOff includes an automated batch processing system:

```bash
# Start the auto-processor
~/KnockOff/auto-process-queue.sh
```

**How it works:**
1. Scans `scripts/` folder for new .md files
2. Validates each script with preflight check
3. Generates videos automatically
4. Saves to NAS
5. Moves processed scripts to `processed/` folder

**Configure in:** `auto-process-queue.sh`

---

## Troubleshooting

### Video has gaps or missing sections
**Cause:** Chunk failed during Wav2Lip processing
**Solution:**
1. Check log for ERROR messages
2. Verify avatar has visible face in all frames
3. Try different quality setting
4. Re-generate video

### Lip sync is off
**Cause:** Audio timing mismatch
**Solution:**
- Use `--quality Enhanced`
- Check avatar video quality
- Verify face is clear in all frames

### Overlay appears at wrong time
**Cause:** Script timing estimate doesn't match actual speech
**Solution:**
1. Adjust overlay position in script
2. Add/remove text before overlay marker
3. Re-generate

### "Chunk boundary issue" error
**Cause:** Visual marker falls on Wav2Lip 20-second boundary
**Solution:**
- Move marker by adding/removing text
- Preflight check will warn you about this

### Crash during generation
**Cause:** Various (check logs)
**Solution:**
1. Check `~/KnockOff/logs/knockoff_YYYYMMDD.log`
2. Look for ERROR or FATAL lines
3. Common causes:
   - Missing dependencies
   - Corrupted avatar video
   - Insufficient disk space
   - Wav2Lip process crashed

### Audio is too quiet/loud
**Cause:** TTS volume or music mixing issue
**Solution:**
- Adjust music volume in script: `[MUSIC: track.mp3 | -15dB]`
- Lower number = quieter (e.g., -20dB very quiet)
- Higher number = louder (e.g., -6dB loud)

---

## Best Practices

### Script Writing
1. **Write naturally** - How you'd actually speak, not formal writing
2. **Keep sentences short** - Easier for TTS to pronounce naturally
3. **Avoid jargon** - Unless your audience expects it
4. **Test pronunciation** - Listen to TTS output for problem words
5. **Use punctuation** - Helps TTS with pacing and inflection

### Visual Elements
1. **Less is more** - 2-3 overlays per minute max
2. **Keep B-roll short** - Under 10 seconds ideal
3. **Test timing** - Generate short test video first
4. **Consistent style** - Use similar graphics/colors
5. **Readable text** - Large fonts, high contrast

### Avatar Creation
1. **Good lighting** - Even, no harsh shadows
2. **Neutral expression** - Slight smile, not too animated
3. **Stable camera** - Use tripod or stable surface
4. **Face centered** - Clear view of mouth
5. **Plain background** - Reduces processing artifacts

### Production Workflow
1. **Start small** - Test with 30s video before 2min video
2. **Pre-flight always** - Catches 90% of issues before generation
3. **Check logs** - After every generation, review for warnings
4. **Iterate quickly** - Small adjustments > perfect first try
5. **Save everything** - Successful videos, avatars, B-roll for reuse

---

## Performance Tips

### Speed Up Generation
- Use `--quality Fast` for previews
- Shorter videos generate faster (obviously)
- Close other apps during generation
- Ensure Mac isn't throttling (check temps)

### Improve Quality
- Use `--quality Enhanced` for final videos
- Record avatar in 1080p or higher
- Use high-quality B-roll footage
- Professional voice cloning (XTTS) for ultimate quality

### Save Disk Space
- Delete `.tmp` folder after successful generation
- Compress B-roll before adding to library
- Archive old videos to NAS/cloud

---

## Advanced Features

### Voice Cloning
Use XTTS to clone your own voice:

```bash
python tools/clone_voice.py \
  --audio sample.wav \
  --name my-voice
```

Then use in scripts:
```bash
python tools/generate_avatar_video.py \
  --script scripts/my-video.md \
  --avatar my-avatar \
  --voice my-voice
```

### Custom Captions
Add `--captions` flag for burned-in subtitles:

```bash
python tools/generate_avatar_video.py \
  -s scripts/my-video.md \
  -a my-avatar \
  --captions
```

### Comparison to HeyGen
Automatically compare output to HeyGen:

```bash
python tools/compare_to_heygen.py \
  --knockoff output/my-video.mp4 \
  --heygen heygen-version.mp4
```

Generates side-by-side comparison with metrics.

---

## System Requirements

**Hardware:**
- **CPU:** Apple Silicon (M1/M2/M3/M4) or Intel with AVX
- **RAM:** 16GB minimum (32GB recommended)
- **Storage:** 50GB free space for processing
- **GPU:** Apple Silicon GPU or NVIDIA GPU (for Wav2Lip)

**Software:**
- **OS:** macOS 12+ or Linux
- **Python:** 3.12
- **ffmpeg:** Latest version
- **Easy-Wav2Lip:** Installed in `~/Easy-Wav2Lip/`

**Installation:**
```bash
cd ~/KnockOff
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## File Format Guide

### Avatar Videos
- **Format:** MP4 (H.264)
- **Resolution:** 1080p recommended
- **Duration:** 5-30 seconds
- **Framerate:** 30fps
- **Requirements:** Face visible, minimal movement

### B-roll Footage
- **Format:** MP4, MOV, or AVI
- **Resolution:** 1080p or higher
- **Duration:** Under 15 seconds recommended
- **Compression:** H.264 or H.265

### Overlays
- **Images:** PNG (with transparency) or JPG
- **Videos:** MP4, MOV (with alpha channel if needed)
- **Resolution:** Match video resolution (1080p)

### Music
- **Format:** MP3 or WAV
- **Quality:** 128kbps or higher
- **License:** Ensure royalty-free

---

## FAQ

**Q: How long does generation take?**
A: ~5-7 minutes for a 2-minute video at Improved quality on M1/M2 Mac.

**Q: Can I use my own voice?**
A: Yes! Use XTTS voice cloning (see Advanced Features).

**Q: Does it work offline?**
A: 100% offline after initial setup. No internet required.

**Q: How does quality compare to HeyGen?**
A: Very close with Enhanced quality. See `comparisons/` folder.

**Q: Can I edit the video after generation?**
A: Yes! Output is standard MP4 - edit in any video editor.

**Q: What about commercial use?**
A: Check licenses for TTS voices and music. Wav2Lip is non-commercial by default.

---

## Support & Resources

**Documentation:**
- `README.md` - Quick start guide
- `PRODUCTION-WORKFLOW.md` - Step-by-step workflow
- `CLAUDE.md` - Project context for AI assistance

**Logs:**
- `~/KnockOff/logs/` - Generation logs with timestamps
- Check here first when troubleshooting

**Community:**
- Project GitHub: (add your repo URL)
- Discord: (optional community link)

---

## Roadmap

**Planned Features:**
- [ ] Real-time preview during generation
- [ ] Batch processing UI
- [ ] Cloud backup integration
- [ ] Custom avatar training
- [ ] Multi-language TTS
- [ ] Advanced caption styling
- [ ] Automated YouTube upload

---

## Credits

**Built with:**
- [Piper TTS](https://github.com/rhasspy/piper) - Local text-to-speech
- [Easy-Wav2Lip](https://github.com/anothermartz/Easy-Wav2Lip) - Lip sync engine
- [MoviePy](https://github.com/Zulko/moviepy) - Video editing
- [ffmpeg](https://ffmpeg.org/) - Video processing

**Created by:** Doug Morse
**Purpose:** Self-hosted video generation for AI education content

---

## License

MIT License - Use freely for personal projects.

**Note:** Check individual component licenses:
- Wav2Lip: Research/non-commercial by default
- Piper TTS: MIT
- Your content: You own it!

---

**Last Updated:** February 4, 2026
**Version:** 1.0
**Author:** Doug Morse (@dmpgh)
