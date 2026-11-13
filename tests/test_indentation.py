"""Leading whitespace is code where indentation carries meaning."""

import pytest

import change_map


def run_of(removed, added):
    return [("-", 1, removed), ("+", 1, added)]


@pytest.mark.parametrize(
    "path, removed, added",
    [
        ("sum.py", "        print(total)", "    print(total)"),
        ("stub.pyi", "    x: int", "x: int"),
        ("ci.yaml", "    retries: 3", "  retries: 3"),
        ("ci.yml", "  - step", "- step"),
        ("Makefile", "\techo done", "echo done"),
        ("rules.mk", "\techo done", "    echo done"),
    ],
)
def test_indentation_change_is_not_formatting(path, removed, added):
    assert change_map.run_noise(run_of(removed, added), path) is None


@pytest.mark.parametrize(
    "path, removed, added",
    [
        ("sum.py", "    total = f(a,b)", "    total = f(a, b)"),
        ("sum.py", "    total = 1   ", "    total = 1"),
        ("main.c", "  return total;", "    return total;"),
        ("app.js", "if(x){", "if (x) {"),
    ],
)
def test_other_whitespace_change_is_formatting(path, removed, added):
    assert change_map.run_noise(run_of(removed, added), path) == "formatting"


def test_python_dedent_out_of_a_loop_is_shown(capsys):
    raw = "\n".join(
        [
            "diff --git a/sum.py b/sum.py",
            "--- a/sum.py",
            "+++ b/sum.py",
            "@@ -1,3 +1,3 @@",
            " for n in numbers:",
            "     total += n",
            "-    print(total)",
            "+print(total)",
            "",
        ]
    )

    change_map.print_git("test", raw, [])

    out = capsys.readouterr().out
    assert "skipped hunk" not in out
    assert "formatting" not in out
