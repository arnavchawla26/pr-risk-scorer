from pr_risk.diff_parser import parse_diff
from pr_risk.rules import (
    rule_binary_files,
    rule_missing_tests,
    rule_oversized_diff,
    rule_secrets_added,
    rule_vendored_dirs,
)

SECRET_DIFF = """\
diff --git a/config.py b/config.py
index 1111111..2222222 100644
--- a/config.py
+++ b/config.py
@@ -1,1 +1,2 @@
 import os
+AWS_KEY = "AKIAABCDEFGHIJKLMNOP"
"""

CONN_STRING_DIFF = """\
diff --git a/db.py b/db.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/db.py
@@ -0,0 +1,1 @@
+MONGO_URI = "mongodb+srv://admin:leaked123@cluster0.mongodb.net/prod"
"""

CLEAN_DIFF = """\
diff --git a/utils.py b/utils.py
index 1111111..2222222 100644
--- a/utils.py
+++ b/utils.py
@@ -1,2 +1,3 @@
 def f():
     return 1
+# just a comment
"""


def _new_file_diff(path: str, n_lines: int) -> str:
    body = "\n".join(f"+line {i}" for i in range(n_lines))
    return (
        f"diff --git a/{path} b/{path}\n"
        f"new file mode 100644\n"
        f"index 0000000..1234567\n"
        f"--- /dev/null\n"
        f"+++ b/{path}\n"
        f"@@ -0,0 +1,{n_lines} @@\n"
        f"{body}\n"
    )


def test_detects_secret_in_new_line():
    files = parse_diff(SECRET_DIFF)
    findings = rule_secrets_added(files)
    assert len(findings) == 1
    assert findings[0].severity == "critical"
    assert findings[0].file == "config.py"


def test_detects_connection_string_secret():
    files = parse_diff(CONN_STRING_DIFF)
    findings = rule_secrets_added(files)
    assert any("Connection string" in f.message for f in findings)


def test_clean_diff_has_no_secret_findings():
    files = parse_diff(CLEAN_DIFF)
    assert rule_secrets_added(files) == []


def test_vendored_dir_bulk_commit_flagged():
    diff = "".join(_new_file_diff(f"node_modules/pkg{i}/index.js", 3) for i in range(6))
    files = parse_diff(diff)
    findings = rule_vendored_dirs(files)
    assert len(findings) == 1
    assert findings[0].severity == "high"


def test_single_vendored_file_not_flagged():
    diff = _new_file_diff("node_modules/pkg/index.js", 3)
    files = parse_diff(diff)
    assert rule_vendored_dirs(files) == []


def test_binary_file_flagged():
    diff = (
        "diff --git a/image.png b/image.png\n"
        "new file mode 100644\n"
        "index 0000000..1234567\n"
        "Binary files /dev/null and b/image.png differ\n"
    )
    files = parse_diff(diff)
    findings = rule_binary_files(files)
    assert len(findings) == 1
    assert findings[0].severity == "medium"


def test_oversized_single_file_diff_flagged():
    diff = _new_file_diff("big.py", 900)
    files = parse_diff(diff)
    findings = rule_oversized_diff(files)
    assert any(f.category == "large-file-diff" for f in findings)


def test_many_files_flagged():
    diff = "".join(_new_file_diff(f"file{i}.py", 2) for i in range(45))
    files = parse_diff(diff)
    findings = rule_oversized_diff(files)
    assert any(f.category == "many-files" for f in findings)


def test_missing_tests_flagged_for_substantial_source_change():
    diff = _new_file_diff("src/feature.py", 20)
    files = parse_diff(diff)
    findings = rule_missing_tests(files)
    assert len(findings) == 1
    assert findings[0].category == "missing-tests"


def test_missing_tests_not_flagged_when_test_touched():
    diff = _new_file_diff("src/feature.py", 20) + _new_file_diff("tests/test_feature.py", 10)
    files = parse_diff(diff)
    assert rule_missing_tests(files) == []


def test_missing_tests_not_flagged_for_trivial_change():
    diff = _new_file_diff("src/feature.py", 3)
    files = parse_diff(diff)
    assert rule_missing_tests(files) == []
