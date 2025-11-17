#!/bin/bash
# Test Runner Script - Execute all test suites
# Phase 10: Tests, QA et Performance

set -e

echo "============================================================"
echo "DECLADO-IA - Test Suite Runner"
echo "Phase 10: Tests, QA et Performance"
echo "============================================================"

# Change to backend directory
cd "$(dirname "$0")/.."

# Run all tests with coverage
echo ""
echo "Running all tests with coverage..."
echo ""

python -m pytest \
    --cov=app \
    --cov-report=html:htmlcov \
    --cov-report=term-missing \
    --cov-report=xml:coverage.xml \
    --cov-fail-under=80 \
    -v

# Generate test report
echo ""
echo "Generating test report..."
python scripts/generate_test_report.py

echo ""
echo "============================================================"
echo "✅ Test suite complete!"
echo "============================================================"
echo ""
echo "Reports generated:"
echo "  - Coverage HTML: htmlcov/index.html"
echo "  - Coverage XML:  coverage.xml"
echo "  - Test Report:   TEST_REPORT.md"
echo ""

