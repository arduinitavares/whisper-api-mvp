#!/usr/bin/env python3
"""
Comprehensive test runner for the Whisper API service.

Provides convenient commands for running different types of tests
with appropriate configurations and reporting.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


def run_command(cmd: List[str], description: str) -> int:
    """Run a command and return the exit code."""
    print(f"\n🔍 {description}")
    print(f"Command: {' '.join(cmd)}")
    print("=" * 60)
    
    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode
    except KeyboardInterrupt:
        print("\n❌ Test run interrupted by user")
        return 130
    except FileNotFoundError as e:
        print(f"❌ Command not found: {e}")
        return 127


def check_dependencies() -> bool:
    """Check that required dependencies are available."""
    print("🔍 Checking test dependencies...")
    
    required_packages = [
        "pytest",
        "pytest-asyncio", 
        "pytest-cov",
        "httpx",
        "fastapi",
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ Missing required packages: {', '.join(missing_packages)}")
        print("Install with: pip install -r requirements.txt")
        return False
    
    print("✅ All test dependencies are available")
    return True


def create_test_dirs() -> None:
    """Create necessary directories for testing."""
    dirs = ["logs", "htmlcov", "test_data", ".pytest_cache"]
    for dir_name in dirs:
        Path(dir_name).mkdir(exist_ok=True)
    print("✅ Test directories created")


def run_unit_tests(verbose: bool = False, coverage: bool = True) -> int:
    """Run unit tests only."""
    cmd = ["python", "-m", "pytest", "-m", "unit"]
    
    if verbose:
        cmd.append("-vv")
    if coverage:
        cmd.extend(["--cov=app", "--cov-report=term-missing"])
    
    return run_command(cmd, "Running unit tests")


def run_api_tests(verbose: bool = False) -> int:
    """Run API endpoint tests."""
    cmd = ["python", "-m", "pytest", "-m", "api"]
    
    if verbose:
        cmd.append("-vv")
    
    return run_command(cmd, "Running API tests")


def run_integration_tests(verbose: bool = False) -> int:
    """Run integration tests."""
    cmd = ["python", "-m", "pytest", "-m", "integration"]
    
    if verbose:
        cmd.append("-vv")
    
    return run_command(cmd, "Running integration tests")


def run_performance_tests(verbose: bool = False) -> int:
    """Run performance and load tests."""
    cmd = ["python", "-m", "pytest", "-m", "performance", "-x"]
    
    if verbose:
        cmd.append("-vv")
    
    return run_command(cmd, "Running performance tests")


def run_error_tests(verbose: bool = False) -> int:
    """Run error handling tests."""
    cmd = ["python", "-m", "pytest", "-m", "error"]
    
    if verbose:
        cmd.append("-vv")
    
    return run_command(cmd, "Running error handling tests")


def run_all_tests(verbose: bool = False, coverage: bool = True, fast: bool = False) -> int:
    """Run all tests with comprehensive reporting."""
    cmd = ["python", "-m", "pytest"]
    
    if fast:
        cmd.extend(["-m", "not slow"])
    
    if verbose:
        cmd.append("-vv")
    else:
        cmd.append("-v")
    
    if coverage:
        cmd.extend([
            "--cov=app",
            "--cov-report=term-missing", 
            "--cov-report=html:htmlcov",
            "--cov-report=xml:coverage.xml"
        ])
    
    return run_command(cmd, "Running all tests")


def run_specific_test(test_path: str, verbose: bool = False) -> int:
    """Run a specific test file or test function."""
    cmd = ["python", "-m", "pytest", test_path]
    
    if verbose:
        cmd.append("-vv")
    
    return run_command(cmd, f"Running specific test: {test_path}")


def run_with_service_check(verbose: bool = False) -> int:
    """Run tests that require the service to be running."""
    # Check if service is running
    import requests
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code != 200:
            print("❌ Service is not responding properly")
            return 1
    except requests.RequestException:
        print("❌ Service is not running on localhost:8000")
        print("Start the service first: ./start.sh start")
        return 1
    
    print("✅ Service is running and responding")
    
    cmd = ["python", "-m", "pytest", "-m", "requires_service"]
    if verbose:
        cmd.append("-vv")
    
    return run_command(cmd, "Running tests that require running service")


def generate_coverage_report() -> int:
    """Generate detailed coverage report."""
    cmd = ["python", "-m", "pytest", "--cov=app", "--cov-report=html", "--cov-report=term"]
    return run_command(cmd, "Generating coverage report")


def lint_code() -> int:
    """Run code linting and formatting checks."""
    print("\n🔍 Running code quality checks")
    
    exit_code = 0
    
    # Check if tools are available
    tools = {
        "black": ["python", "-m", "black", "--check", "app/"],
        "pylint": ["python", "-m", "pylint", "app/"],
        "mypy": ["python", "-m", "mypy", "app/"]
    }
    
    for tool, cmd in tools.items():
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✅ {tool}: passed")
            else:
                print(f"❌ {tool}: failed")
                print(result.stdout)
                print(result.stderr)
                exit_code = 1
        except FileNotFoundError:
            print(f"⚠️ {tool}: not installed (skipping)")
    
    return exit_code


def main():
    """Main test runner function."""
    parser = argparse.ArgumentParser(
        description="Test runner for Whisper API service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_tests.py                    # Run all tests
  python run_tests.py --unit             # Run only unit tests
  python run_tests.py --api              # Run only API tests
  python run_tests.py --performance      # Run performance tests
  python run_tests.py --fast             # Skip slow tests
  python run_tests.py --with-service     # Test with running service
  python run_tests.py --test test_config.py  # Run specific test file
  python run_tests.py --coverage         # Generate coverage report
  python run_tests.py --lint             # Run code quality checks
        """
    )
    
    # Test type selection
    parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    parser.add_argument("--api", action="store_true", help="Run API tests only")
    parser.add_argument("--integration", action="store_true", help="Run integration tests only")
    parser.add_argument("--performance", action="store_true", help="Run performance tests only")
    parser.add_argument("--error", action="store_true", help="Run error handling tests only")
    parser.add_argument("--with-service", action="store_true", help="Run tests requiring service")
    
    # Test configuration
    parser.add_argument("--fast", action="store_true", help="Skip slow tests")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--no-coverage", action="store_true", help="Skip coverage reporting")
    
    # Specific test
    parser.add_argument("--test", "-t", help="Run specific test file or function")
    
    # Utility commands
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report only")
    parser.add_argument("--lint", action="store_true", help="Run code quality checks")
    parser.add_argument("--setup", action="store_true", help="Setup test environment")
    
    args = parser.parse_args()
    
    # Setup test environment
    if args.setup:
        print("🔧 Setting up test environment...")
        create_test_dirs()
        return 0
    
    # Check dependencies
    if not check_dependencies():
        return 1
    
    # Create test directories
    create_test_dirs()
    
    # Set environment for testing
    os.environ["TESTING"] = "true"
    
    exit_code = 0
    
    try:
        # Utility commands
        if args.lint:
            exit_code = lint_code()
        elif args.coverage:
            exit_code = generate_coverage_report()
        
        # Specific test
        elif args.test:
            exit_code = run_specific_test(args.test, args.verbose)
        
        # Test type commands
        elif args.unit:
            exit_code = run_unit_tests(args.verbose, not args.no_coverage)
        elif args.api:
            exit_code = run_api_tests(args.verbose)
        elif args.integration:
            exit_code = run_integration_tests(args.verbose)
        elif args.performance:
            exit_code = run_performance_tests(args.verbose)
        elif args.error:
            exit_code = run_error_tests(args.verbose)
        elif args.with_service:
            exit_code = run_with_service_check(args.verbose)
        
        # Default: run all tests
        else:
            exit_code = run_all_tests(args.verbose, not args.no_coverage, args.fast)
        
        # Report results
        if exit_code == 0:
            print("\n✅ All tests completed successfully!")
            if not args.no_coverage and not args.lint:
                print("📊 Coverage report available at: htmlcov/index.html")
        else:
            print(f"\n❌ Tests failed with exit code: {exit_code}")
    
    except KeyboardInterrupt:
        print("\n❌ Test run interrupted")
        exit_code = 130
    
    finally:
        # Clean up environment
        if "TESTING" in os.environ:
            del os.environ["TESTING"]
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())