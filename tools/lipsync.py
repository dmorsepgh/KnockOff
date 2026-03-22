#!/usr/bin/env python3
"""
Lip Sync - Wrap Easy-Wav2Lip to produce lip-synced avatar video.
"""

import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

WAV2LIP_DIR = Path.home() / "Easy-Wav2Lip"
WAV2LIP_SCRIPT = WAV2LIP_DIR / "inference.py"

QUALITY_MODES = ["Fast", "Improved", "Enhanced"]


def run_lipsync(
    avatar_path: Path,
    audio_path: Path,
    output_path: Path,
    quality: str = "Improved",
) -> Path:
    """
    Run Wav2Lip lip sync on an avatar video + audio file.

    Args:
        avatar_path: Path to avatar video (.mp4)
        audio_path: Path to audio file (.wav)
        output_path: Where to save the lip-synced video
        quality: "Fast", "Improved", or "Enhanced"

    Returns:
        Path to the generated video
    """
    avatar_path = Path(avatar_path)
    audio_path = Path(audio_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not WAV2LIP_SCRIPT.exists():
        raise FileNotFoundError(f"Easy-Wav2Lip not found at {WAV2LIP_DIR}")
    if not avatar_path.exists():
        raise FileNotFoundError(f"Avatar not found: {avatar_path}")
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")
    if quality not in QUALITY_MODES:
        raise ValueError(f"Quality must be one of {QUALITY_MODES}")

    logger.info(f"Running lipsync: avatar={avatar_path.name}, quality={quality}")

    # Swap in a per-avatar face detection cache so we skip re-detection on repeat runs.
    # Easy-Wav2Lip reads/writes "last_detected_face.pkl" relative to its cwd.
    cache = WAV2LIP_DIR / "last_detected_face.pkl"
    avatar_cache = WAV2LIP_DIR / f"face_cache_{avatar_path.stem}.pkl"
    if avatar_cache.exists():
        import shutil
        shutil.copy2(avatar_cache, cache)
        logger.info(f"  Using face cache for {avatar_path.stem}")
    elif cache.exists():
        cache.unlink()

    wav2lip_python = WAV2LIP_DIR / ".venv" / "bin" / "python"
    python_bin = str(wav2lip_python) if wav2lip_python.exists() else "python"

    # Fast uses the base Wav2Lip model; Improved/Enhanced use the GAN model
    checkpoint = "checkpoints/Wav2Lip.pth" if quality == "Fast" else "checkpoints/Wav2Lip_GAN.pth"

    cmd = [
        python_bin, str(WAV2LIP_SCRIPT),
        "--checkpoint_path", checkpoint,
        "--face", str(avatar_path.resolve()),
        "--audio", str(audio_path.resolve()),
        "--outfile", str(output_path.resolve()),
        "--out_height", "720",
        "--quality", quality,
        "--wav2lip_batch_size", "64",
    ]

    result = subprocess.run(cmd, cwd=str(WAV2LIP_DIR), capture_output=True, text=True)

    if result.returncode != 0:
        logger.error(f"Wav2Lip stderr:\n{result.stderr}")
        raise RuntimeError(f"Wav2Lip failed (exit {result.returncode})")

    if not output_path.exists():
        raise RuntimeError(f"Wav2Lip ran but output missing: {output_path}")

    # Save face cache for this avatar so future runs skip detection
    if cache.exists() and not avatar_cache.exists():
        import shutil
        shutil.copy2(cache, avatar_cache)
        logger.info(f"  Saved face cache for {avatar_path.stem}")

    logger.info(f"Lipsync complete: {output_path}")
    return output_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    avatar = Path("avatars/doug.mp4")
    audio = Path("/tmp/tts_test.wav")
    output = Path(".tmp/test_lipsync.mp4")

    if not avatar.exists():
        print(f"Put an avatar at {avatar} first")
    elif not audio.exists():
        print("Run tts.py first to generate /tmp/tts_test.wav")
    else:
        result = run_lipsync(avatar, audio, output, quality="Fast")
        print(f"Generated: {result}")
        import subprocess as sp
        sp.run(["open", str(result)])
