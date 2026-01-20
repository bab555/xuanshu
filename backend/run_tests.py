#!/usr/bin/env python
"""
Test runner script

Usage:
    python run_tests.py              # Run all tests
    python run_tests.py unit         # Run unit tests only
    python run_tests.py api          # Run API tests only
    python run_tests.py network      # Run network connectivity tests
    python run_tests.py integration  # Run integration tests
    python run_tests.py quick        # Run quick tests (skip slow/network)
"""
import sys
import subprocess


def run_pytest(args: list[str]):
    """Run pytest with given arguments"""
    cmd = ["python", "-m", "pytest"] + args
    print(f"\n{'='*60}")
    print(f"Running: {' '.join(cmd)}")
    print(f"{'='*60}\n")
    return subprocess.run(cmd).returncode


def main():
    if len(sys.argv) < 2:
        # Run all tests
        return run_pytest(["-v", "--tb=short"])
    
    test_type = sys.argv[1].lower()
    
    if test_type == "unit":
        # Unit tests only (mocked, no external deps)
        return run_pytest([
            "-v", 
            "tests/test_utils.py",
            "tests/test_nodes.py",
            "tests/test_model_client.py",
            "-m", "not integration"
        ])
    
    elif test_type == "api":
        # API endpoint tests
        return run_pytest([
            "-v",
            "tests/test_auth.py",
            "tests/test_documents.py",
            "tests/test_workflow.py",
            "tests/test_attachments.py",
            "tests/test_export.py",
        ])
    
    elif test_type == "network":
        # Network connectivity tests (requires .env)
        return run_pytest([
            "-v", "-s",  # -s to show prints
            "tests/test_network.py",
        ])
    
    elif test_type == "integration":
        # Full integration tests
        return run_pytest([
            "-v",
            "tests/test_integration.py",
        ])
    
    elif test_type == "quick":
        # Quick tests (skip network-dependent)
        return run_pytest([
            "-v",
            "--ignore=tests/test_network.py",
            "-m", "not slow",
        ])
    
    elif test_type == "coverage":
        # Run with coverage report
        return run_pytest([
            "-v",
            "--cov=app",
            "--cov-report=term-missing",
            "--cov-report=html",
        ])
    
    else:
        print(f"Unknown test type: {test_type}")
        print(__doc__)
        return 1


if __name__ == "__main__":
    sys.exit(main())

