# Environment authoring audit

Audit baseline: `origin/main` `8c3bca14d586003badac1cf3f44891f90c5ec179`, 2026-08-06.

## Runtime contracts

- Engine: Pygame CE/SDL2. `src/config.py` defines the 640x360 logical canvas and loads UTF-8/BOM-safe JSON from `data/gameplay.json`.
- Simulation: `src/game.py::FadesGame` owns campaign state, encounter gates, stage content, prop interaction, and `_draw_gameplay`. It uses fixed 60 Hz simulation and the existing draw/depth pipeline.
- World coordinates: `src/world_engine.py::WorldPoint` stores stage X, floor depth, and elevation. `BeatEmUpProjection` maps floor contact to screen pixels with `chapter1_oblique_v2`; sprites remain constant-size billboards and snap to integer pixels.
- Navigation/collision: `src/world_engine.py::WalkableRegion`, `RectObstacle`, and `StageGeometry` own rails, clamping, swept movement, and obstacle resolution. `src/combat_engine.py` owns combat AABBs and push bodies.
- Camera: `src/world_engine.py::CameraDirector` and `CameraZone` follow human-controlled party targets. Existing camera locks live in `data/gameplay.json`.
- Chunked scenery: `src/stage_world.py::StageWorld`, `StageChunk`, `StageLayerPiece`, and `StageSpawnMarker` load `data/stage_chunks.json`. The required native layers are `far_skyline`, `architecture`, `ground`, and `near_occluder`; world width and chunk seams are validated before drawing.
- Location lock: `src/location_lock.py` validates `data/chapter1_location_lock.json`, route widths, landmark order, physical scene objects, source metadata, and approved panorama/chunk paths.
- Backdrop/atmosphere: `src/backdrop.py` composites world-aligned route layers; `src/atmosphere.py` loads `data/atmosphere.json` and advances three independently phased cloud bands with route-specific parallax.
- Authored props: `src/pixel_art.py::draw_stage_prop` is the existing native presentation for planters, carts, bollards, cones, and other stage props. `src/game.py` connects these records to collision, damage, drops, and depth sorting.

## Existing data and commands

- Route/campaign/rails/encounters: `data/gameplay.json`.
- Location and source provenance: `data/chapter1_location_lock.json`.
- Chunk layer topology: `data/stage_chunks.json`.
- Atmosphere profiles and parallax factors: `data/atmosphere.json`.
- Approved authored scenery: `assets/stage/chapter1_location_locked/`, including its chunk panels and route-specific source records.
- Narrow tests: `python -m unittest tests.test_world_engine tests.test_stage_world tests.test_location_lock -v`.
- Full source validation: `python -m unittest discover -s tests -v` and `python -m src.main --self-test`.
- Scenery/projection gates: `python tools/Render-Projection-Calibration.py --project-root . --output-dir build/projection-calibration`, `python tools/Render-Route-Scenery-QA.py --visual-review-approved`, and `python tools/validate_chapter1.py --output build/chapter1_validation_build.json`.
- Official Windows delivery: `powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\Build-Windows.ps1 -VisualReviewApproved`.

## Authoring-system boundary

`src/environment_generation.py` composes approved assets and existing engine-authored sources into a deterministic manifest. It does not replace `FadesGame`, `StageWorld`, `StageGeometry`, the camera, the renderer, or shipping level JSON. Its `native_stage_world` field is shaped for review/migration into `StageWorld`; it is intentionally not auto-installed into the four playable routes.

Sources are checked in under `data/content-generation/`:

- `style_profiles.json`: the shared `fades_environment_v1` ArtStyleProfile, explicit file allowlist, denied-art patterns, native projection/pixel rules, palettes, density, parallax, and occlusion budgets.
- `modules.json`: manifest-backed environment modules. File modules reference current approved scenery PNGs. Interactive/foliage modules reference the existing `draw_stage_prop` implementation rather than inventing replacement art.
- `recipes/`: lower-cost-authored scene intent and zone grammar.
- `generated/`: reproducible manifests, seed-variation reports, validation reports, and the approved-asset analysis output. Regenerate these with the CLI; do not hand-edit them.

## Allowlist and denylist

The allowlist is the exact `approved_assets` array in `data/content-generation/style_profiles.json` plus the exact `approved_engine_sources` array. A file is rejected if it is outside `assets/`, absent from the array, missing on disk, dimension-mismatched, or matched by a denied pattern. Denied patterns intentionally include `placeholder`, `debug`, `legacy`, `obsolete`, `old_`, `source_concept`, and `preview`. No screenshot reference is in the runtime or authoring allowlist.

## Known coverage boundary

The current approved library has authored chunk scenery, ground, near framing, and native interactive planter/cart/bollard paths. It does not yet have standalone module-backed vehicles, trees, bushes, signs, or light fixtures. The generator reports those exact families as missing instead of fabricating geometry or silently selecting an old asset.
