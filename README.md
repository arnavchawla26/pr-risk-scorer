# pr-risk-scorer

A small, dependency-free CLI that scores a `git diff` / PR patch for risk
*before* it's merged — the kind of pass a careful reviewer does by eye:
did someone paste a secret into a config change, did an entire
`node_modules/` get committed by accident, is this a 2,000-line diff that
nobody's going to review carefully, did the source change land with zero
accompanying test.

It reuses the same secret-detection approach as
[repo-health-auditor](https://github.com/arnavchawla26/repo-health-auditor),
applied to *added diff lines* instead of a whole checked-out tree, so it
can run as a pre-commit hook or a CI gate on just the lines someone is
about to introduce.

## What it checks

| Rule | Severity | What it catches |
| --- | --- | --- |
| Secrets added | critical | AWS/GitHub/Slack/Stripe/Google key shapes, private key blocks, connection strings with embedded credentials, and generic hardcoded secret assignments — in *added* lines only |
| Vendored directory committed | high | 5+ new files landing under `node_modules/`, `vendor/`, `dist/`, `build/`, `venv/`, `target/`, etc. in one diff — the classic "forgot to `.gitignore`" mistake |
| Binary file changed | medium | Binary files can't be reviewed as a diff; flagged so a human confirms it belongs in version control |
| Oversized diff | medium/low | A single file with 800+ changed lines, a diff with 2,000+ total changed lines, or 40+ files touched in one PR |
| Missing tests | medium | 8+ lines changed in source file(s) with no test file touched anywhere in the same diff |

Any **critical** finding (a likely secret) forces the overall risk level to
`critical` regardless of everything else — a leaked credential outweighs
every other signal in the diff.

## Installation

```bash
git clone https://github.com/arnavchawla26/pr-risk-scorer.git
cd pr-risk-scorer
pip install -e .
```

Python 3.9+, no runtime dependencies (pytest is dev-only).

## Usage

Score a diff already on disk:

```bash
pr-risk my-change.patch
```

Score a live git diff by piping it in:

```bash
git diff main...HEAD | pr-risk
```

Or let it run `git diff` for you:

```bash
pr-risk --git-range main...HEAD
```

Example output:

```
Risk score: 80/100 (critical)
Files changed: 1  (+1 / -1 lines)

Findings (2):
  - [CRITICAL] a.py:1 — possible AWS Access Key ID added (secret)
  - [CRITICAL] a.py:1 — possible Hardcoded secret assignment added (secret)
```

Structured output for scripting:

```bash
pr-risk --git-range HEAD~1 --json
```

Use it as a CI/pre-push gate:

```bash
pr-risk --git-range origin/main...HEAD --fail-over 40
```

`--fail-over 40` exits 1 (failing the job) if the risk score is 40 or
above (i.e. "high" or "critical").

## Library usage

```python
from pr_risk.scorer import score_diff_text

diff_text = open("my-change.patch").read()
report = score_diff_text(diff_text)

print(report.risk_score, report.risk_level)
for finding in report.findings:
    print(finding)
```

## Scoring model

Each finding has a severity (`low`/`medium`/`high`/`critical`) that adds a
fixed penalty (3/10/20/40) to a 0–100 risk score, capped at 100. Any
critical finding overrides the numeric score for the risk *level* — the
score still reflects how many things were flagged, but the label always
reads `critical` if a likely secret is present, so it can't get diluted by
a large otherwise-clean diff.

## Running the tests

```bash
pip install -e ".[dev]"  # or: pip install pytest -e .
pytest
```

23 tests covering the unified-diff parser (modifications, new files,
binary files, renames, multi-file diffs), each risk rule in isolation, the
aggregate scorer (including the critical-overrides-level behavior), and
the CLI (stdin, file input, `--json`, `--fail-over`).

## Design notes

- **No dependencies, no network calls.** It parses `git diff` output
  directly rather than depending on a diff-parsing library or shelling out
  to anything beyond `git` itself (and only when `--git-range` is used).
- **Operates on added lines, not the whole file.** This is deliberately
  narrower than a full repo secret scan (see repo-health-auditor for
  that) — the point here is catching what a *specific change* introduces,
  which is the right scope for a pre-merge gate.
- **Heuristic, not exhaustive.** False negatives are possible (a
  cleverly-obfuscated secret won't match a regex) and rare false positives
  are possible too (a config value that happens to look key-shaped). It's
  a fast first pass, not a substitute for a dedicated secret-scanning
  service on a high-stakes repo.
