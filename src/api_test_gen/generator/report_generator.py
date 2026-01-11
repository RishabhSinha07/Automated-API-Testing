import json
import os
from typing import Dict, Any, List, Optional

class ReportGenerator:
    """
    Generates a coverage and test summary report.
    """
    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.report_path = os.path.join(repo_path, "tests/report.json")
        self.stats = {
            "total_endpoints": 0,
            "positive_tests_count": 0,
            "negative_tests_count": 0,
            "security_tests_count": 0,
            "covered_endpoints": 0,
            "coverage_percentage": 0.0,
            "endpoints": []
        }

    def add_endpoint_stats(self, endpoint_id: str, positive: int, negative: int, security: int):
        self.stats["total_endpoints"] += 1
        self.stats["positive_tests_count"] += positive
        self.stats["negative_tests_count"] += negative
        self.stats["security_tests_count"] += security
        
        if positive > 0:
            self.stats["covered_endpoints"] += 1
            
        self.stats["endpoints"].append({
            "id": endpoint_id,
            "positive": positive,
            "negative": negative,
            "security": security
        })

    def generate_report(self):
        if self.stats["total_endpoints"] > 0:
            self.stats["coverage_percentage"] = (self.stats["covered_endpoints"] / self.stats["total_endpoints"]) * 100
        
        try:
            os.makedirs(os.path.dirname(self.report_path), exist_ok=True)
            with open(self.report_path, 'w', encoding='utf-8') as f:
                json.dump(self.stats, f, indent=2)
            return self.stats
        except Exception as e:
            print(f"Error generating report: {e}")
            return None

    @staticmethod
    def get_report(repo_path: str) -> Optional[Dict[str, Any]]:
        report_path = os.path.join(repo_path, "tests/report.json")
        if os.path.exists(report_path):
            with open(report_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
