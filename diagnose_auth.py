# diagnose_auth.py
"""
Quick script to diagnose why authentication is being enforced.

Run this to see your current auth configuration.
"""

import os
import sys
from pathlib import Path

# Check environment variables
print("=== Environment Variables ===")
print(f"REQUIRE_AUTH: {os.environ.get('REQUIRE_AUTH', 'NOT SET')}")
print(
    f"RAPIDAPI_PROXY_SECRET: {'SET' if os.environ.get('RAPIDAPI_PROXY_SECRET') else 'NOT SET'}"
)

# Check .env file
print("\n=== .env File ===")
env_file = Path(".env")
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "REQUIRE_AUTH" in line or "RAPIDAPI" in line:
            print(line)
else:
    print(".env file not found")

# Check Settings
print("\n=== Settings Class ===")
try:
    from app.config import Settings

    settings = Settings()
    print(
        f"settings.REQUIRE_AUTH: {getattr(settings, 'REQUIRE_AUTH', 'ATTRIBUTE NOT FOUND')}"
    )
    print(
        f"settings.RAPIDAPI_PROXY_SECRET: {'SET' if getattr(settings, 'RAPIDAPI_PROXY_SECRET', None) else 'NOT SET'}"
    )
except Exception as e:
    print(f"Error loading settings: {e}")

# Check dependency implementation
print("\n=== Dependency Check ===")
try:
    import inspect

    from app.dependencies import verify_api_key

    source = inspect.getsource(verify_api_key)
    # Check if it checks REQUIRE_AUTH
    if "REQUIRE_AUTH" in source or "settings.REQUIRE_AUTH" in source:
        print("✅ Dependency checks REQUIRE_AUTH setting")
    else:
        print("❌ Dependency does NOT check REQUIRE_AUTH - always enforces auth!")
except Exception as e:
    print(f"Error checking dependency: {e}")

# Check endpoint
print("\n=== Endpoint Check ===")
try:
    from app.main import app

    for route in app.routes:
        if route.path == "/v1/transcribe":
            print(f"Found /v1/transcribe endpoint")
            dependencies = getattr(route, "dependencies", [])
            if dependencies:
                print(f"  Has dependencies: {dependencies}")
            else:
                print("  No dependencies found (might be in endpoint function)")
            break
except Exception as e:
    print(f"Error checking endpoint: {e}")

print("\n=== DIAGNOSIS ===")
print("If REQUIRE_AUTH is false but auth is still enforced, then:")
print("1. The dependency doesn't check settings.REQUIRE_AUTH, OR")
print("2. The Settings class doesn't have REQUIRE_AUTH field, OR")
print("3. The endpoint always applies auth regardless of settings")
print("\nRun the fixed code from the artifacts to resolve this.")
