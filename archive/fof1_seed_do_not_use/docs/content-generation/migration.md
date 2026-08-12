# Environment manifest migration

The authoring system is intentionally additive. Existing playable levels continue to load `data/gameplay.json`, `data/chapter1_location_lock.json`, and `data/stage_chunks.json` unchanged.

## Safe migration path

1. Generate and validate a recipe with `tools/environment_authoring.py`.
2. Review the preview, source hashes, repetition report, coverage report, native-stage adapter, and collision/entrance/spawn checks.
3. A renderer owner maps `native_stage_world.routes[0]` into a new content-pack route or a new `stage_chunks.json` route. Do not overwrite an existing route in the authoring step.
4. Reconcile the generated chunks with `StageWorld.from_route`, `location_lock`, the route's authored physical-scene objects, encounter gates, and camera zones.
5. Add a render-contract test and a representative screenshot/visual QA checkpoint before any shipping route references the generated manifest.
6. Run the full source self-test, `Render-Route-Scenery-QA.py`, `validate_chapter1.py`, and the Windows/Desktop delivery workflow.

## Native adapter contract

The generated `native_stage_world` keeps the existing layer names (`far_skyline`, `architecture`, `ground`, `near_occluder`), world-space chunk origins, widths, heights, seams, global haze path, and collision IDs. It carries a review description so nobody mistakes it for an already-approved shipping route. It does not invent missing physical objects, encounter queues, location-lock provenance, or runtime art.

## Rollback

Rollback is deletion of the new content-pack reference or generated manifest from the task branch; existing route data and approved assets are untouched. Never roll back by replacing current source art or by editing `The Fades of Fate Demo`, which is derived Desktop output.
