# Whisper API Test Execution Guide

This guide provides comprehensive instructions for running the test suite to validate your Whisper API deployment.

## Prerequisites

### 1. Install Test Dependencies
```bash
# Ensure you're in the project directory
cd whisper-api-mvp

# Install Python dependencies (includes testing packages)
pip install -r requirements.txt

# Make test runner executable
chmod +x run_tests.py
```

### 2. Setup Test Environment
```bash
# Create necessary test directories
python run_tests.py --setup

# Verify pytest is working
pytest --version
```

## Test Categories

### Unit Tests (No Service Required)
Test individual components in isolation with mocked dependencies.

```bash
# Run all unit tests
python run_tests.py --unit

# Run specific unit test file
pytest test_config.py -v

# Run unit tests with coverage
pytest -m unit --cov=app --cov-report=html
```

**Expected Results:**
- ✅ Configuration validation works
- ✅ Pydantic models validate correctly  
- ✅ WhisperTranscriber initializes properly
- ✅ Response models serialize to JSON

### API Tests (Mocked Service)
Test API endpoints with mocked transcription service.

```bash
# Run API endpoint tests
python run_tests.py --api

# Run with verbose output
python run_tests.py --api --verbose
```

**Expected Results:**
- ✅ `/health` endpoint returns proper response
- ✅ `/metrics` endpoint provides statistics
- ✅ `/v1/transcribe` accepts valid audio files
- ✅ Error handling returns appropriate HTTP status codes

### Integration Tests
Test component interactions and full request flows.

```bash
# Run integration tests
python run_tests.py --integration

# Run specific integration test
pytest -k "test_app_lifecycle" -v
```

**Expected Results:**
- ✅ Application lifecycle (startup/shutdown) works
- ✅ Request logging functions properly
- ✅ Error propagation through full stack
- ✅ Metrics accurately reflect processing

### Error Handling Tests
Test edge cases and error conditions.

```bash
# Run error handling tests
python run_tests.py --error

# Test specific error scenarios
pytest -m error -v
```

**Expected Results:**
- ✅ Oversized files rejected with 413
- ✅ Invalid file types rejected with 415
- ✅ Memory pressure returns 503
- ✅ Service degradation handled gracefully

## Complete Test Suite

### Run All Tests (Recommended First Run)
```bash
# Run comprehensive test suite
python run_tests.py

# Run fast tests only (skip slow performance tests)
python run_tests.py --fast

# Run with detailed output and coverage
python run_tests.py --verbose
```

**Expected Output:**
```
🔍 Checking test dependencies...
✅ All test dependencies are available
✅ Test directories created

🔍 Running all tests
Command: python -m pytest -v --cov=app --cov-report=term-missing --cov-report=html:htmlcov
============================================================

test_config.py::TestSettingsValidation::test_valid_settings PASSED
test_config.py::TestSettingsValidation::test_concurrent_jobs_bounds PASSED
...
test_whisper_api_comprehensive.py::TestHealthEndpoint::test_health_endpoint_success PASSED
test_whisper_api_comprehensive.py::TestTranscribeEndpoint::test_transcribe_endpoint_success PASSED
...

============== 45 passed, 0 failed, 3 skipped in 12.34s ===============

Name                     Stmts   Miss  Cover   Missing
------------------------------------------------------
app/__init__.py             8      0   100%
app/config.py              89      5    94%   156-160
app/main.py               145     12    92%   89-95, 234-240
app/models.py              35      0   100%
app/transcribe.py          67      8    88%   92-99, 145-149
------------------------------------------------------
TOTAL                     344     25    93%

✅ All tests completed successfully!
📊 Coverage report available at: htmlcov/index.html
```

## Performance Testing (Requires Running Service)

### Start the Service First
```bash
# Start the Whisper API service
./start.sh start

# Verify service is running
curl http://localhost:8000/health
```

### Run Performance Tests
```bash
# Basic performance test
python test_performance_live.py

# Comprehensive performance testing
python test_performance_live.py --all

# Custom load test
python test_performance_live.py --load-test --concurrent 20 --workers 8

# Sustained load test
python test_performance_live.py --sustained-test --duration 120 --rps 10

# Stress test to find breaking point
python test_performance_live.py --stress-test --stress-max 30
```

**Expected Performance Results:**
```
📊 Load Test Results
============================================================
Total Requests:      50
Successful:          50 (100.0%)
Failed:              0 (0.0%)
Total Duration:      15.2s
Requests/Second:     3.29

Response Time Statistics:
  Average:           2847ms
  Minimum:           1234ms
  Maximum:           5432ms
  95th Percentile:   4567ms
  99th Percentile:   5123ms

Status Code Distribution:
  200: 50 requests
```

## Test-Driven Development Workflow

### Before Making Changes
```bash
# Run tests to establish baseline
python run_tests.py --fast

# Run specific tests related to your changes
pytest test_config.py -k "test_settings" -v
```

### During Development
```bash
# Run tests continuously during development
pytest --looponfail

# Run specific test while developing
pytest test_whisper_api_comprehensive.py::TestTranscribeEndpoint::test_transcribe_endpoint_success -v

# Test specific functionality
pytest -k "transcribe" --tb=short
```

### Before Deployment
```bash
# Full test suite with coverage
python run_tests.py

# Code quality checks
python run_tests.py --lint

# Performance validation with running service
./start.sh start
python test_performance_live.py --all
```

## Debugging Failed Tests

### Common Issues and Solutions

**Import Errors:**
```bash
# Install missing dependencies
pip install -r requirements.txt

# Check Python path
export PYTHONPATH=$PWD:$PYTHONPATH
```

**Mock Failures:**
```bash
# Run with more verbose output
pytest -vv --tb=long

# Run specific test with debugging
pytest test_config.py::TestSettingsValidation::test_valid_settings -vv -s
```

**Service Connection Issues:**
```bash
# Check service status
curl http://localhost:8000/health

# Start service if needed
./start.sh start

# Check logs
tail -f logs/service.log
```

**Performance Test Failures:**
```bash
# Check service health first
python test_performance_live.py --url http://localhost:8000

# Reduce load for testing
python test_performance_live.py --concurrent 5 --workers 2
```

### Debugging Commands
```bash
# Run tests with maximum debugging
pytest -vv --tb=long --capture=no --log-cli-level=DEBUG

# Run single test with full output
pytest test_config.py::TestSettingsValidation::test_valid_settings -vv -s --tb=long

# Check test discovery
pytest --collect-only

# Run tests matching pattern
pytest -k "test_health" -v
```

## Coverage Analysis

### Generate Detailed Coverage Report
```bash
# Generate HTML coverage report
python run_tests.py --coverage

# Open coverage report
open htmlcov/index.html  # macOS
# or visit file:///path/to/project/htmlcov/index.html
```

### Coverage Targets
- **Overall Coverage:** >90%
- **Critical Components:** 100%
  - `app/models.py` (response models)
  - `app/config.py` (configuration)
- **Acceptable Coverage:** >80%
  - `app/main.py` (FastAPI routes)
  - `app/transcribe.py` (transcription logic)

## Continuous Integration

### Pre-commit Checks
```bash
# Run all quality checks before committing
python run_tests.py --lint
python run_tests.py --fast
```

### Automated Test Execution
```bash
# Script for CI/CD pipeline
#!/bin/bash
set -e

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Running code quality checks..."
python run_tests.py --lint

echo "Running fast test suite..."
python run_tests.py --fast

echo "Generating coverage report..."
python run_tests.py --coverage

echo "All checks passed!"
```

## Test Maintenance

### Adding New Tests
1. **Unit Tests:** Add to existing test classes or create new ones
2. **API Tests:** Add to `TestTranscribeEndpoint` or similar classes
3. **Performance Tests:** Add to `test_performance_live.py`

### Test Markers
Use pytest markers to categorize tests:
- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.api` - API endpoint tests
- `@pytest.mark.performance` - Performance tests
- `@pytest.mark.slow` - Long-running tests
- `@pytest.mark.integration` - Integration tests

### Test Naming
Follow clear naming conventions:
- `test_<functionality>_<scenario>_<expected_result>`
- Example: `test_transcribe_valid_audio_returns_200`

## Success Criteria

Your test suite should achieve:

✅ **All unit tests pass** (>45 tests)
✅ **All API tests pass** (>15 tests)  
✅ **All error handling tests pass** (>8 tests)
✅ **Code coverage >90%**
✅ **No critical lint issues**
✅ **Performance tests show reasonable response times** (<5s average)
✅ **Service handles concurrent load** (>10 concurrent requests)
✅ **Memory usage remains stable** (<85% threshold)

When all tests pass consistently, your Whisper API service is ready for production deployment! 🚀