#!/usr/bin/env python3
"""
TTS Engine - Generate audio from text using Piper TTS.
"""

import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
MODELS_DIR = PROJECT_ROOT / "models" / "piper"

VOICES = {
    "joe": MODELS_DIR / "en_US-joe-medium.onnx",
    "lessac": MODELS_DIR / "en_US-lessac-medium.onnx",
}


def generate_audio(text: str, output_path: Path, voice: str = "joe") -> Path:
    """
    Generate audio from text using Piper TTS.

    Args:
        text: Text to synthesize
        output_path: Where to save the .wav file
        voice: Voice name ("joe" or "lessac")

    Returns:
        Path to generated .wav file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    model_path = VOICES.get(voice)
    if not model_path:
        raise ValueError(f"Unknown voice '{voice}'. Available: {list(VOICES.keys())}")
    if not model_path.exists():
        raise FileNotFoundError(f"Voice model not found: {model_path}")

    logger.info(f"Generating TTS audio: {len(text)} chars, voice={voice}")

    result = subprocess.run(
        ["piper", "--model", str(model_path), "--output_file", str(output_path)],
        input=text.encode(),
        capture_output=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Piper TTS failed: {result.stderr.decode()}")

    if not output_path.exists():
        raise RuntimeError(f"Piper ran but output file missing: {output_path}")

    logger.info(f"Audio saved: {output_path} ({output_path.stat().st_size} bytes)")
    return output_path


def list_voices() -> list[str]:
    return list(VOICES.keys())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    output = Path("/tmp/tts_test.wav")
    generate_audio("KnockOff TTS engine is working on the new Mac mini.", output, voice="joe")
    print(f"Generated: {output}")
    import subprocess as sp
    sp.run(["open", str(output)])
