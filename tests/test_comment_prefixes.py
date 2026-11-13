"""A run is comment-only when its lines are comments in that file's language."""

import pytest

import change_map


def run_of(removed, added):
    return [("-", 1, removed), ("+", 1, added)]


@pytest.mark.parametrize(
    "path, removed, added",
    [
        ("main.c", "#include <stdio.h>", "#include <stdlib.h>"),
        ("main.c", "#define LIMIT 10", "#define LIMIT 20"),
        ("main.c", "*p = 1;", "*p = 2;"),
        ("main.c", "--x;", "--y;"),
        ("lib.rs", "#[derive(Debug)]", "#[derive(Clone)]"),
        ("run.sh", "#!/bin/sh", "#!/bin/bash"),
        ("tool.py", "#!/usr/bin/env python", "#!/usr/bin/env python3"),
        ("call.py", "**kwargs,", "**options,"),
        ("style.css", "--gap: 4px;", "--gap: 8px;"),
        ("page.js", "#count = 0;", "#count = 1;"),
        ("notes.xyz", "# one", "# two"),
        ("Makefile.am", "; one", "; two"),
    ],
)
def test_code_that_looks_like_a_comment_elsewhere_is_not_noise(path, removed, added):
    assert change_map.run_noise(run_of(removed, added), path) is None


@pytest.mark.parametrize(
    "path, removed, added",
    [
        ("tool.py", "# old note", "# new note"),
        ("conf.yaml", "  # old note", "  # new note"),
        ("Dockerfile", "# old note", "# new note"),
        ("main.c", "// old note", "// new note"),
        ("main.c", "/* old note */", "/* new note */"),
        ("lib.rs", "/// old doc", "/// new doc"),
        ("q.sql", "-- old note", "-- new note"),
        ("init.el", "; old note", "; new note"),
        ("page.html", "<!-- old -->", "<!-- new -->"),
    ],
)
def test_real_comment_edit_is_comment_only(path, removed, added):
    assert change_map.run_noise(run_of(removed, added), path) == "comment-only"


def test_c_hunk_with_include_and_pointer_change_is_shown(capsys):
    raw = "\n".join(
        [
            "diff --git a/main.c b/main.c",
            "--- a/main.c",
            "+++ b/main.c",
            "@@ -1,2 +1,2 @@",
            "-#include <stdio.h>",
            "+#include <stdlib.h>",
            " int main(void) {",
            "@@ -9,1 +9,1 @@",
            "-*p = 1;",
            "+*p = 2;",
            "",
        ]
    )

    change_map.print_git("test", raw, [])

    out = capsys.readouterr().out
    assert "skipped hunk" not in out
    assert "#include <stdlib.h>" in out
    assert "*p = 2;" in out
