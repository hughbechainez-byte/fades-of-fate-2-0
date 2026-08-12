# Background iteration 1

Release: `v0.15.3-background-detail-r6` at `55bb5e120d79978b807b76420b65b7b5eebe157a`.

- Restored the four authored detailed panoramas and made them authoritative in `src/backdrop.py`, `src/pixel_art.py`, and `data/chapter1_location_lock.json`.
- Removed the global floating landmark-label overlay from `tools/build_chapter1_location_art.py`; regenerated all four `ch1_l*_main_v2.png` assets without airborne boxes.
- Reduced parked vehicles to a bounded `0.72` far-apron scale and added validation in `src/location_lock.py`.
- Added one-root content resolution, runtime asset hashes/provenance, deterministic shared PC/Android packages, and refuse-to-release gates.
- Android correction: the local Pygame recipe applies its source patch before the pinned toolchain generates `Setup`, links the ARM64 SIMD fallbacks, audits the actual ARM bundle, and performs location validation through packaged Pygame rather than unbundled Pillow.

Evidence was captured from a clean checkout; no fallback or noncanonical assets were active.

Android release run `30751537514`: exact `0.15.3` ARM64 APK installed on the clean API 35 emulator, reached gameplay through ordinary touch input, and produced zero fatal-log matches.
