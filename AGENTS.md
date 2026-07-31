# Delivery rule

After implementing and testing every fix, rebuild the Windows package with `tools/Build-Windows.ps1 -VisualReviewApproved`, sync the resulting package to `C:\Users\blowb\Desktop\The Fades of Fate Demo`, verify the Desktop and `dist` executable hashes match, then commit and push the finished source and tester artifacts to the active Git branch. Do not report a fix complete while the Desktop build or remote branch is behind.
