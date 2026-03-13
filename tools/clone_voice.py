#!/usr/bin/env python3
"""
Voice cloning module using Coqui XTTS.
Cloned voice samples are stored in the voices/ folder.
"""

import os
import sys
from pathlib import Path

# Set environment before imports
os.environ["COQUI_TOS_AGREED"] = "1"

# Patch torch.load for compatibility
import torch
_original_load = torch.load
def _patched_load(*args, **kwargs):
    kwargs['weights_only'] = False
    return _original_load(*args, **kwargs)
torch.load = _patched_load

from TTS.api import TTS

PROJECT_ROOT = Path(__file__).parent.parent
VOICES_DIR = PROJECT_ROOT / "voices"

# Lazy-loaded TTS model
_tts_model = None

def get_tts_model():
    """Get or initialize the XTTS model."""
    global _tts_model
    if _tts_model is None:
        print("Loading XTTS voice cloning model...")
        _tts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
    return _tts_model

def get_cloned_voices():
    """List available cloned voices."""
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    return [f.stem for f in VOICES_DIR.glob("*.wav")]

def is_cloned_voice(voice_name: str) -> bool:
    """Check if a voice name refers to a cloned voice."""
    voice_file = VOICES_DIR / f"{voice_name}.wav"
    return voice_file.exists()

def text_to_speech_cloned(text: str, output_path: Path, voice_name: str) -> Path:
    """Generate speech using a cloned voice."""
    voice_file = VOICES_DIR / f"{voice_name}.wav"
    if not voice_file.exists():
        raise ValueError(f"Cloned voice '{voice_name}' not found in {VOICES_DIR}")

    print(f"Generating speech with cloned voice '{voice_name}'...")

    tts = get_tts_model()
    tts.tts_to_file(
        text=text,
        file_path=str(output_path),
        speaker_wav=str(voice_file),
        language="en"
    )

    return output_path

if __name__ == "__main__":
    # Test/demo
    voices = get_cloned_voices()
    print(f"Available cloned voices: {voices}")
