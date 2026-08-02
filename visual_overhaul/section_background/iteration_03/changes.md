# Background iteration 3

Release: `v0.15.8-canonical-visual-overhaul-r6` at `5da9760a569a1e5277d0f3c082f5aa3c095e633b`.

- Finalized the far, mid, world, ground, foreground, and world-locked lighting order in `src/pixel_art.py`.
- Added restrained perspective ground cues, cached lighting integration, and two-wheel vehicle contact shadows without covering authored texture.
- Preserved combat readability while keeping the detailed panorama, animated atmosphere, and proportional route-specific cars.
- Added regression checks for the complete ground/depth/lighting composite and Pillow-free runtime validation, corrected the pinned toolchain's Pygame prebuild ordering, and made CI reject unresolved native SIMD calls before release.

Clean-gate result: 13/13 visual checks, 116/116 self-test checks, no fallback assets, and identical PC/Android manifests.

Android release run `30751550865`: exact `0.15.8` ARM64 APK reached ordinary gameplay on the clean API 35 emulator with zero fatal-log matches; the fixed proof scene visibly confirms the calibrated car-to-character scale.
