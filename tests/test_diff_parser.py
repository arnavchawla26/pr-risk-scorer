from pr_risk.diff_parser import parse_diff

SIMPLE_DIFF = """\
diff --git a/app.py b/app.py
index 1234567..89abcde 100644
--- a/app.py
+++ b/app.py
@@ -1,3 +1,4 @@
 def hello():
-    return "hi"
+    return "hello"
+
 hello()
"""

NEW_FILE_DIFF = """\
diff --git a/new_module.py b/new_module.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/new_module.py
@@ -0,0 +1,2 @@
+def add(a, b):
+    return a + b
"""

BINARY_DIFF = """\
diff --git a/logo.png b/logo.png
new file mode 100644
index 0000000..abcdef1
Binary files /dev/null and b/logo.png differ
"""

RENAME_DIFF = """\
diff --git a/old_name.py b/new_name.py
similarity index 100%
rename from old_name.py
rename to new_name.py
"""


def test_parses_simple_modification():
    files = parse_diff(SIMPLE_DIFF)
    assert len(files) == 1
    f = files[0]
    assert f.path == "app.py"
    assert f.added_line_count == 2
    assert f.removed_line_count == 1
    assert not f.is_binary


def test_parses_new_file_with_correct_line_numbers():
    files = parse_diff(NEW_FILE_DIFF)
    f = files[0]
    assert f.is_new_file
    assert f.old_path is None
    assert [a.line_no for a in f.added_lines] == [1, 2]
    assert f.added_lines[0].text == "def add(a, b):"


def test_parses_binary_file():
    files = parse_diff(BINARY_DIFF)
    f = files[0]
    assert f.is_binary
    assert f.added_line_count == 0


def test_parses_rename():
    files = parse_diff(RENAME_DIFF)
    f = files[0]
    assert f.is_rename
    assert f.old_path == "old_name.py"
    assert f.new_path == "new_name.py"


def test_multiple_files_in_one_diff():
    combined = SIMPLE_DIFF + NEW_FILE_DIFF
    files = parse_diff(combined)
    assert len(files) == 2
    assert files[0].path == "app.py"
    assert files[1].path == "new_module.py"


def test_empty_diff_returns_no_files():
    assert parse_diff("") == []
