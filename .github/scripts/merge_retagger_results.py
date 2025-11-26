# ================================
# 
# OK- Read No of retagger batches
# OK- Artifact is exported as python-unittest-retagger-gate-batch{NO}-{OS}-{ARCH}-jdk-latest_logs
# 
# list => new job => require_artifacts: reports list
# 
# Download all artifacts => extraxt => filter by name retagger-report
# OK- Merge => report-merged.json
# run mx merge-tags-from-report => git diff => export git diff artifact
#
# ================================

import os
import sys
import json
import glob
import argparse
from dataclasses import dataclass

# Tests' status we want to merge and export
EXPORT_STATUS = ["FAILED"]

@dataclass
class Test:
    name: str
    status: str
    duration: str

def read_report(path: str) -> list[Test]:
    tests = []
    with open(path) as f:
        data = json.load(f)
        for result in data:
            name, status, duration = result.values()
            if status in EXPORT_STATUS: tests.append(Test(f"{name}", status, duration))

    return tests

def merge_tests(report: list[Test], merged: dict[str, dict]):
    for test in report:
        if test.name not in merged: merged[test.name] = test.__dict__

def export_reports(merged: dict[str, dict], outfile: str):
    with open(outfile, "w") as f:
        json.dump(list(merged.values()), f)
    print(f"=== Exported {len(merged)} failing tests to {f.name} ===")

def merge_reports(reports: list[str], outfile: str):
    merged_reports = {} # key: test_name
    for report in reports:
        report_tests = read_report(report)
        merge_tests(report_tests, merged_reports)

    export_reports(merged_reports, outfile)

def main(outfile: str, source_dir: str, pattern: str):
    path = f"{source_dir}/{pattern}"
    files = glob.glob(path)
    if len(files) == 0: raise FileNotFoundError("No report file found")

    files = [file for file in files if file.endswith(".json")]
    merge_reports(files, outfile)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge unittest retagger report JSON files")
    parser.add_argument("--outfile", help="Output file name (optional)", default="reports-merged.json")
    parser.add_argument("--dir", help="Reports files directory (optional)", default=".")
    parser.add_argument("--pattern", default="*", help="Pattern matching for input files (optional)")

    args = parser.parse_args()
    main(
        outfile=args.outfile,
        source_dir=args.dir,
        pattern=args.pattern
    )