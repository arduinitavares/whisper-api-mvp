# filename: scripts/run_inference_stress.py
"""
Full stress test for the Whisper API using a small, local test data subset.

- Autodetects API base URL from .env or by probing common ports.
- Reads the local LJSpeech subset index for expected transcriptions.
- Finds all .wav files in the test data directory.
- Sends a concurrent request for every audio file.
- Compares the model's transcription with the ground truth.
- Reports on success, rejection (backpressure), and failures.
"""
from __future__ import annotations

import concurrent.futures
import csv
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter

# --- Script Configuration ---
# MODIFICATION: Point to the small, prepared LJSpeech subset directory.
AUDIO_DATA_DIR = Path("tests/data/ljs")
# MODIFICATION: Point to the subset's specific index file.
INDEX_FILE = AUDIO_DATA_DIR / "subset_index.csv"
# Number of parallel requests to send to the server.
MAX_WORKERS = 10


# --- API Endpoint Detection ---
def read_port_from_env(env_path: Path) -> Optional[int]:
    """Return PORT from .env as int if present and valid."""
    if not env_path.is_file():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or not s.startswith("PORT="):
            continue
        raw = s.split("=", 1)[1]
        raw = raw.split("#", 1)[0].strip().strip('"').strip("'")
        try:
            return int(raw)
        except ValueError:
            return None
    return None


def probe_base_url(ports: List[int], timeout_s: float = 2.0) -> Optional[str]:
    """Return first base URL whose /health responds 200."""
    for p in ports:
        base = f"http://localhost:{p}"
        try:
            r = requests.get(f"{base}/health", timeout=timeout_s)
            if r.status_code == 200:
                return base
        except requests.RequestException:
            pass
    return None


repo_root = Path.cwd()
env_port = read_port_from_env(repo_root / ".env")
candidate_ports: List[int] = []
if env_port:
    candidate_ports.append(env_port)
for common in (8000, 8001):
    if common not in candidate_ports:
        candidate_ports.append(common)

API_BASE_URL = probe_base_url(candidate_ports) or f"http://localhost:{env_port or 8000}"
TRANSCRIBE_URL = f"{API_BASE_URL}/v1/transcribe"
HEALTH_URL = f"{API_BASE_URL}/health"

print(f"Selected API base: {API_BASE_URL}")


# --- HTTP Session and Health Check ---
def build_session(pool_maxsize: int = 32) -> requests.Session:
    """Return a Session with an increased connection pool."""
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=pool_maxsize, pool_maxsize=pool_maxsize)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


HTTP_SESSION = build_session()


def check_api_health(timeout_s: float = 5.0) -> bool:
    """Check if the API is healthy and reachable."""
    try:
        resp = requests.get(HEALTH_URL, timeout=timeout_s)
        if resp.status_code == 200:
            print("✅ API is healthy!")
            return True
        print(f"❌ /health returned HTTP {resp.status_code}")
    except requests.RequestException as exc:
        print("❌ Cannot connect to API. Start with: ./start.sh start")
        print(f"   Details: {exc}")
    return False


# --- Data Loading ---
def load_audio_tasks(data_dir: Path, index_path: Path) -> Dict[str, Dict[str, Any]]:
    """Load audio file paths and their expected transcriptions from the subset."""
    if not index_path.is_file():
        raise FileNotFoundError(f"Index file not found: {index_path}")

    tasks = {}
    with open(index_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)  # Skip header row
        for row in reader:
            if len(row) >= 2:
                wav_filename, text, *_ = row
                filename_stem = Path(wav_filename).stem
                wav_path = data_dir / wav_filename
                if wav_path.is_file():
                    tasks[filename_stem] = {"path": wav_path, "expected_text": text}
    print(f"Found {len(tasks)} audio files to test.")
    return tasks


# --- Transcription Task ---
def transcribe_file(
    filename: str, audio_path: Path, timeout_s: float = 120.0
) -> Dict[str, Any]:
    """Send a single audio file for transcription and return the result."""
    try:
        with open(audio_path, "rb") as f:
            files = {"file": (audio_path.name, f, "audio/wav")}
            t0 = time.time()
            resp = HTTP_SESSION.post(TRANSCRIBE_URL, files=files, timeout=timeout_s)
            latency = time.time() - t0

        result: Dict[str, Any] = {
            "filename": filename,
            "status_code": resp.status_code,
            "latency_s": latency,
        }
        if resp.status_code == 200:
            result["response_json"] = resp.json()
        return result
    except requests.RequestException as exc:
        return {
            "filename": filename,
            "status_code": None,
            "error": f"Request failed: {exc}",
        }


# --- Main Execution ---
def main() -> None:
    """Run the full stress test."""
    print(time.strftime("Starting test at: %Y-%m-%d %H:%M:%S"))
    if not check_api_health():
        raise SystemExit(1)

    try:
        tasks = load_audio_tasks(AUDIO_DATA_DIR, INDEX_FILE)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        raise SystemExit(1)

    results: List[Dict[str, Any]] = []
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        future_to_name = {
            pool.submit(transcribe_file, name, task["path"]): name
            for name, task in tasks.items()
        }
        for future in concurrent.futures.as_completed(future_to_name):
            results.append(future.result())

    elapsed = time.time() - t0

    # --- Summarize Results ---
    ok = [r for r in results if r.get("status_code") == 200]
    lim = [r for r in results if r.get("status_code") == 503]
    fail = [r for r in results if r.get("status_code") not in (200, 503)]

    print(f"\n--- Test Summary ---")
    print(f"Completed {len(results)} requests in {elapsed:.2f} seconds.")
    print(f"  ✅ Successful (200): {len(ok)}")
    print(f"  ⏳ Rejected   (503): {len(lim)}")
    print(f"  ❌ Failed/Other:     {len(fail)}")

    print("\n--- Detailed Results for Successful Transcriptions ---")
    for r in sorted(ok, key=lambda x: x["filename"]):
        filename = r["filename"]
        actual_text = r.get("response_json", {}).get("text", "N/A").strip()
        expected_text = tasks[filename]["expected_text"].strip()
        latency = r["latency_s"]

        print(f"\n📄 {filename} ({latency:.2f}s)")
        print(f"  - EXPECTED: {expected_text}")
        print(f"  - ACTUAL:   {actual_text}")
        if actual_text != expected_text:
            print("  - ⚠️  MISMATCH")


if __name__ == "__main__":
    main()
