# Delivery rule

After implementing and testing every fix, rebuild the Windows package with `tools/Build-Windows.ps1 -VisualReviewApproved`, sync the resulting package to `C:\Users\blowb\Desktop\The Fades of Fate Demo`, verify the Desktop and `dist` executable hashes match, then commit and push the finished source and tester artifacts to the active Git branch. Do not report a fix complete while the Desktop build or remote branch is behind.

After every task, finish the branch cleanup path: commit the exact changed files, fast-forward or merge into `main`, push the result, and remove any temporary task branch only after confirming the commit(s) are preserved on `main` so no work can be overwritten.

For every `v*` tag, `.github/workflows/windows-desktop-release.yml` repeats the package gates on Windows and uploads the complete executable package ZIP to that tag's GitHub Release.
