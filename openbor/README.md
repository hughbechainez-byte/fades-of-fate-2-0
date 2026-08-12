# OpenBOR project root (Fades of Fate 2.0)

Ground-up OpenBOR target.

## Layout (conventional)

| Path | Purpose |
|------|---------|
| `data/` | `game.txt`, models.txt, levels list, etc. |
| `chars/` | Playable / NPC entity folders |
| `levels/` | Stage definitions |
| `scenes/` | Intros, menus, cutscenes |
| `scripts/` | OpenBOR script files |

## Current Black Dave package

The first native package is generated under `data/chars/black_dave/` from the approved source in `../content/characters/black_dave/`:

- 220 authored rooted frame PNGs on a 224×160 canvas
- 44 manifest clips and 50 named `anim` blocks
- 21 combat-route steps mapped in `black_dave_combat_routes.json`
- `cool_underpass_dusk_v1` grade retained in the package metadata
- I-8 underpass art localized under `data/levels/i8_underpass/`

Regenerate and validate with:

```powershell
python tools/Build-OpenBOR-Black-Dave.py
python tools/Validate-OpenBOR-Black-Dave.py
```

The repository does not currently include an OpenBOR executable/toolchain, so validation here proves native package structure, source provenance, frame integrity, animation registration, route coverage, and setpiece localization. Engine boot/combat capture remains the next gate once a local OpenBOR runtime is supplied.

## Rules

See repo root `2.0_CHARTER.md` and `AGENTS.md`. No FoF1 models/settings/structure without explicit owner request.
