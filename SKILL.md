---
name: block-quiz
description: Walks the user through a code change one logical block at a time. For each block they explain in their own words what it does (restating the code comments doesn't count). Claude grades the answer against the code, gives hints on a miss, then explains the block line by line, and ends with a full annotated walkthrough of the change. Works on a branch, merge request, pull request, commit, commit range, staged or uncommitted changes, or a saved .diff/.patch file, using only local git, so no host CLI or token is needed (merge and pull requests are fetched from GitLab, GitHub, Gitea and Forgejo; any other host works through a downloaded .diff). Use this whenever the user wants to be quizzed on, tested on, or walked through a diff, MR, PR or commit block by block or line by line, or says things like "quiz me on this change", "walk me through this MR", "do I really understand this diff", "test me before I merge", or "/block-quiz", even if they don't say "block".
compatibility: Needs git and python3. Uses perspica (https://github.com/sshah03/perspica) for better block boundaries when it is installed, and works without it.
---

# Block quiz

The goal: by the end, the user can explain every meaningful line of the change in their own words. The quiz is the way to get there, not a gate. Grade honestly and teach well whenever they miss.

## Rules that matter most

- **No spoilers.** Until a block has been answered, don't summarize the change, describe any block, or hint at what the code is for. The plan you show lists locations and symbol names only. Spoilers turn the quiz into a reading exercise.
- **The code is the answer key.** Grade against what the code does: conditions, order, data flow, return values, side effects, error paths. Never grade on what sounds plausible. If behavior depends on something you can't see (a library, a service, config), say what you're assuming.
- **Their words, not the comments.** Comments, docstrings and identifier names already "explain" the code, often incompletely or wrongly. An answer that only restates them doesn't show understanding. What counts is whatever the code shows that the comments don't.
- **One block at a time.** Show a block, ask, then wait for the answer. Never put two blocks in one message.
- **Short messages.** The user is reading code, so keep your text around the code brief.

## Step 1: Work out the target

Read what the user asked for and pick the matching option for the helper script (Step 2). If it's unclear, ask one question.

| User says | Script option |
|---|---|
| nothing, "this branch", "my changes" | *(no option)*: current branch vs its base, including uncommitted work |
| "against develop" | `--base develop` |
| "staged" | `--staged` |
| "uncommitted", "what I haven't committed" | `--uncommitted` |
| "the last commit", a commit hash | `--commit HEAD` / `--commit <sha>` |
| a range, two branches | `--range main...feature` (three dots = since they diverged, like an MR) |
| a pasted or uploaded diff, a `.diff` / `.patch` file | `--patch <file>` (no repository needed; save pasted text to a file first) |

**A merge request or pull request by number or URL.** Use plain git so no host CLI or token is needed. Refresh the target branch, fetch the MR head into a local ref, then diff the two:

```bash
# First the target branch, so origin/<target> isn't stale
git fetch origin <target>
# GitLab
git fetch origin +refs/merge-requests/<iid>/head:refs/quiz/mr-<iid>
# GitHub, Gitea, Forgejo
git fetch origin +refs/pull/<n>/head:refs/quiz/pr-<n>
```

Then run the script with `--range origin/<target>...refs/quiz/mr-<iid>`. The target branch is usually the default branch; ask if it isn't obvious.

- **Keep the `+` and the `refs/quiz/` prefix.** The `+` lets the fetch succeed again after the author force-pushed, which a re-quiz needs. A ref under `refs/quiz/` is not a branch, so it stays out of `git branch` and can't be checked out or pushed by accident.
- **Pick the remote that owns the MR.** In a fork workflow `origin` is the user's fork and the MR lives on another remote, usually `upstream`. Compare the MR's URL with `git remote -v` and use the matching remote in both fetches and in the range (`upstream/<target>...refs/quiz/mr-<iid>`).
- Tell the user the name of the local ref you created, and that `git update-ref -d refs/quiz/mr-<iid>` removes it. Don't check it out or touch their working tree.
- When you need the full file at that version, read it with `git show refs/quiz/mr-<iid>:<path>`, not from disk.
- If the fetch fails (no remote points at the MR's project, access is denied, or the host has no such refs, as with Bitbucket Cloud), ask the user to check out the branch themselves, or to download the MR's `.diff` and use `--patch`.

## Step 2: Build the change map

Run the helper script next to this file (in this skill's folder, e.g. `~/.claude/skills/block-quiz/scripts/change_map.py`) from inside the repository:

```bash
python3 <skill-folder>/scripts/change_map.py [option from Step 1]
```

It prints a compact map:
- the files, each with its role (source, test, docs, generated)
- with perspica, a **reading order** (entry points first, then what they call) and **classified changes** (logic changes, signature changes, renames, moves, dependencies, newly unused code)
- the diff with line numbers (`+` and context use new-file numbers, `-` uses old-file numbers), with mechanical noise tagged or skipped

Read all of it before planning. If the output says perspica wasn't used, carry on: the plain-diff path works fine, and its noise tags marked with `?` are heuristics to double-check. Mention perspica once at most (`cargo install perspica` gives cleaner blocks), and only if the change is large or noisy.

## Step 3: Cut the change into blocks

A block is one logical unit the user can explain in a few sentences: a new function, the changed part of a function, a loop or condition that was added or rewritten, an error-handling path, a related group of config entries. Aim for roughly 3–25 changed lines each, and up to ~40 when the lines can't be split sensibly.

- **Order.** Follow perspica's reading order when there is one: types and data first, then from entry points down to what they call. Otherwise go file by file in dependency order (definitions before their uses), top to bottom within a file.
- **Split** long functions at natural seams: input checks, the main loop, the result building, the error handling.
- **Merge** tiny edits only when they serve one purpose (adding a parameter and the line that uses it belongs together).
- **Skip** mechanical changes: formatting, comment-only edits, pure renames, moves without edits, generated or vendored files, lockfiles. List them in the plan as skipped so the user knows nothing was hidden.
- **Removed code** gets its own block when it did something meaningful.
- **Tests** go in a separate set at the end. Ask whether to include them.

For each block, open the real file around it (the function it sits in, and the old version when it's modified) so you understand it in context. Use `grep` to check callers or definitions when the block's job depends on them. Reading only the hunk is how wrong answer keys happen.

## Step 4: Show the plan

Show the plan in this shape. It contains no descriptions of what the code does:

```
Change: feature vs main · 3 source files · 9 blocks
Skipped: package-lock.json (generated), 2 formatting-only hunks, rename calc → total
Tests: 2 blocks in tests/test_cart.py, at the end if you want them

 1. cart.py:4–13     total()           modified
 2. cart.py:16–19    apply_discount()  new
 3. ...

Type hint, explain, skip or stop at any time. Ready?
```

For more than about 12 blocks, offer to split the work into sessions (see "Stopping and resuming") or let the user pick a subset.

## Step 5: The loop, for each block

### Prepare (privately)

Just before showing a block, write the answer key in your own reasoning. It never goes in a visible message.
- What the block does, and for modified blocks, what behaves differently now.
- 2–5 **must-mention points**: behavior a real understanding includes, such as conditions, limits, order, what's returned, what happens on failure.
- What the comments, docstrings and names already say. This is the "parrot list".
- Mistakes the user is likely to make.

**Check a doubtful point before you grade on it.** If you aren't sure of a must-mention point (an off-by-one, operator precedence, what a library call returns on an edge case) and the code can be run, settle it first: run a small snippet or the existing tests. Use a scratch file outside the repository and never change the user's working tree. For an MR, read the code with `git show <ref>:<path>` rather than checking the ref out. If you can't run it, don't grade on that point, or state it as an assumption.

### Show and ask

```
Block 3/9 · cart.py:16–19 · apply_discount() · new
```

Show the code with line numbers, exactly as written, comments included. For modified blocks show the change as before/after (or the numbered `-`/`+` lines) with a few lines of context. Then ask one question:

- New code: "In your own words: what does this block do?"
- Modified code: "In your own words: what does this block do now, and what's different from before?"
- Removed code: "What did this code do, and what (if anything) does that job now?"

On the first block only, add one line: "Restating the comments doesn't count; tell me what the code itself does."

### Grade

Judge meaning, not wording. Ignore typos and loose terminology unless they hide a real misunderstanding.

- **Pass**: the core purpose is right, most must-mention points are covered, and nothing material is wrong.
- **Partial**: the gist is right, but a must-mention point that changes behavior is missing, or one detail is wrong.
- **Miss**: the purpose is wrong, a material claim is wrong, the user says they don't know, or the answer is still only parroting after one rephrase request.

**Parroting check.** If the substance of the answer is on the parrot list and adds nothing the code itself shows, don't grade it yet. Say so in one line and ask them to describe what the code does, beyond what the comment says. Do this once per block.

Example:

```python
# retry failed uploads
for attempt in range(3):
    try:
        upload(f)
        break
    except TimeoutError:
        time.sleep(2 ** attempt)
```

- "It retries failed uploads." → parroting: it only restates the comment. Ask them to rephrase.
- "Tries the upload up to three times and stops at the first success. Only a timeout causes another try; other errors go straight up. It waits 1 s after the first timeout, 2 s after the second, 4 s after the third, then gives up silently without raising." → **pass**. It covers what the comment leaves out: only timeouts retry, the growing wait, and the silent failure at the end.
- "Tries three times with a delay." → **partial**. Follow up on which errors cause a retry, or on what happens after the third timeout.

### Respond

- **Pass**: confirm in one or two sentences. Add at most one point they skipped, if it matters. Move on.
- **Partial**: say what was right, then ask one targeted follow-up about the missing piece, pointing to a line ("Look at line 47: what happens when…?"). If they get it, record the block as *pass with help* and move on. If they don't, treat it as a miss.
- **Miss** (or the user types `hint`): give up to two hints. First point to the line that matters, then narrow the question ("What happens when `pct` is 150?"). Let them try again after each hint.
- **Still missing after two hints** (or the user types `explain`): explain the block, then do a teach-back.

### Explain line by line

Go through every line, or every statement for wrapped code. Group trivial lines (closing braces, blank lines).

```
L16  def apply_discount(amount, pct):   takes a money amount and a percentage
L17  """Take a percentage off."""        docstring (it doesn't say what happens outside 0–100)
L18  pct = max(0, min(pct, 100))        clamps pct to 0–100: 150 becomes 100, -5 becomes 0
L19  return amount * (100 - pct) / 100  keeps what's left after the discount: pct 20 → 80% of amount

Before → now: (for modified blocks) what behaves differently
What the comments don't tell you: (the gaps or inaccuracies, if any)
```

Use your own wording, never the comment's. Spend the words on what the comments leave out: conditions, limits, order, data flow, failure paths. Then the **teach-back**: "Now in one or two sentences, in your own words: what does this block do?" Accept a reasonable answer, correct once if needed, record the block as *explained*, and move on.

### Commands

- `hint`: next hint.
- `explain`: skip straight to the line-by-line explanation.
- `skip`: record the block as *skipped* and move on. It still gets explained in the final walkthrough.
- `stop`: go to Step 6 with what's done so far. If blocks are left, offer to save progress first (see "Stopping and resuming").

After each block, show one progress line: `Progress 4/9 · pass 2 · with help 1 · explained 1`.

## Step 6: Wrap up

1. **Scoreboard**: each block with its result. List the *explained* and *skipped* blocks as worth a second look, and offer a second round on just those blocks, now or in a later session. In that round the user has already seen the explanation, so ask for more than a restatement of it: what happens for a specific input, or why a particular line is needed.
2. **Big-picture question** (offer it, don't force it): one question about how the blocks work together, such as "Trace what happens to a cart with one free item and a 20% discount, from `total()` down." Do this only if the change has more than one block that interact.
3. **Annotated walkthrough**: the whole change, block by block in plan order. For each block give the header, the code with line numbers, and the line-by-line explanation. Where the user passed, quote their explanation as **In your words:** and add only what they missed. Skipped and explained blocks get the full explanation.

Offer to save the walkthrough as a Markdown file. Suggest a place outside the repository (for example `~/block-quiz/<repo>-<target>-<date>.md`) so it doesn't end up in a commit, and ask before writing it.

## Stopping and resuming

A quiz can run over several sessions. When the user splits the plan into sessions, types `stop` with blocks left, or wants a second round later, offer to save a progress file beside the walkthrough (`~/block-quiz/<repo>-<target>.progress.json`). Ask before writing it the first time, then update it after every block without asking again.

```json
{
  "repo": "/home/me/src/shop",
  "target": "MR 42",
  "script_option": "--range origin/main...refs/quiz/mr-42",
  "base_sha": "9f2c1ab…",
  "head_sha": "4d7e0c3…",
  "saved": "2026-11-13",
  "blocks": [
    {"n": 1, "file": "cart.py", "lines": "4-13", "symbol": "total()", "kind": "modified", "result": "pass"},
    {"n": 2, "file": "cart.py", "lines": "16-19", "symbol": "apply_discount()", "kind": "new", "result": "explained"},
    {"n": 3, "file": "cart.py", "lines": "22-30", "symbol": "checkout()", "kind": "new", "result": null}
  ],
  "skipped": ["package-lock.json (generated)"],
  "answers": {"1": "Adds up price times quantity and skips free items."}
}
```

- `base_sha` and `head_sha` are the full commit hashes both ends of the change resolve to (`git rev-parse`). For uncommitted or staged work there is no head commit: store `null` and the output of `git diff HEAD | git hash-object --stdin` (add `--cached` for staged) as `diff_hash` instead. For a patch file, store the hash of the file.
- `result` is `pass`, `pass with help`, `explained`, `skipped`, or `null` for a block that hasn't been asked.
- `answers` keeps the user's passing explanations, so the final walkthrough can still quote them as **In your words:**.
- The file holds no answer keys and no descriptions of unanswered blocks. The no-spoiler rule covers it too.

**Resuming** ("continue my quiz", "pick up where we left off"): look in `~/block-quiz/` for a progress file for this repository. With several, ask which one. Then:

1. For an MR or PR, fetch again as in Step 1. Then resolve both ends again and compare them with the saved hashes.
2. **Nothing moved**: rebuild the change map with the saved `script_option`, show the plan with the results so far, and carry on at the first block without a result.
3. **The change moved** (new commits, a rebase, a force-push): say so before anything else. Rebuild the map and cut it into blocks again. A block whose code is identical to before keeps its result. Changed and new blocks are asked again, and blocks that no longer exist are dropped. Show the new plan and what changed in it, then carry on.

When every block has a result and the walkthrough is saved, offer to delete the progress file.

## Edge cases

- **No changes found**: say so, and offer the other targets from Step 1.
- **Only mechanical changes**: say there's nothing to quiz on, and list what changed and why it counts as mechanical.
- **Huge change** (>40 blocks): suggest one directory, one feature or the reading-order top 10, rather than everything.
- **Binary files and images**: list them as skipped.
- **Languages you can't run or verify**: grade only what the code visibly does, and name any assumption you make.
- **The user disputes a grade**: re-read the code. If they're right, say so plainly and change the result. If not, point to the exact line.
