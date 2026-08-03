# Delivery rule

After implementing and testing every fix, rebuild the Windows package with `tools/Build-Windows.ps1 -VisualReviewApproved`, sync the resulting package to `C:\Users\blowb\Desktop\The Fades of Fate Demo`, verify the Desktop and `dist` executable hashes match, then commit and push the finished source and tester artifacts to the active Git branch. Do not report a fix complete while the Desktop build or remote branch is behind.

After completion, merge the finished work into `main`, verify `main` contains the final commit, then delete the completed feature branch and remove its temporary worktree. `main` is the only surviving project branch; never leave completed work stranded on another branch.

For every `v*` tag, `.github/workflows/windows-desktop-release.yml` repeats the package gates on Windows and uploads the complete executable package ZIP to that tag's GitHub Release.
