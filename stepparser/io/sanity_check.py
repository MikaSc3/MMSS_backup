import os
import glob
import time
from typing import List
from .utils import save_json

class SanityChecker:
    """Validates analysis output files"""

    DEFAULT_KEYWORDS = ['ERROR', 'error', 'Error', 'NaN', 'failed', 'warning', 'Warning', 'missing']

    @staticmethod
    def check_assemblies(processed_dir: str, keywords: List[str] = None) -> None:
        """Generate sanity reports for all assemblies"""
        keywords = keywords or SanityChecker.DEFAULT_KEYWORDS

        print("\n" + "="*80)
        print("RUNNING SANITY CHECKS")
        print(f"Keywords: {', '.join(keywords)}")
        print("="*80 + "\n")

        total_issues = 0

        for assembly_name in os.listdir(processed_dir):
            assembly_path = os.path.join(processed_dir, assembly_name)
            if not os.path.isdir(assembly_path):
                continue

            print(f"[DEBUG] Checking: {assembly_name}")
            issues_in_assembly = SanityChecker._check_assembly(assembly_path, assembly_name, keywords)
            total_issues += issues_in_assembly

        if total_issues:
            print(f"\n[WARNING] Sanity checks complete: {total_issues} issue(s) found")
        else:
            print("\n[SUCCESS] Sanity checks complete\nNo problems found")

    @staticmethod
    def _check_assembly(assembly_path: str, assembly_name: str, keywords: List[str]) -> int:
        """Check single assembly and generate report"""
        issues = []

        for item in os.listdir(assembly_path):
            item_path = os.path.join(assembly_path, item)

            # Skip non-directories and assembly folders
            if not os.path.isdir(item_path) or item.endswith('_assembly'):
                continue

            part_name = item

            # Check JSON files
            for json_file in glob.glob(os.path.join(item_path, "*.json")):
                json_name = os.path.basename(json_file)

                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        found = [kw for kw in keywords if kw in content]

                        if found:
                            issues.append({
                                'assembly': assembly_name,
                                'part': part_name,
                                'file': json_name,
                                'found_keywords': found
                            })

                except Exception as e:
                    issues.append({
                        'assembly': assembly_name,
                        'part': part_name,
                        'file': json_name,
                        'issue': f'READ_ERROR: {str(e)}'
                    })

        # Save report
        report = {
            'assembly': assembly_name,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'keywords_searched': keywords,
            'total_issues': len(issues),
            'issues': issues
        }

        save_json(os.path.join(assembly_path, 'sanity.json'), report)

        if issues:
            print(f"[WARNING] Found {len(issues)} issues in {assembly_name}")
        else:
            print(f"[OK] No issues in {assembly_name}")

        return len(issues)