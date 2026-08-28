"""A small, dependency-free parser for unified diff text (the output of
`git diff`, `git show`, or a saved `.patch`/`.diff` file).

This does not aim to be a fully general unified-diff parser — it covers
what `git diff` actually emits, which is what the rest of this tool
consumes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

FILE_HEADER_RE = re.compile(r"^diff --git a/(.*) b/(.*)$")
OLD_PATH_RE = re.compile(r"^--- (?:a/(.*)|/dev/null)$")
NEW_PATH_RE = re.compile(r"^\+\+\+ (?:b/(.*)|/dev/null)$")
HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")
BINARY_RE = re.compile(r"^Binary files (a/.*|/dev/null) and (b/.*|/dev/null) differ$")
RENAME_FROM_RE = re.compile(r"^rename from (.*)$")
RENAME_TO_RE = re.compile(r"^rename to (.*)$")
NEW_FILE_MODE_RE = re.compile(r"^new file mode")
DELETED_FILE_MODE_RE = re.compile(r"^deleted file mode")


@dataclass
class AddedLine:
    line_no: int
    text: str


@dataclass
class FileDiff:
    old_path: str | None
    new_path: str | None
    is_binary: bool = False
    is_new_file: bool = False
    is_deleted_file: bool = False
    is_rename: bool = False
    added_lines: list[AddedLine] = field(default_factory=list)
    removed_line_count: int = 0
    added_line_count: int = 0

    @property
    def path(self) -> str:
        """The most relevant path to display: new path, falling back to old."""
        return self.new_path or self.old_path or "<unknown>"


def parse_diff(text: str) -> list[FileDiff]:
    """Parse unified diff text into a list of FileDiff objects."""
    lines = text.splitlines()
    files: list[FileDiff] = []
    current: FileDiff | None = None
    new_line_cursor = 0

    i = 0
    while i < len(lines):
        line = lines[i]

        header_match = FILE_HEADER_RE.match(line)
        if header_match:
            if current is not None:
                files.append(current)
            old_p, new_p = header_match.groups()
            current = FileDiff(old_path=old_p, new_path=new_p)
            i += 1
            continue

        if current is None:
            i += 1
            continue

        if NEW_FILE_MODE_RE.match(line):
            current.is_new_file = True
            i += 1
            continue

        if DELETED_FILE_MODE_RE.match(line):
            current.is_deleted_file = True
            i += 1
            continue

        rename_from = RENAME_FROM_RE.match(line)
        if rename_from:
            current.is_rename = True
            current.old_path = rename_from.group(1)
            i += 1
            continue

        rename_to = RENAME_TO_RE.match(line)
        if rename_to:
            current.is_rename = True
            current.new_path = rename_to.group(1)
            i += 1
            continue

        binary_match = BINARY_RE.match(line)
        if binary_match:
            current.is_binary = True
            i += 1
            continue

        old_path_match = OLD_PATH_RE.match(line)
        if old_path_match:
            if old_path_match.group(1):
                current.old_path = old_path_match.group(1)
            else:
                current.old_path = None
            i += 1
            continue

        new_path_match = NEW_PATH_RE.match(line)
        if new_path_match:
            if new_path_match.group(1):
                current.new_path = new_path_match.group(1)
            else:
                current.new_path = None
            i += 1
            continue

        hunk_match = HUNK_HEADER_RE.match(line)
        if hunk_match:
            new_line_cursor = int(hunk_match.group(2))
            i += 1
            continue

        if line.startswith("+") and not line.startswith("+++"):
            current.added_lines.append(AddedLine(line_no=new_line_cursor, text=line[1:]))
            current.added_line_count += 1
            new_line_cursor += 1
            i += 1
            continue

        if line.startswith("-") and not line.startswith("---"):
            current.removed_line_count += 1
            i += 1
            continue

        if line.startswith(" "):
            new_line_cursor += 1
            i += 1
            continue

        i += 1

    if current is not None:
        files.append(current)

    return files
