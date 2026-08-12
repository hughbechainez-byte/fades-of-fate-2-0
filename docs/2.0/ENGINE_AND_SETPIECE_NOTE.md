# Engine note — underpass setpiece

## What system produced the underpass setpiece lookdev?

**The original FoF1 Pygame engine** (quarantined under `archive/fof1_seed_do_not_use/`), used temporarily as an art compositor:

- `draw_stage_background` / backdrop / atmosphere ambient
- Not OpenBOR

## What is the 2.0 shipping engine?

**OpenBOR** — see `openbor/` and `2.0_CHARTER.md`.

The underpass plates and life direction must be **rebuilt / re-authored into OpenBOR** as the real playable stage. Do not ship the Pygame capture path as 2.0.
