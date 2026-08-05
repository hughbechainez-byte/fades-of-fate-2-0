# Delivery rule

After implementing and testing every fix, commit the focused task changes, reconcile them with the newest `origin/main`, and integrate them into the canonical `main`. Rebuild the Windows package from that exact clean `main` commit with `tools/Build-Windows.ps1 -VisualReviewApproved`, sync the resulting package to `C:\Users\blowb\Desktop\The Fades of Fate Demo`, verify the Desktop and `dist` executable hashes match, then push canonical `main` and verify remote parity. Do not report a fix complete while `main`, the Desktop build, or the remote is behind.

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
After every task, finish the branch cleanup path: commit the exact changed files, fast-forward or merge into `main`, push the result, and remove any temporary task branch only after confirming the commit(s) are preserved on `main` so no work can be overwritten.
If a task adds or changes files, commit and push them to canonical `main` before stopping. Other work elsewhere in the delivery chain is not a reason to leave finished changes uncommitted, unintegrated, or unpushed: isolate the task, reconcile both lines, and complete the delivery safely.

For every `v*` tag, `.github/workflows/windows-desktop-release.yml` repeats the package gates on Windows and uploads the complete executable package ZIP to that tag's GitHub Release.

## Art style rule

All gameplay art is authored and composited on the 640x360 logical canvas. Keep silhouettes, outlines, material accents, and small props crisp with integer-aligned pixels. When an external or high-resolution source is needed, crop its alpha bounds and resize with nearest-neighbor only; never use `smoothscale` for gameplay characters, tents, vehicles, or foreground props. Background vehicles may be compact, but must preserve the same hard-edged palette and deliberate pixel clusters. Add a render-contract test whenever a new asset path is introduced.

### Enemy model rule

Refer to the repository-wide character-art approach as the **rooted whole-cel authored pixel-animation standard**. A requested named enemy model must be a dedicated, manifest-backed sprite actor made from complete pose-integrated source art and registered through the authoritative animation builder and atlas. Sharing AI, timing, or motion structure is allowed; shipping another actor's rendered body with runtime recolors, alpha-bound or centroid-attached `pygame.draw` clothing/anatomy, heuristic weapon erasure, or floating equipment is not a new model. Bake the body, clothing, hands, held gear, lighting, and front/behind occlusion into every cel; keep only released projectiles and transient VFX separate, with authored hand and release anchors controlling continuity. Every registered animation phase must remain a distinct progressive whole-body cel after translation normalization; repeated timing holds do not count as authored poses. Approval GIFs must show production gameplay rendering without reticles, anchors, phase labels, or debug effects; emit any debug-overlay sheets separately. Add render-contract tests for dedicated clip coverage, provenance, unique phase silhouettes, root/ground stability, hand-to-gear attachment, release timing, state/phase distinction, and cell-edge clipping.

## Canonical Main Integration, Build Verification, and Publishing Protocol

Apply this protocol to every task in this repository.

- Begin from the latest canonical `main` and preserve unrelated unfinished work.
- Temporary task branches/worktrees are isolation tools only. Completed work must land on canonical `main`; never substitute a task-branch push for `main` integration.
- Before editing, trace the current implementation and review recent `main` commits touching the same animation, combat, effects, background, enemy, art, gameplay, build, or release subsystem.
- Immediately before committing, integrating, building, and pushing, fetch again and inspect new `origin/main` commits plus active worktree changes that overlap the task.
- When concurrent work has landed, replay or merge the task onto the newest canonical `main`, compare the combined result semantically, and rerun affected tests. Never resolve a conflict by blindly taking all of `ours` or `theirs`.
- Build and publish only from the final integrated canonical `main` commit. Rebuild again if reconciliation changes that commit after an earlier build.
- After verified push parity, remove the completed task's local/remote branch and linked worktree. Keep no stale non-main development line once its commits are preserved on `main`.
- Never leave completed work only on a task branch, detached `HEAD`, temporary worktree, local commit, unpushed `main`, generated package, or Desktop folder.

### Canonical worktree

There must be exactly one designated canonical integration and release worktree for this repository.

- Only that worktree may have canonical `main` checked out.
- Only that worktree may integrate completed task branches, create final integration commits, run official clean builds, run official verification, update public Desktop or Android packages, and push canonical `main`.
- Codex, ChatGPT Work, and human developers must use the same canonical worktree for integration and publishing.

### Required synchronization

Before each job and again before final integration/push:

1. Fetch the newest remote state with pruning.
2. Inspect whether canonical `main` has local unpushed commits or remote commits missing locally.
3. Inspect every active worktree and branch for overlapping files or commits.
4. Verify the canonical worktree is clean and determine the newest canonical `main` commit.
5. Create a unique short-lived `codex/<task>` branch/worktree from that commit when isolation is needed.
6. If the task line already exists, integrate the newest canonical `main` before continuing.
7. Review `main...task` and recent same-subsystem history so newer behavior is retained alongside the task.
8. Resolve conflicts semantically and test the combined behavior; never replace whole files with an older branch snapshot.

### Preserve unrelated unfinished work

- Do not delete, reset, clean, stash, replace, overwrite, stage, or commit unrelated unfinished work.
- A dirty worktree is an isolation problem to solve, not permission to skip commit, integration, build, push, or cleanup.
- Use a clean task worktree, path-specific staging, or patch transfer when changes overlap.
- Do not use broad destructive commands unless the exact scope is proven safe and explicitly authorized.

### Task implementation

- Confirm whether the requested behavior already partially exists before editing.
- Make the smallest coherent change that fully addresses the task.
- Regenerate assets through the authoritative pipeline when needed.
- Test ordinary playable behavior, not only source presence or self-tests.
- Treat unexpected visual or behavioral regressions as blockers.

### Commit and integrate

- Commit every completed job with a descriptive message and verify its exact file/hunk scope.
- Return to the canonical worktree, fetch again, and reconcile any newly landed `main` work before integration.
- Fast-forward, merge, or cherry-pick the focused task commit into canonical `main` without discarding newer changes.
- Never build the official package directly from a task branch or push a task branch as a substitute for canonical `main`.

### Verification, build, publish, and cleanup

- Use the repository's authoritative build-verification scripts and build from the final clean canonical commit.
- Run the staged and Desktop executables, confirm the requested behavior, and verify artifact provenance and hash parity after publication.
- Push canonical `main` without force, fetch it back, and prove local `main`, `origin/main`, package provenance, and Desktop output name the same commit.
- Delete completed non-main remote branches, local branches, and linked worktrees only after their commits are demonstrably preserved or superseded on `main` and all dirty content has been classified.
- Run `scripts/git-worktree-doctor.ps1`, `git worktree list --porcelain`, and local/remote branch inventories after cleanup; the steady state is one canonical `main` worktree and no stale development branches.

### Completion criteria

Do not report success unless implementation, semantic reconciliation with the newest work, commit, canonical integration, verification, artifact rebuild, provenance checks, publication, push-to-main parity, and safe temporary-branch/worktree cleanup are complete.
