#!/usr/bin/env python3
"""
Generate SRT captions using Whisper for accurate word-level timestamps.

Uses Whisper's word_timestamps feature to get precise timing for each word,
then groups words into readable caption chunks.
"""

import argparse
import sys
from pathlib import Path


def format_srt_time(seconds: float) -> str:
    """Format seconds as SRT timestamp (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt_from_whisper(
    audio_path: Path,
    output_path: Path,
    words_per_caption: int = 6,
    model_size: str = "base"
) -> Path:
    """
    Generate SRT file using Whisper word-level timestamps.

    Args:
        audio_path: Path to audio file (wav/mp3)
        output_path: Path for output SRT file
        words_per_caption: Max words per caption line (default 6 for readability)
        model_size: Whisper model size (tiny/base/small/medium/large)

    Returns:
        Path to generated SRT file
    """
    import whisper

    print(f"Loading Whisper model ({model_size})...")
    model = whisper.load_model(model_size)

    print(f"Transcribing {audio_path.name}...")
    result = model.transcribe(
        str(audio_path),
        word_timestamps=True,
        language="en"
    )

    # Extract word-level timestamps
    words_with_timing = []
    for segment in result["segments"]:
        if "words" in segment:
            for word_info in segment["words"]:
                words_with_timing.append({
                    "word": word_info["word"].strip(),
                    "start": word_info["start"],
                    "end": word_info["end"]
                })

    if not words_with_timing:
        print("Warning: No word timestamps found, falling back to segment timing")
        # Fallback to segment-level timing
        for segment in result["segments"]:
            words = segment["text"].strip().split()
            if words:
                duration = segment["end"] - segment["start"]
                time_per_word = duration / len(words)
                for i, word in enumerate(words):
                    words_with_timing.append({
                        "word": word,
                        "start": segment["start"] + (i * time_per_word),
                        "end": segment["start"] + ((i + 1) * time_per_word)
                    })

    print(f"Found {len(words_with_timing)} words with timestamps")

    # Group words into caption chunks
    srt_lines = []
    caption_num = 1

    i = 0
    while i < len(words_with_timing):
        # Get chunk of words
        chunk = words_with_timing[i:i + words_per_caption]

        if not chunk:
            break

        # Build caption text
        caption_text = " ".join(w["word"] for w in chunk)

        # Get timing from first and last word in chunk
        start_time = chunk[0]["start"]
        end_time = chunk[-1]["end"]

        # Add small buffer to end time for readability
        end_time = min(end_time + 0.1,
                      words_with_timing[min(i + words_per_caption, len(words_with_timing) - 1)]["start"]
                      if i + words_per_caption < len(words_with_timing) else end_time + 0.5)

        # Write SRT entry
        srt_lines.append(str(caption_num))
        srt_lines.append(f"{format_srt_time(start_time)} --> {format_srt_time(end_time)}")
        srt_lines.append(caption_text)
        srt_lines.append("")

        caption_num += 1
        i += words_per_caption

    # Write SRT file
    output_path.write_text("\n".join(srt_lines))
    print(f"Generated {caption_num - 1} captions: {output_path}")

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate SRT captions using Whisper word-level timestamps"
    )
    parser.add_argument(
        "audio",
        type=Path,
        help="Input audio file (wav/mp3)"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output SRT file (default: same name as audio with .srt)"
    )
    parser.add_argument(
        "-w", "--words",
        type=int,
        default=6,
        help="Max words per caption (default: 6)"
    )
    parser.add_argument(
        "-m", "--model",
        choices=["tiny", "base", "small", "medium", "large"],
        default="base",
        help="Whisper model size (default: base)"
    )

    args = parser.parse_args()

    if not args.audio.exists():
        print(f"Error: Audio file not found: {args.audio}")
        sys.exit(1)

    output_path = args.output or args.audio.with_suffix(".srt")

    generate_srt_from_whisper(
        audio_path=args.audio,
        output_path=output_path,
        words_per_caption=args.words,
        model_size=args.model
    )


if __name__ == "__main__":
    main()
