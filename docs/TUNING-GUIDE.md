# KnockOff Tuning Guide

How to improve KnockOff output based on HeyGen comparisons.

---

## Quick Comparison Workflow

```bash
# 1. Generate HeyGen video (manual - use their web app)

# 2. Run comparison
python tools/compare_to_heygen.py \
  --heygen ~/Downloads/heygen-video.mp4 \
  --knockoff ~/KnockOff/comparisons/knockoff-script1.mp4 \
  --name "script1" \
  --open

# OR generate + compare in one step
python tools/compare_to_heygen.py \
  --heygen ~/Downloads/heygen-video.mp4 \
  --script "Your script text here" \
  --avatar doug \
  --voice doug \
  --name "script1" \
  --open
```

---

## Common Issues & Fixes

### 1. Lip Sync Off

**Symptom:** Mouth movements don't match audio

**Fixes:**
- Check audio/video alignment in source avatar
- Try different Wav2Lip quality levels:
  ```bash
  --quality fast      # Fastest, lower quality
  --quality improved  # Default, balanced
  --quality enhanced  # Slowest, best quality (needs GFPGAN)
  ```
- Ensure avatar video has clear, well-lit face
- Re-record avatar with more neutral expression

### 2. Audio Too Quiet/Loud

**Symptom:** Volume doesn't match HeyGen

**Fixes:**
Edit `tools/generate_avatar_video.py` and adjust normalization:
```python
# Find the audio normalization section and adjust target loudness
# HeyGen typically targets around -16 LUFS
ffmpeg ... -af "loudnorm=I=-16:TP=-1.5:LRA=11" ...
```

### 3. Voice Sounds Robotic

**Symptom:** TTS lacks natural inflection

**Fixes:**
- Try different Piper voice models
- Add SSML tags for emphasis (if supported)
- Use voice cloning with more training samples
- Add slight pitch variation in post-processing

### 4. Video Resolution Mismatch

**Symptom:** Different aspect ratio than HeyGen

**Fixes:**
```bash
# For vertical (Shorts/TikTok):
--resolution 1080x1920

# For horizontal (YouTube):
--resolution 1920x1080

# For square (Instagram):
--resolution 1080x1080
```

### 5. Face Quality/Artifacts

**Symptom:** Blurry face, weird artifacts around mouth

**Fixes:**
- Install GFPGAN for face enhancement:
  ```bash
  pip install gfpgan
  ```
- Use `--quality enhanced` flag
- Ensure source avatar has high resolution
- Better lighting in avatar recording

### 6. Pacing Too Fast/Slow

**Symptom:** Speech rate doesn't match HeyGen's natural pace

**Fixes:**
Adjust Piper TTS speaking rate:
```python
# In generate_avatar_video.py, find TTS section
# Add length_scale parameter (1.0 = normal, 1.1 = 10% slower, 0.9 = 10% faster)
```

---

## Metrics to Track

The comparison tool logs these metrics to `comparisons/metrics_history.json`:

| Metric | Target | How to Improve |
|--------|--------|----------------|
| Duration difference | < 2 seconds | Adjust TTS speed |
| Loudness (LUFS) | Within 2dB of HeyGen | Adjust normalization |
| Suggestion count | 0 | Fix each suggestion |

### Viewing History

```bash
# See improvement over time
cat ~/KnockOff/comparisons/metrics_history.json | jq '.[-5:]'

# Count suggestions over time (should decrease)
cat ~/KnockOff/comparisons/metrics_history.json | jq '.[].suggestion_count'
```

---

## A/B Testing Workflow

1. **Baseline:** Record HeyGen version
2. **Test:** Generate KnockOff version
3. **Compare:** Run comparison tool
4. **Tweak:** Adjust one parameter
5. **Repeat:** Generate new KnockOff version
6. **Track:** Check if suggestion count decreased

### Example Session

```bash
# Run 1: Baseline
python tools/compare_to_heygen.py --heygen hg.mp4 --knockoff ko_v1.mp4 --name v1

# Tweak: Increased audio normalization to -16 LUFS

# Run 2: After tweak
python tools/compare_to_heygen.py --heygen hg.mp4 --knockoff ko_v2.mp4 --name v2

# Check improvement
cat comparisons/metrics_history.json | jq '.[-2:] | .[].suggestion_count'
# Output: 3, 2  (improved!)
```

---

## Avatar Recording Tips

For best lip sync results:

1. **Lighting:** Even, front-facing light (ring light ideal)
2. **Background:** Plain, non-distracting
3. **Position:** Face fills 40-60% of frame
4. **Expression:** Neutral, mouth slightly open
5. **Movement:** Minimal head movement
6. **Duration:** 10-30 seconds (loops automatically)
7. **Audio:** Silent or very quiet (will be replaced)

---

## Voice Clone Quality

For better voice cloning:

1. **Samples:** Provide 3-5 minutes of clean audio
2. **Quality:** No background noise, no music
3. **Variety:** Include different sentence types
4. **Format:** WAV or high-quality MP3
5. **Content:** Natural speech, not reading robotically

---

*Last updated: January 30, 2025*
