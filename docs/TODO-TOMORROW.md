# KnockOff - Tomorrow's To-Do List

## Completed Today
- [x] Found KnockOff project at ~/KnockOff
- [x] Set up voice cloning with Coqui XTTS
- [x] Created "mc" cloned voice from your audio sample
- [x] Added cloned voice support to generate_avatar_video.py
- [x] Fixed CTA overlay crash (skips gracefully when drawtext unavailable)
- [x] Generated full explainer with mc voice + dt avatar

## To Fix
1. **Install ffmpeg with drawtext support** - CTAs are currently skipped
   ```bash
   brew install ffmpeg --with-freetype
   # or compile from source with --enable-libfreetype
   ```

2. **DT avatar is slow** - Portrait orientation (442x628) causes issues
   - Consider cropping to landscape for better performance
   - Or record a new landscape version

## To Try
1. **Run explainer with kitchen-chef avatar** (faster, landscape)
   ```bash
   python tools/generate_avatar_video.py --script scripts/local-ai-coding-explainer.md --avatar kitchen-chef --voice mc
   ```

2. **Clone additional voices** - Just need 30+ second audio samples
   - Save WAV files to `voices/` folder
   - Use with `--voice <name>`

## Videos Generated Today
- `/Volumes/homes/dmpgh/KnockOff/local-ai-coding-explainer_2026-01-27_22-21-21.mp4` - Full explainer (mc + dt)
- `/Volumes/homes/dmpgh/KnockOff/dt-cloned-voice-test.mp4` - Short test
- `/Volumes/homes/dmpgh/KnockOff/local-ai-coding-explainer_2026-01-27_14-38-43.mp4` - Chef avatar version

## Quick Start Tomorrow
```bash
cd ~/KnockOff
source .venv/bin/activate

# List available voices and avatars
python tools/generate_avatar_video.py --list-voices
python tools/generate_avatar_video.py --list-avatars

# Generate with your cloned voice
python tools/generate_avatar_video.py "Your text here" --avatar kitchen-chef --voice mc
```
