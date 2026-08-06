# Lower-cost environment authoring contract

The lower-cost model is a constrained content author. It edits recipes, approved module metadata, content-pack manifests, pack documentation, and tests directly associated with a recipe. It must not edit `src/game.py`, `src/world_engine.py`, `src/stage_world.py`, `src/backdrop.py`, `src/pixel_art.py`, collision/combat code, asset-loader internals, build scripts, shipping route data, art allow/deny rules, or validation thresholds.

All authored file paths must already be in the style-profile allowlist. Do not crop screenshots, add screenshot files, invent placeholder art, use smooth scaling, or hand-edit generated manifests.

## Exact commands

Run from `C:\Users\blowb\Desktop\the-fades-of-fate` or an isolated task worktree:

```powershell
python tools/environment_authoring.py list-modules --style-profile fades_environment_v1
python tools/environment_authoring.py inspect-module civic_hall_architecture
python tools/environment_authoring.py validate-library --style-profile fades_environment_v1
python tools/environment_authoring.py analyze-assets --style-profile fades_environment_v1 --output data/content-generation/generated/approved_asset_analysis.json
```

Create a recipe from a proof template, then edit only the recipe source:

```powershell
python tools/environment_authoring.py save-recipe --template civic --output data/content-generation/recipes/my_civic_scene.json
python tools/environment_authoring.py validate-recipe --recipe data/content-generation/recipes/my_civic_scene.json
```

Generate, reroll, validate, and preview without touching the game runtime:

```powershell
python tools/environment_authoring.py bake --recipe data/content-generation/recipes/my_civic_scene.json --seed 4242 --output data/content-generation/generated/my_civic_scene_manifest.json --preview build/content-generation/my_civic_scene_preview.png
python tools/environment_authoring.py compare-seeds --recipe data/content-generation/recipes/my_civic_scene.json --seeds 4242 4243 4244 --output data/content-generation/generated/my_civic_scene_seed_variations.json
python tools/environment_authoring.py validate-manifest --recipe data/content-generation/recipes/my_civic_scene.json --manifest data/content-generation/generated/my_civic_scene_manifest.json
```

Reroll one zone while preserving the recipe and seed contract:

```powershell
python tools/environment_authoring.py bake --recipe data/content-generation/recipes/my_civic_scene.json --seed 4242 --zone hall_garden --output build/content-generation/my_civic_scene_hall_garden_reroll.json --preview build/content-generation/my_civic_scene_hall_garden_reroll.png
```

Run the focused tests and then the normal game/build gates:

```powershell
python -m unittest tests.test_environment_generation -v
python -m unittest discover -s tests -v
python -m src.main --self-test
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\Build-Windows.ps1 -VisualReviewApproved
```

The current runtime has no unsafe `--load-generated-scene` flag. The exact debug-safe opening command is the `--preview` command above; it produces a native-resolution contact sheet plus a `native_stage_world` adapter for review. Do not copy that adapter over `data/stage_chunks.json` or launch it as a shipping route until the migration checklist has been completed by a renderer owner.

## Required authoring behavior

- Keep `seed`, `version`, `style_profile`, `target_length`, zones, sockets, budgets, and clearances explicit.
- Use approved module IDs, not raw asset paths invented inside a recipe.
- Keep entrances, exits, spawn markers, encounter lanes, and camera lock areas clear.
- Use authored/native interactive modules for breakables and foliage; do not create rectangles as shipping content.
- Run validation after every recipe change. Errors identify the recipe/module/field and rule.
- Review the preview and the generated `repetition_report`, `coverage`, `source_attribution`, and `native_stage_world` before requesting integration.
