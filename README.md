# KnockOff

Local AI video generation - a HeyGen/Synthesia alternative that runs entirely on your machine.

**No subscriptions. No API costs. Full control.**

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
# Create virtual environment (Python 3.12)
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install piper-tts torch moviepy==1.0.3

# Generate a simple video
python tools/generate_avatar_video.py "Your script here" --avatar vg-host

# With B-roll script
python tools/generate_avatar_video.py --script myscript.md --avatar vg-host --voice joe
```

## Script Markers

Write your script in markdown with these markers:

```markdown
This is spoken text that becomes TTS.

[OVERLAY: product-screens.png | 10s]

More spoken text continues here.

[BROLL: demo-footage.mp4 | 5s]

Final speech text.

[CTA: Subscribe | Links in description]

[MUSIC: upbeat.mp3 | -12dB]
```

| Marker | Description |
|--------|-------------|
| `[BROLL: file \| duration]` | Full cut to B-roll video |
| `[OVERLAY: file \| duration]` | Overlay fills frame |
| `[CTA: text \| subtext]` | Text overlay centered on avatar |
| `[MUSIC: file \| volume]` | Background music (e.g., -12dB) |

## Dependencies

- **Piper TTS** - Local text-to-speech
- **Easy-Wav2Lip** - Lip sync engine (install separately to ~/Easy-Wav2Lip)
- **ffmpeg** - Video processing

## Directory Structure

```
avatars/        # Avatar video library (reference by name)
broll/          # B-roll video clips
overlays/       # Overlay images/graphics
music/          # Background music tracks
tools/          # Python scripts
models/piper/   # TTS voice models
```

## Avatar Requirements

- Face clearly visible in every frame
- Looking at camera
- Minimal head movement
- Consistent lighting
- 5-30 seconds (loops automatically)
- MP4 with H.264 codec
- No burned-in text or PIP overlays

## Options

```bash
--avatar NAME      # Avatar name from avatars/ folder
--voice NAME       # Voice: joe (male), lessac (female)
--format FORMAT    # portrait, landscape, square
--captions         # Burn in closed captions
--quality LEVEL    # Fast, Improved, Enhanced
```

## License

MIT
