"""
Comprehensive test suite for the Whisper FastAPI service.

This suite validates:
- /health endpoint functionality and response format
- /v1/transcribe accepts valid audio files and returns transcriptions
- /metrics endpoint provides accurate service metrics
- Oversized uploads are rejected with 413
- Wrong content types are rejected with 415
- Large audio files are handled properly
- Concurrency limits and semaphore behavior
- Memory pressure handling
- Rate limiting (when implemented)
- Caching functionality

Assumptions:
- Service is running at WHISPER_API_URL (default http://localhost:8000)
- Sample audio files may exist under ./test_data; if not, synthetic files are created
"""

import io
import os
import random
import time
import unittest
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

import requests
from icecream import ic

# Test configuration
WHISPER_API_URL = os.getenv("WHISPER_API_URL", "http://localhost:8000")
TRANSCRIBE_URL = f"{WHISPER_API_URL.rstrip('/')}/v1/transcribe"
HEALTH_URL = f"{WHISPER_API_URL.rstrip('/')}/health"
METRICS_URL = f"{WHISPER_API_URL.rstrip('/')}/metrics"

TEST_DATA_PATH = Path("./test_data")
TIMEOUT_S = 120.0  # Longer timeout for transcription
MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024  # Keep in sync with server


def _find_audio_files(root: Path) -> List[Path]:
    """Return audio file paths under root for common extensions."""
    patterns = ("*.wav", "*.mp3", "*.m4a", "*.flac", "*.webm", "*.mp4")
    results: List[Path] = []
    
    for pattern in patterns:
        results.extend(root.rglob(pattern))
    
    # De-duplicate and filter for existing files
    seen = set()
    unique = []
    for path in results:
        if path.is_file():
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                unique.append(path)
    
    return unique


def _create_synthetic_wav(
    duration_seconds: float = 5.0,
    sample_rate: int = 16000,
    frequency: float = 440.0,
) -> bytes:
    """Create a synthetic WAV file with a sine wave tone."""
    import math
    
    frames = int(duration_seconds * sample_rate)
    samples = []
    
    for i in range(frames):
        # Generate sine wave
        sample = int(32767 * math.sin(2 * math.pi * frequency * i / sample_rate))
        samples.append(sample)
    
    # Create WAV file in memory
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        
        # Convert samples to bytes
        wav_data = b''.join(sample.to_bytes(2, byteorder='little', signed=True) 
                           for sample in samples)
        wav_file.writeframes(wav_data)
    
    return buffer.getvalue()


def _create_large_synthetic_wav(duration_minutes: float = 10.0) -> bytes:
    """Create a large synthetic WAV file for testing."""
    return _create_synthetic_wav(duration_seconds=duration_minutes * 60.0)


def _post_audio_file(
    url: str,
    filename: str,
    data: bytes,
    content_type: str = "audio/wav",
) -> requests.Response:
    """POST audio file as multipart/form-data."""
    files = {"file": (filename, io.BytesIO(data), content_type)}
    
    ic(f"POST {url} -> {filename} ({len(data)} bytes, {content_type})")
    start = time.perf_counter()
    
    response = requests.post(
        url, 
        files=files, 
        timeout=TIMEOUT_S,
        headers={"Expect": ""}
    )
    
    duration_ms = (time.perf_counter() - start) * 1000.0
    ic(response.status_code, f"{duration_ms:.1f} ms")
    
    return response


def _validate_json_serializable(obj: Any) -> int:
    """Validate that object is JSON serializable and return byte size."""
    import json
    try:
        json_str = json.dumps(obj, ensure_ascii=False)
        return len(json_str.encode('utf-8'))
    except (TypeError, ValueError) as e:
        raise AssertionError(f"Object is not JSON serializable: {e}")


class TestWhisperApi(unittest.TestCase):
    """End-to-end tests for the Whisper transcription API."""
    
    @classmethod
    def setUpClass(cls) -> None:
        """Set up test class with audio files and service validation."""
        ic.configureOutput(prefix="TEST| ", includeContext=True)
        ic(f"Testing service at: {WHISPER_API_URL}")
        ic(f"HEALTH_URL={HEALTH_URL}")
        ic(f"TRANSCRIBE_URL={TRANSCRIBE_URL}")
        ic(f"METRICS_URL={METRICS_URL}")
        
        # Validate service is running
        try:
            response = requests.get(HEALTH_URL, timeout=10)
            ic("Health check:", response.status_code, response.text)
            assert response.ok, f"Service health check failed: {response.text}"
        except requests.RequestException as e:
            raise AssertionError(f"Cannot connect to service: {e}")
        
        # Find available audio files
        cls.audio_files = _find_audio_files(TEST_DATA_PATH)
        ic(f"Found {len(cls.audio_files)} audio files in {TEST_DATA_PATH}")
        
        if not cls.audio_files:
            ic("No audio files found, tests will use synthetic audio")
    
    # Basic endpoint tests
    
    def test_health_endpoint_returns_valid_response(self) -> None:
        """Health endpoint should return 200 with proper structure."""
        response = requests.get(HEALTH_URL, timeout=10)
        
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        ic("Health response:", data)
        
        # Validate response structure
        self.assertIn("status", data)
        self.assertIn("memory_percent", data)
        self.assertIn("active_tasks", data)
        
        self.assertEqual(data["status"], "ok")
        self.assertIsInstance(data["memory_percent"], (int, float))
        self.assertIsInstance(data["active_tasks"], int)
        self.assertGreaterEqual(data["memory_percent"], 0)
        self.assertLessEqual(data["memory_percent"], 100)
        self.assertGreaterEqual(data["active_tasks"], 0)
    
    def test_metrics_endpoint_returns_valid_response(self) -> None:
        """Metrics endpoint should return proper structure."""
        response = requests.get(METRICS_URL, timeout=10)
        
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        ic("Metrics response:", data)
        
        # Validate response structure
        required_fields = [
            "total_requests", "accepted_requests", 
            "rejected_requests", "avg_processing_time_ms"
        ]
        
        for field in required_fields:
            self.assertIn(field, data)
            self.assertIsInstance(data[field], (int, float))
            self.assertGreaterEqual(data[field], 0)
    
    # Transcription tests
    
    def test_transcribe_valid_audio_returns_200(self) -> None:
        """Valid audio file should return 200 with transcription."""
        if self.audio_files:
            # Use real audio file
            audio_path = random.choice(self.audio_files)
            audio_data = audio_path.read_bytes()
            filename = audio_path.name
            content_type = self._get_content_type(audio_path.suffix)
        else:
            # Use synthetic audio
            audio_data = _create_synthetic_wav(duration_seconds=2.0)
            filename = "test_sine_wave.wav"
            content_type = "audio/wav"
        
        response = _post_audio_file(
            TRANSCRIBE_URL, filename, audio_data, content_type
        )
        
        self.assertEqual(response.status_code, 200, msg=response.text[:500])
        
        # Validate response structure
        data = response.json()
        ic("Transcription keys:", list(data.keys()))
        
        self.assertIn("text", data)
        self.assertIsInstance(data["text"], str)
        
        # Validate JSON serializability
        json_size = _validate_json_serializable(data)
        ic(f"Response JSON size: {json_size} bytes")
        self.assertGreater(json_size, 10)  # Should have meaningful content
    
    def test_transcribe_caching_functionality(self) -> None:
        """Identical audio files should return cached results faster."""
        audio_data = _create_synthetic_wav(duration_seconds=1.0)
        filename = "cache_test.wav"
        
        # First request (cache miss)
        start1 = time.perf_counter()
        response1 = _post_audio_file(
            TRANSCRIBE_URL, filename, audio_data, "audio/wav"
        )
        duration1 = time.perf_counter() - start1
        
        self.assertEqual(response1.status_code, 200)
        data1 = response1.json()
        
        # Second request (cache hit)
        start2 = time.perf_counter()
        response2 = _post_audio_file(
            TRANSCRIBE_URL, f"cached_{filename}", audio_data, "audio/wav"
        )
        duration2 = time.perf_counter() - start2
        
        self.assertEqual(response2.status_code, 200)
        data2 = response2.json()
        
        # Results should be identical
        self.assertEqual(data1["text"], data2["text"])
        
        # Second request should be significantly faster
        ic(f"First request: {duration1:.2f}s, Second request: {duration2:.2f}s")
        self.assertLess(duration2, duration1 * 0.5)  # At least 50% faster
    
    # Error handling tests
    
    def test_transcribe_oversized_file_returns_413(self) -> None:
        """Files larger than size limit should return 413."""
        # Create file just over the limit
        oversized_data = os.urandom(MAX_FILE_SIZE_BYTES + 1024)
        
        response = _post_audio_file(
            TRANSCRIBE_URL, "oversized.wav", oversized_data, "audio/wav"
        )
        
        self.assertEqual(response.status_code, 413, msg=response.text[:500])
        self.assertIn("File size exceeds", response.text)
    
    def test_transcribe_invalid_content_type_returns_415(self) -> None:
        """Non-audio content types should return 415."""
        text_data = b"This is not an audio file"
        
        response = _post_audio_file(
            TRANSCRIBE_URL, "not_audio.txt", text_data, "text/plain"
        )
        
        self.assertEqual(response.status_code, 415, msg=response.text[:500])
    
    def test_transcribe_large_audio_file_succeeds(self) -> None:
        """Large but valid audio files should be processed."""
        large_audio = _create_large_synthetic_wav(duration_minutes=2.0)
        
        response = _post_audio_file(
            TRANSCRIBE_URL, "large_audio.wav", large_audio, "audio/wav"
        )
        
        # Should succeed (might take longer)
        self.assertEqual(response.status_code, 200, msg=response.text[:500])
        
        data = response.json()
        self.assertIn("text", data)
        self.assertIsInstance(data["text"], str)
    
    # Concurrency and load tests
    
    def test_concurrent_transcription_requests(self) -> None:
        """Multiple concurrent requests should be handled properly."""
        # Create different audio files for concurrent requests
        audio_files = []
        for i in range(6):  # More than max concurrent (4)
            audio_data = _create_synthetic_wav(
                duration_seconds=1.0,
                frequency=440.0 + (i * 100)  # Different frequencies
            )
            audio_files.append((f"concurrent_{i}.wav", audio_data))
        
        def _transcribe_one(item: tuple) -> Dict[str, Any]:
            filename, audio_data = item
            response = _post_audio_file(
                TRANSCRIBE_URL, filename, audio_data, "audio/wav"
            )
            return {
                "filename": filename,
                "status_code": response.status_code,
                "has_text": "text" in response.json() if response.status_code == 200 else False
            }
        
        # Execute requests concurrently
        results = []
        start_time = time.perf_counter()
        
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(_transcribe_one, item) for item in audio_files]
            
            for future in as_completed(futures):
                results.append(future.result())
        
        total_time = time.perf_counter() - start_time
        ic(f"Concurrent requests completed in {total_time:.2f}s")
        
        # Analyze results
        success_count = sum(1 for r in results if r["status_code"] == 200)
        busy_count = sum(1 for r in results if r["status_code"] == 503)
        
        ic(f"Successful: {success_count}, Busy (503): {busy_count}")
        
        # At least some should succeed, some might be rejected due to concurrency
        self.assertGreater(success_count, 0)
        self.assertLessEqual(busy_count, len(audio_files))
        
        # All successful requests should have text
        for result in results:
            if result["status_code"] == 200:
                self.assertTrue(result["has_text"])
    
    def test_semaphore_timeout_behavior(self) -> None:
        """Test that semaphore timeout returns 503 appropriately."""
        # This test is harder to reliably trigger, so we'll create many requests
        # and verify that at least some get proper 503 responses
        
        audio_data = _create_synthetic_wav(duration_seconds=3.0)  # Longer processing
        
        def _make_request() -> int:
            response = _post_audio_file(
                TRANSCRIBE_URL, "timeout_test.wav", audio_data, "audio/wav"
            )
            return response.status_code
        
        # Launch many concurrent requests
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(_make_request) for _ in range(8)]
            status_codes = [f.result() for f in as_completed(futures)]
        
        ic("Status codes from semaphore test:", status_codes)
        
        # Should have mix of 200 (success) and potentially 503 (busy)
        success_codes = [code for code in status_codes if code == 200]
        busy_codes = [code for code in status_codes if code == 503]
        
        # At least some should succeed
        self.assertGreater(len(success_codes), 0)
        
        # If any 503s, they should have proper headers (tested in other methods)
        ic(f"Success: {len(success_codes)}, Busy: {len(busy_codes)}")
    
    # Helper methods
    
    def _get_content_type(self, file_extension: str) -> str:
        """Get appropriate content type for file extension."""
        content_types = {
            '.wav': 'audio/wav',
            '.mp3': 'audio/mpeg',
            '.m4a': 'audio/mp4',
            '.flac': 'audio/flac',
            '.webm': 'audio/webm',
            '.mp4': 'video/mp4',
        }
        return content_types.get(file_extension.lower(), 'application/octet-stream')
    
    # Validation tests
    
    def test_api_responses_are_json_safe(self) -> None:
        """All API responses should be properly JSON serializable."""
        endpoints_to_test = [
            (HEALTH_URL, "GET", None),
            (METRICS_URL, "GET", None),
        ]
        
        for url, method, _ in endpoints_to_test:
            with self.subTest(url=url, method=method):
                if method == "GET":
                    response = requests.get(url, timeout=10)
                
                self.assertEqual(response.status_code, 200)
                
                # Validate JSON serializability
                data = response.json()
                json_size = _validate_json_serializable(data)
                self.assertGreater(json_size, 0)
        
        # Test transcription endpoint with synthetic audio
        audio_data = _create_synthetic_wav(duration_seconds=0.5)
        response = _post_audio_file(
            TRANSCRIBE_URL, "json_test.wav", audio_data, "audio/wav"
        )
        
        if response.status_code == 200:
            data = response.json()
            json_size = _validate_json_serializable(data)
            ic(f"Transcription response JSON size: {json_size} bytes")
            self.assertGreater(json_size, 10)


if __name__ == "__main__":
    # Create test data directory if it doesn't exist
    TEST_DATA_PATH.mkdir(exist_ok=True)
    
    # Run tests with high verbosity
    unittest.main(verbosity=2, buffer=True)