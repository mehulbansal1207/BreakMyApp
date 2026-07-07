#!/usr/bin/env python3
"""
Test runner for custom Semgrep rule fixtures.

Imports CUSTOM_RULES_YAML from custom_scanner.py, writes it to a temp file,
then runs semgrep against each _vulnerable and _safe fixture to verify that:
  - _vulnerable fixtures produce at least one finding with the expected rule_id
  - _safe fixtures produce zero findings for that rule_id

Prints a PASS/FAIL table and exits non-zero on any failure.
"""

import json
import os
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------------------
# Import CUSTOM_RULES_YAML from the scanner module
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from custom_scanner import CUSTOM_RULES_YAML  # noqa: E402

# ---------------------------------------------------------------------------
# Rule ID → fixture file extension mapping (all 13 variants)
# ---------------------------------------------------------------------------
RULE_FIXTURES = [
    ("custom-ssti-jinja2", "py"),
    ("custom-redos-python", "py"),
    ("custom-redos-javascript", "js"),
    ("custom-long-password-dos-python", "py"),
    ("custom-long-password-dos-javascript", "js"),
    ("custom-aws-hardcoded-key-python", "py"),
    ("custom-aws-hardcoded-key-js", "js"),
    ("custom-aws-key-literal", "py"),
    ("custom-nosql-injection-python", "py"),
    ("custom-nosql-injection-javascript", "js"),
    ("custom-clipboard-hijacking", "js"),
    ("custom-jwt-no-exp-python", "py"),
    ("custom-jwt-no-exp-javascript", "js"),
]


def run_semgrep(config_path: str, target_path: str) -> dict:
    """Run semgrep scan and return parsed JSON output."""
    try:
        result = subprocess.run(
            [
                "semgrep", "scan",
                "--config", config_path,
                target_path,
                "--json",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"  WARN: Could not parse semgrep JSON for {os.path.basename(target_path)}")
        print(f"  stderr: {result.stderr[:500]}")
        return {"results": []}
    except FileNotFoundError:
        print("ERROR: semgrep binary not found. Is Semgrep installed?")
        sys.exit(2)


def get_findings_for_rule(output: dict, rule_id: str) -> list:
    """Extract findings whose check_id ends with the given rule_id."""
    return [
        r for r in output.get("results", [])
        if r.get("check_id", "").endswith(rule_id)
    ]


def main():
    fixtures_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "custom")

    # Write rules YAML to a temp file
    tmp = tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False)
    try:
        tmp.write(CUSTOM_RULES_YAML)
        tmp.close()
        config_path = tmp.name

        results_table = []
        any_failure = False

        for rule_id, ext in RULE_FIXTURES:
            vuln_file = os.path.join(fixtures_dir, f"{rule_id}_vulnerable.{ext}")
            safe_file = os.path.join(fixtures_dir, f"{rule_id}_safe.{ext}")

            # --- Vulnerable fixture ---
            if not os.path.exists(vuln_file):
                print(f"  MISSING: {vuln_file}")
                results_table.append((rule_id, False, False))
                any_failure = True
                continue

            vuln_output = run_semgrep(config_path, vuln_file)
            vuln_findings = get_findings_for_rule(vuln_output, rule_id)
            vuln_pass = len(vuln_findings) > 0

            # --- Safe fixture ---
            if not os.path.exists(safe_file):
                print(f"  MISSING: {safe_file}")
                results_table.append((rule_id, vuln_pass, False))
                any_failure = True
                continue

            safe_output = run_semgrep(config_path, safe_file)
            safe_findings = get_findings_for_rule(safe_output, rule_id)
            safe_pass = len(safe_findings) == 0

            if not vuln_pass:
                print(f"  DEBUG [{rule_id}] vuln findings: {len(vuln_findings)} "
                      f"(all findings: {len(vuln_output.get('results', []))})")
                any_failure = True
            if not safe_pass:
                print(f"  DEBUG [{rule_id}] safe findings for this rule: {len(safe_findings)}")
                any_failure = True

            results_table.append((rule_id, vuln_pass, safe_pass))

        # ----- Print results table -----
        print()
        print("=" * 80)
        print(f"  {'Rule ID':<48} {'Vuln':>6} {'Safe':>6}")
        print("-" * 80)
        for rule_id, vuln_pass, safe_pass in results_table:
            v = "PASS" if vuln_pass else "FAIL"
            s = "PASS" if safe_pass else "FAIL"
            print(f"  {rule_id:<48} {v:>6} {s:>6}")
        print("=" * 80)

        total = len(results_table) * 2
        passed = sum(1 for _, v, s in results_table for p in [v, s] if p)
        print(f"\n  {passed}/{total} checks passed.")

        if any_failure:
            print("\n  *** Some checks FAILED! ***")
            sys.exit(1)
        else:
            print("\n  All checks PASSED!")
            sys.exit(0)

    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


if __name__ == "__main__":
    main()
