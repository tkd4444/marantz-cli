#!/usr/bin/env python3
"""Dependency-free source syntax, local documentation links and hygiene checks.

This targeted scan is not a substitute for reviewing Git history or secret scans.
"""
import ast
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = [ROOT / name for name in (
    "README.md", "CONTRIBUTING.md", "CHANGELOG.md", "SECURITY.md", "LICENSING.md",
    "install.sh", "uninstall.sh", ".gitignore",
)]
for directory in ("bin", "libexec", "man", "docs", "tests", ".github"):
    PUBLIC.extend(path for path in (ROOT / directory).rglob("*") if path.is_file()
                  and "__pycache__" not in path.parts)

REQUIRED = ("docs/COMPATIBILITY.md", "docs/RELEASE_READINESS.md",
            ".github/workflows/ci.yml", ".github/ISSUE_TEMPLATE/bug_report.md",
            ".github/ISSUE_TEMPLATE/compatibility_report.md")
for name in REQUIRED:
    if not (ROOT / name).is_file():
        raise SystemExit("Missing public-release file: " + name)

private_patterns = (
    r"/(?:Users|home)/[^/\s]+/",  # absolute private home paths, not ~/ examples
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    r"\bgh[pousr]_[A-Za-z0-9]{30,}\b",
    r"\bAKIA[0-9A-Z]{16}\b",
)
for path in PUBLIC:
    text = path.read_text(encoding="utf-8")
    relative = path.relative_to(ROOT)
    if any(re.search(pattern, text) for pattern in private_patterns):
        raise SystemExit("Potential private material in " + str(relative))
    if any(line.rstrip(" \t") != line for line in text.splitlines()):
        raise SystemExit("Trailing whitespace in " + str(relative))
    if path.suffix == ".py":
        ast.parse(text, filename=str(relative))
    if path.suffix == ".md":
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            if "://" in target or target.startswith("#"):
                continue
            local = target.split("#", 1)[0]
            if not (path.parent / local).is_file():
                raise SystemExit("Broken local link in {}: {}".format(relative, target))
print("Public-file syntax, local links and targeted hygiene checks: OK")
