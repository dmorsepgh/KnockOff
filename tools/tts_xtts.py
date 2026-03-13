#!/usr/bin/env python3
"""
XTTS voice cloning TTS - standalone script.
Called by generate_avatar_video.py when using cloned voices.

Usage:
    python tts_xtts.py --text "Hello world" --voice mc --output /path/to/output.wav
"""

import argparse
import os
import sys
from pathlib import Path

# Set environment before imports
os.environ["COQUI_TOS_AGREED"] = "1"

# Patch torch.load for compatibility with newer PyTorch
import torch
_original_load = torch.load
def _patched_load(*args, **kwargs):
    kwargs['weights_only'] = False
    return _original_load(*args, **kwargs)
torch.load = _patched_load

from TTS.api import TTS

PROJECT_ROOT = Path(__file__).parent.parent
VOICES_DIR = PROJECT_ROOT / "voices"

# Global model cache
_tts_model = None

def get_model():
    global _tts_model
    if _tts_model is None:
        _tts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
    return _tts_model


def main():
    parser = argparse.ArgumentParser(description="Generate speech with cloned voice")
    parser.add_argument("--text", required=True, help="Text to speak")
    parser.add_argument("--voice", required=True, help="Voice name (from voices/ folder)")
    parser.add_argument("--output", required=True, help="Output WAV file path")
    parser.add_argument("--speed", type=float, default=1.15, help="Speaking speed multiplier (1.0=normal, 1.15=15%% faster)")
    args = parser.parse_args()

    voice_file = VOICES_DIR / f"{args.voice}.wav"
    if not voice_file.exists():
        print(f"Error: Voice '{args.voice}' not found at {voice_file}", file=sys.stderr)
        sys.exit(1)

    tts = get_model()
    tts.tts_to_file(
        text=args.text,
        file_path=args.output,
        speaker_wav=str(voice_file),
        language="en",
        speed=args.speed
    )
    print(f"Generated: {args.output} (speed={args.speed}x)")


if __name__ == "__main__":
    main()
