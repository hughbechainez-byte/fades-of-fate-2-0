# Living underpass setpiece — review package (ground-up)

**Status:** pending human approve / request-edits  
**Owner:** setpiece development (2.0)  
**Scope:** scenery only — no characters, no enemies, **no FoF1 vehicle models**

## Correction note

An earlier review drop mixed **2.0 lookdev targets** with **legacy FoF1 location-lock engine frames** (different art, candy colors, old ambient cars). That package was archived on Desktop under  
`_archive_mismatched_fof1_engine_captures/`.

## What you are reviewing now

Living ambient composited onto the **cleaned 2.0 underpass target still** (same aesthetic as the first approved lookdev photos):

- birds, mist, foliage sway, soft warm practicals, paper/dust  
- **no** previous-game traffic vans/sedans  
- **no** magenta/cyan road chips  

Tool: `tools/Review-Setpiece-Underpass.py`  
Outputs: `build/setpiece_review/underpass_groundup/` and Desktop  
`Fades of Fate 2.0 - Review Photos/setpiece_review_underpass_groundup/`

## How to re-run

```bash
cd /home/DAVE/fades-of-fate-2-0
.venv/bin/python tools/Review-Setpiece-Underpass.py --frames 12 \
  --plate docs/visual_direction/target_renders/ch1_l2_i8_underpass_target_clean.png
```

## Status: approved (ground-up setpiece)

Usable in-engine theme: **`underpass_setpiece_v1`**

| Item | Path |
|------|------|
| Main plate | `assets/stage/setpieces/underpass_i8_v1/main.png` (1600×360) |
| Runtime route | registered in `pixel_art._ground_up_setpiece_routes()` |
| Capture GIF | `tools/Capture-Setpiece-Underpass-Gif.py` |
| Desktop GIF | `09_underpass_setpiece_ENGINE.gif` |

In-game underpass life: denser mist, wetter reflective road, birds, foliage, soft practicals — **no FoF1 vehicles**.

```bash
.venv/bin/python tools/Capture-Setpiece-Underpass-Gif.py --frames 48 --fps 12 --seconds 4
```
