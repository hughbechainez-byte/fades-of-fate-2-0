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

## Playable entity combat demo

The combat-first Build 7949 module is committed at
`releases/entity_tech_demo/TheFadesOfFate2_EntityTechDemo.pak`. Put it in the
`Paks/` folder beside the pinned `OpenBOR.exe`; the package manifest records the
required executable and PAK hashes.

- Black Dave: 220 unique authored poses
- Homeless Man: 120 unique authored poses
- Police Officer: 120 unique authored poses
- All runtime poses use indexed 192×160 sprites with one shared palette per entity
- Combat starts immediately on the verified panel-only I-8 underpass stage

Regenerate and validate with:

```powershell
python -B tools/Build-OpenBOR-Entity-Art.py
python -B tools/Build-OpenBOR-Black-Dave.py
python -B tools/Build-OpenBOR-Enemies.py
python -B tools/Build-OpenBOR-Entity-Tech-Demo.py
python -B tools/Validate-OpenBOR-Entities.py --stage implementation
python -B tools/Build-OpenBOR-Package.py --runtime-exe C:\path\to\OpenBOR.exe
```

The executable is not redistributed. The committed demo PAK was launch-tested
with the exact Build 7949 executable recorded in its manifest.

## Rules

See repo root `2.0_CHARTER.md` and `AGENTS.md`. No FoF1 models/settings/structure without explicit owner request.
