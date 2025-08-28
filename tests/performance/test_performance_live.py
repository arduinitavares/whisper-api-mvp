"""
Live performance tests for running Whisper API service.

These tests are designed to be run against an actual running service
to validate performance, concurrency, and stability under load.

Usage:
    python test_performance_live.py
    python test_performance_live.py --url http://localhost:8000 --duration 60
    python test_performance_live.py --concurrent 10 --requests 100
"""

import argparse
import asyncio
import io
import math
import statistics
import time
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import httpx
import requests
from icecream import ic


@dataclass
class TestResult:
    """Test result data structure."""
    success: bool
    duration_ms: float
    status_code: int
    response_size: int
    error_message: Optional[str] = None


@dataclass
class LoadTestResults:
    """Load test results summary."""
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_response_time_ms: float
    min_response_time_ms: float
    max_response_time_ms: float
    p95_response_time_ms: float
    p99_response_time_ms: float
    requests_per_second: float
    total_duration_s: float
    error_rate_percent: float
    status_code_distribution: Dict[int, int]


def create_synthetic_wav(
    duration_seconds: float = 1.0,
    sample_rate: int = 16000,
    frequency: float = 440.0,
) -> bytes:
    """Create synthetic WAV file for testing."""
    frames = int(duration_seconds * sample_rate)
    samples = []
    
    for i in range(frames):
        sample = int(32767 * math.sin(2 * math.pi * frequency * i / sample_rate))
        samples.append(sample)
    
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        
        wav_data = b''.join(
            sample.to_bytes(2, byteorder='little', signed=True) 
            for sample in samples
        )
        wav_file.writeframes(wav_data)
    
    return buffer.getvalue()


class WhisperAPITester:
    """Performance tester for Whisper API."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.health_url = f"{self.base_url}/health"
        self.transcribe_url = f"{self.base_url}/v1/transcribe"
        self.metrics_url = f"{self.base_url}/metrics"
        
        # Test audio files
        self.test_files = {
            "short": create_synthetic_wav(1.0, frequency=440.0),
            "medium": create_synthetic_wav(5.0, frequency=880.0),
            "long": create_synthetic_wav(10.0, frequency=220.0),
        }
    
    def check_service_health(self) -> bool:
        """Check if service is running and responding."""
        try:
            response = requests.get(self.health_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                ic("Service health:", data)
                return data.get("status") == "ok"
            else:
                print(f"❌ Health check failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Cannot connect to service: {e}")
            return False
    
    def single_transcription_test(
        self, 
        audio_data: bytes, 
        filename: str = "test.wav",
        timeout: float = 30.0
    ) -> TestResult:
        """Perform single transcription request."""
        files = {"file": (filename, io.BytesIO(audio_data), "audio/wav")}
        
        start_time = time.perf_counter()
        
        try:
            response = requests.post(
                self.transcribe_url, 
                files=files,
                timeout=timeout,
                headers={"Expect": ""}
            )
            
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            
            return TestResult(
                success=response.status_code == 200,
                duration_ms=duration_ms,
                status_code=response.status_code,
                response_size=len(response.content),
                error_message=None if response.status_code == 200 else response.text[:200]
            )
        
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return TestResult(
                success=False,
                duration_ms=duration_ms,
                status_code=0,
                response_size=0,
                error_message=str(e)
            )
    
    def concurrent_load_test(
        self,
        num_requests: int = 50,
        max_workers: int = 10,
        audio_type: str = "short"
    ) -> LoadTestResults:
        """Perform concurrent load testing."""
        print(f"🚀 Starting load test: {num_requests} requests with {max_workers} workers")
        
        audio_data = self.test_files[audio_type]
        test_start = time.perf_counter()
        
        def make_request(request_id: int) -> TestResult:
            return self.single_transcription_test(
                audio_data, 
                f"load_test_{request_id}.wav"
            )
        
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(make_request, i) 
                for i in range(num_requests)
            ]
            
            for future in as_completed(futures):
                results.append(future.result())
        
        total_duration = time.perf_counter() - test_start
        
        return self._analyze_results(results, total_duration)
    
    def sustained_load_test(
        self,
        duration_seconds: int = 60,
        requests_per_second: int = 5,
        audio_type: str = "short"
    ) -> LoadTestResults:
        """Perform sustained load testing over time."""
        print(f"🔄 Starting sustained test: {requests_per_second} RPS for {duration_seconds}s")
        
        audio_data = self.test_files[audio_type]
        results = []
        test_start = time.perf_counter()
        
        request_interval = 1.0 / requests_per_second
        request_count = 0
        
        while time.perf_counter() - test_start < duration_seconds:
            loop_start = time.perf_counter()
            
            # Make request
            result = self.single_transcription_test(
                audio_data,
                f"sustained_{request_count}.wav"
            )
            results.append(result)
            request_count += 1
            
            # Calculate sleep time to maintain rate
            elapsed = time.perf_counter() - loop_start
            sleep_time = max(0, request_interval - elapsed)
            
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        total_duration = time.perf_counter() - test_start
        
        return self._analyze_results(results, total_duration)
    
    def stress_test(
        self,
        max_concurrent: int = 20,
        ramp_up_seconds: int = 30
    ) -> LoadTestResults:
        """Gradually increase load to find breaking point."""
        print(f"📈 Starting stress test: ramping up to {max_concurrent} concurrent requests")
        
        audio_data = self.test_files["medium"]
        all_results = []
        test_start = time.perf_counter()
        
        # Ramp up gradually
        for concurrent in range(1, max_concurrent + 1):
            print(f"Testing with {concurrent} concurrent requests...")
            
            def make_stress_request(request_id: int) -> TestResult:
                return self.single_transcription_test(
                    audio_data,
                    f"stress_{concurrent}_{request_id}.wav"
                )
            
            batch_results = []
            with ThreadPoolExecutor(max_workers=concurrent) as executor:
                futures = [
                    executor.submit(make_stress_request, i)
                    for i in range(concurrent)
                ]
                
                for future in as_completed(futures):
                    batch_results.append(future.result())
            
            all_results.extend(batch_results)
            
            # Check if service is struggling
            success_rate = sum(1 for r in batch_results if r.success) / len(batch_results)
            avg_response_time = statistics.mean(r.duration_ms for r in batch_results)
            
            print(f"  Success rate: {success_rate:.1%}, Avg response time: {avg_response_time:.0f}ms")
            
            if success_rate < 0.8 or avg_response_time > 10000:  # 10s threshold
                print(f"⚠️ Service degradation detected at {concurrent} concurrent requests")
                break
            
            # Brief pause between ramp-up steps
            time.sleep(2)
        
        total_duration = time.perf_counter() - test_start
        
        return self._analyze_results(all_results, total_duration)
    
    def cache_effectiveness_test(self) -> Dict[str, float]:
        """Test caching effectiveness with identical requests."""
        print("🗄️ Testing cache effectiveness...")
        
        audio_data = self.test_files["short"]
        
        # First request (cache miss)
        result1 = self.single_transcription_test(audio_data, "cache_test_1.wav")
        
        # Second request with same content (cache hit)
        result2 = self.single_transcription_test(audio_data, "cache_test_2.wav")
        
        # Third request with different filename but same content (cache hit)
        result3 = self.single_transcription_test(audio_data, "cache_test_3.wav")
        
        if result1.success and result2.success and result3.success:
            cache_speedup_2 = result1.duration_ms / result2.duration_ms
            cache_speedup_3 = result1.duration_ms / result3.duration_ms
            
            return {
                "first_request_ms": result1.duration_ms,
                "second_request_ms": result2.duration_ms,
                "third_request_ms": result3.duration_ms,
                "speedup_factor_2": cache_speedup_2,
                "speedup_factor_3": cache_speedup_3,
                "cache_working": cache_speedup_2 > 2.0 and cache_speedup_3 > 2.0
            }
        else:
            return {"error": "Cache test failed due to request errors"}
    
    def _analyze_results(self, results: List[TestResult], total_duration: float) -> LoadTestResults:
        """Analyze test results and generate summary."""
        successful_results = [r for r in results if r.success]
        failed_results = [r for r in results if not r.success]
        
        if not results:
            raise ValueError("No results to analyze")
        
        # Response time statistics
        if successful_results:
            response_times = [r.duration_ms for r in successful_results]
            avg_response_time = statistics.mean(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
            
            # Percentiles
            sorted_times = sorted(response_times)
            p95_index = int(0.95 * len(sorted_times))
            p99_index = int(0.99 * len(sorted_times))
            
            p95_response_time = sorted_times[min(p95_index, len(sorted_times) - 1)]
            p99_response_time = sorted_times[min(p99_index, len(sorted_times) - 1)]
        else:
            avg_response_time = min_response_time = max_response_time = 0.0
            p95_response_time = p99_response_time = 0.0
        
        # Status code distribution
        status_codes = {}
        for result in results:
            status_codes[result.status_code] = status_codes.get(result.status_code, 0) + 1
        
        # Calculate metrics
        total_requests = len(results)
        successful_requests = len(successful_results)
        failed_requests = len(failed_results)
        error_rate = (failed_requests / total_requests) * 100 if total_requests > 0 else 0
        rps = total_requests / total_duration if total_duration > 0 else 0
        
        return LoadTestResults(
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            avg_response_time_ms=avg_response_time,
            min_response_time_ms=min_response_time,
            max_response_time_ms=max_response_time,
            p95_response_time_ms=p95_response_time,
            p99_response_time_ms=p99_response_time,
            requests_per_second=rps,
            total_duration_s=total_duration,
            error_rate_percent=error_rate,
            status_code_distribution=status_codes
        )
    
    def print_results(self, results: LoadTestResults, test_name: str = "Test") -> None:
        """Print formatted test results."""
        print(f"\n📊 {test_name} Results")
        print("=" * 60)
        print(f"Total Requests:      {results.total_requests}")
        print(f"Successful:          {results.successful_requests} ({(results.successful_requests/results.total_requests)*100:.1f}%)")
        print(f"Failed:              {results.failed_requests} ({results.error_rate_percent:.1f}%)")
        print(f"Total Duration:      {results.total_duration_s:.1f}s")
        print(f"Requests/Second:     {results.requests_per_second:.2f}")
        print()
        print("Response Time Statistics:")
        print(f"  Average:           {results.avg_response_time_ms:.0f}ms")
        print(f"  Minimum:           {results.min_response_time_ms:.0f}ms")
        print(f"  Maximum:           {results.max_response_time_ms:.0f}ms")
        print(f"  95th Percentile:   {results.p95_response_time_ms:.0f}ms")
        print(f"  99th Percentile:   {results.p99_response_time_ms:.0f}ms")
        print()
        print("Status Code Distribution:")
        for status_code, count in sorted(results.status_code_distribution.items()):
            print(f"  {status_code}: {count} requests")


def main():
    """Main performance testing function."""
    parser = argparse.ArgumentParser(description="Whisper API Performance Testing")
    
    parser.add_argument("--url", default="http://localhost:8000", 
                       help="Base URL of the Whisper API service")
    parser.add_argument("--concurrent", type=int, default=50,
                       help="Number of concurrent requests for load test")
    parser.add_argument("--workers", type=int, default=10,
                       help="Number of worker threads")
    parser.add_argument("--duration", type=int, default=60,
                       help="Duration for sustained test (seconds)")
    parser.add_argument("--rps", type=int, default=5,
                       help="Requests per second for sustained test")
    parser.add_argument("--stress-max", type=int, default=20,
                       help="Maximum concurrent requests for stress test")
    
    # Test selection
    parser.add_argument("--load-test", action="store_true",
                       help="Run concurrent load test")
    parser.add_argument("--sustained-test", action="store_true", 
                       help="Run sustained load test")
    parser.add_argument("--stress-test", action="store_true",
                       help="Run stress test")
    parser.add_argument("--cache-test", action="store_true",
                       help="Run cache effectiveness test")
    parser.add_argument("--all", action="store_true",
                       help="Run all tests")
    
    args = parser.parse_args()
    
    # Create tester
    tester = WhisperAPITester(args.url)
    
    # Check service health
    print(f"🏥 Checking service health at {args.url}...")
    if not tester.check_service_health():
        print("❌ Service is not healthy. Please start the service first.")
        return 1
    
    print("✅ Service is healthy and ready for testing\n")
    
    # Run selected tests
    if args.all or args.load_test:
        print("🚀 Running Load Test")
        results = tester.concurrent_load_test(args.concurrent, args.workers)
        tester.print_results(results, "Load Test")
    
    if args.all or args.sustained_test:
        print("\n🔄 Running Sustained Test")
        results = tester.sustained_load_test(args.duration, args.rps)
        tester.print_results(results, "Sustained Test")
    
    if args.all or args.stress_test:
        print("\n📈 Running Stress Test")
        results = tester.stress_test(args.stress_max)
        tester.print_results(results, "Stress Test")
    
    if args.all or args.cache_test:
        print("\n🗄️ Running Cache Test")
        cache_results = tester.cache_effectiveness_test()
        print("Cache Test Results:")
        for key, value in cache_results.items():
            print(f"  {key}: {value}")
    
    # If no specific test was selected, run basic load test
    if not any([args.load_test, args.sustained_test, args.stress_test, 
                args.cache_test, args.all]):
        print("🚀 Running Basic Load Test (use --help for more options)")
        results = tester.concurrent_load_test(20, 5, "short")
        tester.print_results(results, "Basic Load Test")
    
    print("\n✅ Performance testing completed!")
    return 0


if __name__ == "__main__":
    exit(main())