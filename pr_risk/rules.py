"""Heuristic risk rules evaluated against a parsed diff.

Each rule looks at the list of `FileDiff` objects and produces zero or
more `Finding`s. Rules are intentionally simple and explainable — the goal
is to catch the handful of PR-diff mistakes that come up over and over
(a secret pasted into a config change, an entire `node_modules/` committed
by accident, a large behavioral change with no accompanying test) rather
than to be a general static analyzer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from .diff_parser import FileDiff

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@dataclass
class Finding:
    severity: str  # low | medium | high | critical
    category: str
    file: str
    message: str
    line: int | None = None

    def __str__(self) -> str:  # pragma: no cover - trivial
        loc = f":{self.line}" if self.line else ""
        return f"[{self.severity.upper()}] {self.file}{loc} — {self.message} ({self.category})"


# --- secrets -----------------------------------------------------------

SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "AWS Access Key ID": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Generic private key block": re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "Stripe secret key": re.compile(r"\bsk_live_[A-Za-z0-9]{16,}\b"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"),
    "Connection string with credentials": re.compile(
        r"(?i)(mongodb(\+srv)?|postgres(ql)?|mysql|redis)://[^\s:/]+:[^\s@/]+@"
    ),
    "Hardcoded secret assignment": re.compile(
        r"(?i)(jwt|api|db|database)[_-]?(secret|key|password|pwd)\s*[=:]\s*['\"][^'\"\s]{8,}['\"]"
    ),
}


def rule_secrets_added(files: list[FileDiff]) -> list[Finding]:
    findings: list[Finding] = []
    for f in files:
        if f.is_binary:
            continue
        for added in f.added_lines:
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(added.text):
                    findings.append(
                        Finding(
                            severity="critical",
                            category="secret",
                            file=f.path,
                            line=added.line_no,
                            message=f"possible {label} added",
                        )
                    )
    return findings


# --- vendored / generated directories ----------------------------------

VENDORED_DIR_MARKERS = (
    "node_modules/",
    "vendor/",
    "dist/",
    "build/",
    ".venv/",
    "venv/",
    "__pycache__/",
    "target/",  # rust/java build output
)


def rule_vendored_dirs(files: list[FileDiff]) -> list[Finding]:
    findings: list[Finding] = []
    hits: dict[str, int] = {}
    for f in files:
        if not (f.is_new_file or f.old_path is None):
            continue
        for marker in VENDORED_DIR_MARKERS:
            if marker in f.path:
                hits[marker] = hits.get(marker, 0) + 1
                break

    for marker, count in hits.items():
        if count >= 5:
            findings.append(
                Finding(
                    severity="high",
                    category="vendored-commit",
                    file=f"{marker}*",
                    message=(
                        f"{count} new files committed under '{marker}' — looks like a "
                        "vendored/build directory got committed by accident. Add it to "
                        ".gitignore instead."
                    ),
                )
            )
    return findings


# --- large / binary files ----------------------------------------------

LARGE_DIFF_LINE_THRESHOLD = 800  # added+removed lines in one file
LARGE_PR_LINE_THRESHOLD = 2000  # added+removed lines across the whole diff
MANY_FILES_THRESHOLD = 40


def rule_binary_files(files: list[FileDiff]) -> list[Finding]:
    return [
        Finding(
            severity="medium",
            category="binary-file",
            file=f.path,
            message="binary file added/changed — can't be reviewed as a diff; confirm it belongs in version control.",
        )
        for f in files
        if f.is_binary
    ]


def rule_oversized_diff(files: list[FileDiff]) -> list[Finding]:
    findings: list[Finding] = []

    for f in files:
        total = f.added_line_count + f.removed_line_count
        if total > LARGE_DIFF_LINE_THRESHOLD:
            findings.append(
                Finding(
                    severity="medium",
                    category="large-file-diff",
                    file=f.path,
                    message=f"{total} lines changed in a single file — consider splitting this change.",
                )
            )

    total_lines = sum(f.added_line_count + f.removed_line_count for f in files)
    if total_lines > LARGE_PR_LINE_THRESHOLD:
        findings.append(
            Finding(
                severity="medium",
                category="large-pr",
                file="<entire diff>",
                message=(
                    f"{total_lines} total lines changed across the diff — large PRs are "
                    "harder to review carefully and more likely to hide a real issue."
                ),
            )
        )

    if len(files) > MANY_FILES_THRESHOLD:
        findings.append(
            Finding(
                severity="low",
                category="many-files",
                file="<entire diff>",
                message=f"{len(files)} files touched — consider whether this should be multiple PRs.",
            )
        )

    return findings


# --- missing tests -------------------------------------------------------

SOURCE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt",
    ".rb", ".c", ".cpp", ".cs", ".swift", ".php",
}

NON_TESTABLE_HINTS = (
    "migrations/", "__init__.py", "config", "settings", ".d.ts",
    "types.ts", "constants",
)


def _is_test_path(path: str) -> bool:
    p = path.lower()
    name = PurePosixPath(p).name
    return (
        "/test" in p
        or "/tests/" in p
        or "/__tests__/" in p
        or "/spec/" in p
        or name.startswith("test_")
        or "_test." in name
        or ".test." in name
        or ".spec." in name
    )


def _is_testable_source(path: str) -> bool:
    p = PurePosixPath(path)
    if p.suffix.lower() not in SOURCE_EXTENSIONS:
        return False
    if _is_test_path(path):
        return False
    lower = path.lower()
    return not any(hint in lower for hint in NON_TESTABLE_HINTS)


def rule_missing_tests(files: list[FileDiff]) -> list[Finding]:
    changed_source = [f for f in files if not f.is_binary and _is_testable_source(f.path)]
    touched_tests = any(_is_test_path(f.path) for f in files)

    if changed_source and not touched_tests:
        substantial = [f for f in changed_source if (f.added_line_count + f.removed_line_count) >= 8]
        if substantial:
            files_list = ", ".join(f.path for f in substantial[:5])
            more = "" if len(substantial) <= 5 else f" (+{len(substantial) - 5} more)"
            return [
                Finding(
                    severity="medium",
                    category="missing-tests",
                    file="<entire diff>",
                    message=(
                        f"{len(substantial)} source file(s) changed with no test file touched "
                        f"in the same diff: {files_list}{more}."
                    ),
                )
            ]
    return []


ALL_RULES = [
    rule_secrets_added,
    rule_vendored_dirs,
    rule_binary_files,
    rule_oversized_diff,
    rule_missing_tests,
]


def run_all_rules(files: list[FileDiff]) -> list[Finding]:
    findings: list[Finding] = []
    for rule in ALL_RULES:
        findings.extend(rule(files))
    findings.sort(key=lambda f: -SEVERITY_ORDER.get(f.severity, 0))
    return findings
