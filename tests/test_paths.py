"""File roles, file names from diff headers, and untracked file line counts."""

import pytest

import change_map


@pytest.mark.parametrize(
    "path, role",
    [
        ("src/build/real.py", "source"),
        ("app/out/report.py", "source"),
        ("crates/core/target/x.rs", "source"),
        ("build/bundle.js", "generated"),
        ("dist/app.js", "generated"),
        ("web/node_modules/left-pad/index.js", "generated"),
        ("go/vendor/lib/lib.go", "generated"),
        ("package-lock.json", "generated"),
        ("requirements.txt", "source"),
        ("CMakeLists.txt", "source"),
        ("docs/guide.md", "docs"),
        ("README.txt", "docs"),
        ("tests/test_cart.py", "test"),
    ],
)
def test_role_for(path, role):
    assert change_map.role_for(path) == role


def test_mode_only_change_with_b_slash_inside_the_path():
    raw = "\n".join(
        [
            "diff --git a/x b/y.sh b/x b/y.sh",
            "old mode 100644",
            "new mode 100755",
            "",
        ]
    )

    files = change_map.parse_unified(raw)

    assert [(f["old"], f["new"]) for f in files] == [("x b/y.sh", "x b/y.sh")]


def test_rename_without_hunks_uses_rename_lines():
    raw = "\n".join(
        [
            "diff --git a/old b/name.py b/new b/name.py",
            "similarity index 100%",
            "rename from old b/name.py",
            "rename to new b/name.py",
            "",
        ]
    )

    files = change_map.parse_unified(raw)

    assert [(f["status"], f["old"], f["new"]) for f in files] == [
        ("R", "old b/name.py", "new b/name.py")
    ]


def test_untracked_file_has_no_phantom_last_line(tmp_path, monkeypatch, capsys):
    (tmp_path / "new.py").write_text("a = 1\nb = 2\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    change_map.print_git("test", "", ["new.py"])

    out = capsys.readouterr().out
    assert "@@ new 1-2 @@" in out
    assert "+     3 |" not in out
