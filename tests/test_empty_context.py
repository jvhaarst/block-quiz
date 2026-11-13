"""Pasted diffs often lose the single space that marks a blank context line."""

import change_map


def test_empty_line_inside_a_hunk_counts_as_context():
    raw = "\n".join(
        [
            "diff --git a/f.py b/f.py",
            "--- a/f.py",
            "+++ b/f.py",
            "@@ -1,4 +1,4 @@",
            " a = 1",
            "",
            "-c = 3",
            "+c = 4",
            " d = 5",
            "",
        ]
    )

    files = change_map.parse_unified(raw)

    assert files[0]["hunks"][0]["lines"] == [
        (" ", 1, "a = 1"),
        (" ", 2, ""),
        ("-", 3, "c = 3"),
        ("+", 3, "c = 4"),
        (" ", 4, "d = 5"),
    ]


def test_blank_line_after_a_complete_hunk_is_not_context():
    raw = "\n".join(
        [
            "diff --git a/f.py b/f.py",
            "--- a/f.py",
            "+++ b/f.py",
            "@@ -1 +1 @@",
            "-a = 1",
            "+a = 2",
            "",
            "",
        ]
    )

    files = change_map.parse_unified(raw)

    assert files[0]["hunks"][0]["lines"] == [("-", 1, "a = 1"), ("+", 1, "a = 2")]
