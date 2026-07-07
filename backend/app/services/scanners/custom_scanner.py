import os
import json
import logging
import subprocess
import tempfile
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Map Semgrep severity labels → canonical scanner severity
SEVERITY_MAP = {
    "ERROR": "HIGH",
    "WARNING": "MEDIUM",
    "INFO": "LOW",
}

# ---------------------------------------------------------------------------
# Inline Semgrep YAML rules — piped via stdin using --config -
# ---------------------------------------------------------------------------
CUSTOM_RULES_YAML = """\
rules:

  # 1. Server-Side Template Injection (SSTI) --------------------------------
  - id: custom-ssti-jinja2
    pattern-either:
      # Qualified inline
      - pattern: flask.render_template_string(flask.request.args.get(...), ...)
      - pattern: flask.render_template_string(flask.request.args[...], ...)
      - pattern: flask.render_template_string(flask.request.form.get(...), ...)
      - pattern: flask.render_template_string(flask.request.form[...], ...)
      - pattern: flask.render_template_string(flask.request.json.get(...), ...)
      - pattern: flask.render_template_string(flask.request.json[...], ...)
      - pattern: flask.render_template_string(flask.request.data, ...)
      # Unqualified inline
      - pattern: render_template_string(request.args.get(...), ...)
      - pattern: render_template_string(request.args[...], ...)
      - pattern: render_template_string(request.form.get(...), ...)
      - pattern: render_template_string(request.form[...], ...)
      - pattern: render_template_string(request.json.get(...), ...)
      - pattern: render_template_string(request.json[...], ...)
      - pattern: render_template_string(request.data, ...)
      # Qualified variable-assigned
      - patterns:
          - pattern: flask.render_template_string($TMPL, ...)
          - pattern-either:
              - pattern-inside: |
                  $TMPL = flask.request.args.get(...)
                  ...
              - pattern-inside: |
                  $TMPL = flask.request.args[...]
                  ...
              - pattern-inside: |
                  $TMPL = flask.request.form.get(...)
                  ...
              - pattern-inside: |
                  $TMPL = flask.request.form[...]
                  ...
              - pattern-inside: |
                  $TMPL = flask.request.json.get(...)
                  ...
              - pattern-inside: |
                  $TMPL = flask.request.json[...]
                  ...
              - pattern-inside: |
                  $TMPL = flask.request.data
                  ...
      # Unqualified variable-assigned
      - patterns:
          - pattern: render_template_string($TMPL, ...)
          - pattern-either:
              - pattern-inside: |
                  $TMPL = request.args.get(...)
                  ...
              - pattern-inside: |
                  $TMPL = request.args[...]
                  ...
              - pattern-inside: |
                  $TMPL = request.form.get(...)
                  ...
              - pattern-inside: |
                  $TMPL = request.form[...]
                  ...
              - pattern-inside: |
                  $TMPL = request.json.get(...)
                  ...
              - pattern-inside: |
                  $TMPL = request.json[...]
                  ...
              - pattern-inside: |
                  $TMPL = request.data
                  ...
    message: >
      Potential Server-Side Template Injection (SSTI): user-controlled input is
      passed directly to render_template_string(). An attacker can execute
      arbitrary Python code via Jinja2 template expressions.
    languages: [python]
    severity: ERROR
    metadata:
      category: security
      cwe: ["CWE-94"]

  # 2. ReDoS — nested quantifiers in regex  ---------------------------------
  - id: custom-redos-python
    patterns:
      - pattern-either:
          - pattern: re.compile($PAT)
          - pattern: re.match($PAT, ...)
          - pattern: re.search($PAT, ...)
          - pattern: re.fullmatch($PAT, ...)
      - metavariable-regex:
          metavariable: $PAT
          regex: '.*(\(.*[+*]\))[+*].*'
    message: >
      Potential Regular Expression Denial of Service (ReDoS): the regex
      pattern contains nested quantifiers (e.g. (a+)+ or (.*)*) that can
      cause catastrophic backtracking on adversarial input.
    languages: [python]
    severity: WARNING
    metadata:
      category: security
      cwe: ["CWE-1333"]

  - id: custom-redos-javascript
    patterns:
      - pattern-either:
          - pattern: new RegExp($PAT)
          - pattern: /$PAT/.test(...)
          - pattern: /$PAT/.exec(...)
      - metavariable-regex:
          metavariable: $PAT
          regex: '.*(\(.*[+*]\))[+*].*'
    message: >
      Potential Regular Expression Denial of Service (ReDoS): the regex
      pattern contains nested quantifiers (e.g. (a+)+ or (.*)*) that can
      cause catastrophic backtracking on adversarial input.
    languages: [javascript]
    severity: WARNING
    metadata:
      category: security
      cwe: ["CWE-1333"]

  # 3. Long Password DoS via bcrypt  ----------------------------------------
  - id: custom-long-password-dos-python
    patterns:
      - pattern-either:
          - pattern: bcrypt.hashpw($PWD, ...)
          - pattern: bcrypt.hash($PWD, ...)
          - pattern: $CTX.hash($PWD)
      - pattern-not-inside: |
          if len($PWD) > ...:
              ...
          ...
      - pattern-not-inside: |
          if len($PWD) < ...:
              ...
          ...
    message: >
      Potential Long Password DoS: bcrypt (or passlib) hash is called on a
      user-supplied value without a preceding length check. Extremely long
      passwords can cause the bcrypt operation to consume excessive CPU time.
    languages: [python]
    severity: WARNING
    metadata:
      category: security
      cwe: ["CWE-400"]

  - id: custom-long-password-dos-javascript
    patterns:
      - pattern-either:
          - pattern: bcrypt.hash($PWD, ...)
          - pattern: bcrypt.hashSync($PWD, ...)
      - pattern-not-inside: |
          if ($PWD.length > ...) { ... }
          ...
      - pattern-not-inside: |
          if ($PWD.length < ...) { ... }
          ...
    message: >
      Potential Long Password DoS: bcrypt.hash/hashSync is called without a
      preceding password length check, allowing denial-of-service via
      extremely long passwords.
    languages: [javascript]
    severity: WARNING
    metadata:
      category: security
      cwe: ["CWE-400"]

  # 4. AWS S3 Secret Exposure  ----------------------------------------------
  - id: custom-aws-hardcoded-key-python
    patterns:
      - pattern-either:
          - pattern: boto3.client($SVC, aws_access_key_id="...", aws_secret_access_key="...", ...)
          - pattern: boto3.resource($SVC, aws_access_key_id="...", aws_secret_access_key="...", ...)
          - pattern: boto3.Session(aws_access_key_id="...", aws_secret_access_key="...", ...)
    message: >
      Hardcoded AWS credentials detected. Never embed aws_access_key_id or
      aws_secret_access_key as string literals; use IAM roles, environment
      variables, or AWS Secrets Manager instead.
    languages: [python]
    severity: ERROR
    metadata:
      category: security
      cwe: ["CWE-798"]

  - id: custom-aws-hardcoded-key-js
    patterns:
      - pattern-either:
          - pattern: |
              new AWS.S3({accessKeyId: "...", secretAccessKey: "...", ...})
          - pattern: |
              new S3Client({credentials: {accessKeyId: "...", secretAccessKey: "..."}, ...})
    message: >
      Hardcoded AWS credentials detected in JavaScript/TypeScript. Use
      environment variables or instance-profile credentials instead.
    languages: [javascript, typescript]
    severity: ERROR
    metadata:
      category: security
      cwe: ["CWE-798"]

  - id: custom-aws-key-literal
    pattern-regex: 'AKIA[0-9A-Z]{16}'
    message: >
      AWS Access Key ID pattern (AKIA...) found in source code. Remove and
      rotate this credential immediately.
    languages: [python, javascript, typescript]
    severity: ERROR
    metadata:
      category: security
      cwe: ["CWE-798"]

  # 5. NoSQL Injection  -----------------------------------------------------
  - id: custom-nosql-injection-python
    patterns:
      - pattern-either:
          - pattern: '$COL.find({"$KEY": flask.request.args.get(...)})'
          - pattern: '$COL.find({"$KEY": flask.request.args[...]})'
          - pattern: '$COL.find({"$KEY": flask.request.json.get(...)})'
          - pattern: '$COL.find({"$KEY": flask.request.json[...]})'
          - pattern: '$COL.find_one({"$KEY": flask.request.args.get(...)})'
          - pattern: '$COL.find_one({"$KEY": flask.request.json.get(...)})'
          - pattern: '$COL.update_one({"$KEY": flask.request.args.get(...)}, ...)'
          - pattern: '$COL.update_one({"$KEY": flask.request.json.get(...)}, ...)'
          - pattern: '$COL.delete_one({"$KEY": flask.request.args.get(...)})'
          - pattern: '$COL.delete_one({"$KEY": flask.request.json.get(...)})'
    message: >
      Potential NoSQL Injection: a MongoDB query is constructed using
      unsanitised user input from the request. An attacker can manipulate
      the query by injecting MongoDB operators (e.g. {"$gt": ""}).
    languages: [python]
    severity: ERROR
    metadata:
      category: security
      cwe: ["CWE-943"]

  - id: custom-nosql-injection-javascript
    patterns:
      - pattern-either:
          - pattern: '$COL.find({$KEY: req.query.$VAL})'
          - pattern: '$COL.find({$KEY: req.body.$VAL})'
          - pattern: '$COL.findOne({$KEY: req.query.$VAL})'
          - pattern: '$COL.findOne({$KEY: req.body.$VAL})'
          - pattern: '$COL.updateOne({$KEY: req.query.$VAL}, ...)'
          - pattern: '$COL.updateOne({$KEY: req.body.$VAL}, ...)'
          - pattern: '$COL.deleteOne({$KEY: req.query.$VAL})'
          - pattern: '$COL.deleteOne({$KEY: req.body.$VAL})'
    message: >
      Potential NoSQL Injection: a MongoDB query is constructed using
      unsanitised request data. Validate and sanitise all query fields
      before passing them to MongoDB operations.
    languages: [javascript]
    severity: ERROR
    metadata:
      category: security
      cwe: ["CWE-943"]

  # 6. Clipboard Hijacking  -------------------------------------------------
  - id: custom-clipboard-hijacking
    pattern-either:
      - pattern: document.addEventListener('copy', ...)
      - pattern: document.addEventListener('paste', ...)
      - pattern: document.addEventListener("copy", ...)
      - pattern: document.addEventListener("paste", ...)
      - pattern: $EV.clipboardData.setData(...)
      - pattern: window.clipboardData.setData(...)
    message: >
      Clipboard event listener or clipboardData.setData() detected. Overriding
      copy/paste behaviour can be used for clipboard hijacking, silently
      replacing content the user copies. Review whether this is intentional.
    languages: [javascript, typescript]
    severity: INFO
    metadata:
      category: security
      cwe: ["CWE-356"]

  # 7. Login Replay Attack — JWT without exp / session without TTL  ----------
  - id: custom-jwt-no-exp-python
    patterns:
      - pattern-either:
          - pattern: jwt.encode($PAYLOAD, ...)
      - pattern-not-inside: |
          $PAYLOAD = {..., "exp": ..., ...}
          ...
      - pattern-not-inside: |
          $PAYLOAD["exp"] = ...
          ...
          jwt.encode($PAYLOAD, ...)
          ...
    message: >
      JWT token is created without an 'exp' (expiration) claim. Tokens without
      expiry are valid indefinitely, enabling replay attacks after credential
      compromise. Always include an expiration time.
    languages: [python]
    severity: WARNING
    metadata:
      category: security
      cwe: ["CWE-613"]

  - id: custom-jwt-no-exp-javascript
    patterns:
      - pattern: jwt.sign($PAYLOAD, $SECRET)
      - pattern-not: 'jwt.sign($PAYLOAD, $SECRET, {expiresIn: ...})'
      - pattern-not: 'jwt.sign($PAYLOAD, $SECRET, {..., expiresIn: ..., ...})'
    message: >
      jwt.sign() called without an expiresIn option. Tokens without expiry are
      valid indefinitely, enabling replay attacks. Pass {expiresIn: '...'} as
      the options argument.
    languages: [javascript]
    severity: WARNING
    metadata:
      category: security
      cwe: ["CWE-613"]
"""


def scan_custom(repo_path: str) -> Dict[str, Any]:
    """
    Scans a repository for seven custom vulnerability classes using inline
    Semgrep rules passed via stdin (--config -).

    Vulnerability classes detected:
      1. Server-Side Template Injection (SSTI)        — HIGH
      2. Regular Expression DoS (ReDoS)               — MEDIUM
      3. Long Password DoS via bcrypt                 — MEDIUM
      4. AWS S3 / IAM secret exposure                 — HIGH
      5. NoSQL Injection                              — HIGH
      6. Clipboard Hijacking                          — LOW
      7. Login Replay Attack (JWT / session no TTL)   — MEDIUM

    Args:
        repo_path: Absolute path to the cloned repository to scan.

    Returns:
        dict: Structured result with tool, status, findings_count, findings,
              and error. Always returns this dict — never raises.
    """
    result: Dict[str, Any] = {
        "tool": "custom",
        "status": "failed",
        "findings_count": 0,
        "findings": [],
        "error": None,
    }

    try:
        logger.info(f"Starting custom Semgrep scan on {repo_path}")

        # Write CUSTOM_RULES_YAML to a named temp file
        temp_file = tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False)
        try:
            temp_file.write(CUSTOM_RULES_YAML)
            temp_file.close()

            process = subprocess.run(
                [
                    "semgrep", "scan", repo_path,
                    "--config", temp_file.name,
                    "--json",
                    "--quiet",
                    "--timeout", "30",
                    "--exclude", "node_modules",
                    "--exclude", "*.lock",
                    "--exclude", ".next",
                    "--exclude", "dist",
                    "--exclude", "build",
                    "--exclude", "__pycache__",
                    "--exclude", "*.min.js",
                ],
                capture_output=True,
                text=True,
                timeout=90,
            )
        finally:
            try:
                os.unlink(temp_file.name)
            except Exception as e:
                logger.warning(f"Failed to delete temp file {temp_file.name}: {e}")

        try:
            output = json.loads(process.stdout)
        except json.JSONDecodeError:
            logger.error(
                f"Failed to parse custom scanner JSON output. "
                f"stderr: {process.stderr[:500]}"
            )
            result["error"] = "Failed to parse custom scanner output as JSON"
            return result

        errors = output.get("errors", [])
        if errors:
            for err in errors:
                logger.warning(f"Custom scanner reported error: {err}")

        results_list = output.get("results", [])

        # Normalise repo_path so prefix-stripping works consistently
        repo_prefix = repo_path.rstrip(os.sep) + os.sep

        for item in results_list:
            raw_severity = item.get("extra", {}).get("severity", "")
            mapped_severity = SEVERITY_MAP.get(raw_severity, "LOW")

            raw_path = item.get("path", "")
            relative_path = (
                raw_path[len(repo_prefix):]
                if raw_path.startswith(repo_prefix)
                else raw_path
            )

            metadata = item.get("extra", {}).get("metadata", {})

            finding = {
                "severity": mapped_severity,
                "rule_id": item.get("check_id", "unknown"),
                "message": item.get("extra", {}).get("message", ""),
                "file": relative_path,
                "line_start": item.get("start", {}).get("line", 0),
                "line_end": item.get("end", {}).get("line", 0),
                "category": metadata.get("category", "security"),
                "cwe": metadata.get("cwe", []),
            }
            result["findings"].append(finding)

        result["status"] = "completed"
        result["findings_count"] = len(result["findings"])
        logger.info(
            f"Custom scanner completed. Found {result['findings_count']} issues."
        )

    except subprocess.TimeoutExpired:
        logger.error(f"Custom scanner timed out for {repo_path}")
        result["error"] = "Custom scanner timed out after 90 seconds"
    except FileNotFoundError:
        logger.error("Semgrep binary not found for custom scanner")
        result["error"] = "semgrep binary not found or not installed"
    except Exception as e:
        logger.error(f"Unexpected error in custom scanner: {e}")
        result["error"] = str(e)

    return result
