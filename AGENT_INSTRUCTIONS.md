Use this as the standing project-wide instruction for Codex:

# PROJECT-WIDE TASK COMPLETION, VERSION CONTROL, AND BUILD POLICY

Apply these rules to every task performed in this project unless I explicitly override them in my latest message.

## Core requirement

A task is not complete merely because source files were edited or tests passed. Every completed task must result in:

1. Verified source changes.
2. Relevant tests and validation.
3. A task-specific Git commit.
4. A successful push to the designated remote branch.
5. A freshly rebuilt and refreshed playable desktop build.
6. A final report containing exact commit and build information.

Do not leave completed fixes only as uncommitted local changes. Do not allow the playable Desktop copy to remain on an older revision after source changes are completed.

## Canonical source and packaged builds

Before editing:

1. Identify the canonical Git source checkout.
2. Confirm the repository root, current branch, remote, and current commit.
3. Never edit a packaged Desktop build, exported build, generated output folder, release directory, installed application, or copied runtime unless the project specifically defines that location as source.
4. Treat the canonical source as the only authoritative place for code and asset changes.
5. Treat Desktop builds and other packaged outputs as disposable products generated from canonical source.

If the initial directory is not a Git repository, locate the canonical source rather than making changes in the packaged copy.

## Existing unrelated work

Unrelated uncommitted work is not a reason to stop, skip the commit, skip the push, or skip the build.

Before starting each task:

1. Inspect `git status`, staged changes, unstaged changes, untracked files, and relevant diffs.
2. Record which files and changes existed before the task.
3. Preserve all pre-existing unrelated work exactly as found.
4. Do not delete, overwrite, revert, reset, clean, stash, stage, commit, reformat, or otherwise disturb unrelated unfinished work.
5. Do not use broad destructive commands such as:
   - `git reset --hard`
   - `git clean -fd`
   - blanket checkout/restore commands
   - indiscriminate staging with `git add .` or `git add -A`
6. Do not silently include unrelated changes in the task commit.

Use the safest isolation method available, such as:

- A dedicated Git worktree created from the correct branch.
- A task-specific branch.
- Path-specific staging.
- Patch-based transfer of only the task’s changes.
- Selective commits containing only files or hunks belonging to the current task.

Prefer a clean dedicated worktree when the main checkout contains overlapping or difficult-to-separate unfinished work.

## Overlapping files

If the task requires editing a file that already contains unrelated uncommitted changes:

1. Preserve the existing edits.
2. Identify the exact pre-task version of the file and the unrelated diff.
3. Make only the minimum task-specific additions.
4. Separate the task’s hunks from unrelated hunks through patch staging, a temporary worktree, or another non-destructive method.
5. Commit only the task-specific changes.
6. Confirm that the unrelated edits remain present and unmodified afterward.

Do not refuse to complete the task solely because the same file has unrelated edits. Carefully isolate the task-specific patch.

## Task execution

For each request:

1. Restate the concrete acceptance criteria internally.
2. Trace the relevant runtime path before editing.
3. Implement the smallest complete fix that satisfies the request.
4. Update all necessary code, assets, manifests, generated data, tests, and documentation.
5. Avoid unrelated refactors and formatting churn.
6. Confirm that generated assets correspond to their authoritative source assets.
7. Test the actual behavior, not merely the existence of code.

For visual, animation, gameplay, audio, or UI tasks, inspect the result in the running game or application. Static file inspection and unit tests alone are insufficient.

## Validation

Run the narrowest relevant checks first, followed by broader validation when practical.

At minimum:

1. Run task-specific tests.
2. Run relevant subsystem tests.
3. Build the application from canonical source.
4. Launch or inspect the fresh build.
5. Verify the requested behavior in the actual playable build.
6. Clearly distinguish:
   - New failures caused by the task.
   - Pre-existing failures.
   - Unrelated failures.
7. Do not claim success when the requested behavior was only inferred rather than observed.

A pre-existing unrelated test failure does not automatically block committing, pushing, or refreshing the build. Document it accurately and ensure the task did not worsen it.

## Commit policy

After validation:

1. Review the final diff.
2. Stage only the current task’s files or hunks.
3. Never use blanket staging in a dirty checkout.
4. Create one focused commit for the completed task.
5. Use a clear commit message describing the user-visible fix or improvement.
6. Verify the commit contents immediately after committing.
7. Confirm no unrelated files or hunks entered the commit.
8. Confirm pre-existing unrelated work remains intact.

If the task naturally requires multiple atomic commits, keep them narrowly scoped and explain why.

## Push policy

After committing:

1. Push the task commit to the designated remote branch.
2. If working on a temporary branch or worktree, integrate the task commit into the designated project branch using the safest non-destructive method.
3. Push the final designated branch.
4. Verify that the remote contains the new commit.
5. Report the remote branch and commit hash.

Do not say the task is done while the completed changes exist only locally.

Do not force-push, rewrite shared history, or overwrite remote work unless I explicitly direct you to do so.

If the remote branch has moved:

1. Fetch the latest remote state.
2. Reconcile safely.
3. Preserve both remote work and unrelated local work.
4. Resolve only conflicts relevant to the task.
5. Re-run validation before pushing.

## Desktop build refresh

After every completed task:

1. Produce a new desktop build from the committed canonical source.
2. Ensure the build embeds or records the current commit, version, content revision, or build timestamp where supported.
3. Replace or refresh the designated Desktop playable build using a safe staged deployment:
   - Build into a temporary output directory.
   - Validate that the build completed.
   - Confirm required executable and asset files exist.
   - Preserve user saves, settings, logs, and other persistent data.
   - Atomically replace or refresh only the packaged application files.
4. Do not edit the Desktop build manually.
5. Remove or clearly archive stale outputs that could be mistaken for the newest build, without deleting user data or unrelated development work.
6. Launch the refreshed Desktop build.
7. Verify that it is running the newly committed revision.
8. Verify the requested change inside that build.

The Desktop copy must never silently point to an older source revision after a task is marked complete.

## Other platform builds

When the project includes Android or another maintained counterpart:

1. Propagate shared code and content changes through the established cross-platform pipeline.
2. Build the corresponding debug artifact after each task unless I explicitly limit the task to desktop only.
3. Confirm the secondary build uses the same intended content revision.
4. Report its exact output path and version.
5. Do not let the desktop and secondary platform silently diverge.

Do not claim platform parity unless both builds were actually produced and checked.

## Handling build or push failures

If commit, push, or build fails:

1. Diagnose and attempt to fix the failure.
2. Do not undo unrelated work.
3. Preserve the completed task patch and commit whenever possible.
4. Report the exact command, error, affected stage, and current repository state.
5. Continue completing every stage that remains safely possible.
6. Do not replace a required stage with a vague statement such as “not performed due to unrelated work.”

Unrelated uncommitted work is an isolation problem to solve, not a stopping condition.

Only stop short of committing or pushing when there is a concrete, unavoidable safety issue such as unavailable credentials, an inaccessible remote, a genuine unresolved conflict, or a failing build that would make publication misleading. Explain the precise blocker and leave the repository in a recoverable state.

## Required final report

At the end of every task, provide:

- Summary of the implemented change.
- Canonical repository path.
- Branch used.
- Files changed for this task.
- Tests run and results.
- Pre-existing unrelated failures, if any.
- Commit hash and commit message.
- Remote and branch pushed.
- Desktop build output path.
- Desktop build revision/version.
- Confirmation that the refreshed desktop build was launched.
- Actual runtime behavior verified.
- Android or secondary artifact path and revision, when applicable.
- Confirmation that unrelated unfinished work remains untouched.
- Remaining blockers or risks.

Never end with only “files edited,” “tests passed,” or “no commit/push/release due to unrelated changes.”

## Definition of done

A task is done only when the change is implemented, validated in the real application, committed without unrelated work, pushed, rebuilt into the current Desktop version, and clearly reported.

Maintain one clear chain of custody:

User request → canonical source change → validation → isolated commit → push → fresh build → runtime verification → final report.
