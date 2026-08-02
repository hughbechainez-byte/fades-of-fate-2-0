# Background iteration 2

Release: `v0.15.4-background-life-r5` at `f464aa75dbdea4026e3854390a45686aec66e5e8`.

- Added four route-specific vehicle models with distinct colors, facing, wear, decals, roof rack, and window details in `data/chapter1_location_lock.json` and `src/pixel_art.py`.
- Added deterministic far traffic, moving paper, mist, wash spray, underpass lights, Revive neon, crowd motion, and birds tied to the 30 Hz atmosphere clock.
- Added anti-repetition and model/scale validation in `src/location_lock.py` and `tools/build_content_release.py`.
- Kept all animated layers world/depth anchored and cached reusable ambient surfaces to remain under budget.
- Android correction: applied Pygame's source patch before `Setup` generation, retained joystick input, audited the actual ARM bundle, and removed the unbundled Pillow dependency from runtime scene validation.

Evidence was captured from a clean checkout; no fallback or noncanonical assets were active.

Android release run `30751545485`: exact `0.15.4` ARM64 APK installed on the clean API 35 emulator, reached gameplay through ordinary touch input, and produced zero fatal-log matches.
