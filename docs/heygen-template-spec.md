# HeyGen Video Template Specification

Based on analysis of "Day 3 - First Revenue Stream.mp4"

## Video Format

- **Resolution**: 1080x1920 pixels
- **Aspect Ratio**: 9:16 (vertical/portrait)
- **Frame Rate**: 25 fps
- **Codec**: H.264
- **Target for**: Social media (Instagram Reels, TikTok, YouTube Shorts)

## Layout Structure

### 1. Avatar/Narrator (Primary Element)

- **Position**: Centered, full-frame
- **Framing**: Medium close-up (head and shoulders, torso visible)
- **Background**:
  - Blurred bokeh effect (depth of field)
  - Professional environment (office/home office)
  - Warm, inviting lighting
  - Background stays consistent throughout video
- **Avatar Quality**:
  - High-resolution photorealistic avatar
  - Natural facial expressions
  - Lip-sync matches audio perfectly
  - Subtle head movements and gestures

### 2. Text Overlays (Captions/Key Points)

- **Position**: Lower third of frame
  - Typically bottom 20-25% of screen
  - Centered horizontally
  - ~100-150px from bottom edge

- **Typography**:
  - Font: Sans-serif (appears to be Montserrat, Roboto, or similar)
  - Weight: Bold/Semi-bold
  - Size: ~48-60pt (readable on mobile)
  - Color: White (#FFFFFF)
  - Stroke/Outline: Black or dark shadow for legibility
  - Text alignment: Center

- **Animation**:
  - Text appears synced to speech
  - Shows key phrases or important words
  - Simple fade in/out or instant appearance
  - Duration: Matches the spoken phrase timing
  - No distracting animations

### 3. Color Scheme

- **Background**: Warm, professional tones (browns, creams, soft blues)
- **Text**: High contrast white on darker background
- **Overall Feel**: Professional, trustworthy, modern

## Audio Specifications

- **Codec**: AAC
- **Loudness**: -25.46 LUFS (broadcast standard)
- **Voice Quality**:
  - Natural, conversational tone
  - Clear pronunciation
  - Good pacing (not too fast, not too slow)
  - Professional but approachable

## Content Structure

### Video Flow
1. **Opening Hook** (0-5s)
   - Immediate value statement
   - Sets context (e.g., "Day three of the 90-day AI millionaire challenge")

2. **Main Content** (5-60s)
   - Story/narrative delivery
   - Key points with text emphasis
   - Problem → Solution → Result structure

3. **Call to Action** (60-75s)
   - Clear next step
   - Website/URL mention
   - Friendly sign-off

### Caption Strategy
- Key phrases appear as lower-third text
- Emphasizes important numbers, concepts, actions
- Examples from Day 3 video:
  - "Stream Day three of the ninety day A.I."
  - "Affiliate marketing."
  - "Affiliate marketing isn't passive."

## Technical Requirements for Matching

### For KnockOff Generator to Match:

1. **Avatar Requirements**:
   - High-quality source avatar image
   - Professional background with bokeh
   - Proper lighting on subject
   - Centered composition

2. **Text Overlay System**:
   - Parse script for key phrases
   - Time text to match audio
   - Apply proper styling (white + stroke)
   - Position in lower third

3. **Video Processing**:
   - Output at 1080x1920
   - Maintain 25 fps (or 30 fps for social)
   - Proper audio normalization to -24 LUFS
   - H.264 encoding for compatibility

4. **Quality Targets**:
   - Lip-sync accuracy: <100ms delay
   - Audio clarity: No artifacts or robotic sound
   - Visual quality: No obvious AI artifacts
   - Duration accuracy: Match script pacing

## Differences from Current KnockOff Output

Based on previous comparisons (metrics_history.json):

| Metric | HeyGen | Current KnockOff | Target |
|--------|---------|------------------|---------|
| Resolution | 1080x1920 | 1280x720 | Match HeyGen: 1080x1920 |
| FPS | 25 | 60 | Match HeyGen: 25 or use 30 |
| Audio Loudness | -25.46 LUFS | -24.07 LUFS | Match within 1dB |
| Duration | Natural pacing | Sometimes faster | Match speech rate |

## Implementation Checklist

- [ ] Set output resolution to 1080x1920 (portrait)
- [ ] Reduce FPS to 25 or 30 (not 60)
- [ ] Normalize audio to -24 to -25 LUFS
- [ ] Implement lower-third text overlay system
- [ ] Add text stroke/shadow for readability
- [ ] Sync text to speech timing
- [ ] Optimize TTS voice for natural pacing
- [ ] Match Wav2Lip quality settings
- [ ] Verify background blur/bokeh effect on avatar source

## Example Text Overlay Timing

From Day 3 script:

```
00:00 - 00:06: "Stream Day three of the ninety day A.I."
00:06 - 00:12: "millionaire challenge, starting point, negative $170"
00:18 - 00:23: "first real revenue stream, affiliate marketing"
00:23 - 00:28: "The logic is simple"
00:40 - 00:44: "Affiliate marketing isn't passive"
00:53 - 00:57: "Claude writes the comparison guys. Knockoff generates the videos"
01:07 - 01:13: "Want more tips and tricks like this? Head over to dmpgh.com"
```

## Notes

- HeyGen videos are consistent: same background, same framing, same style
- This creates brand recognition and professional appearance
- Focus on quality over quantity
- Text overlays should enhance, not distract
- Keep mobile viewing in mind (vertical format, large text, high contrast)
