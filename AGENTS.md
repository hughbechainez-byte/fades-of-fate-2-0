# Fades of Fate 2.0 — Agent instructions (binding)

Read **`2.0_CHARTER.md` first**. It wins over any older doc, chat memory, or quarantined FoF1 file.

## Mandatory task-specific standards

- Before starting any model, character, entity, animation, combat, collision, or combat-VFX work, read **`docs/OPENBOR_ENTITY_PIXEL_ART_AND_ANIMATION_STANDARD.md`** completely.
- Before starting any stage, level, background, setpiece, parallax, environmental-art, traversal, or stage-geometry work, read **`docs/OPENBOR_LAYERED_2_5D_STAGE_CREATION_STANDARD.md`** completely.
- If a task touches both areas, read both standards before planning, editing, generating assets, scripting, or testing. These task-specific standards supplement **`docs/OPENBOR_COMPATIBILITY_STANDARD.md`**; all applicable gates remain binding.

## Stop before any entity work: mandatory art gate

Before creating or changing any playable character, enemy, elite, boss, NPC, summon, or interactive animated entity, read **`docs/OPENBOR_COMPATIBILITY_STANDARD.md`**, especially **Entity art-first pose completeness gate**. This applies to new entities and existing entities touched by a task.

- Determine and record the entity class, production or `(alpha)` maturity, one exact unique-pose target, per-state allocation, and complete action/reachability list. If any item is unclear, stop and ask the user before doing art or code.
- Established production bands are playable hero `220-320`, basic enemy `90-130`, elite enemy `150-240`, and boss `250-400`; lower preproduction bands do not satisfy production. The selected exact target is mandatory and may not be reduced later.
- A pose count means unique, approved, whole-body drawings. Atlas slots, filenames, aliases, mirrored/recolored frames, VFX variants, translations, jitter, padding changes, and reused drawings do not increase the count.
- Except for an explicitly labeled `(alpha)` cohesion prototype, the complete art target and automated uniqueness audit must pass before model, controller, AI, combat, collision, VFX, or package implementation begins.
- `(alpha)` work must remain labeled in its manifest, evidence, package, and report. It cannot be called complete, fully authored, production-ready, or used to pass a release gate.
- Before implementation, before every PAK build, and after runtime integration, fail on duplicate inflation, missing references, unreachable poses, truncated/zero-duration poses, incomplete gait transitions, root/anatomy/scale drift, dead controls/AI triggers, generic bank-wide hitboxes, or native/script dual animation ownership.
- Do not approve or report completion until the declared target, unique approved count, unique referenced-pose count, unique runtime-reachable-pose count, and unique visibly exercised packaged-gameplay-pose count all reconcile and meet the exact target.

## Source of truth

- **Repo:** `https://github.com/hughbechainez-byte/fades-of-fate-2-0`  
- **Branch:** project `main` on this remote only  
- **Not source of truth:** `the-fades-of-fate`, Desktop FoF1 Demo folders, old agent chats that assumed FoF1

## Engine: OpenBOR (ground-up)

- Develop **2.0 on OpenBOR**, not on the original Pygame demo engine.  
- Place OpenBOR project work under `openbor/`.  
- Do **not** resume FoF1 `src/game.py` / `pixel_art` / location-lock as the product path.  
- Art may be authored and reviewed as stills/GIFs; shipping gameplay targets OpenBOR.

## Hard ban: original game content

Unless the user **explicitly** requests original-game material, you must **not**:

| Banned | Examples |
|--------|----------|
| Models / art | FoF1 atlases, sedans, Couch, enemy roster, Chapter 1 plates |
| Settings / data | FoF1 `gameplay.json` campaign, Couch bosses, FoF1 atmosphere as product |
| Structure | Four-level Chapter 1 lock, FoF1 validators forcing Couch-in-last-level |
| Systems | FoF1 ambient traffic cars, FoF1 location-lock as default scenery |
| Delivery | FoF1 Windows Desktop package rules as 2.0 completion criteria |

If a task would be “easier” by reusing FoF1, **stop and build ground-up** or ask the user.

## Current content scope (do not expand unprompted)

Only this is in-scope for active development:

1. **Black Dave authored poses** (under `content/characters/black_dave/`)  
2. **First setpiece / backdrop** — I-8 underpass ground-up work (under `content/setpieces/underpass_i8/`)

No other characters, levels, bosses, or systems until the user asks.

## Quarantine path

`archive/fof1_seed_do_not_use/` — entire original-demo seed.  

- Do not edit for features.  
- Do not import assets from it without explicit user order.  
- Do not run it as “the game” for 2.0 deliverables.

## Workflow

- Read **`docs/OPENBOR_COMPATIBILITY_STANDARD.md` before creating or changing any OpenBOR sprite, background, setpiece, model, level, script, or package. No such work is complete until every applicable gate in that standard passes.**
- All frames belonging to one character model must use one identical 256-entry indexed palette, with palette index 0 reserved for transparency. Never quantize animation frames independently.

- Prefer small commits on this repo’s `main` (or short-lived branches merged to it).  
- Do not force-push.  
- Do not report FoF1 Desktop hash parity as 2.0 completion.  
- After art review, put review images on the user’s Desktop review folder if they use that workflow; that is for **review**, not FoF1 packaging.
- Before every OpenBOR PAK or desktop build, run `python tools/Preflight-OpenBOR-Assets.py --data openbor/data`. Character sprites must be non-interlaced 8-bit indexed PNGs; backgrounds may use the documented background formats.
- Preflight must require every level `background.png` to be non-interlaced 8-bit indexed PNG and require `data/video.txt` to contain exactly one parser-compatible `video WIDTHxHEIGHT` directive; reject shorthand tokens such as `a1280x720`.
- The PAK builder must run the preflight before and after packing with `--pak`; verify source payload hashes, package entries, and file counts so stale or manually copied PAKs cannot pass.
- Reject unsupported OpenBOR directives such as `shadow_coords` before launch. Use only directives accepted by the pinned runtime, and record the runtime/build in the package manifest.
- A desktop launch check is incomplete unless the executable is started from its package directory, the sibling `Paks/` file is selected, and the log is checked for asset-load errors.
- The Build 7949 underpass free-walk demo must use indexed 640×360 `panel` assets; do not ship the wide `background` directive in that demo because this runtime crashes after level load. Quarantine any old loose Desktop `data/` tree so it cannot shadow the verified PAK.

## If you discover FoF1 bleed

1. Stop using the FoF1 path.  
2. Move or leave the bleed in quarantine.  
3. Tell the user what FoF1 surface was touched.  
4. Continue only with allowed 2.0 content + OpenBOR.
