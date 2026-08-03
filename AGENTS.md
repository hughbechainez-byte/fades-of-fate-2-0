# Delivery rule

After implementing and testing every fix, rebuild the Windows package with `tools/Build-Windows.ps1 -VisualReviewApproved`, sync the resulting package to `C:\Users\blowb\Desktop\The Fades of Fate Demo`, verify the Desktop and `dist` executable hashes match, then commit and push the finished source and tester artifacts to the active Git branch. Do not report a fix complete while the Desktop build or remote branch is behind.

## Permanent workflow

- Before every task, locate the repo root, run `git fetch --all --prune`, `git worktree list --porcelain`, and `git status --short --branch`, then identify which worktree owns `main`.
- Never check out `main` in a secondary worktree.
- Never treat `C:\Users\blowb\Desktop\The Fades of Fate Demo` as editable source.
- Never touch unrelated dirty files.
- If the current worktree has unrelated unfinished work, create a clean task branch or task worktree from the latest `origin/main` instead of editing that work directly.
- Use `scripts\git-worktree-doctor.ps1` to audit worktree safety before and after task work.
- Start tasks from `origin/main` on a unique `codex/<task>` branch and keep the branch name unique.
- Finish tasks by integrating through the canonical `main` worktree, pushing without force, and refreshing the Desktop build from that final `main`.
- Keep `BUILD_SOURCE_COMMIT.txt` in the packaged build; it must record commit SHA, branch, UTC timestamp, source path, and whether the source tree was clean.
- Safe repo-local defaults are `pull.ff=only`, `fetch.prune=true`, and sensible upstream setup for new branches.

For every `v*` tag, `.github/workflows/windows-desktop-release.yml` repeats the package gates on Windows and uploads the complete executable package ZIP to that tag's GitHub Release.
