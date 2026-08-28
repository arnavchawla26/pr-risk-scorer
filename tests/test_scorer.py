import json
import subprocess
import sys
from pathlib import Path

from pr_risk.scorer import score_diff_text

CLEAN_DIFF = """\
diff --git a/utils.py b/utils.py
index 1111111..2222222 100644
--- a/utils.py
+++ b/utils.py
@@ -1,2 +1,3 @@
 def f():
     return 1
+# comment
"""

SECRET_DIFF = """\
diff --git a/config.py b/config.py
index 1111111..2222222 100644
--- a/config.py
+++ b/config.py
@@ -1,1 +1,2 @@
 import os
+AWS_KEY = "AKIA0000000000000000"
"""


def test_clean_diff_scores_low_risk():
    report = score_diff_text(CLEAN_DIFF)
    assert report.risk_score < 15
    assert report.risk_level == "low"


def test_secret_diff_scores_critical():
    report = score_diff_text(SECRET_DIFF)
    assert report.risk_level == "critical"
    assert report.risk_score >= 40


def test_report_to_json_round_trips():
    report = score_diff_text(SECRET_DIFF)
    payload = json.loads(report.to_json())
    assert payload["risk_level"] == "critical"
    assert payload["findings"][0]["category"] == "secret"


def _run_cli(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pr_risk.cli", *args],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parent.parent),
    )


def test_cli_reads_from_stdin():
    result = _run_cli(stdin=CLEAN_DIFF)
    assert result.returncode == 0
    assert "Risk score" in result.stdout


def test_cli_reads_from_file(tmp_path: Path):
    diff_file = tmp_path / "change.diff"
    diff_file.write_text(SECRET_DIFF)

    result = _run_cli(str(diff_file), "--fail-over", "40")

    assert result.returncode == 1
    assert "critical" in result.stdout


def test_cli_json_flag(tmp_path: Path):
    diff_file = tmp_path / "change.diff"
    diff_file.write_text(CLEAN_DIFF)

    result = _run_cli(str(diff_file), "--json")

    payload = json.loads(result.stdout)
    assert "risk_score" in payload
