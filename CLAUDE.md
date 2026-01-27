# KnockOff - Local AI Video Generation

HeyGen alternative using local AI models. No subscriptions, no API costs, full control.

## What It Does

Takes a script + avatar video → produces lip-synced talking head video with B-roll, overlays, and background music.

```
Text Script → Piper TTS → Audio
                            ↓
Avatar Video + Audio → Wav2Lip → Lip-synced Video
                            ↓
+ B-roll/Overlays/CTAs/Music → Final Video
```

## Quick Start

```bash
# Simple video
python tools/generate_avatar_video.py "Your script here" --avatar vg-host

# With B-roll script
python tools/generate_avatar_video.py --script myscript.md --avatar vg-host
```

## Script Markers

```markdown
This is spoken text that becomes TTS.

[OVERLAY: product-screens.png | 10s]    # Image over avatar, avatar in corner PIP

More spoken text continues here.

[BROLL: demo-footage.mp4 | 5s]          # Full cut to video, avatar hidden

Final speech text.

[CTA: Subscribe | Links in description]  # Text overlay on avatar

[MUSIC: upbeat.mp3 | -12dB]             # Background music track
```

| Marker | Description |
|--------|-------------|
| `[BROLL: file \| duration]` | Full cut to B-roll video |
| `[OVERLAY: file \| duration]` | Overlay fills frame, avatar in corner PIP |
| `[CTA: text \| subtext]` | Text overlay centered on avatar |
| `[MUSIC: file \| volume]` | Background music (e.g., -12dB) |

## Dependencies

- **Piper TTS** - Local text-to-speech (`pip install piper-tts`)
- **Easy-Wav2Lip** - Lip sync engine (~/Easy-Wav2Lip)
- **ffmpeg** - Video processing

## Directory Structure

```
avatars/        # Avatar video library (reference by name)
broll/          # B-roll video clips
overlays/       # Overlay images/graphics
music/          # Background music tracks
tools/          # Python scripts
models/piper/   # TTS voice models
.tmp/avatar/output/  # Generated videos
```

## Avatar Requirements

- Face clearly visible in every frame
- Looking at camera
- Minimal head movement
- Consistent lighting
- 5-30 seconds (loops automatically)
- MP4 with H.264 codec

## Quality Levels

| Level | Speed | Use Case |
|-------|-------|----------|
| Fast | Fastest | Testing, previews |
| Improved | Medium | General use |
| Enhanced | Slowest | Final production |

## Known Issues

- GFPGAN not installed (Enhanced mode unavailable, Fast/Improved work fine)
- Uses CPU for inference (no CUDA on Mac)
