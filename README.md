# block-quiz

A skill for Claude that quizzes you on a code change, one logical block at a time.
For each block you explain in your own words what it does. Claude grades your
answer against what the code actually does, not what the comments claim. When you
miss, you get hints first, then a line-by-line explanation. At the end you get an
annotated walkthrough of the whole change.

Use it before you merge something you didn't write, when you review a merge
request, or to check that you really understand code an AI wrote for you.

## How a session goes

1. You name a change: your branch, a commit, a merge or pull request, staged work, or a `.diff` file.
2. Claude cuts it into blocks and shows a plan. The plan lists only locations and symbol names, never what the code does.
3. For each block, Claude shows the code and asks what it does. Restating the comments doesn't count.
4. Each answer is graded **pass**, **partial** or **miss**. A partial answer gets one targeted follow-up question. A miss gets up to two hints, then a line-by-line explanation, and then you explain the block back in a sentence or two.
5. At the end you get a scoreboard and an annotated walkthrough. Claude offers to save it as Markdown outside the repository.

A plan looks like this:

```text
Change: feature vs main · 3 source files · 9 blocks
Skipped: package-lock.json (generated), 2 formatting-only hunks, rename calc → total
Tests: 2 blocks in tests/test_cart.py, at the end if you want them

 1. cart.py:4–13     total()           modified
 2. cart.py:16–19    apply_discount()  new
 3. ...

Type hint, explain, skip or stop at any time. Ready?
```

## Requirements

- [Claude Code](https://docs.claude.com/en/docs/claude-code/overview), or another agent that supports Agent Skills (`SKILL.md`)
- `git`
- Python 3.8 or newer. The helper script uses only the standard library.
- Optional: [perspica](https://github.com/sshah03/perspica) (`cargo install perspica`). With it, blocks follow a reading order from entry points down, and renames, moves and formatting-only edits are recognised reliably. Without it, the skill works from plain `git diff`.

## Install

**Claude Code, for all your projects:**

```bash
git clone https://github.com/OWNER/block-quiz.git ~/.claude/skills/block-quiz
```

**Claude Code, for one project** (shared with everyone who clones that project):

```bash
git submodule add https://github.com/OWNER/block-quiz.git .claude/skills/block-quiz
```

If Claude Code was already running, restart it so it picks up the skill.

**claude.ai:** download `block-quiz.skill` from the
[latest release](https://github.com/OWNER/block-quiz/releases/latest) and upload
it under Settings → Capabilities → Skills. Code execution has to be on. There is
no local repository there, so paste a diff or upload a `.diff` or `.patch` file.

**Update** a Claude Code install:

```bash
git -C ~/.claude/skills/block-quiz pull
```

## Usage

Start Claude Code inside the repository you want to be quizzed on. Then type
`/block-quiz`, or ask for it in plain words:

- "quiz me on this branch"
- "walk me through the last commit"
- "test me on MR 42 before I merge"
- "do I really understand what I've staged?"

### What it can quiz you on

| You say | The change it uses |
|---|---|
| nothing, "this branch", "my changes" | the current branch vs its base, including uncommitted work |
| "against develop" | the current branch vs `develop` |
| "staged" | staged changes only |
| "uncommitted" | the working tree vs `HEAD` |
| "the last commit", or a commit hash | that one commit |
| "main...feature" | any range git understands |
| a merge or pull request number or URL | that merge or pull request |
| a pasted diff, or a `.diff` / `.patch` file | that patch; no repository needed |

Merge and pull requests are fetched with plain `git fetch` into a local ref
(`quiz/mr-<iid>` or `quiz/pr-<n>`). No host CLI or API token is needed, and your
working tree is left alone. This works for GitLab, GitHub, Gitea and Forgejo. For
other hosts, check out the branch yourself or download the change as a `.diff`.

### Commands during the quiz

| Type | What happens |
|---|---|
| `hint` | the next hint, up to two per block |
| `explain` | skip straight to the line-by-line explanation |
| `skip` | move on; the block is still explained in the final walkthrough |
| `stop` | end now and go to the scoreboard and walkthrough |

Mechanical changes (formatting, comment-only edits, pure renames and moves,
generated files, lockfiles) are skipped, and the plan lists them so you can see
nothing was hidden. Tests come at the end, and only if you want them. For more
than about 12 blocks, Claude offers to split the work over several sessions or let
you pick a subset.

## The helper script

`scripts/change_map.py` builds the line-numbered change map the skill works from.
You can also run it on its own, from inside a repository:

```bash
python3 ~/.claude/skills/block-quiz/scripts/change_map.py                    # branch vs base
python3 ~/.claude/skills/block-quiz/scripts/change_map.py --range main...feature
python3 ~/.claude/skills/block-quiz/scripts/change_map.py --patch change.diff
```

Other options are `--base`, `--staged`, `--uncommitted`, `--commit`,
`--no-perspica` and `--perspica-json`. Run it with `--help` for the details.

## License

[MIT](LICENSE)
