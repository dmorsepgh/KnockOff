#!/usr/bin/env python3.12
"""
Record voice sample from Shure MV7 for HeyGen voice cloning.
"""

import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

MIC_DEVICE = ":6"  # Shure MV7 (audio device index 6)
SAMPLE_RATE = 48000
OUTPUT_DIR = Path("/Users/douglasmorse/KnockOff/voices")
OUTPUT_DIR.mkdir(exist_ok=True)

SCRIPT = """
Hi, I'm Doug Morse. This is a voice sample for HeyGen voice cloning.
I'm recording this so the system can learn how I sound.

Today is a beautiful day to build something new. The sky is clear,
the coffee is hot, and the code is almost working.

Here are a few numbers to calibrate: one, two, three, four, five.
And a few sentences with different tones.

I'm excited about this project because it turns any script into a
video. That's the kind of automation that changes how people create.

Thanks for listening. This is Doug, signing off for now.
"""


def main():
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 45
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    wav_out = OUTPUT_DIR / f"doug-mv7-{stamp}.wav"

    print("=" * 60)
    print("   SHURE MV7 VOICE SAMPLE RECORDER")
    print("=" * 60)
    print()
    print(f"Duration: {duration} seconds")
    print(f"Output:   {wav_out}")
    print()
    print("READ THIS SCRIPT OUT LOUD:")
    print("-" * 60)
    print(SCRIPT.strip())
    print("-" * 60)
    print()
    print("Press ENTER when you're ready to start recording...")
    input()

    print()
    print("Recording in:")
    for i in (3, 2, 1):
        print(f"  {i}...")
        time.sleep(1)
    print("\n🔴 RECORDING NOW — SPEAK!")
    print()

    cmd = [
        "ffmpeg", "-y",
        "-f", "avfoundation",
        "-i", MIC_DEVICE,
        "-ar", str(SAMPLE_RATE),
        "-ac", "1",
        "-t", str(duration),
        "-acodec", "pcm_s16le",
        str(wav_out),
    ]

    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True)

    # Countdown while recording
    for remaining in range(duration, 0, -1):
        print(f"   {remaining:3d}s remaining... ", end="\r", flush=True)
        time.sleep(1)

    proc.wait(timeout=5)
    print()
    print()

    if wav_out.exists() and wav_out.stat().st_size > 1000:
        size_kb = wav_out.stat().st_size / 1024
        print(f"✅ Recorded: {wav_out}")
        print(f"   Size: {size_kb:.0f} KB")
        print()

        # Play it back
        print("Playing back...")
        subprocess.run(["afplay", str(wav_out)])
        print()
        print("Good? If yes, this file is ready to use.")
        print(f"Path: {wav_out}")
    else:
        print(f"❌ Recording failed. Check the mic connection.")
        print(proc.stderr.read() if proc.stderr else "")


if __name__ == "__main__":
    main()
