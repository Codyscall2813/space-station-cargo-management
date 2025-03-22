#!/usr/bin/env python3
"""
Integration Test Runner for Space Station Cargo Management System.

This script discovers and runs all integration tests, generating a
comprehensive report on system stability and integration status.
"""

import os
import sys
import time
import pytest
import argparse
from datetime import datetime
import json
from pathlib import Path

# Ensure the project root is in the path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
sys.path.insert(0, project_root)

class IntegrationTestRunner:
    """Runs integration tests and generates reports."""
    
    def __init__(self, test_dir=None, report_dir=None, skip_slow=False, verbose=False):
        """
        Initialize the test runner.
        
        Args:
            test_dir: Directory containing integration tests
            report_dir: Directory for test reports
            skip_slow: Whether to skip slow tests
            verbose: Whether to show verbose output
        """
        self.test_dir = test_dir or os.path.join(project_root, 'tests', 'integration')
        self.report_dir = report_dir or os.path.join(project_root, 'reports')
        self.skip_slow = skip_slow
        self.verbose = verbose
        
        # Create report directory if it doesn't exist
        os.makedirs(self.report_dir, exist_ok=True)
    
    def discover_tests(self):
        """Discover integration test files."""
        test_files = []
        for root, _, files in os.walk(self.test_dir):
            for file in files:
                if file.startswith('test_') and file.endswith('.py'):
                    test_files.append(os.path.join(root, file))
        return test_files
    
    def main():
    """Main entry point for the test runner."""
    parser = argparse.ArgumentParser(description='Run integration tests for the Space Station Cargo Management System')
    
    parser.add_argument('--test-dir', type=str, help='Directory containing integration tests')
    parser.add_argument('--report-dir', type=str, help='Directory for test reports')
    parser.add_argument('--skip-slow', action='store_true', help='Skip slow tests')
    parser.add_argument('--verbose', action='store_true', help='Show verbose output')
    
    args = parser.parse_args()
    
    # Create and run the test runner
    runner = IntegrationTestRunner(
        test_dir=args.test_dir,
        report_dir=args.report_dir,
        skip_slow=args.skip_slow,
        verbose=args.verbose
    )
    
    print("Discovering integration tests...")
    test_files = runner.discover_tests()
    print(f"Found {len(test_files)} test files:")
    for test_file in test_files:
        print(f"  - {os.path.relpath(test_file, project_root)}")
    
    print("\nRunning integration tests...")
    results = runner.run_tests()
    
    print("\nGenerating test report...")
    report = runner.generate_report(results)
    
    # Print summary
    print("\nTest Run Summary:")
    print(f"  Status: {'SUCCESS' if results['success'] else 'FAILED'}")
    print(f"  Duration: {results['duration']:.2f} seconds")
    print(f"  Total tests: {report['summary'].get('total', 0)}")
    print(f"  Passed: {report['summary'].get('passed', 0)}")
    print(f"  Failed: {report['summary'].get('failed', 0)}")
    print(f"  Errors: {report['summary'].get('errors', 0)}")
    print(f"  Skipped: {report['summary'].get('skipped', 0)}")
    
    # Exit with appropriate code
    return 0 if results['success'] else 1

if __name__ == "__main__":
    sys.exit(main())tests(self):
        """Run all discovered tests and return results."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Assemble pytest arguments
        pytest_args = [
            '--verbose' if self.verbose else '--quiet',
            '-xvs' if self.verbose else '-v',
            '--junitxml=' + os.path.join(self.report_dir, f'report_{timestamp}.xml'),
            '--no-header',
            '--no-summary' if not self.verbose else '',
            '--tb=short',
            self.test_dir
        ]
        
        if self.skip_slow:
            pytest_args.append('-k "not slow"')
        
        # Record start time
        start_time = time.time()
        
        # Run tests and capture results
        try:
            retcode = pytest.main(pytest_args)
            success = (retcode == 0)
        except Exception as e:
            print(f"Error running tests: {e}")
            success = False
        
        # Calculate duration
        duration = time.time() - start_time
        
        return {
            "success": success,
            "timestamp": timestamp,
            "duration": duration,
            "skip_slow": self.skip_slow
        }
    
    def generate_report(self, results):
        """Generate a comprehensive test report."""
        # Load the XML report
        report_file = os.path.join(self.report_dir, f'report_{results["timestamp"]}.xml')
        
        # Create the report data structure
        report = {
            "timestamp": results["timestamp"],
            "success": results["success"],
            "duration": results["duration"],
            "skip_slow": results["skip_slow"],
            "summary": self._extract_summary_from_xml(report_file) if os.path.exists(report_file) else {},
            "details": self._extract_details_from_xml(report_file) if os.path.exists(report_file) else []
        }
        
        # Write the report to a JSON file
        report_json_path = os.path.join(self.report_dir, f'report_{results["timestamp"]}.json')
        with open(report_json_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        # Generate an HTML report
        self._generate_html_report(report)
        
        return report
    
    def _extract_summary_from_xml(self, xml_path):
        """Extract summary information from JUnit XML report."""
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            # Extract overall test statistics
            total_tests = int(root.get('tests', 0))
            failures = int(root.get('failures', 0))
            errors = int(root.get('errors', 0))
            skipped = int(root.get('skipped', 0))
            
            return {
                "total": total_tests,
                "passed": total_tests - failures - errors - skipped,
                "failed": failures,
                "errors": errors,
                "skipped": skipped
            }
        except Exception as e:
            print(f"Error extracting summary from XML: {e}")
            return {}
    
    def _extract_details_from_xml(self, xml_path):
        """Extract test details from JUnit XML report."""
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            details = []
            # Iterate through testcases
            for testcase in root.findall('.//testcase'):
                test_detail = {
                    "name": testcase.get('name', ''),
                    "classname": testcase.get('classname', ''),
                    "time": float(testcase.get('time', 0)),
                    "status": "passed"
                }
                
                # Check for failures
                failure = testcase.find('failure')
                if failure is not None:
                    test_detail["status"] = "failed"
                    test_detail["message"] = failure.get('message', '')
                    test_detail["traceback"] = failure.text if failure.text else ''
                
                # Check for errors
                error = testcase.find('error')
                if error is not None:
                    test_detail["status"] = "error"
                    test_detail["message"] = error.get('message', '')
                    test_detail["traceback"] = error.text if error.text else ''
                
                # Check for skipped
                skipped = testcase.find('skipped')
                if skipped is not None:
                    test_detail["status"] = "skipped"
                    test_detail["message"] = skipped.get('message', '')
                
                details.append(test_detail)
            
            return details
        except Exception as e:
            print(f"Error extracting details from XML: {e}")
            return []
    
    def _generate_html_report(self, report_data):
        """Generate an HTML report from the test results."""
        html_path = os.path.join(self.report_dir, f'report_{report_data["timestamp"]}.html')
        
        # Generate a styled HTML report
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Integration Test Report - {report_data["timestamp"]}</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 0; padding: 0; color: #333; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        header {{ background-color: #f8f8f8; padding: 20px; border-bottom: 1px solid #eee; margin-bottom: 20px; }}
        h1 {{ margin: 0; color: #444; }}
        .summary {{ background-color: {('#dff0d8' if report_data["success"] else '#f2dede')}; 
                  padding: 15px; border-radius: 4px; margin-bottom: 20px; }}
        .summary h2 {{ margin-top: 0; color: {('#3c763d' if report_data["success"] else '#a94442')}; }}
        .stats {{ display: flex; flex-wrap: wrap; gap: 15px; margin-bottom: 20px; }}
        .stat-box {{ flex: 1; min-width: 120px; padding: 15px; background-color: #f8f8f8; 
                   border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .stat-value {{ font-size: 24px; font-weight: bold; margin-bottom: 5px; }}
        .stat-label {{ font-size: 14px; color: #777; }}
        .pass {{ color: #3c763d; }}
        .fail {{ color: #a94442; }}
        .skip {{ color: #8a6d3b; }}
        .error {{ color: #a94442; }}
        .test-list {{ margin-top: 30px; }}
        .test-item {{ padding: 10px; margin-bottom: 10px; border-radius: 4px; }}
        .test-passed {{ background-color: #dff0d8; }}
        .test-failed {{ background-color: #f2dede; }}
        .test-error {{ background-color: #f2dede; }}
        .test-skipped {{ background-color: #fcf8e3; }}
        .test-name {{ font-weight: bold; margin-bottom: 5px; }}
        .test-time {{ font-size: 12px; color: #777; }}
        .traceback {{ background-color: #f8f8f8; padding: 10px; border-radius: 4px; 
                   font-family: monospace; white-space: pre-wrap; margin-top: 10px; }}
        .footer {{ margin-top: 30px; padding-top: 10px; border-top: 1px solid #eee; 
                 font-size: 12px; color: #777; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Integration Test Report</h1>
            <div>Space Station Cargo Management System</div>
            <div>Run at: {datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')}</div>
        </header>
        
        <div class="summary">
            <h2>Test Run {('Successful' if report_data["success"] else 'Failed')}</h2>
            <p>Duration: {report_data["duration"]:.2f} seconds</p>
            <p>Configuration: {"Skipping slow tests" if report_data["skip_slow"] else "Running all tests"}</p>
        </div>
        
        <div class="stats">
            <div class="stat-box">
                <div class="stat-value">{report_data["summary"].get("total", 0)}</div>
                <div class="stat-label">Total Tests</div>
            </div>
            <div class="stat-box">
                <div class="stat-value pass">{report_data["summary"].get("passed", 0)}</div>
                <div class="stat-label">Passed</div>
            </div>
            <div class="stat-box">
                <div class="stat-value fail">{report_data["summary"].get("failed", 0)}</div>
                <div class="stat-label">Failed</div>
            </div>
            <div class="stat-box">
                <div class="stat-value error">{report_data["summary"].get("errors", 0)}</div>
                <div class="stat-label">Errors</div>
            </div>
            <div class="stat-box">
                <div class="stat-value skip">{report_data["summary"].get("skipped", 0)}</div>
                <div class="stat-label">Skipped</div>
            </div>
        </div>
        
        <div class="test-list">
            <h2>Test Details</h2>
"""
        
        # Add individual test results
        for test in report_data["details"]:
            status_class = f"test-{test['status']}"
            html_content += f"""
            <div class="test-item {status_class}">
                <div class="test-name">{test['classname']} » {test['name']}</div>
                <div class="test-time">Time: {test['time']:.2f}s</div>
"""
            
            # Add message and traceback for failures/errors
            if test["status"] in ["failed", "error"] and "message" in test:
                html_content += f"""
                <div class="test-message">{test['message']}</div>
"""
                
            if test["status"] in ["failed", "error"] and "traceback" in test:
                html_content += f"""
                <div class="traceback">{test['traceback']}</div>
"""
                
            html_content += f"""
            </div>
"""
        
        # Close HTML tags
        html_content += f"""
        </div>
        
        <div class="footer">
            <p>Generated by Integration Test Runner on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
    </div>
</body>
</html>
"""
        
        # Write the HTML report
        with open(html_path, 'w') as f:
            f.write(html_content)
        
        print(f"HTML report generated: {html_path}")

def run_
