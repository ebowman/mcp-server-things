#!/usr/bin/env python3
"""
Comprehensive Test Runner for Move Record Functionality

This script runs all tests for move_record and other missing functionality,
providing detailed reporting on test results, performance metrics, and
coverage analysis.
"""

import sys
import os
import time
import json
import asyncio
import argparse
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ComprehensiveTestRunner:
    """
    Comprehensive test runner with detailed reporting and analysis.
    """
    
    def __init__(self, test_directory: Path = None):
        """Initialize the test runner."""
        self.test_directory = test_directory or Path(__file__).parent
        self.results = {
            "start_time": None,
            "end_time": None,
            "total_duration": None,
            "test_categories": {},
            "performance_metrics": {},
            "coverage_report": {},
            "errors_summary": []
        }
    
    def run_all_tests(
        self, 
        verbose: bool = True,
        performance_tests: bool = True,
        integration_tests: bool = True,
        generate_report: bool = True
    ) -> Dict[str, Any]:
        """
        Run all comprehensive tests and generate detailed report.
        
        Args:
            verbose: Enable verbose output
            performance_tests: Include performance tests
            integration_tests: Include integration tests
            generate_report: Generate detailed HTML report
            
        Returns:
            Dict with complete test results and metrics
        """
        logger.info("Starting comprehensive test suite execution...")
        self.results["start_time"] = datetime.now().isoformat()
        start_time = time.time()
        
        try:
            # Run different categories of tests
            self._run_core_functionality_tests(verbose)
            self._run_error_handling_tests(verbose)
            self._run_json_serialization_tests(verbose)
            
            if performance_tests:
                self._run_performance_tests(verbose)
            
            if integration_tests:
                self._run_integration_tests(verbose)
            
            # Run missing functionality tests
            self._run_missing_functionality_tests(verbose)
            
            # Calculate metrics
            end_time = time.time()
            self.results["end_time"] = datetime.now().isoformat()
            self.results["total_duration"] = end_time - start_time
            
            # Generate performance metrics
            self._calculate_performance_metrics()
            
            # Generate summary
            self._generate_test_summary()
            
            if generate_report:
                self._generate_html_report()
            
            logger.info(f"Test suite completed in {self.results['total_duration']:.2f} seconds")
            return self.results
            
        except Exception as e:
            logger.error(f"Error during test execution: {e}")
            self.results["fatal_error"] = str(e)
            return self.results
    
    def _run_core_functionality_tests(self, verbose: bool):
        """Run core move_record functionality tests."""
        logger.info("Running core functionality tests...")
        
        test_args = [
            str(self.test_directory / "test_move_record_comprehensive.py::TestMoveRecordCore"),
            "-v" if verbose else "-q",
            "--tb=short",
            "--json-report",
            "--json-report-file=core_results.json"
        ]
        
        exit_code = pytest.main(test_args)
        
        # Parse results
        try:
            with open("core_results.json", "r") as f:
                results = json.load(f)
            self.results["test_categories"]["core_functionality"] = {
                "exit_code": exit_code,
                "summary": results.get("summary", {}),
                "tests": results.get("tests", [])
            }
        except FileNotFoundError:
            self.results["test_categories"]["core_functionality"] = {
                "exit_code": exit_code,
                "error": "Results file not found"
            }
    
    def _run_error_handling_tests(self, verbose: bool):
        """Run error handling and edge case tests."""
        logger.info("Running error handling tests...")
        
        test_args = [
            str(self.test_directory / "test_move_record_comprehensive.py::TestMoveRecordErrorHandling"),
            "-v" if verbose else "-q",
            "--tb=short",
            "--json-report",
            "--json-report-file=error_results.json"
        ]
        
        exit_code = pytest.main(test_args)
        
        try:
            with open("error_results.json", "r") as f:
                results = json.load(f)
            self.results["test_categories"]["error_handling"] = {
                "exit_code": exit_code,
                "summary": results.get("summary", {}),
                "tests": results.get("tests", [])
            }
        except FileNotFoundError:
            self.results["test_categories"]["error_handling"] = {
                "exit_code": exit_code,
                "error": "Results file not found"
            }
    
    def _run_json_serialization_tests(self, verbose: bool):
        """Run JSON serialization tests."""
        logger.info("Running JSON serialization tests...")
        
        test_args = [
            str(self.test_directory / "test_move_record_comprehensive.py::TestJSONSerialization"),
            "-v" if verbose else "-q",
            "--tb=short",
            "--json-report",
            "--json-report-file=json_results.json"
        ]
        
        exit_code = pytest.main(test_args)
        
        try:
            with open("json_results.json", "r") as f:
                results = json.load(f)
            self.results["test_categories"]["json_serialization"] = {
                "exit_code": exit_code,
                "summary": results.get("summary", {}),
                "tests": results.get("tests", [])
            }
        except FileNotFoundError:
            self.results["test_categories"]["json_serialization"] = {
                "exit_code": exit_code,
                "error": "Results file not found"
            }
    
    def _run_performance_tests(self, verbose: bool):
        """Run performance and load tests."""
        logger.info("Running performance tests...")
        
        test_args = [
            str(self.test_directory / "test_move_record_comprehensive.py::TestPerformanceTesting"),
            "-v" if verbose else "-q",
            "--tb=short",
            "--json-report",
            "--json-report-file=performance_results.json"
        ]
        
        exit_code = pytest.main(test_args)
        
        try:
            with open("performance_results.json", "r") as f:
                results = json.load(f)
            self.results["test_categories"]["performance"] = {
                "exit_code": exit_code,
                "summary": results.get("summary", {}),
                "tests": results.get("tests", [])
            }
        except FileNotFoundError:
            self.results["test_categories"]["performance"] = {
                "exit_code": exit_code,
                "error": "Results file not found"
            }
    
    def _run_integration_tests(self, verbose: bool):
        """Run integration tests with existing MCP server."""
        logger.info("Running integration tests...")
        
        test_args = [
            str(self.test_directory / "test_move_record_comprehensive.py::TestMCPServerIntegration"),
            "-v" if verbose else "-q",
            "--tb=short",
            "--json-report",
            "--json-report-file=integration_results.json"
        ]
        
        exit_code = pytest.main(test_args)
        
        try:
            with open("integration_results.json", "r") as f:
                results = json.load(f)
            self.results["test_categories"]["integration"] = {
                "exit_code": exit_code,
                "summary": results.get("summary", {}),
                "tests": results.get("tests", [])
            }
        except FileNotFoundError:
            self.results["test_categories"]["integration"] = {
                "exit_code": exit_code,
                "error": "Results file not found"
            }
    
    def _run_missing_functionality_tests(self, verbose: bool):
        """Run tests for other missing functionality."""
        logger.info("Running missing functionality tests...")
        
        test_args = [
            str(self.test_directory / "test_move_record_comprehensive.py::TestMissingFunctionality"),
            "-v" if verbose else "-q",
            "--tb=short",
            "--json-report",
            "--json-report-file=missing_results.json"
        ]
        
        exit_code = pytest.main(test_args)
        
        try:
            with open("missing_results.json", "r") as f:
                results = json.load(f)
            self.results["test_categories"]["missing_functionality"] = {
                "exit_code": exit_code,
                "summary": results.get("summary", {}),
                "tests": results.get("tests", [])
            }
        except FileNotFoundError:
            self.results["test_categories"]["missing_functionality"] = {
                "exit_code": exit_code,
                "error": "Results file not found"
            }
    
    def _calculate_performance_metrics(self):
        """Calculate performance metrics from test results."""
        metrics = {
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "skipped_tests": 0,
            "average_test_duration": 0,
            "slowest_tests": [],
            "fastest_tests": []
        }
        
        all_test_durations = []
        
        for category_name, category_results in self.results["test_categories"].items():
            if "summary" in category_results:
                summary = category_results["summary"]
                metrics["total_tests"] += summary.get("total", 0)
                metrics["passed_tests"] += summary.get("passed", 0)
                metrics["failed_tests"] += summary.get("failed", 0)
                metrics["skipped_tests"] += summary.get("skipped", 0)
            
            if "tests" in category_results:
                for test in category_results["tests"]:
                    duration = test.get("duration", 0)
                    all_test_durations.append({
                        "name": test.get("nodeid", "unknown"),
                        "duration": duration,
                        "category": category_name
                    })
        
        # Calculate average duration
        if all_test_durations:
            total_duration = sum(t["duration"] for t in all_test_durations)
            metrics["average_test_duration"] = total_duration / len(all_test_durations)
            
            # Find slowest and fastest tests
            sorted_tests = sorted(all_test_durations, key=lambda x: x["duration"])
            metrics["slowest_tests"] = sorted_tests[-5:]  # Top 5 slowest
            metrics["fastest_tests"] = sorted_tests[:5]   # Top 5 fastest
        
        # Calculate success rate
        if metrics["total_tests"] > 0:
            metrics["success_rate"] = (metrics["passed_tests"] / metrics["total_tests"]) * 100
        else:
            metrics["success_rate"] = 0
        
        self.results["performance_metrics"] = metrics
    
    def _generate_test_summary(self):
        """Generate a comprehensive test summary."""
        summary = {
            "overall_status": "PASSED",
            "categories_summary": {},
            "key_findings": [],
            "recommendations": []
        }
        
        failed_categories = []
        
        for category_name, category_results in self.results["test_categories"].items():
            exit_code = category_results.get("exit_code", 1)
            category_status = "PASSED" if exit_code == 0 else "FAILED"
            
            if category_status == "FAILED":
                failed_categories.append(category_name)
            
            summary["categories_summary"][category_name] = {
                "status": category_status,
                "exit_code": exit_code
            }
        
        # Overall status
        if failed_categories:
            summary["overall_status"] = "FAILED"
            summary["key_findings"].append(f"Failed categories: {', '.join(failed_categories)}")
        
        # Performance findings
        metrics = self.results.get("performance_metrics", {})
        if metrics.get("success_rate", 0) >= 95:
            summary["key_findings"].append("Excellent test success rate (>=95%)")
        elif metrics.get("success_rate", 0) >= 80:
            summary["key_findings"].append("Good test success rate (>=80%)")
        else:
            summary["key_findings"].append("Low test success rate (<80%) - needs attention")
        
        if metrics.get("average_test_duration", 0) < 0.1:
            summary["key_findings"].append("Excellent test performance (<100ms average)")
        elif metrics.get("average_test_duration", 0) < 0.5:
            summary["key_findings"].append("Good test performance (<500ms average)")
        else:
            summary["key_findings"].append("Slow test performance (>=500ms average)")
        
        # Recommendations
        if failed_categories:
            summary["recommendations"].append("Address failing test categories before deployment")
        
        if metrics.get("success_rate", 0) < 100:
            summary["recommendations"].append("Investigate and fix failing tests")
        
        if metrics.get("average_test_duration", 0) > 0.5:
            summary["recommendations"].append("Optimize slow-running tests")
        
        self.results["summary"] = summary
    
    def _generate_html_report(self):
        """Generate an HTML report of the test results."""
        html_content = self._build_html_report()
        
        report_path = Path("test_report.html")
        with open(report_path, "w") as f:
            f.write(html_content)
        
        logger.info(f"HTML report generated: {report_path.absolute()}")
    
    def _build_html_report(self) -> str:
        """Build HTML content for the test report."""
        metrics = self.results.get("performance_metrics", {})
        summary = self.results.get("summary", {})
        
        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Move Record Comprehensive Test Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 3px solid #007acc; padding-bottom: 10px; }}
        h2 {{ color: #555; margin-top: 30px; }}
        .status-passed {{ color: #28a745; font-weight: bold; }}
        .status-failed {{ color: #dc3545; font-weight: bold; }}
        .metric {{ background: #f8f9fa; padding: 15px; margin: 10px 0; border-left: 4px solid #007acc; }}
        .category {{ background: #fff; border: 1px solid #ddd; margin: 15px 0; padding: 20px; border-radius: 5px; }}
        .findings {{ background: #e9ecef; padding: 15px; border-radius: 5px; margin: 15px 0; }}
        ul {{ padding-left: 20px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #f8f9fa; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Move Record Comprehensive Test Report</h1>
        
        <div class="metric">
            <h2>Overall Status: <span class="status-{summary.get('overall_status', 'unknown').lower()}">{summary.get('overall_status', 'UNKNOWN')}</span></h2>
            <p><strong>Test Duration:</strong> {self.results.get('total_duration', 0):.2f} seconds</p>
            <p><strong>Generated:</strong> {self.results.get('end_time', 'Unknown')}</p>
        </div>
        
        <h2>Performance Metrics</h2>
        <div class="metric">
            <table>
                <tr><th>Metric</th><th>Value</th></tr>
                <tr><td>Total Tests</td><td>{metrics.get('total_tests', 0)}</td></tr>
                <tr><td>Passed Tests</td><td class="status-passed">{metrics.get('passed_tests', 0)}</td></tr>
                <tr><td>Failed Tests</td><td class="status-failed">{metrics.get('failed_tests', 0)}</td></tr>
                <tr><td>Skipped Tests</td><td>{metrics.get('skipped_tests', 0)}</td></tr>
                <tr><td>Success Rate</td><td>{metrics.get('success_rate', 0):.1f}%</td></tr>
                <tr><td>Average Duration</td><td>{metrics.get('average_test_duration', 0):.3f}s</td></tr>
            </table>
        </div>
        
        <h2>Test Categories</h2>
        """
        
        for category_name, category_results in self.results["test_categories"].items():
            status = "PASSED" if category_results.get("exit_code") == 0 else "FAILED"
            status_class = status.lower()
            
            html += f"""
        <div class="category">
            <h3>{category_name.replace('_', ' ').title()}: <span class="status-{status_class}">{status}</span></h3>
            <p><strong>Exit Code:</strong> {category_results.get('exit_code', 'Unknown')}</p>
            """
            
            if "summary" in category_results:
                summary_data = category_results["summary"]
                html += f"""
            <p><strong>Tests:</strong> {summary_data.get('total', 0)} total, 
               {summary_data.get('passed', 0)} passed, 
               {summary_data.get('failed', 0)} failed</p>
                """
            
            html += "</div>"
        
        html += f"""
        <h2>Key Findings</h2>
        <div class="findings">
            <ul>
        """
        
        for finding in summary.get("key_findings", []):
            html += f"<li>{finding}</li>"
        
        html += """
            </ul>
        </div>
        
        <h2>Recommendations</h2>
        <div class="findings">
            <ul>
        """
        
        for recommendation in summary.get("recommendations", []):
            html += f"<li>{recommendation}</li>"
        
        html += """
            </ul>
        </div>
    </div>
</body>
</html>
        """
        
        return html
    
    def print_summary(self):
        """Print a concise summary to the console."""
        print("\n" + "="*80)
        print("COMPREHENSIVE TEST SUITE SUMMARY")
        print("="*80)
        
        summary = self.results.get("summary", {})
        metrics = self.results.get("performance_metrics", {})
        
        print(f"Overall Status: {summary.get('overall_status', 'UNKNOWN')}")
        print(f"Total Duration: {self.results.get('total_duration', 0):.2f} seconds")
        print(f"Total Tests: {metrics.get('total_tests', 0)}")
        print(f"Success Rate: {metrics.get('success_rate', 0):.1f}%")
        
        print("\nCategory Results:")
        for category_name, category_data in summary.get("categories_summary", {}).items():
            status = category_data.get("status", "UNKNOWN")
            print(f"  {category_name.replace('_', ' ').title()}: {status}")
        
        print("\nKey Findings:")
        for finding in summary.get("key_findings", []):
            print(f"  • {finding}")
        
        if summary.get("recommendations"):
            print("\nRecommendations:")
            for rec in summary.get("recommendations", []):
                print(f"  • {rec}")
        
        print("="*80 + "\n")


def main():
    """Main entry point for the test runner."""
    parser = argparse.ArgumentParser(description="Run comprehensive tests for move_record functionality")
    parser.add_argument("--no-performance", action="store_true", help="Skip performance tests")
    parser.add_argument("--no-integration", action="store_true", help="Skip integration tests")
    parser.add_argument("--no-report", action="store_true", help="Skip HTML report generation")
    parser.add_argument("--quiet", action="store_true", help="Reduce output verbosity")
    
    args = parser.parse_args()
    
    # Create and run test suite
    test_runner = ComprehensiveTestRunner()
    
    results = test_runner.run_all_tests(
        verbose=not args.quiet,
        performance_tests=not args.no_performance,
        integration_tests=not args.no_integration,
        generate_report=not args.no_report
    )
    
    # Print summary
    test_runner.print_summary()
    
    # Save results to JSON
    with open("comprehensive_test_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"Detailed results saved to: comprehensive_test_results.json")
    
    # Exit with appropriate code
    overall_status = results.get("summary", {}).get("overall_status", "FAILED")
    sys.exit(0 if overall_status == "PASSED" else 1)


if __name__ == "__main__":
    main()