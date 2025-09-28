from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _extract_error_line(lines: list[str]) -> str:
    for line in lines:
        if line.startswith("E   "):
            return line.strip()
    for line in reversed(lines):
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def main() -> int:
    log_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("pytest.log")
    log_text = log_path.read_text(errors="ignore") if log_path.exists() else ""
    lines = log_text.splitlines()

    error_line = _extract_error_line(lines)
    excerpt_lines = [line.rstrip() for line in lines[-20:]]

    package = os.environ.get("PACKAGE_UNDER_TEST", "")
    version = os.environ.get("PACKAGE_VERSION", "")

    run_url = (
        f"{os.environ.get('GITHUB_SERVER_URL', '')}/"
        f"{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/"
        f"{os.environ.get('GITHUB_RUN_ID', '')}"
    )

    payload = {
        "workflow": os.environ.get("GITHUB_WORKFLOW"),
        "job": os.environ.get("GITHUB_JOB"),
        "matrix_label": f"{package}=={version}".strip("="),
        "package": package,
        "version": version,
        "run_url": run_url,
        "error_line": error_line,
        "log_excerpt": "\n".join(excerpt_lines),
    }

    Path("failure.json").write_text(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
