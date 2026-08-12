# Fades of Fate 2.0 — Agent instructions (binding)

Read **`2.0_CHARTER.md` first**. It wins over any older doc, chat memory, or quarantined FoF1 file.

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

- Prefer small commits on this repo’s `main` (or short-lived branches merged to it).  
- Do not force-push.  
- Do not report FoF1 Desktop hash parity as 2.0 completion.  
- After art review, put review images on the user’s Desktop review folder if they use that workflow; that is for **review**, not FoF1 packaging.

## If you discover FoF1 bleed

1. Stop using the FoF1 path.  
2. Move or leave the bleed in quarantine.  
3. Tell the user what FoF1 surface was touched.  
4. Continue only with allowed 2.0 content + OpenBOR.
