# Whisper API MVP

High-performance audio transcription service using MLX-accelerated Whisper models, optimized for Mac Studio M3 Ultra deployment.

## Overview

This service provides robust, production-ready audio transcription capabilities with:

- **Metal GPU Acceleration**: Leverages Mac Studio M3 Ultra's Metal performance shaders via MLX
- **Async Concurrency**: Semaphore-based job scheduling with configurable concurrency limits
- **Production Hardening**: Memory pressure handling, rate limiting, graceful degradation
- **Intelligent Caching**: SHA256-based deduplication for identical audio files  
- **Comprehensive Monitoring**: Health checks, metrics, and structured logging

## Architecture

### Single-Process Design
- FastAPI application with asyncio concurrency
- Semaphore-controlled transcription jobs (default: 4 concurrent)
- Shared model loading for memory efficiency
- Direct Metal GPU access without virtualization overhead

### Key Features
- **Backpressure Handling**: HTTP 503 with `Retry-After` headers when busy
- **Memory Protection**: Automatic rejection above 85% memory usage
- **Smart Caching**: In-memory cache with SHA256 deduplication
- **Robust Error Handling**: Graceful degradation without service crashes

## Tech Stack

- **Language**: Python 3.12.11
- **Web Framework**: FastAPI with Uvicorn
- **ML Framework**: MLX with mlx-community Whisper implementation
- **Process Management**: PM2 with ecosystem configuration
- **Monitoring**: psutil for system metrics
- **Platform**: macOS (optimized for Mac Studio M3 Ultra)

## Quick Start

### Prerequisites
- macOS (Metal GPU support required)
- Python 3.12.11
- At least 32GB RAM recommended
- 20GB+ free disk space for model storage

### Installation

1. **Clone and setup environment:**
```bash
git clone <repository-url>
cd whisper-api-mvp
cp .env.example .env
chmod +x start.sh
```

2. **Install system dependencies:**
```bash
# Install PM2 globally
npm install -g pm2

# Install Python dependencies
./start.sh setup
```

3. **Start the service:**
```bash
./start.sh start
```

4. **Verify deployment:**
```bash
curl http://localhost:8000/health
```

## API Endpoints

### POST /v1/transcribe
Transcribe audio files to text.

**Request:**
- **Content-Type**: `multipart/form-data`
- **File Field**: `file` (required)
- **Supported Formats**: mp3, wav, m4a, flac, webm, mp4, avi, mov
- **Max Size**: 200MB

**Response (200):**
```json
{
  "text": "Transcribed text content from the audio file."
}
```

**Error Responses:**
- **413**: File size exceeds 200MB limit
- **415**: Unsupported file format
- **503**: Service busy or under memory pressure (includes `Retry-After: 30` header)

**Example Usage:**
```bash
curl -X POST "http://localhost:8000/v1/transcribe" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@audio.wav"
```

### GET /health
Service health check with system status.

**Response (200):**
```json
{
  "status": "ok",
  "memory_percent": 67.2,
  "active_tasks": 2
}
```

### GET /metrics
Service performance metrics.

**Response (200):**
```json
{
  "total_requests": 1542,
  "accepted_requests": 1489,
  "rejected_requests": 53,
  "avg_processing_time_ms": 2847.5
}
```

## Configuration

All settings can be configured via environment variables or the `.env` file:

### Core Settings
- `MODEL_NAME`: Whisper model to use (default: `mlx-community/whisper-large-v3-mlx`)
- `MAX_CONCURRENT_JOBS`: Concurrent transcription limit (default: `4`)
- `MAX_FILE_SIZE_BYTES`: Maximum file size in bytes (default: `209715200` - 200MB)
- `MAX_MEMORY_THRESHOLD`: Memory usage rejection threshold (default: `85.0`%)

### Performance Tuning
- `SEMAPHORE_TIMEOUT`: Timeout for job acquisition (default: `1.0` seconds)
- `MAX_CACHE_SIZE`: Maximum cached results (default: `100`)
- `MLX_NUM_THREADS`: MLX thread count (default: `4`)

### Mac Studio Optimizations
- `METAL_DEVICE_WRAPPER`: Enable Metal GPU targeting (default: `1`)
- `PREVENT_SLEEP`: Prevent system sleep during operation (default: `true`)

See `.env.example` for complete configuration options.

## Deployment

### Production Deployment

1. **Configure PM2 ecosystem:**
```bash
# Edit ecosystem.config.js with your paths
vim ecosystem.config.js

# Start with PM2
pm2 start ecosystem.config.js --env production
pm2 save
```

2. **Setup system startup:**
```bash
# Generate startup script
pm2 startup

# Save PM2 process list
pm2 save
```

3. **Enable log rotation:**
```bash
pm2 install pm2-logrotate
```

### macOS Launchd Integration

For maximum uptime, create a launchd service:

1. **Create plist file** (`~/Library/LaunchAgents/com.yourorg.whisper-api.plist`):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.yourorg.whisper-api</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/pm2</string>
        <string>resurrect</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>/usr/local/var/log/whisper-api.err</string>
    <key>StandardOutPath</key>
    <string>/usr/local/var/log/whisper-api.out</string>
</dict>
</plist>
```

2. **Load the service:**
```bash
launchctl load ~/Library/LaunchAgents/com.yourorg.whisper-api.plist
```

## Service Management

### Using start.sh Script
```bash
# Start service with Mac Studio optimizations
./start.sh start

# Stop service
./start.sh stop

# Restart service
./start.sh restart

# Check service status
./start.sh status

# Setup environment only
./start.sh setup
```

### Using PM2 Directly
```bash
# Start application
pm2 start ecosystem.config.js

# Monitor processes
pm2 monit

# View logs
pm2 logs whisper-api

# Restart service
pm2 restart whisper-api

# Check status
pm2 status
```

## Monitoring & Logging

### Log Files
- **Application Logs**: `logs/combined.log`
- **Error Logs**: `logs/error.log`
- **Request Logs**: `logs/requests.log` (JSON format)
- **Service Logs**: `logs/service.log`

### Request Logging Format
Each request is logged as a JSON line with:
```json
{
  "request_id": "req_1642781234567",
  "timestamp": 1642781234.567,
  "processing_time_ms": 2847.5,
  "status": 200,
  "file_size_bytes": 1048576,
  "client_ip": "192.168.1.100",
  "audio_hash": "sha256_hash_of_audio_content",
  "error_message": null
}
```

### Health Monitoring
Monitor service health by polling the `/health` endpoint:

```bash
# Simple health check
curl -f http://localhost:8000/health

# Detailed monitoring with jq
curl -s http://localhost:8000/health | jq '.memory_percent, .active_tasks'
```

## Testing

### Running Tests
```bash
# Install test dependencies
pip install -r requirements.txt

# Run comprehensive test suite
python -m pytest test_whisper_api.py -v

# Run with coverage
python -m pytest test_whisper_api.py --cov=app --cov-report=html
```

### Test Categories
- **Health/Metrics Endpoints**: Basic service validation
- **Transcription Functionality**: Audio processing and response validation
- **Error Handling**: File size limits, content types, error responses
- **Concurrency**: Semaphore behavior and load handling
- **Caching**: Deduplication and performance optimization

### Load Testing
```bash
# Generate synthetic test data
mkdir -p test_data

# Run concurrent transcription test
python test_whisper_api.py TestWhisperApi.test_concurrent_transcription_requests
```

## Performance Optimization

### Mac Studio Specific
1. **Metal GPU Utilization**: Automatic via `METAL_DEVICE_WRAPPER=1`
2. **Memory Mapping**: Large model files use efficient memory mapping
3. **Thread Optimization**: `MLX_NUM_THREADS` tuned for M3 Ultra cores
4. **System Sleep Prevention**: `caffeinate` integration prevents sleep during processing

### Model Performance
- **Whisper-Large-v3**: Best accuracy/performance balance
- **Half Precision**: Automatic FP16 usage for faster inference
- **Beam Search Optimization**: Single beam for maximum speed
- **Deterministic Output**: Temperature=0 for consistent results

### Caching Strategy
- **SHA256 Deduplication**: Identical audio files return cached results
- **Memory-Only Cache**: Fast in-memory storage with LRU eviction
- **Configurable Size**: Default 100 cached results, adjustable via `MAX_CACHE_SIZE`

## Troubleshooting

### Common Issues

**Service won't start:**
```bash
# Check Python version
python3.12 --version

# Verify MLX installation
python3.12 -c "import mlx.core; print('MLX OK')"

# Check system requirements
./start.sh setup
```

**High memory usage:**
```bash
# Check current usage
curl -s http://localhost:8000/health | jq '.memory_percent'

# Reduce cache size
export MAX_CACHE_SIZE=50

# Restart with new settings
./start.sh restart
```

**Transcription errors:**
```bash
# Check recent logs
tail -f logs/requests.log | jq '.'

# Test with simple audio
curl -X POST "http://localhost:8000/v1/transcribe" \
  -F "file=@test_audio.wav"
```

**Performance issues:**
```bash
# Check active tasks
curl -s http://localhost:8000/metrics | jq '.avg_processing_time_ms'

# Monitor system resources
pm2 monit

# Adjust concurrency
export MAX_CONCURRENT_JOBS=2
./start.sh restart
```

### Debug Mode
Enable debug logging for troubleshooting:
```bash
# Set debug environment
echo "DEBUG=true" >> .env
echo "LOG_LEVEL=DEBUG" >> .env

# Restart service
./start.sh restart

# Monitor debug logs
tail -f logs/combined.log
```

## API Integration

### RapidAPI Marketplace
The service includes headers for RapidAPI integration:
- Parses `X-RapidAPI-User` and `X-RapidAPI-Proxy-Secret` headers
- Ready for marketplace deployment with rate limiting
- Standardized error responses for marketplace requirements

### Rate Limiting (Future)
Placeholder implementation for tiered access:
- Free tier: 10 requests/hour
- Premium tier: 1000 requests/hour
- API key-based authentication

## Security Considerations

### File Validation
- Strict file size limits (200MB default)
- Content-type validation
- File extension whitelist
- No file persistence (temp files cleaned immediately)

### System Protection
- Memory pressure monitoring
- Process isolation via PM2
- No shell command execution
- Structured logging without sensitive data

### Network Security
- CORS middleware for cross-origin requests
- Request timeout limits
- No external network access required (after model download)

## Contributing

### Development Setup
```bash
# Clone repository
git clone <repository-url>
cd whisper-api-mvp

# Setup development environment
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install pre-commit hooks
pip install pre-commit
pre-commit install

# Run in development mode
export DEBUG=true RELOAD=true
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Code Style
- **Linting**: pylint, pylance
- **Formatting**: black (88 character line limit)
- **Type Hints**: Required for all functions
- **Documentation**: Concise docstrings focusing on purpose
- **Testing**: Comprehensive test coverage required

## License

This project is licensed under the MIT License. See LICENSE file for details.

## Support

For issues and questions:
1. Check this README and logs for common solutions
2. Review test suite for usage examples
3. Open GitHub issue with detailed error logs
4. Include system information (macOS version, hardware specs)

---

**Mac Studio M3 Ultra Optimized** | **Production Ready** | **API Marketplace Compatible**