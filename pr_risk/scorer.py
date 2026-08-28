"""Aggregate rule findings into a single risk report."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from .diff_parser import FileDiff, parse_diff
from .rules import Finding, run_all_rules

SEVERITY_PENALTY = {"low": 3, "medium": 10, "high": 20, "critical": 40}


@dataclass
class RiskReport:
    files_changed: int
    lines_added: int
    lines_removed: int
    findings: list[Finding] = field(default_factory=list)
    risk_score: int = 0  # 0 (no risk) - 100 (critical)
    risk_level: str = "low"

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


def _risk_level_for(score: int, has_critical_finding: bool) -> str:
    # Any critical-severity finding (a likely secret) makes the whole diff
    # "critical" regardless of how the rest of the score adds up — one
    # leaked credential outweighs everything else in the diff.
    if has_critical_finding:
        return "critical"
    if score >= 40:
        return "high"
    if score >= 15:
        return "medium"
    return "low"


def score_files(files: list[FileDiff]) -> RiskReport:
    findings = run_all_rules(files)

    score = 0
    for finding in findings:
        score += SEVERITY_PENALTY.get(finding.severity, 0)
    score = min(score, 100)

    has_critical = any(f.severity == "critical" for f in findings)

    return RiskReport(
        files_changed=len(files),
        lines_added=sum(f.added_line_count for f in files),
        lines_removed=sum(f.removed_line_count for f in files),
        findings=findings,
        risk_score=score,
        risk_level=_risk_level_for(score, has_critical),
    )


def score_diff_text(diff_text: str) -> RiskReport:
    files = parse_diff(diff_text)
    return score_files(files)


def format_text_report(report: RiskReport) -> str:
    lines = [
        f"Risk score: {report.risk_score}/100 ({report.risk_level})",
        f"Files changed: {report.files_changed}  "
        f"(+{report.lines_added} / -{report.lines_removed} lines)",
        "",
    ]
    if not report.findings:
        lines.append("No risk findings.")
    else:
        lines.append(f"Findings ({len(report.findings)}):")
        for finding in report.findings:
            lines.append(f"  - {finding}")
    return "\n".join(lines)
