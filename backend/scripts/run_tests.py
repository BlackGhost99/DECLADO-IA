"""
Test Runner Script - Execute all test suites with reporting
Phase 10: Tests, QA et Performance
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest


def run_tests_with_marker(marker: str, verbose: bool = True) -> dict:
    """Run tests with a specific marker."""
    args = [
        "-m",
        marker,
        "--tb=short",
        "--cov=app",
        "--cov-report=term-missing",
    ]

    if verbose:
        args.append("-v")

    print(f"\n{'='*70}")
    print(f"Running tests with marker: {marker}")
    print(f"{'='*70}\n")

    exit_code = pytest.main(args)

    return {
        "marker": marker,
        "exit_code": exit_code,
        "passed": exit_code == 0,
    }


def run_all_tests() -> dict:
    """Run all test suites."""
    results = {}

    # Unit tests
    results["unit"] = run_tests_with_marker("unit")

    # Integration tests
    results["integration"] = run_tests_with_marker("integration")

    # E2E tests
    results["e2e"] = run_tests_with_marker("e2e")

    # Performance tests
    results["performance"] = run_tests_with_marker("performance")

    # Security tests
    results["security"] = run_tests_with_marker("security")

    return results


def generate_coverage_report():
    """Generate HTML coverage report."""
    print("\n" + "="*70)
    print("Generating coverage report...")
    print("="*70 + "\n")

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--cov=app",
            "--cov-report=html:htmlcov",
            "--cov-report=term-missing",
            "--cov-report=xml:coverage.xml",
            "-q",  # Quiet mode for coverage only
        ],
        check=False,
    )

    print("\n✅ Coverage report generated:")
    print("   - HTML: htmlcov/index.html")
    print("   - XML:  coverage.xml")


def generate_test_report(results: dict, output_file: str = "test_report.json"):
    """Generate JSON test report."""
    report = {
        "timestamp": datetime.now().isoformat(),
        "test_suites": results,
        "summary": {
            "total_suites": len(results),
            "passed_suites": sum(1 for r in results.values() if r["passed"]),
            "failed_suites": sum(1 for r in results.values() if not r["passed"]),
        },
    }

    report_path = Path(output_file)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\n✅ Test report saved to: {output_file}")

    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    for marker, result in results.items():
        status = "✅ PASS" if result["passed"] else "❌ FAIL"
        print(f"  {marker:15s}: {status}")
    print("="*70)

    return report


def main():
    """Main test runner."""
    print("="*70)
    print("DECLADO-IA - Test Suite Runner")
    print("Phase 10: Tests, QA et Performance")
    print("="*70)

    # Parse command line arguments
    if len(sys.argv) > 1:
        marker = sys.argv[1]
        if marker == "all":
            results = run_all_tests()
        else:
            results = {marker: run_tests_with_marker(marker)}
    else:
        # Run all tests by default
        results = run_all_tests()

    # Generate coverage report
    generate_coverage_report()

    # Generate test report
    generate_test_report(results)

    # Exit with error if any suite failed
    if any(not r["passed"] for r in results.values()):
        print("\n❌ Some test suites failed. Check the output above.")
        sys.exit(1)
    else:
        print("\n✅ All test suites passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()

