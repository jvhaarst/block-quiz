"""Whitespace inside a string literal is data, not formatting."""

import pytest

import change_map


def run_of(removed, added):
    return [("-", 1, removed), ("+", 1, added)]


@pytest.mark.parametrize(
    "path, removed, added",
    [
        ("app.js", 'const sep = ", ";', 'const sep = ",";'),
        ("app.py", "name = 'a b'", "name = 'ab'"),
        ("app.go", "s := `a b`", "s := `ab`"),
        ("msg.c", 'puts("hello world");', 'puts("helloworld");'),
    ],
)
def test_whitespace_change_inside_a_string_is_not_formatting(path, removed, added):
    assert change_map.run_noise(run_of(removed, added), path) is None


@pytest.mark.parametrize(
    "path, removed, added",
    [
        ("app.js", '  const sep = ", ";', '    const sep = ", ";'),
        ("app.js", 'const  sep = ", ";  ', 'const sep = ", ";'),
        ("app.js", "if(x){", "if (x) {"),
    ],
)
def test_whitespace_change_outside_a_string_is_still_formatting(path, removed, added):
    assert change_map.run_noise(run_of(removed, added), path) == "formatting"
