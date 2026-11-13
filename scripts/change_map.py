#!/usr/bin/env python3
"""Print a compact, line-numbered map of a git change, for the block-quiz skill.

Uses perspica (https://github.com/sshah03/perspica) when it is installed: it marks
mechanical noise (formatting, comment-only edits, renames, moves, generated files)
and gives a reading order from entry points down. Without perspica it falls back to
plain `git diff` with light heuristics. Only local git is used, so it works the same
for any host (GitLab, GitHub, Gitea, Forgejo, Bitbucket, none).

Usage (run inside the repository):
  change_map.py                      current branch vs its base, plus uncommitted work
  change_map.py --base develop       current branch vs another base branch
  change_map.py --staged             staged changes only
  change_map.py --uncommitted        working tree vs HEAD
  change_map.py --range A...B        any range git understands (a..b, a...b, or one ref)
  change_map.py --commit SHA         one commit
  change_map.py --patch FILE         a saved diff or patch (git diff output, a GitLab/GitHub .diff download)
  change_map.py --no-perspica        force the plain git path
  change_map.py --perspica-json F    read a saved `perspica --json` output instead of running it

Standard library only. Python 3.8+.
"""

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys

NOISE_LABEL = {
    "formatting": "formatting",
    "comment": "comment-only",
    "rename": "rename-only",
    "moved": "moved unchanged",
    "generated": "generated",
}

GENERATED_PATTERNS = [
    r"(^|/)package-lock\.json$", r"(^|/)npm-shrinkwrap\.json$", r"(^|/)yarn\.lock$",
    r"(^|/)pnpm-lock\.yaml$", r"(^|/)bun\.lockb?$", r"(^|/)Cargo\.lock$", r"(^|/)poetry\.lock$",
    r"(^|/)Pipfile\.lock$", r"(^|/)uv\.lock$", r"(^|/)composer\.lock$", r"(^|/)Gemfile\.lock$",
    r"(^|/)go\.sum$", r"(^|/)packages\.lock\.json$", r"\.min\.(js|css)$", r"\.map$", r"\.snap$",
    r"(^|/)(dist|build|out|target|vendor|node_modules|third_party)/", r"_pb2(_grpc)?\.py$",
    r"\.pb\.go$", r"\.generated\.", r"\.g\.dart$", r"\.designer\.cs$",
]
TEST_PATTERNS = [
    r"(^|/)(test|tests|__tests__|spec|specs|testing)/", r"(^|/)test_[^/]+\.py$", r"_test\.(py|go|rs|rb|exs?)$",
    r"\.(test|spec)\.[cm]?[jt]sx?$", r"Tests?\.(java|kt|cs|scala|swift)$", r"_spec\.rb$",
]
DOC_PATTERNS = [r"\.(md|mdx|rst|adoc|txt)$", r"(^|/)docs?/", r"(^|/)(CHANGELOG|LICENSE|README)"]

# Comment markers depend on the language: "#" opens a comment in Python but a
# preprocessor line in C and an attribute in Rust. A file whose language is not
# listed here gets no markers, so none of its lines are ever called comment-only.
# The bare "*" of a block-comment continuation is left out on purpose: it is
# also a dereference ("*p = 1;") or an unpacking ("**kwargs").
HASH = ("#",)
SLASH = ("//", "/*", "*/")
COMMENT_PREFIXES_BY_EXT = {}
for _exts, _prefixes in (
    ("py pyi", HASH + ('"""', "'''")),
    ("rb sh bash zsh fish yaml yml toml pl pm r tf nix ex exs ps1 mk cmake", HASH),
    ("cfg conf properties gitignore dockerignore", HASH),
    ("c h cc cpp cxx hpp hh java js jsx mjs cjs ts tsx go rs swift kt kts", SLASH),
    ("scala cs dart m mm groovy proto scss less", SLASH),
    ("php", SLASH + HASH),
    ("css", ("/*", "*/")),
    ("sql lua hs elm adb ads", ("--",)),
    ("el lisp clj cljs scm asm s", (";",)),
    ("ini", (";", "#")),
    ("html htm xml svg vue md", ("<!--",)),
):
    for _ext in _exts.split():
        COMMENT_PREFIXES_BY_EXT[_ext] = _prefixes
COMMENT_PREFIXES_BY_NAME = {
    "Dockerfile": HASH, "Makefile": HASH, "GNUmakefile": HASH, "CMakeLists.txt": HASH,
    "Gemfile": HASH, "Rakefile": HASH,
}


def comment_prefixes(path):
    """Line-comment markers for the language of `path`, or () when unknown."""
    name = os.path.basename(path)
    if name in COMMENT_PREFIXES_BY_NAME:
        return COMMENT_PREFIXES_BY_NAME[name]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return COMMENT_PREFIXES_BY_EXT.get(ext, ())


def is_comment(text, prefixes):
    # "#!" is a shebang: it picks the interpreter, so changing it changes behavior.
    return bool(prefixes) and text.startswith(prefixes) and not text.startswith("#!")


# ---------------------------------------------------------------------------
# helpers

def run(cmd, check=True, cwd=None):
    proc = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = proc.stdout.decode("utf-8", errors="replace")
    err = proc.stderr.decode("utf-8", errors="replace")
    if check and proc.returncode != 0:
        raise RuntimeError("{} failed ({}): {}".format(" ".join(cmd), proc.returncode, err.strip()))
    return proc.returncode, out, err


def git(*args, check=True):
    return run(["git", "--no-pager", "-c", "core.quotepath=false", *args], check=check)[1]


def matches(path, patterns):
    return any(re.search(p, path) for p in patterns)


def role_for(path):
    if matches(path, GENERATED_PATTERNS):
        return "generated"
    if matches(path, TEST_PATTERNS):
        return "test"
    if matches(path, DOC_PATTERNS):
        return "docs"
    return "source"


def fmt_loc(loc, fallback_file=""):
    if not isinstance(loc, dict):
        return "?"
    f = loc.get("file") or fallback_file
    a, b = loc.get("line_start"), loc.get("line_end")
    side = loc.get("side", "new")
    rng = "{}".format(a) if a == b else "{}-{}".format(a, b)
    return "{}:{}{}".format(f, rng, " (old)" if side == "old" else "")


def default_base():
    rc, out, _ = run(["git", "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], check=False)
    if rc == 0 and out.strip():
        return out.strip()
    for cand in ("origin/main", "origin/master", "main", "master", "origin/develop", "develop"):
        rc, _, _ = run(["git", "rev-parse", "--verify", "--quiet", cand], check=False)
        if rc == 0:
            return cand
    return None


# ---------------------------------------------------------------------------
# perspica path

def perspica_args(ns):
    args = ["perspica", "--json", "--no-sessions"]
    if ns.staged:
        args.append("--staged")
    elif ns.uncommitted:
        args.append("--git")
    elif ns.range:
        args += ["--git", ns.range]
    elif ns.commit:
        args += ["--git", "{0}~1..{0}".format(ns.commit)]
    elif ns.base:
        args += ["--branch", ns.base]
    return args


def load_perspica(ns):
    if ns.perspica_json:
        with open(ns.perspica_json, encoding="utf-8") as fh:
            return json.load(fh), "saved perspica JSON ({})".format(ns.perspica_json)
    if ns.no_perspica or not shutil.which("perspica"):
        return None, None
    rc, out, err = run(perspica_args(ns), check=False)
    if rc != 0:
        sys.stderr.write("perspica failed, using plain git instead: {}\n".format(err.strip()[:300]))
        return None, None
    try:
        return json.loads(out), "perspica"
    except json.JSONDecodeError:
        sys.stderr.write("perspica output was not JSON, using plain git instead\n")
        return None, None


def print_perspica(data, analyzer):
    files = data.get("files") or []
    results = data.get("results") or []
    source = data.get("source") or {}
    cross = data.get("cross_file") or {}

    print("# Change map")
    print("- Target: {}".format(source.get("label") or "?"))
    if source.get("detail"):
        print("- Detail: {}".format(source["detail"]))
    if source.get("pr_title"):
        print("- Title: {}".format(source["pr_title"]))
    print("- Analyzer: {} {}".format(analyzer, data.get("version", "")).rstrip())
    if len(files) != len(results):
        print("- WARNING: {} files but {} results; file pairing may be off".format(len(files), len(results)))
    print()

    print("## Files")
    for i, f in enumerate(files):
        r = results[i] if i < len(results) else {}
        rv = r.get("review") or {}
        role = rv.get("role") or role_for(f.get("new_path", ""))
        if rv.get("generated"):
            role = "generated"
        path = f.get("new_path") or f.get("old_path")
        if f.get("old_path") and f.get("new_path") and f["old_path"] != f["new_path"]:
            path = "{} -> {}".format(f["old_path"], f["new_path"])
        extra = []
        if f.get("binary"):
            extra.append("binary")
        if rv and not rv.get("parsed", True):
            extra.append("not parsed: plain line diff")
        print("- {} [{} · {} · {}] changed {}, mechanical {}{}".format(
            path, f.get("status", "?"), role, f.get("language", "?"),
            rv.get("changed_lines", "?"), rv.get("mechanical_lines", "?"),
            " · " + ", ".join(extra) if extra else ""))
    print()

    order = cross.get("reading_order") or []
    if order:
        print("## Reading order (entry points first, then what they call)")
        for s in order:
            if s.get("repeat"):
                continue
            calls = ", ".join(s.get("calls") or [])
            print("{}- [{}] {} — {}{}".format(
                "  " * int(s.get("depth") or 0), s.get("kind", "?"), s.get("name", "?"), s.get("file", "?"),
                "  (calls: {})".format(calls) if calls else ""))
        print()

    print("## Classified changes")
    any_entry = False
    for i, r in enumerate(results):
        fpath = files[i].get("new_path", "") if i < len(files) else ""
        m = r.get("manifest") or {}
        test_ids = set(m.get("test_entries") or [])
        for e in m.get("logic_changes") or []:
            any_entry = True
            print("- logic #{} {} `{}` {}{}: {}".format(e.get("id"), e.get("kind"), e.get("name"),
                  fmt_loc(e.get("location"), fpath), " [test]" if e.get("id") in test_ids else "",
                  e.get("description", "")))
        for e in m.get("signature_changes") or []:
            any_entry = True
            print("- signature #{} `{}` {}: {}".format(e.get("id"), e.get("name"),
                  fmt_loc(e.get("location"), fpath), e.get("description", "")))
        for e in m.get("extracted_functions") or []:
            any_entry = True
            print("- extracted #{} from `{}` into {}".format(e.get("id"), e.get("original_name"),
                  ", ".join("`{}`".format(n) for n in e.get("extracted_names") or [])))
        for e in m.get("renames") or []:
            any_entry = True
            print("- rename #{} {} `{}` -> `{}` (mechanical)".format(e.get("id"), e.get("kind"),
                  e.get("old_name"), e.get("new_name")))
        for e in m.get("moved_code") or []:
            any_entry = True
            print("- moved #{} `{}` {} -> {} (mechanical)".format(e.get("id"), e.get("name"),
                  fmt_loc(e.get("from_location"), fpath), fmt_loc(e.get("to_location"), fpath)))
        for e in m.get("dependency_changes") or []:
            any_entry = True
            syms = []
            if e.get("symbols_added"):
                syms.append("+" + ",".join(e["symbols_added"]))
            if e.get("symbols_removed"):
                syms.append("-" + ",".join(e["symbols_removed"]))
            print("- dependency #{} {} `{}` in {}{}".format(e.get("id"), e.get("change_type"), e.get("name"),
                  fpath, " " + " ".join(syms) if syms else ""))
        for e in m.get("dead_code") or []:
            any_entry = True
            print("- now unused #{} `{}` {}: {}".format(e.get("id"), e.get("name"),
                  fmt_loc(e.get("location"), fpath), e.get("reason", "")))
    for e in cross.get("moves") or []:
        any_entry = True
        print("- moved across files #{} `{}` {} -> {}{}".format(e.get("id"), e.get("name"), e.get("from_file"),
              e.get("to_file"), " (body edited)" if e.get("modified") else " (mechanical)"))
    for e in cross.get("signature_impacts") or []:
        any_entry = True
        print("- signature impact #{} `{}`: {} ({} call sites)".format(e.get("id"), e.get("name"),
              e.get("description", ""), len(e.get("call_sites") or [])))
    for e in cross.get("broken_references") or []:
        any_entry = True
        print("- broken reference #{} `{}` at {}: {}".format(e.get("id"), e.get("symbol_name"),
              fmt_loc(e.get("reference_location"), e.get("reference_file", "")), e.get("reason", "")))
    if not any_entry:
        print("- (none: unsupported languages or no structural changes; use the diff below)")
    print()

    print("## Diff (line numbers: new file for + and context, old file for -)")
    for i, f in enumerate(files):
        r = results[i] if i < len(results) else {}
        rv = r.get("review") or {}
        path = f.get("new_path") or f.get("old_path")
        role = "generated" if rv.get("generated") else (rv.get("role") or role_for(path))
        if f.get("binary"):
            print("\n### {} — binary, skipped".format(path))
            continue
        if role in ("generated", "vendored"):
            print("\n### {} — {}, skipped".format(path, role))
            continue
        print("\n### {} [{} · {}]".format(path, f.get("status", "?"), role))
        for h in r.get("hunks") or []:
            orng, nrng = h.get("old_range") or {}, h.get("new_range") or {}
            head = "old {}-{} -> new {}-{}".format(orng.get("start"), orng.get("end"), nrng.get("start"), nrng.get("end"))
            if h.get("noise"):
                print("\n(skipped hunk {}: all {})".format(head, NOISE_LABEL.get(h["noise"], h["noise"])))
                continue
            refs = h.get("manifest_refs") or []
            print("\n@@ {} @@{}{}".format(head, "  entries: " + ", ".join(map(str, refs)) if refs else "",
                                          "  [test]" if h.get("test") else ""))
            for c in h.get("changes") or []:
                print_change(c)


def print_change(c):
    kind = c.get("kind")
    noise = c.get("noise")
    tag = "[{}] ".format(NOISE_LABEL.get(noise, noise)) if noise else ""
    if kind == "added":
        n = (c.get("new_span") or {}).get("start_line", "")
        print("+ {:>5} | {}{}".format(n, tag, c.get("content_new") or ""))
    elif kind == "removed":
        n = (c.get("old_span") or {}).get("start_line", "")
        print("- {:>5} | {}{}".format(n, tag, c.get("content_old") or ""))
    elif kind == "modified":
        o = (c.get("old_span") or {}).get("start_line", "")
        n = (c.get("new_span") or {}).get("start_line", "")
        print("- {:>5} | {}{}".format(o, tag, c.get("content_old") or ""))
        print("+ {:>5} | {}{}".format(n, tag, c.get("content_new") or ""))
    else:
        n = (c.get("new_span") or {}).get("start_line", "")
        print("  {:>5} | {}".format(n, c.get("content_new") or c.get("content_old") or ""))


# ---------------------------------------------------------------------------
# plain git path

DIFF_FLAGS = ["diff", "--no-color", "--no-ext-diff", "-M", "-U5", "--src-prefix=a/", "--dst-prefix=b/"]


def git_target(ns):
    """Return (label, raw unified diff, untracked file list)."""
    untracked = []
    if ns.staged:
        return "staged changes", git(*DIFF_FLAGS, "--cached"), untracked
    if ns.uncommitted:
        untracked = git("ls-files", "--others", "--exclude-standard").split("\n")
        return "uncommitted changes (working tree vs HEAD)", git(*DIFF_FLAGS, "HEAD"), [u for u in untracked if u]
    if ns.range:
        return ns.range, git(*DIFF_FLAGS, ns.range), untracked
    if ns.commit:
        rc, _, _ = run(["git", "rev-parse", "--verify", "--quiet", ns.commit + "~1"], check=False)
        if rc == 0:
            return "commit " + ns.commit, git(*DIFF_FLAGS, ns.commit + "~1", ns.commit), untracked
        return "commit " + ns.commit + " (root)", git("show", "--format=", "--no-color", "-U5", ns.commit), untracked
    base = ns.base or default_base()
    if not base:
        raise RuntimeError("could not find a base branch; pass --base <branch> or --range A...B")
    mb = git("merge-base", "HEAD", base).strip()
    untracked = [u for u in git("ls-files", "--others", "--exclude-standard").split("\n") if u]
    head = git("rev-parse", "--abbrev-ref", "HEAD").strip()
    label = "{} vs {} (merge-base {}), including uncommitted changes".format(head, base, mb[:10])
    return label, git(*DIFF_FLAGS, mb), untracked


HUNK_RE = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)")


def parse_unified(raw):
    files, cur, hunk = [], None, None
    old_n = new_n = old_left = new_left = 0
    for line in raw.split("\n"):
        if hunk is not None and (old_left > 0 or new_left > 0):
            # Inside a hunk the @@ counts say how many lines belong to it, so a
            # removed "-- note" (printed as "--- note") is content, not a file
            # header, and a format-patch "-- " signature after the hunk is not.
            sign = line[:1]
            if sign == "+":
                hunk["lines"].append(("+", new_n, line[1:]))
                new_n += 1
                new_left -= 1
                continue
            if sign == "-":
                hunk["lines"].append(("-", old_n, line[1:]))
                old_n += 1
                old_left -= 1
                continue
            if sign == " " or line == "":
                # An empty line is a blank context line that lost its leading
                # space, which happens when a diff is pasted or mailed.
                hunk["lines"].append((" ", new_n, line[1:]))
                old_n += 1
                new_n += 1
                old_left -= 1
                new_left -= 1
                continue
            if sign == "\\":
                continue
            hunk = None  # truncated hunk: this line is a header, handled below
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(.*) b/(.*)$", line)
            cur = {"old": m.group(1) if m else "?", "new": m.group(2) if m else "?", "status": "M",
                   "binary": False, "hunks": []}
            files.append(cur)
            hunk = None
        elif cur is None:
            continue
        elif line.startswith("new file mode"):
            cur["status"] = "A"
        elif line.startswith("deleted file mode"):
            cur["status"] = "D"
        elif line.startswith("rename to "):
            cur["status"] = "R"
        elif line.startswith("Binary files "):
            cur["binary"] = True
        elif line.startswith("@@"):
            m = HUNK_RE.match(line)
            if m:
                old_n, new_n = int(m.group(1)), int(m.group(3))
                old_left = int(m.group(2)) if m.group(2) is not None else 1
                new_left = int(m.group(4)) if m.group(4) is not None else 1
                hunk = {"header": m.group(5).strip(), "lines": []}
                cur["hunks"].append(hunk)
    return files


def run_noise(run_lines, path=""):
    """Noise label for one run of consecutive changed lines, or None."""
    removed = [t for s, _, t in run_lines if s == "-"]
    added = [t for s, _, t in run_lines if s == "+"]
    squash = lambda xs: [re.sub(r"\s+", "", x) for x in xs if x.strip()]
    if squash(removed) == squash(added):
        return "formatting"
    changed = [t.strip() for t in removed + added if t.strip()]
    prefixes = comment_prefixes(path)
    if changed and all(is_comment(t, prefixes) for t in changed):
        return "comment-only"
    return None


def tag_noise(lines, path=""):
    """Return [(sign, n, text, noise_or_None)] and whether every changed line is noise."""
    out, run_buf = [], []

    def flush():
        noise = run_noise(run_buf, path) if run_buf else None
        out.extend((s, n, t, noise) for s, n, t in run_buf)
        run_buf.clear()

    for s, n, t in lines:
        if s == " ":
            flush()
            out.append((s, n, t, None))
        else:
            run_buf.append((s, n, t))
    flush()
    changed = [x for x in out if x[0] != " "]
    return out, bool(changed) and all(x[3] for x in changed)


def print_git(label, raw, untracked):
    files = parse_unified(raw)
    print("# Change map")
    print("- Target: {}".format(label))
    print("- Analyzer: plain unified diff (perspica not used). Noise tags marked ? are heuristics.")
    print()
    print("## Files")
    for f in files:
        path = f["new"] if f["status"] != "D" else f["old"]
        n_add = sum(1 for h in f["hunks"] for s, _, _ in h["lines"] if s == "+")
        n_del = sum(1 for h in f["hunks"] for s, _, _ in h["lines"] if s == "-")
        ren = " (from {})".format(f["old"]) if f["status"] == "R" else ""
        print("- {}{} [{} · {}] +{} -{}{}".format(path, ren, f["status"], role_for(path), n_add, n_del,
                                               " · binary" if f["binary"] else ""))
    for u in untracked:
        print("- {} [untracked · {}]".format(u, role_for(u)))
    print()
    print("## Diff (line numbers: new file for + and context, old file for -)")
    for f in files:
        path = f["new"] if f["status"] != "D" else f["old"]
        role = role_for(path)
        if f["binary"]:
            print("\n### {} — binary, skipped".format(path))
            continue
        if role == "generated":
            print("\n### {} — looks generated, skipped".format(path))
            continue
        print("\n### {} [{} · {}]".format(path, f["status"], role))
        for h in f["hunks"]:
            plus = [n for s, n, _ in h["lines"] if s in "+ "]
            minus = [n for s, n, _ in h["lines"] if s == "-"]
            head = "new {}-{}".format(min(plus), max(plus)) if plus else "old {}-{}".format(min(minus), max(minus))
            tagged, all_noise = tag_noise(h["lines"], path)
            if all_noise:
                labels = sorted({x[3] for x in tagged if x[3]})
                print("\n(skipped hunk {}: looks {})".format(head, " / ".join(labels)))
                continue
            print("\n@@ {} @@{}".format(head, "  in: " + h["header"] if h["header"] else ""))
            for s, n, t, noise in tagged:
                tag = "[{}?] ".format(noise) if noise else ""
                print("{} {:>5} | {}{}".format(s, n, tag, t))
    for u in untracked:
        role = role_for(u)
        if role == "generated" or not os.path.isfile(u):
            continue
        try:
            with open(u, encoding="utf-8") as fh:
                text = fh.read()
        except (UnicodeDecodeError, OSError):
            print("\n### {} — untracked, not text, skipped".format(u))
            continue
        lines = text.split("\n")
        if len(lines) > 1500:
            print("\n### {} — untracked, {} lines, too long to inline; read it directly".format(u, len(lines)))
            continue
        print("\n### {} [untracked (new file) · {}]".format(u, role))
        print("\n@@ new 1-{} @@".format(len(lines)))
        for i, t in enumerate(lines, 1):
            print("+ {:>5} | {}".format(i, t))


# ---------------------------------------------------------------------------

def main():
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # quiet when piped into head
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--base", help="base branch to compare the current branch against")
    g.add_argument("--staged", action="store_true")
    g.add_argument("--uncommitted", action="store_true")
    g.add_argument("--range", help="a..b, a...b, or a single ref")
    g.add_argument("--commit", help="a single commit")
    g.add_argument("--patch", help="a saved unified diff / patch file; no repository needed")
    p.add_argument("--no-perspica", action="store_true")
    p.add_argument("--perspica-json", help="read saved perspica JSON instead of running perspica")
    ns = p.parse_args()

    if ns.patch:
        with open(ns.patch, encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
        print_git("patch file " + ns.patch, raw, [])
        return

    if not ns.perspica_json:
        rc, _, _ = run(["git", "rev-parse", "--is-inside-work-tree"], check=False)
        if rc != 0:
            sys.exit("Not inside a git repository. cd into the repo first.")

    try:
        data, analyzer = load_perspica(ns)
        if data is not None:
            print_perspica(data, analyzer)
            return
        label, raw, untracked = git_target(ns)
        if not raw.strip() and not untracked:
            print("# Change map\n- Target: {}\n- No changes found.".format(label))
            return
        print_git(label, raw, untracked)
    except RuntimeError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
