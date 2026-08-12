# Proof brief — I-8 underpass (Chapter 1 Level 2 end)

**Setpiece ID:** `ch1_l2_i8_underpass`  
**Progression stop:** L2 synthwave approach (first true neon canyon)  
**Canvas intent:** 16:9 gameplay frame language (target ~640×360 feel; concept may be higher-res)  
**Status:** brief for target render review

---

## Purpose

Prove that the **I-8 underpass** is a **2.5D setpiece**, not a flat backdrop: concrete volume, playable asphalt apron, depth-sorted silhouette against a synth-sunset portal, and (when allowed) a hero rooted on the floor plane at combat scale.

## Why this setpiece

- End of Level 2 in the locked El Cajon route (7-Eleven → underpass).  
- Best natural handoff from warm corridor to cool fill + magenta horizon (L2 progression).  
- Existing source panel `art_source/chapter1_location_locked/source_panels/l2_p4_i8_underpass_v3_source.png` already encodes massing.

## Must show (pass)

1. **Overhead mass** — deck underside, beams, piers as enclosing volume (player feels *under* something).  
2. **Playable floor** — cracked charcoal asphalt in the near third; clear combat mid-band.  
3. **Depth stack** — near curb/sidewalk → mid fence/creek edge → far portal (palms/hills/sky) with distinct values.  
4. **Synth stop L2** — orange–magenta–violet sky through the portal; cool blue-gray concrete fill inside; **sparse** pink/cyan practicals only (utility lights, distant sign glints)—not full cyber city.  
5. **El Cajon truth** — chain-link, utility boxes, dry scrub, creek/channel cue, palms/hills—not skyscrapers.  
6. **2.5D read** — camera roughly side-scroller / slight oblique; hero (if present) as constant-size billboard with contact shadow, feet planted.

## Must not show (fail)

- Flat wallpaper sky behind a 2D cutout prop with no pier volume.  
- L4-level full neon dusk wash.  
- Soft cinematic bloom destroying pixel edges.  
- Mirrored or east-side massing sold as this westbound/northbound underpass end.  
- Hero drawn from **non-approved** pose sources (see pose policy).

## Pose policy for this brief (updated)

**Only authored Black Dave poses created in the current review window (~last hour) may appear.**

**Check result (2026-08-11 evening):** no new Black Dave pose sheets were authored in the last hour on this machine. Repo V2 cels/atlas carry clone timestamps only; local `docs/visual_direction/refs/*` crops are **not** new authorship.

**Therefore this target render is setpiece-primary:** environment + depth + lighting direction. Any human figure must be labeled **style stand-in (not pose-approved)** or omitted. Prefer **omit hero** until fresh poses land.

## Layer recipe for target render

| Layer | Content |
|-------|---------|
| Far | Magenta–orange portal sky, hills, palms (through openings) |
| Structure | Concrete deck, piers, ramps (world-locked) |
| Mid | Fence, creek, utility boxes, scrub |
| Ground | Asphalt apron + curb; optional wet chips catching pink |
| Near (optional) | Low curb edge / light pole base that can occlude feet later |
| Actor | *Deferred* until last-hour authored poses exist |
| Accent | Sparse cool practicals under deck; no logo spam |

## Acceptance

Reviewer either:

- **Approves** lighting/depth/massing for L2 underpass setpiece, or  
- **Requests edits** with notes on volume, palette stop, or El Cajon authenticity.

After approval, art can be rebaked into location-locked layers; this still is **not** a shipping PNG until lock + bake + QA.

## Related files

- Visual bible: `docs/visual_direction/FADES_OF_FATE_2_VISUAL_BIBLE.md`  
- Source massing: `art_source/chapter1_location_locked/source_panels/l2_p4_i8_underpass_v3_source.png`  
- Target render: `docs/visual_direction/target_renders/ch1_l2_i8_underpass_target.png`  
- Atmosphere L2 feel: cool underpass dimming + emerging magenta sky (see bible §4)
