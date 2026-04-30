#!/usr/bin/env python3
"""
TTS Engine - Generate audio from text using Piper TTS and XTTS voice cloning.
"""

import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
MODELS_DIR = PROJECT_ROOT / "models" / "piper"
VOICES_DIR = PROJECT_ROOT / "voices"
XTTS_PYTHON = PROJECT_ROOT / ".venv-voice" / "bin" / "tts"

VOICES = {
    "joe": MODELS_DIR / "en_US-joe-medium.onnx",
    "lessac": MODELS_DIR / "en_US-lessac-medium.onnx",
    "amy": MODELS_DIR / "en_US-amy-medium.onnx",
    "danny": MODELS_DIR / "en_US-danny-low.onnx",
    "ryan": MODELS_DIR / "en_US-ryan-medium.onnx",
    "kusal": MODELS_DIR / "en_US-kusal-medium.onnx",
    "arctic": MODELS_DIR / "en_US-arctic-medium.onnx",
}

# Custom voice presets: (base_voice, length_scale, pitch_shift)
# pitch_shift is a multiplier on sample rate (1.08 = 8% higher)
VOICE_PRESETS = {
    "cooper": ("kusal", 0.85, 1.08),
    "trump": ("ryan", 1.1, 0.92),
}

# XTTS voice clones: name -> reference WAV file
# Use "hannity-clone" etc. in scripts to use cloned voices
VOICE_CLONES = {}
if VOICES_DIR.exists():
    for ref_file in VOICES_DIR.glob("*_ref.wav"):
        clone_name = ref_file.stem.replace("_ref", "") + "-clone"
        VOICE_CLONES[clone_name] = ref_file


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

    logger.info(f"Generating TTS audio: {len(text)} chars, voice={voice}")

    # Check for XTTS voice clone
    clone_ref = VOICE_CLONES.get(voice)
    if clone_ref:
        return _generate_xtts(text, output_path, clone_ref, voice)

    # Check for custom voice preset
    preset = VOICE_PRESETS.get(voice)
    if preset:
        base_voice, length_scale, pitch_shift = preset
        model_path = VOICES.get(base_voice)
        if not model_path:
            raise ValueError(f"Unknown base voice '{base_voice}' for preset '{voice}'")
    else:
        model_path = VOICES.get(voice)
        length_scale = None
        pitch_shift = None

    if not model_path:
        all_voices = list(VOICES.keys()) + list(VOICE_PRESETS.keys()) + list(VOICE_CLONES.keys())
        raise ValueError(f"Unknown voice '{voice}'. Available: {all_voices}")
    if not model_path.exists():
        raise FileNotFoundError(f"Voice model not found: {model_path}")

    # Build piper command
    piper_cmd = ["piper", "--model", str(model_path), "--output_file", str(output_path)]
    if length_scale:
        piper_cmd.extend(["--length_scale", str(length_scale)])

    result = subprocess.run(
        piper_cmd,
        input=text.encode(),
        capture_output=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Piper TTS failed: {result.stderr.decode()}")

    if not output_path.exists():
        raise RuntimeError(f"Piper ran but output file missing: {output_path}")

    # Apply pitch shift if preset requires it
    if pitch_shift and pitch_shift != 1.0:
        import tempfile
        tmp = Path(tempfile.mktemp(suffix=".wav"))
        # Shift pitch up by changing sample rate, then correct tempo
        tempo_correct = 1.0 / pitch_shift
        subprocess.run([
            "ffmpeg", "-y", "-i", str(output_path),
            "-af", f"asetrate=22050*{pitch_shift},atempo={tempo_correct:.4f}",
            str(tmp)
        ], capture_output=True, check=True)
        tmp.replace(output_path)

    logger.info(f"Audio saved: {output_path} ({output_path.stat().st_size} bytes)")
    return output_path


def _generate_xtts(text: str, output_path: Path, ref_wav: Path, voice_name: str) -> Path:
    """Generate audio using XTTS v2 voice cloning."""
    logger.info(f"XTTS clone: {voice_name} (ref: {ref_wav.name})")

    cmd = [
        str(XTTS_PYTHON),
        "--model_name", "tts_models/multilingual/multi-dataset/xtts_v2",
        "--speaker_wav", str(ref_wav),
        "--language_idx", "en",
        "--text", text,
        "--out_path", str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        raise RuntimeError(f"XTTS failed: {result.stderr[-300:]}")

    if not output_path.exists():
        raise RuntimeError(f"XTTS ran but output file missing: {output_path}")

    logger.info(f"Audio saved: {output_path} ({output_path.stat().st_size} bytes)")
    return output_path


def list_voices() -> list[str]:
    return list(VOICES.keys()) + list(VOICE_PRESETS.keys()) + list(VOICE_CLONES.keys())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    output = Path("/tmp/tts_test.wav")
    generate_audio("KnockOff TTS engine is working on the new Mac mini.", output, voice="joe")
    print(f"Generated: {output}")
    import subprocess as sp
    sp.run(["open", str(output)])
