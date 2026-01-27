# Workflow: Generate Avatar Video

## Objective
Create HeyGen-style lip-synced avatar videos from text scripts using local AI models.

## Pipeline
```
Text Script → Piper TTS → Audio (.wav)
                              ↓
Avatar Video + Audio → Wav2Lip → Lip-synced Video
```

## Required Inputs
- **Text script** - What the avatar should say
- **Avatar video** - A short video of a person (ideally looking at camera, neutral expression)

## Tool
`tools/generate_avatar_video.py`

## Basic Usage

```bash
# Direct text input
python tools/generate_avatar_video.py "Hello, welcome to my channel!" --avatar avatar.mp4

# From script file
python tools/generate_avatar_video.py --script docs/explainer-vg-system.md --avatar avatar.mp4

# Custom output path
python tools/generate_avatar_video.py "Your message" --avatar avatar.mp4 --output .tmp/output.mp4
```

## Options

| Flag | Description |
|------|-------------|
| `--avatar, -a` | Path to avatar video file (required) |
| `--script, -s` | Read text from file instead of command line |
| `--output, -o` | Output video path (default: .tmp/avatar/output/video.mp4) |
| `--quality, -q` | Wav2Lip quality: Fast, Improved, Enhanced (default: Improved) |
| `--skip-checks` | Skip dependency verification |

## Quality Levels

| Level | Speed | Quality | Best For |
|-------|-------|---------|----------|
| Fast | Fastest | Basic lip sync | Quick previews, testing |
| Improved | Medium | Better blending | General use (recommended) |
| Enhanced | Slowest | GFPGAN upscaling | Final production videos |

## Avatar Video Requirements

For best results, your avatar video should:
- Show a face clearly in every frame
- Have the subject looking at the camera
- Have minimal head movement
- Use consistent lighting
- Be short (5-15 seconds) - it will loop automatically
- Format: MP4 with H.264 codec

## Directory Structure

```
.tmp/avatar/
├── video/          # Place avatar videos here
├── audio/          # Generated audio files
└── output/         # Final lip-synced videos

models/
├── piper/          # Piper TTS model (en_US-lessac-medium.onnx)
└── wav2lip/        # (unused - models in Easy-Wav2Lip)

~/Easy-Wav2Lip/
└── checkpoints/    # Wav2Lip models
    ├── Wav2Lip.pth
    ├── Wav2Lip_GAN.pth
    └── shape_predictor_68_face_landmarks_GTX.dat
```

## Dependencies

### Required Software
- Python 3.10+
- ffmpeg
- Piper TTS: `pip install piper-tts`

### Models (Auto-downloaded)
- Piper: `en_US-lessac-medium.onnx` (~63MB)
- Wav2Lip: `Wav2Lip.pth` (~416MB)
- Face detector: `shape_predictor_68_face_landmarks_GTX.dat` (~63MB)

## Examples

```bash
# Quick test with default settings
python tools/generate_avatar_video.py "Testing one two three" -a avatar.mp4

# Production quality video
python tools/generate_avatar_video.py --script script.txt -a presenter.mp4 -q Enhanced -o final.mp4

# Using avatar from default folder
cp my_video.mp4 .tmp/avatar/video/
python tools/generate_avatar_video.py "Hello world" -a my_video.mp4
```

## Troubleshooting

### "Piper TTS not installed"
```bash
pip install piper-tts
```

### "Wav2Lip model not found"
Run the model download:
```bash
cd ~/Easy-Wav2Lip/checkpoints
curl -L -o Wav2Lip.pth "https://github.com/anothermartz/Easy-Wav2Lip/releases/download/Prerequesits/Wav2Lip.pth"
```

### "No face detected"
- Ensure the avatar video has a clearly visible face in all frames
- Try a different video with better lighting
- Crop the video to focus on the face

### Poor lip sync quality
- Use `--quality Enhanced` for better results
- Ensure audio is clear (no background noise in TTS)
- Try the Wav2Lip_GAN version by editing config.ini

## Notes

- First run may be slow as models initialize
- GPU acceleration available on Mac (MPS) and NVIDIA (CUDA)
- Output videos are ~30fps MP4 with H.264 encoding
- Audio is embedded in the final video
