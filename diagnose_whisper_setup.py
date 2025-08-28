# diagnose_whisper_setup.py
"""
Comprehensive diagnostic script for mlx-whisper setup and troubleshooting.

Run this to verify all requirements are met and test transcription.
"""

import io
import math
import subprocess
import sys
import tempfile
import wave
from pathlib import Path


def check_python_version():
    """Check Python version is 3.12."""
    print("1. Checking Python version...")
    version = sys.version_info
    if version.major == 3 and version.minor == 12:
        print(f"   ✅ Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"   ⚠️  Python {version.major}.{version.minor} (3.12 recommended)")
        return False


def check_ffmpeg():
    """Check if ffmpeg is installed and working."""
    print("\n2. Checking ffmpeg installation...")
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if result.returncode == 0:
            # Extract version from output
            lines = result.stdout.split("\n")
            version_line = lines[0] if lines else "Unknown"
            print(f"   ✅ ffmpeg installed: {version_line}")
            return True
        else:
            print("   ❌ ffmpeg command failed")
            return False
    except FileNotFoundError:
        print("   ❌ ffmpeg not found in PATH")
        print("      Install with: brew install ffmpeg")
        return False
    except subprocess.TimeoutExpired:
        print("   ❌ ffmpeg command timed out")
        return False


def check_mlx_packages():
    """Check if MLX and mlx-whisper are installed."""
    print("\n3. Checking MLX packages...")
    packages = {
        "mlx": "MLX framework",
        "mlx_whisper": "MLX Whisper",
        "huggingface_hub": "HuggingFace Hub (for model downloads)",
    }

    all_installed = True
    for module, description in packages.items():
        try:
            mod = __import__(module)
            version = getattr(mod, "__version__", "unknown")
            print(f"   ✅ {description}: {version}")
        except ImportError:
            print(f"   ❌ {description} not installed")
            all_installed = False

    if not all_installed:
        print("      Install missing packages with: pip install mlx mlx-whisper")

    return all_installed


def check_models():
    """Check which MLX Whisper models are available."""
    print("\n4. Checking available models...")

    # Common MLX-optimized Whisper models
    models = [
        "mlx-community/whisper-tiny-mlx",
        "mlx-community/whisper-base-mlx",
        "mlx-community/whisper-small-mlx",
        "mlx-community/whisper-medium-mlx",
        "mlx-community/whisper-large-v3-mlx",
        "mlx-community/whisper-large-v3-turbo",
    ]

    print("   Common MLX Whisper models:")
    for model in models:
        print(f"   - {model}")

    # Check if any models are already cached
    cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    if cache_dir.exists():
        cached_models = list(cache_dir.glob("models--mlx-community--whisper*"))
        if cached_models:
            print(f"\n   📦 Found {len(cached_models)} cached model(s):")
            for model_path in cached_models[:3]:  # Show first 3
                model_name = model_path.name.replace("models--", "").replace("--", "/")
                size_mb = sum(
                    f.stat().st_size for f in model_path.rglob("*") if f.is_file()
                ) / (1024 * 1024)
                print(f"      - {model_name} ({size_mb:.1f} MB)")
        else:
            print("   ℹ️  No models cached yet (will download on first use)")

    return True


def create_test_audio() -> bytes:
    """Create a simple test WAV file with a tone."""
    print("\n5. Creating test audio file...")

    # Create 2 seconds of audio: 1s silence + 1s tone
    sample_rate = 16000
    duration = 2.0
    samples = []

    for i in range(int(sample_rate * duration)):
        if i < sample_rate:
            # First second: silence
            sample = 0
        else:
            # Second second: 440Hz sine wave (A note)
            t = (i - sample_rate) / sample_rate
            sample = int(16000 * math.sin(2 * math.pi * 440 * t))
        samples.append(sample)

    # Create WAV file in memory
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)  # Mono
        wav.setsampwidth(2)  # 16-bit
        wav.setframerate(sample_rate)

        wav_data = b"".join(
            sample.to_bytes(2, byteorder="little", signed=True) for sample in samples
        )
        wav.writeframes(wav_data)

    audio_bytes = buffer.getvalue()
    print(f"   ✅ Created test audio: 16kHz mono WAV, {len(audio_bytes)} bytes")
    return audio_bytes


def test_transcription(audio_bytes: bytes):
    """Test actual transcription with mlx_whisper."""
    print("\n6. Testing transcription...")

    try:
        import mlx_whisper
    except ImportError:
        print("   ❌ Cannot import mlx_whisper")
        return False

    # Write to temp file (mlx_whisper needs a file path)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = Path(tmp.name)

    try:
        # Use tiny model for quick testing
        model = "mlx-community/whisper-tiny-mlx"
        print(f"   Using model: {model}")
        print("   ⏳ Transcribing (first run downloads model)...")

        result = mlx_whisper.transcribe(
            str(tmp_path), path_or_hf_repo=model, verbose=False
        )

        text = result.get("text", "").strip()
        print(f"   ✅ Transcription successful!")
        print(f"      Result: '{text}' ({len(text)} chars)")

        # Note: synthetic audio often produces empty or hallucinated text
        if not text:
            print("      (Empty result is normal for synthetic audio)")

        return True

    except FileNotFoundError as e:
        if "ffmpeg" in str(e).lower():
            print(f"   ❌ ffmpeg not found: {e}")
            print("      Install with: brew install ffmpeg")
        else:
            print(f"   ❌ File error: {e}")
        return False

    except Exception as e:
        print(f"   ❌ Transcription failed: {e}")
        print(f"      Error type: {type(e).__name__}")

        # Common issues and solutions
        if "connection" in str(e).lower() or "ssl" in str(e).lower():
            print("\n   💡 Network issue detected. Check:")
            print("      - Internet connection")
            print("      - Proxy/firewall settings")
            print("      - Try: export HF_HUB_OFFLINE=1 (if model is cached)")
        elif "memory" in str(e).lower():
            print("\n   💡 Memory issue detected. Try:")
            print("      - Close other applications")
            print("      - Use a smaller model (tiny or base)")

        return False

    finally:
        # Clean up temp file
        try:
            tmp_path.unlink(missing_ok=True)
        except:
            pass


def test_with_real_audio():
    """Test with a real audio file if available."""
    print("\n7. Testing with real audio (optional)...")

    # Look for test audio files
    test_paths = [
        Path("tests/data/ljs/LJ001-0001.wav"),
        Path("test_data/sample.wav"),
        Path("audio.wav"),
    ]

    for audio_path in test_paths:
        if audio_path.exists():
            print(f"   Found test file: {audio_path}")
            print(f"   File size: {audio_path.stat().st_size / 1024:.1f} KB")

            try:
                import mlx_whisper

                print("   ⏳ Transcribing real audio...")
                result = mlx_whisper.transcribe(
                    str(audio_path),
                    path_or_hf_repo="mlx-community/whisper-base-mlx",
                    verbose=False,
                )

                text = result.get("text", "").strip()
                print(f"   ✅ Transcription successful!")
                print(f"      First 100 chars: '{text[:100]}...'")
                return True

            except Exception as e:
                print(f"   ❌ Failed: {e}")
                return False

    print("   ℹ️  No real audio files found to test")
    return None


def main():
    """Run all diagnostic checks."""
    print("=" * 60)
    print("MLX Whisper Diagnostic Tool")
    print("=" * 60)

    # Track results
    checks = {
        "Python 3.12": check_python_version(),
        "ffmpeg": check_ffmpeg(),
        "MLX packages": check_mlx_packages(),
        "Model info": check_models(),
    }

    # Only test transcription if prerequisites are met
    if checks["ffmpeg"] and checks["MLX packages"]:
        audio_bytes = create_test_audio()
        checks["Synthetic audio transcription"] = test_transcription(audio_bytes)

        # Optional: test with real audio
        real_result = test_with_real_audio()
        if real_result is not None:
            checks["Real audio transcription"] = real_result
    else:
        print("\n⚠️  Skipping transcription tests due to missing prerequisites")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    for check, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"{status} {check}")

    all_passed = all(checks.values())

    if all_passed:
        print("\n🎉 All checks passed! Your MLX Whisper setup is ready.")
    else:
        print("\n⚠️  Some checks failed. Please fix the issues above.")
        print("\nNext steps:")
        if not checks.get("ffmpeg"):
            print("1. Install ffmpeg: brew install ffmpeg")
        if not checks.get("MLX packages"):
            print("2. Install MLX: pip install mlx mlx-whisper")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
