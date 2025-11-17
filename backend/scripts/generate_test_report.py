"""
Generate comprehensive test report with coverage, performance metrics, and UAT status
Phase 10: Tests, QA et Performance
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def get_coverage_data() -> dict:
    """Extract coverage data from coverage.xml or HTML report."""
    coverage_xml = Path("coverage.xml")
    if not coverage_xml.exists():
        return {"status": "not_available", "message": "Run tests with --cov first"}

    try:
        import xml.etree.ElementTree as ET

        tree = ET.parse(coverage_xml)
        root = tree.getroot()

        # Extract coverage percentages
        coverage_data = {}
        for package in root.findall(".//package"):
            name = package.get("name", "unknown")
            line_rate = float(package.get("line-rate", 0)) * 100
            branch_rate = float(package.get("branch-rate", 0)) * 100
            coverage_data[name] = {
                "line_coverage": round(line_rate, 2),
                "branch_coverage": round(branch_rate, 2),
            }

        # Overall coverage
        overall = root.find(".//coverage")
        if overall is not None:
            overall_line = float(overall.get("line-rate", 0)) * 100
            overall_branch = float(overall.get("branch-rate", 0)) * 100
            coverage_data["_overall"] = {
                "line_coverage": round(overall_line, 2),
                "branch_coverage": round(overall_branch, 2),
            }

        return {"status": "success", "data": coverage_data}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_test_results() -> dict:
    """Run pytest and capture results."""
    print("Running tests to collect results...")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--tb=no",
            "-q",
            "--json-report",
            "--json-report-file=test_results.json",
        ],
        capture_output=True,
        text=True,
    )

    # Try to read JSON report if available
    json_report = Path("test_results.json")
    if json_report.exists():
        try:
            with open(json_report, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # Fallback: parse exit code
    return {
        "exit_code": result.returncode,
        "passed": result.returncode == 0,
    }


def generate_markdown_report(report_data: dict, output_file: str = "TEST_REPORT.md"):
    """Generate markdown test report."""
    md_lines = [
        "# DECLADO-IA - Test Report",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "---",
        "",
        "## 📊 Coverage Summary",
        "",
    ]

    coverage = report_data.get("coverage", {})
    if coverage.get("status") == "success":
        overall = coverage.get("data", {}).get("_overall", {})
        line_cov = overall.get("line_coverage", 0)
        branch_cov = overall.get("branch_coverage", 0)

        md_lines.extend(
            [
                f"- **Line Coverage:** {line_cov}%",
                f"- **Branch Coverage:** {branch_cov}%",
                "",
                f"**Target:** 80% line coverage",
                "",
                "✅ **PASS**" if line_cov >= 80 else "❌ **FAIL**",
                "",
            ]
        )
    else:
        md_lines.extend(
            [
                "⚠️ Coverage data not available",
                "Run: `pytest --cov=app --cov-report=xml`",
                "",
            ]
        )

    md_lines.extend(
        [
            "---",
            "",
            "## 🧪 Test Suites",
            "",
        ]
    )

    test_results = report_data.get("test_results", {})
    for suite, result in test_results.items():
        status = "✅ PASS" if result.get("passed") else "❌ FAIL"
        md_lines.append(f"- **{suite}**: {status}")

    md_lines.extend(
        [
            "",
            "---",
            "",
            "## ⚡ Performance Metrics",
            "",
            "See `test_performance.py` output for detailed metrics.",
            "",
            "**Targets:**",
            "- Single calculation: < 2s",
            "- Batch 200 items: < 30 minutes",
            "- Memory usage: < 2GB",
            "- CPU usage: < 80%",
            "",
            "---",
            "",
            "## 🔒 Security Tests",
            "",
            "Security test results are included in the test suites above.",
            "",
            "**Coverage:**",
            "- SQL injection prevention",
            "- File upload validation",
            "- Input sanitization",
            "- Database encryption",
            "",
            "---",
            "",
            "## ✅ UAT Status",
            "",
            "See `backend/docs/UAT_CHECKLIST.md` for User Acceptance Testing checklist.",
            "",
            "**UAT Sign-off required before production deployment.**",
            "",
            "---",
            "",
            "## 📝 Next Steps",
            "",
            "1. Review coverage gaps and add tests",
            "2. Run UAT with real users (operator/supervisor)",
            "3. Address any performance bottlenecks",
            "4. Complete security audit",
            "5. Obtain UAT sign-off",
            "",
        ]
    )

    report_path = Path(output_file)
    report_path.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"✅ Markdown report generated: {output_file}")


def main():
    """Generate comprehensive test report."""
    print("="*70)
    print("DECLADO-IA - Test Report Generator")
    print("="*70)

    report_data = {
        "timestamp": datetime.now().isoformat(),
        "coverage": get_coverage_data(),
        "test_results": get_test_results(),
    }

    # Save JSON report
    json_path = Path("test_report_full.json")
    json_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    print(f"✅ JSON report saved: {json_path}")

    # Generate markdown report
    generate_markdown_report(report_data)

    print("\n✅ Test report generation complete!")


if __name__ == "__main__":
    main()

