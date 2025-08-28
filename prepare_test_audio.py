# prepare_test_audio.py
"""
Prepare audio files for testing by ensuring they're in the optimal format.

This script uses ffmpeg to convert audio files to Whisper-friendly format:
- 16kHz sample rate
- Mono channel
- 16-bit PCM WAV
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


def check_ffmpeg() -> bool:
    """Check if ffmpeg is available."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def convert_audio_to_whisper_format(
    input_path: Path, output_path: Path, verbose: bool = True
) -> bool:
    """
    Convert audio file to Whisper-friendly format using ffmpeg.

    Args:
        input_path: Path to input audio file
        output_path: Path for output WAV file
        verbose: Whether to print progress

    Returns:
        True if successful, False otherwise
    """
    if verbose:
        print(f"Converting: {input_path.name}")

    # Build ffmpeg command for Whisper-optimized output
    cmd = [
        "ffmpeg",
        "-i",
        str(input_path),  # Input file
        "-ar",
        "16000",  # 16kHz sample rate
        "-ac",
        "1",  # Mono
        "-c:a",
        "pcm_s16le",  # 16-bit PCM
        "-y",  # Overwrite output
        str(output_path),  # Output file
    ]

    try:
        # Run with minimal output
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=30
        )

        if result.returncode == 0:
            if verbose:
                # Check file size
                size_kb = output_path.stat().st_size / 1024
                print(f"   ✅ Created: {output_path.name} ({size_kb:.1f} KB)")
            return True
        else:
            if verbose:
                print(f"   ❌ Failed: ffmpeg returned {result.returncode}")
                if result.stderr:
                    print(f"      Error: {result.stderr[:200]}")
            return False

    except subprocess.TimeoutExpired:
        if verbose:
            print(f"   ❌ Timeout: conversion took too long")
        return False
    except Exception as e:
        if verbose:
            print(f"   ❌ Error: {e}")
        return False


def prepare_ljs_audio_files() -> List[Tuple[Path, Path]]:
    """
    Find and prepare LJSpeech audio files for testing.

    Returns:
        List of (original_path, converted_path) tuples
    """
    ljs_dir = Path("tests/data/ljs")

    if not ljs_dir.exists():
        print(f"LJSpeech directory not found: {ljs_dir}")
        print("Creating directory structure...")
        ljs_dir.mkdir(parents=True, exist_ok=True)
        return []

    # Find all WAV files
    audio_files = list(ljs_dir.glob("*.wav"))

    if not audio_files:
        print(f"No WAV files found in {ljs_dir}")
        return []

    print(f"Found {len(audio_files)} audio files in {ljs_dir}")

    # Create processed directory
    processed_dir = ljs_dir / "processed"
    processed_dir.mkdir(exist_ok=True)

    converted_files = []
    for audio_path in audio_files[:5]:  # Process first 5 for testing
        output_path = processed_dir / f"whisper_{audio_path.name}"

        if output_path.exists():
            print(f"   ⏭️  Skipping {audio_path.name} (already processed)")
            converted_files.append((audio_path, output_path))
        else:
            success = convert_audio_to_whisper_format(
                audio_path, output_path, verbose=True
            )
            if success:
                converted_files.append((audio_path, output_path))

    return converted_files


def create_sample_test_files() -> None:
    """Create sample test files if no LJS data is available."""
    import math
    import wave

    test_dir = Path("tests/data/ljs")
    test_dir.mkdir(parents=True, exist_ok=True)

    print("\nCreating sample test audio files...")

    # Create different test patterns
    test_cases = [
        ("test_silence.wav", lambda i, rate: 0),  # Silence
        (
            "test_tone_440.wav",
            lambda i, rate: int(16000 * math.sin(2 * math.pi * 440 * i / rate)),
        ),  # 440Hz
        (
            "test_tone_880.wav",
            lambda i, rate: int(16000 * math.sin(2 * math.pi * 880 * i / rate)),
        ),  # 880Hz
    ]

    for filename, sample_func in test_cases:
        output_path = test_dir / filename

        if output_path.exists():
            print(f"   ⏭️  {filename} already exists")
            continue

        # Create 3 seconds of audio
        sample_rate = 16000
        duration = 3.0

        with wave.open(str(output_path), "wb") as wav:
            wav.setnchannels(1)  # Mono
            wav.setsampwidth(2)  # 16-bit
            wav.setframerate(sample_rate)

            samples = []
            for i in range(int(sample_rate * duration)):
                sample = sample_func(i, sample_rate)
                # Clip to 16-bit range
                sample = max(-32768, min(32767, sample))
                samples.append(sample.to_bytes(2, "little", signed=True))

            wav.writeframes(b"".join(samples))

        size_kb = output_path.stat().st_size / 1024
        print(f"   ✅ Created: {filename} ({size_kb:.1f} KB)")


def verify_audio_file(audio_path: Path) -> None:
    """Use ffprobe to verify audio file properties."""
    if not audio_path.exists():
        print(f"File not found: {audio_path}")
        return

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-select_streams",
        "a:0",
        "-of",
        "json",
        str(audio_path),
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=5
        )

        import json

        data = json.loads(result.stdout)

        if data.get("streams"):
            stream = data["streams"][0]
            print(f"\nAudio properties for {audio_path.name}:")
            print(f"  Codec: {stream.get('codec_name', 'unknown')}")
            print(f"  Sample Rate: {stream.get('sample_rate', 'unknown')} Hz")
            print(f"  Channels: {stream.get('channels', 'unknown')}")
            print(f"  Duration: {stream.get('duration', 'unknown')} seconds")
            print(f"  Bit Rate: {stream.get('bit_rate', 'unknown')} bps")

    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        json.JSONDecodeError,
    ) as e:
        print(f"Could not verify audio properties: {e}")


def main():
    """Main function to prepare test audio files."""
    print("=" * 60)
    print("Audio File Preparation for MLX Whisper")
    print("=" * 60)

    # Check ffmpeg
    if not check_ffmpeg():
        print("\n❌ ffmpeg is not installed!")
        print("Install with: brew install ffmpeg")
        return 1

    print("✅ ffmpeg is installed\n")

    # Try to prepare LJS files
    converted = prepare_ljs_audio_files()

    if not converted:
        # Create sample files as fallback
        create_sample_test_files()

    # Verify one file
    test_dir = Path("tests/data/ljs")
    if test_dir.exists():
        test_files = list(test_dir.glob("*.wav"))
        if test_files:
            print("\n" + "-" * 40)
            verify_audio_file(test_files[0])

    print("\n" + "=" * 60)
    print("✅ Audio preparation complete!")
    print("Test files are in: tests/data/ljs/")

    return 0


if __name__ == "__main__":
    sys.exit(main())
