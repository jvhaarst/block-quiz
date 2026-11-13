"""Hunk bodies are read by the @@ line counts, not by what a line looks like."""

import change_map


def diff(*lines):
    return "\n".join(lines) + "\n"


def hunk_lines(files, index=0):
    return [line for h in files[index]["hunks"] for line in h["lines"]]


def test_removed_line_starting_with_two_dashes_is_kept():
    raw = diff(
        "diff --git a/q.sql b/q.sql",
        "--- a/q.sql",
        "+++ b/q.sql",
        "@@ -1,3 +1,3 @@",
        " SELECT 1;",
        "--- old note",
        "+-- new note",
        " SELECT 2;",
    )

    files = change_map.parse_unified(raw)

    assert hunk_lines(files) == [
        (" ", 1, "SELECT 1;"),
        ("-", 2, "-- old note"),
        ("+", 2, "-- new note"),
        (" ", 3, "SELECT 2;"),
    ]


def test_added_line_starting_with_two_pluses_is_kept():
    raw = diff(
        "diff --git a/n.c b/n.c",
        "--- a/n.c",
        "+++ b/n.c",
        "@@ -1,2 +1,3 @@",
        " int n = 0;",
        "+++ n;",
        " return n;",
    )

    files = change_map.parse_unified(raw)

    assert hunk_lines(files) == [
        (" ", 1, "int n = 0;"),
        ("+", 2, "++ n;"),
        (" ", 3, "return n;"),
    ]


def test_format_patch_signature_is_not_a_removed_line():
    raw = diff(
        "From 1234567890abcdef Mon Sep 17 00:00:00 2001",
        "From: A Dev <dev@example.com>",
        "Subject: [PATCH] bump",
        "",
        "---",
        " f.py | 2 +-",
        " 1 file changed, 1 insertion(+), 1 deletion(-)",
        "",
        "diff --git a/f.py b/f.py",
        "index 1111111..2222222 100644",
        "--- a/f.py",
        "+++ b/f.py",
        "@@ -1 +1 @@",
        "-a = 1",
        "+a = 2",
        "-- ",
        "2.43.0",
        "",
    )

    files = change_map.parse_unified(raw)

    assert hunk_lines(files) == [("-", 1, "a = 1"), ("+", 1, "a = 2")]


def test_next_file_header_after_a_hunk_is_not_content():
    raw = diff(
        "diff --git a/a.py b/a.py",
        "--- a/a.py",
        "+++ b/a.py",
        "@@ -1 +1 @@",
        "-x = 1",
        "+x = 2",
        "diff --git a/b.py b/b.py",
        "--- a/b.py",
        "+++ b/b.py",
        "@@ -4 +4 @@",
        "-y = 1",
        "+y = 2",
    )

    files = change_map.parse_unified(raw)

    assert [f["new"] for f in files] == ["a.py", "b.py"]
    assert hunk_lines(files, 0) == [("-", 1, "x = 1"), ("+", 1, "x = 2")]
    assert hunk_lines(files, 1) == [("-", 4, "y = 1"), ("+", 4, "y = 2")]


def test_truncated_hunk_stops_at_the_next_file():
    raw = diff(
        "diff --git a/a.py b/a.py",
        "--- a/a.py",
        "+++ b/a.py",
        "@@ -1,9 +1,9 @@",
        "-x = 1",
        "+x = 2",
        "diff --git a/b.py b/b.py",
        "--- a/b.py",
        "+++ b/b.py",
        "@@ -4 +4 @@",
        "-y = 1",
        "+y = 2",
    )

    files = change_map.parse_unified(raw)

    assert [f["new"] for f in files] == ["a.py", "b.py"]
    assert hunk_lines(files, 1) == [("-", 4, "y = 1"), ("+", 4, "y = 2")]
