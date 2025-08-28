/**
 * PM2 ecosystem configuration for Whisper API service.
 * 
 * Manages the FastAPI application with auto-restart, logging,
 * and health monitoring optimized for Mac Studio M3 Ultra.
 */

module.exports = {
  apps: [
    {
      name: 'whisper-api',
      script: 'uvicorn',
      args: 'app.main:app --host 0.0.0.0 --port 8000 --workers 1',
      cwd: '/path/to/whisper-api-mvp',
      
      // Process management
      instances: 1,  // Single process for shared model loading
      exec_mode: 'fork',
      
      // Auto-restart configuration
      autorestart: true,
      watch: false,  // Disable in production
      max_memory_restart: '4G',  // Restart if memory exceeds 4GB
      
      // Environment variables
      env: {
        NODE_ENV: 'production',
        PYTHONPATH: '/path/to/whisper-api-mvp',
        METAL_DEVICE_WRAPPER: '1',
        MLX_NUM_THREADS: '4',
        LOG_LEVEL: 'INFO'
      },
      
      // Development environment (optional)
      env_development: {
        NODE_ENV: 'development',
        LOG_LEVEL: 'DEBUG',
        DEBUG: 'true'
      },
      
      // Logging configuration
      log_file: './logs/combined.log',
      out_file: './logs/out.log',
      error_file: './logs/error.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      merge_logs: true,
      
      // Process monitoring
      min_uptime: '10s',  // Minimum uptime before considering stable
      max_restarts: 10,   // Maximum restarts within restart_delay period
      restart_delay: 4000, // Delay between restarts (ms)
      
      // Health monitoring
      health_check_http: {
        url: 'http://localhost:8000/health',
        interval: 30000,  // Check every 30 seconds
        timeout: 5000,    // 5 second timeout
        max_failures: 3   // Max failures before restart
      },
      
      // System resource limits
      kill_timeout: 3000,  // Time to wait before force kill (ms)
      listen_timeout: 3000, // Time to wait for app to listen
      
      // Additional PM2 options
      time: true,  // Add timestamps to logs
      ignore_watch: [
        'node_modules',
        'logs',
        '*.log',
        '.git',
        '__pycache__',
        '*.pyc'
      ],
      
      // Interpreter settings
      interpreter: 'python3.12',
      interpreter_args: '-u',  // Unbuffered output
      
      // Advanced options for Mac Studio optimization
      node_args: [],
      
      // Custom startup script (alternative to direct uvicorn)
      // script: './start.sh',
      
      // Environment-specific overrides
      env_staging: {
        NODE_ENV: 'staging',
        PORT: 8001,
        LOG_LEVEL: 'DEBUG'
      }
    }
  ],
  
  // Deploy configuration (optional)
  deploy: {
    production: {
      user: 'macstudio',
      host: 'localhost',
      ref: 'origin/main',
      repo: 'git@github.com:yourorg/whisper-api-mvp.git',
      path: '/opt/whisper-api',
      'pre-deploy-local': '',
      'post-deploy': 'pip install -r requirements.txt && pm2 reload ecosystem.config.js --env production',
      'pre-setup': ''
    }
  }
};