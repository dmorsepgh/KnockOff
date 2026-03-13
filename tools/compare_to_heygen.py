#!/usr/bin/env python3
"""
Compare KnockOff output to HeyGen and generate improvement suggestions.

Usage:
    python tools/compare_to_heygen.py --heygen video.mp4 --knockoff video.mp4
    python tools/compare_to_heygen.py --heygen video.mp4 --script "Your script" --avatar doug --voice doug
"""

import argparse
import subprocess
import json
import os
from pathlib import Path
from datetime import datetime

COMPARISONS_DIR = Path(__file__).parent.parent / "comparisons"
METRICS_LOG = COMPARISONS_DIR / "metrics_history.json"


def get_video_info(video_path):
    """Extract video metadata using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(video_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout)


def get_audio_levels(video_path):
    """Get audio loudness stats."""
    cmd = [
        "ffmpeg", "-i", str(video_path), "-af",
        "loudnorm=print_format=json", "-f", "null", "-"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    # Parse loudnorm output from stderr
    lines = result.stderr.split('\n')
    for i, line in enumerate(lines):
        if '"input_i"' in line:
            # Found the JSON block
            json_str = '\n'.join(lines[i-1:i+12])
            try:
                # Extract just the JSON part
                start = json_str.find('{')
                end = json_str.rfind('}') + 1
                return json.loads(json_str[start:end])
            except:
                pass
    return {}


def create_side_by_side(heygen_path, knockoff_path, output_path):
    """Create side-by-side comparison video."""
    # First normalize HeyGen to same height
    temp_heygen = output_path.parent / "temp_heygen.mp4"

    # Get KnockOff dimensions
    ko_info = get_video_info(knockoff_path)
    ko_height = None
    for stream in ko_info.get('streams', []):
        if stream.get('codec_type') == 'video':
            ko_height = stream.get('height', 720)
            break
    ko_height = ko_height or 720

    # Scale HeyGen to match height (preserve aspect ratio, ensure even width)
    subprocess.run([
        "ffmpeg", "-y", "-i", str(heygen_path),
        "-vf", f"scale=-2:{ko_height}",
        "-c:v", "libx264", "-crf", "23",
        str(temp_heygen)
    ], capture_output=True)

    # Stack side by side
    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(temp_heygen),
        "-i", str(knockoff_path),
        "-filter_complex",
        "[0:v][1:v]hstack=inputs=2,"
        "drawtext=text='HeyGen':x=50:y=30:fontsize=32:fontcolor=white:shadowcolor=black:shadowx=2:shadowy=2,"
        "drawtext=text='KnockOff':x=w/2+50:y=30:fontsize=32:fontcolor=white:shadowcolor=black:shadowx=2:shadowy=2[v];"
        "[0:a][1:a]amix=inputs=2:duration=shortest[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-crf", "23", "-shortest",
        str(output_path)
    ], capture_output=True)

    # Cleanup
    if temp_heygen.exists():
        temp_heygen.unlink()

    return output_path.exists()


def analyze_differences(heygen_info, knockoff_info, heygen_audio, knockoff_audio):
    """Analyze differences and generate improvement suggestions."""
    suggestions = []
    metrics = {}

    # Video resolution
    for info, name in [(heygen_info, 'heygen'), (knockoff_info, 'knockoff')]:
        for stream in info.get('streams', []):
            if stream.get('codec_type') == 'video':
                metrics[f'{name}_resolution'] = f"{stream.get('width')}x{stream.get('height')}"
                metrics[f'{name}_fps'] = stream.get('r_frame_rate', 'unknown')
                metrics[f'{name}_bitrate'] = stream.get('bit_rate', 'unknown')

    # Audio levels
    if heygen_audio and knockoff_audio:
        heygen_loud = float(heygen_audio.get('input_i', -24))
        knockoff_loud = float(knockoff_audio.get('input_i', -24))
        metrics['heygen_loudness'] = heygen_loud
        metrics['knockoff_loudness'] = knockoff_loud

        if abs(heygen_loud - knockoff_loud) > 3:
            if knockoff_loud < heygen_loud:
                suggestions.append(f"Audio too quiet: KnockOff is {heygen_loud - knockoff_loud:.1f}dB quieter. Increase TTS volume or normalize audio.")
            else:
                suggestions.append(f"Audio too loud: KnockOff is {knockoff_loud - heygen_loud:.1f}dB louder. Reduce TTS volume.")

    # Duration comparison
    heygen_dur = float(heygen_info.get('format', {}).get('duration', 0))
    knockoff_dur = float(knockoff_info.get('format', {}).get('duration', 0))
    metrics['heygen_duration'] = heygen_dur
    metrics['knockoff_duration'] = knockoff_dur

    if abs(heygen_dur - knockoff_dur) > 5:
        suggestions.append(f"Duration mismatch: HeyGen={heygen_dur:.1f}s, KnockOff={knockoff_dur:.1f}s. Check TTS speaking rate.")

    # Resolution suggestions
    if 'knockoff_resolution' in metrics and 'heygen_resolution' in metrics:
        if metrics['knockoff_resolution'] != metrics['heygen_resolution']:
            suggestions.append(f"Resolution differs: HeyGen={metrics['heygen_resolution']}, KnockOff={metrics['knockoff_resolution']}. Consider matching aspect ratio.")

    return metrics, suggestions


def log_metrics(metrics, suggestions, script_name="unknown"):
    """Log metrics to history file for tracking improvement over time."""
    COMPARISONS_DIR.mkdir(exist_ok=True)

    history = []
    if METRICS_LOG.exists():
        with open(METRICS_LOG) as f:
            history = json.load(f)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "script": script_name,
        "metrics": metrics,
        "suggestions": suggestions,
        "suggestion_count": len(suggestions)
    }
    history.append(entry)

    with open(METRICS_LOG, 'w') as f:
        json.dump(history, f, indent=2)

    return entry


def print_report(metrics, suggestions, comparison_video):
    """Print comparison report."""
    print("\n" + "="*60)
    print("KNOCKOFF vs HEYGEN COMPARISON REPORT")
    print("="*60)

    print("\n📊 METRICS:")
    print(f"  HeyGen:   {metrics.get('heygen_resolution', '?')} @ {metrics.get('heygen_fps', '?')} fps, {metrics.get('heygen_duration', 0):.1f}s")
    print(f"  KnockOff: {metrics.get('knockoff_resolution', '?')} @ {metrics.get('knockoff_fps', '?')} fps, {metrics.get('knockoff_duration', 0):.1f}s")

    if 'heygen_loudness' in metrics:
        print(f"\n🔊 AUDIO LOUDNESS:")
        print(f"  HeyGen:   {metrics.get('heygen_loudness', 0):.1f} LUFS")
        print(f"  KnockOff: {metrics.get('knockoff_loudness', 0):.1f} LUFS")

    print(f"\n💡 IMPROVEMENT SUGGESTIONS ({len(suggestions)}):")
    if suggestions:
        for i, s in enumerate(suggestions, 1):
            print(f"  {i}. {s}")
    else:
        print("  ✅ No major issues detected!")

    print(f"\n🎬 SIDE-BY-SIDE VIDEO: {comparison_video}")
    print("\n" + "="*60)

    # Common manual checks
    print("\n👁️ MANUAL CHECKS (watch the comparison):")
    print("  □ Lip sync timing - do lips match audio?")
    print("  □ Face quality - any artifacts or blur?")
    print("  □ Voice naturalness - does TTS sound robotic?")
    print("  □ Pacing - is speech too fast/slow?")
    print("  □ Expression - does avatar look natural?")
    print("="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Compare KnockOff to HeyGen output")
    parser.add_argument("--heygen", required=True, help="Path to HeyGen video")
    parser.add_argument("--knockoff", help="Path to KnockOff video (or generate new)")
    parser.add_argument("--script", help="Script text to generate KnockOff video")
    parser.add_argument("--avatar", default="doug", help="Avatar name")
    parser.add_argument("--voice", default="doug", help="Voice name")
    parser.add_argument("--name", default="comparison", help="Name for this comparison")
    parser.add_argument("--open", action="store_true", help="Open comparison video when done")

    args = parser.parse_args()

    COMPARISONS_DIR.mkdir(exist_ok=True)

    heygen_path = Path(args.heygen)
    if not heygen_path.exists():
        print(f"Error: HeyGen video not found: {heygen_path}")
        return 1

    # Generate KnockOff video if script provided
    if args.script and not args.knockoff:
        print("🎬 Generating KnockOff video...")
        knockoff_path = COMPARISONS_DIR / f"knockoff_{args.name}.mp4"

        # Run generation
        gen_script = Path(__file__).parent / "generate_avatar_video.py"
        result = subprocess.run([
            "python", str(gen_script),
            args.script,
            "--avatar", args.avatar,
            "--voice", args.voice,
            "--output", str(knockoff_path)
        ], capture_output=True, text=True, cwd=Path(__file__).parent.parent)

        if not knockoff_path.exists():
            print(f"Error generating KnockOff video: {result.stderr}")
            return 1
    else:
        knockoff_path = Path(args.knockoff)

    if not knockoff_path.exists():
        print(f"Error: KnockOff video not found: {knockoff_path}")
        return 1

    print("📊 Analyzing videos...")

    # Get video info
    heygen_info = get_video_info(heygen_path)
    knockoff_info = get_video_info(knockoff_path)

    # Get audio levels
    heygen_audio = get_audio_levels(heygen_path)
    knockoff_audio = get_audio_levels(knockoff_path)

    # Create comparison video
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    comparison_path = COMPARISONS_DIR / f"compare_{args.name}_{timestamp}.mp4"

    print("🎬 Creating side-by-side comparison...")
    if create_side_by_side(heygen_path, knockoff_path, comparison_path):
        print(f"✅ Comparison video: {comparison_path}")
    else:
        print("⚠️ Failed to create comparison video")
        comparison_path = "N/A"

    # Analyze differences
    metrics, suggestions = analyze_differences(
        heygen_info, knockoff_info,
        heygen_audio, knockoff_audio
    )

    # Log metrics
    log_metrics(metrics, suggestions, args.name)

    # Print report
    print_report(metrics, suggestions, comparison_path)

    # Open if requested
    if args.open and comparison_path != "N/A":
        subprocess.run(["open", str(comparison_path)])

    return 0


if __name__ == "__main__":
    exit(main())
