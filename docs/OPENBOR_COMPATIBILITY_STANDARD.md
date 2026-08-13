# OpenBOR 4.0 Build 7949 Compatibility Standard

This is the binding acceptance contract for every new or changed sprite, background, setpiece, model, level, script, and package in Fades of Fate 2.0. Work is not implementation-ready merely because an editor can open it or the PAK builds: every applicable gate below must pass against the pinned Windows runtime in `openbor/runtime/OpenBOR.exe`.

## Engine evidence

- OpenBOR is a sprite-based side-scrolling engine whose module data is parsed at runtime: [official project](https://github.com/DCurrent/openbor).
- The engine accepts non-interlaced 8-bit PNG sprites and permits 24-bit PNG only for backgrounds; its loader reports this contract directly in [`openbor.c`](https://github.com/DCurrent/openbor/blob/e9f5312df0ad26543fd3cf2948adda98dc72a93d/engine/openbor.c#L6227-L6233).
- In high-color video modes, a model takes its palette base from its first frame and assigns that model palette to its loaded sprites: [`openbor.c`](https://github.com/DCurrent/openbor/blob/e9f5312df0ad26543fd3cf2948adda98dc72a93d/engine/openbor.c#L20061-L20090). Therefore all frames for a Fades model must share the exact same palette and index meanings.
- Animation capacity is declared in `data/models.txt`; a model exceeding `maxfreespecials` is rejected by the loader: [`openbor.c`](https://github.com/DCurrent/openbor/blob/e9f5312df0ad26543fd3cf2948adda98dc72a93d/engine/openbor.c#L4328-L4338). Build 7949 exposes eight safe freespecial constants; route clips must be banked into those slots instead of inventing higher constants.
- Current upstream behavior is useful evidence, but Build 7949 is the shipping authority. A command is allowed only after it parses and runs in the pinned executable.

## Entity art-first pose completeness gate

This section is binding for every new entity and every existing entity touched by a task, including playable characters, ordinary enemies, elite enemies, bosses, NPCs, summons, and interactive animated entities. It applies before implementation begins, not merely at release review.

### Classification and exact target

Before any sprite, model, controller, AI, combat, hitbox, VFX, or packaging work begins, record all of the following in the entity's production manifest:

1. Entity classification.
2. Production or explicitly labeled `(alpha)` maturity.
3. One exact required unique-pose count.
4. A per-state pose allocation that reconciles to that exact count.
5. The complete action list and the input, AI, damage, or level event that makes each action reachable.

If any item is unknown, stop and ask the user. A planning range is not permission to stop at an arbitrary number. Once an exact target is selected, it is a hard floor and may not be reduced to fit incomplete art. A target of 220 requires at least 220 valid unique body poses; 219 fails.

The established class bands are:

| Entity class | Preproduction minimum | Production band | Ideal band |
|---|---:|---:|---:|
| Playable hero | 120-160 | 220-320 | 350-500 |
| Basic enemy | 45-70 | 90-130 | Not yet established |
| Elite enemy | Not separately established | 150-240 | Not yet established |
| Boss | 140-200 | 250-400 | Not yet established |

A production target may never be below the lower bound of its production band. If the user or entity manifest selects a higher value within or above the band, that exact value becomes mandatory.

The established per-animation guidance is written as minimum / production / ideal:

| Animation or state | Minimum | Production | Ideal |
|---|---:|---:|---:|
| Idle | 6 | 8-12 | 16-24 |
| Walk | 8 | 12-16 | 24 |
| Run | 8 | 12-16 | 20-24 |
| Start, stop, or pivot | 3 | 4-6 | 6-8 |
| Light attack | 6 | 8-10 | 12-16 |
| Heavy attack | 8 | 10-14 | 16-20 |
| Special | 10 | 14-20 | 24-36 |
| Light hurt | 4 | 5-6 | 8 |
| Heavy hurt | 6 | 7-8 | 10-12 |
| Knockdown | 6 | 8 | 10-12 |
| Grounded/down | 4 | 6-8 | 10-12 |
| Get-up | 6 | 8-10 | 12-16 |
| Jump start | 3 | 4-6 | 6-8 |
| Airborne | 4 | 6-8 | 8-12 |
| Air attack | 6 | 8-10 | 12-16 |
| Landing | 3 | 4-6 | 6-8 |
| Dodge | 6 | 8-10 | 12-16 |
| Grab/throw | 10 | 14-20 | 24-32 |
| Interaction | 6 | 8-10 | 12-16 |
| Victory/defeat | 8 | 10-16 | 20-32 |

These per-animation values are floors for each applicable authored action, not a substitute for the entity's exact total. Extra poses needed to reach the exact total must add meaningful actions, transitions, acting, or motion clarity.

### What counts as one authored pose

A pose counts only when it is a meaningfully distinct, approved, whole-body drawing with a stable pose ID. Count the body before rear/front VFX, shadows, weapons, flames, or contact effects are composited.

The following do not increase the unique-pose count:

- Duplicate pixels or duplicate root-registered silhouettes.
- Reusing one drawing in several clips, routes, phases, or files.
- Mirroring, recoloring, palette swaps, costume variants, or effect variants of an unchanged body.
- Translation, one-pixel jitter, padding changes, root movement, renamed files, aliases, generated copies, or repackaged atlas slots.
- Senseless filler or imperceptible edits made only to satisfy a numeric target.

Reused poses may remain in multiple runtime clips when artistically appropriate, but they count once globally. Exact raster hashes catch identical copies; root-registered alpha/silhouette comparison must flag translated, jittered, or near-duplicate bodies for review. Flagged near-duplicates do not count unless a human review records the meaningful pose difference.

### Art-before-code gate and `(alpha)` exception

The complete production pose target must exist and pass the art audit before normal entity implementation begins. Normal implementation includes model routing, state-machine work, AI, combat, collision, effects integration, and release packaging.

An explicitly declared `(alpha)` entity is the only exception. It may temporarily use fewer poses solely for silhouette, identity, palette, scale, and in-game cohesion review. Its manifest, review evidence, package title, and status report must say `(alpha)`. It may not be called complete, fully authored, production-ready, or used to satisfy a production/release gate. Production work remains blocked until the full exact target exists and passes.

### Mandatory pose, reachability, and timing audit

The repository must provide an automated entity-animation validator, and OpenBOR preflight and PAK builds must invoke it. If that validator does not yet exist when an entity task begins, creating it is prerequisite work; the entity task may not bypass the gate with a manual file count.

For each entity the audit must report:

- Classification, maturity, exact target, total atlas/file slots, and unique approved body-pose count.
- Exact duplicate groups, root-registered silhouette duplicates, and unresolved near-duplicate flags.
- Required and actual counts for every applicable state/action.
- Pose IDs absent from the model, unreferenced by clips, unreachable through runtime state transitions, or absent from packaged gameplay.
- Poses truncated by state duration, presented for zero authored 30 Hz samples, skipped on a 60 Hz simulation, or hidden by an immediate state reset.
- Canvas, palette, root, ground contact, anatomy, and apparent body-scale continuity.
- Full left/right gait contacts, start/stop/pivot transitions, and locomotion phase calibrated to applied displacement rather than input time alone.
- A working input, AI, damage, or level-event trigger for every declared action, with one authoritative animation owner and no native/script competition.
- Per-pose hurtboxes, active hitboxes, startup/active/recovery timing, cancel rules, contact events, hitstop, audio, and VFX alignment. One generic attack box across a bank of unrelated frames is forbidden.
- Source revision, model revision, packaged PAK hash, and paths to the required gameplay evidence.

The audit fails if the unique approved count is below the exact target, a cosmetic/duplicate variant inflated the count, any counted pose is unreferenced or unreachable, any required pose is truncated, gait/root/scale continuity fails, an action has no trigger, or more than one system owns animation selection.

### Required runtime evidence and completion equation

Static atlases, preview GIFs, manifest totals, parser success, and successful PAK creation cannot approve an entity. Packaged gameplay evidence must visibly exercise idle, complete locomotion cycles and transitions, every attack route, jump/landing, hurt, knockdown, get-up, input/AI triggers, contact, hitstop, and stable body scale.

Production approval requires all four measured unique-pose sets to meet the exact target, with no unexplained difference:

`declared target <= unique approved poses = unique referenced pose IDs = unique runtime-reachable pose IDs = unique visibly exercised pose IDs`

Any failure or inequality is a release blocker. Do not describe the entity as fully authored, complete, implemented, or production-ready.

## Character sprites and effects

1. Use non-interlaced, 8-bit indexed PNG (`P`/color type 3), standard PNG compression/filtering, and an explicit transparency entry at palette index 0.
2. Every frame referenced by a single model must contain the identical 256-entry palette. Color index *n* must mean the same RGB color in every frame. Build one master palette from the approved source atlas, then map all frames to it without dithering. Independent per-frame quantization is forbidden.
3. Keep transparent padding truly index 0. Do not encode semitransparent edge pixels; OpenBOR collision and sprite presentation require deterministic hard alpha in this project.
4. Use a stable canvas, ground/root anchor, and `offset` convention within each entity. Bounds are image-local integers: `bbox` must remain inside the frame; every attack box must be intentional, non-negative, and validated on its active frame.
5. Use forward-slash, ASCII, case-stable `data/...` paths in model text. Every referenced file must exist in source and in the final PAK.
6. Define the required native player animations (`spawn`, `idle`, `walk`, pain/fall/rise and the actions actually reachable by controls). Player models must explicitly define a valid `atchain`; never rely on an unverified default attack-chain table. Use only animation names supported by Build 7949. Declare sufficient `maxattacks` and `maxfreespecials` before loading the model.
7. Effects are separate entities/layers. They must never change the fighter body scale, root, canvas contract, or collision geometry. Their palette contract is validated per effect model.

## Backgrounds and setpieces

1. The project baseline is indexed, non-interlaced PNG. Level `background.png` is always indexed. Other background-only images may be RGB/RGBA only where Build 7949 has been launch-tested with that exact directive.
2. Build 7949 underpass stages use indexed 640x360 `panel` sections. Do not use the wide `background` directive for this demo; that combination previously failed after level loading.
3. `panel`, `bglayer`, and `fglayer` paths must exist, use supported argument counts, and be tested for scrolling seams, camera edges, transparency, layer order, and memory behavior.
4. Large setpieces are divided into runtime-tested panels/layers. Source artwork can be larger, but production assets must meet the pinned runtime's proven layout. Never infer compatibility from a still preview.
5. Visual layers cannot silently define gameplay geometry. Walls, holes, platforms, spawn positions, and scroll limits belong in the level data and require a gameplay traversal check.

## Models, levels, and scripts

1. Text files are UTF-8/ASCII-compatible and use Build 7949 commands only. Unsupported or guessed directives are release blockers; `shadow_coords` is explicitly rejected in this project.
2. A state controller may select supported native animation slots and frames, but it must not restart an animation every update. State changes occur on entry; authored pose selection uses the fixed 60 Hz simulation and 30 Hz pose clock.
3. Read entity/contact values only in callbacks where Build 7949 supplies them. Confirmed hit callbacks latch hitstop once; visual effects do not authoritatively decide combat contact.
4. Model references, animation counts, frame paths, level-order references, scene references, and script imports must resolve before packaging. Parser success alone is insufficient: the level must spawn the entity and execute controller ticks.
5. Keep the full model and compatibility probes separate. Never ship a reduced shim while claiming the authored model passed.

## Packaging and mandatory gates

Run these in order after any relevant change:

1. `python tools/Build-OpenBOR-Black-Dave.py` when Black Dave source art/model routing changes.
2. `python tools/Preflight-OpenBOR-Assets.py --data openbor/data` — validates PNG structure, transparency, one palette per model, video syntax, and rejected directives.
3. `python tools/Build-OpenBOR-Package.py` — runs preflight, writes the PAK, and verifies every packaged payload against source.
4. Launch the pinned executable from a clean package directory containing only the intended sibling `Paks/` package. No loose `data/` directory may shadow the PAK.
5. Pass a sustained gameplay run after the level reports loaded and the player reports spawned. Reject any nonzero exit, access violation, parser warning, missing asset, script compile/runtime error, or early log termination.
   A surviving process is only the crash gate: a visible non-black gameplay capture is still required for visual approval.
6. Capture actual gameplay evidence showing spawn, idle, directional movement, jump/land, attacks, contact/hitstop, hurt/fall/rise, setpiece traversal, and stable rendering. Build success or atlas review alone cannot approve the work.
7. Record runtime build, source commit, PAK hash, file count, launch result, log result, and gameplay evidence paths in the build manifest. Push only the intentionally scoped files and verify remote SHA parity.

## Definition of ready

Art is ready for implementation only when its file format, shared palette, transparency, canvas/root convention, model routing, collision metadata, and preflight pass are complete. Code is ready only when it uses Build 7949-supported slots/callbacks and survives gameplay. A setpiece is ready only when its packaged layers render and traverse correctly in the pinned runtime. If an entity classification, animation slot, directive, or format is unclear, stop and ask before producing dependent work.
