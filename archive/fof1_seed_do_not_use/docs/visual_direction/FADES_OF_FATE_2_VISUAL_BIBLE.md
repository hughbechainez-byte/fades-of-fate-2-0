# Fades of Fate 2.0 — Visual Bible

**Status:** draft for review  
**Scope:** Chapter 1 El Cajon corridor, 2.5D setpiece-led presentation, progressive synthwave  
**Engine bottom line:** scenery is play space, not wallpaper

---

## 1. One-sentence mission

Make every block of North 2nd Street a **walkable setpiece** with real depth, collision, and lighting—so players fight *in* El Cajon, while the sky and practical neon slowly turn the corridor synthwave as Chapter 1 advances.

---

## 2. Non-negotiables (2.5D is the bottom line)

| Rule | Meaning in production |
|------|------------------------|
| **Setpiece ≠ background** | Every major landmark owns floor depth, curb setback, props, occlusion, and encounter space—not only a painted plate behind sprites. |
| **World coordinates win** | Stage X, floor depth, and elevation map through the oblique projection. Actors are constant-size billboards; feet root to the floor plane. |
| **Playable side is architecture** | Ch1 stays west/even, northbound. Lots, planters, bollards, cars, and façades on the playable side are combat-relevant mass. |
| **Opposite side is parallax set dressing** | East side reads and moves slower; it never becomes walkable. |
| **1:1 world anchors** | Driveways, poles, carts, and parked cars lock to world X. Decorative haze/skyline may drift; combat props may not. |
| **Near occluders after actors** | Sparse foreground pieces (rails, apron edge, low props) prove depth by covering feet/legs when correct. |
| **640×360 logical canvas** | Pixel clusters, integer roots, nearest-neighbor scale. No soft full-frame bloom that erases edges. |
| **Authored massing first** | Real corridor geometry and order stay legible. Synthwave is **lighting, sky, and practical neon**—not a generic cyber city swap. |

### What “setpiece-led” demands per landmark

For each named anchor (Sprouts lot, Town & Country, underpass, Soapy’s, Awaken…):

1. **Volume** — parking setback or curb depth encoded in art *and* walk rails / obstacles.  
2. **Threshold** — a readable entrance (driveway, shadow line, canopy mouth, intersection).  
3. **Readable silhouette** — massing still names the place after palette shift.  
4. **Interactive band** — at least one prop family or physical object registered to that anchor.  
5. **Exit beat** — next setpiece visible or recently passed so travel feels continuous.

If a plate only changes color and never changes how you stand, fight, or hide—**it is still a background.** Fail the setpiece review.

---

## 3. Layer stack (engine-aligned)

Draw order for a living frame (matches the restored FoF1 compositor intent):

```
far sky / haze bands (atmosphere-driven)
far skyline / opposite corridor (bounded parallax)
MAIN SETPIECE PLATE (authored, world-locked, authoritative)
mid ambient life (traffic, birds, mist — depth planes)
gameplay ground cues (lane, curb, wet chips — not covering plate texture)
world props / vehicles (physical, sorted by floor depth)
ACTORS + combat VFX
near occluders (after actors)
local lighting accents (tubes, signs, underpass fill)
UI
```

**Authority rule:** the main panorama / setpiece plate is never replaced by low-detail chunk architecture. Chunks help culling and near plates only.

---

## 4. Chapter 1 synthwave progression

Synthwave is a **gradual weather of the world**, not a day-one full rebrand. Each level pushes one more stop toward neon dusk while massing stays El Cajon.

| Level | Setpiece spine | Lighting dialect | Neon budget | Player feeling |
|-------|----------------|------------------|-------------|----------------|
| **L1** Sprouts → El Cilantro | Lots, strip columns, Madison corner | **Golden hour.** Warm amber, rose sky, soft violet only on horizon | Minimal: existing store practicals, UI accents only | “Real El Cajon, slightly cinematic” |
| **L2** 7-Eleven → **I-8 underpass** | Pads, plaza, service bays, freeway approach | **Magenta–orange sunset** into cool concrete fill. Sky picks up purple bands | Low–medium: gas canopy edge lights, plaza signs, **underpass as first true neon canyon** | “The sky starts lying” |
| **L3** Soapy’s → Broadway / Revive | Blue roof wash, drive-through, intersection turn | **Blue hour.** Cool fills dominate; wet asphalt holds cyan/pink chips | Medium: wash bay tubes, Revive neon, Broadway signals | “Night is choosing us” |
| **L4** Awaken lot | Church façade, boss lock, BMX prop | **Neon dusk / finale night.** Deep navy sky, magenta rim, electric title language | High but localized: façade glass, lot poles as soft practicals, boss-readable floor still mid charcoal | “Setpiece showdown under synth weather” |

### Progression rules

- **Do not** jump L1 straight to full magenta night.  
- **Do** carry one new practical family per level (L2 underpass tubes → L3 wet reflections → L4 glass glow).  
- **Combat floor** stays readable charcoal/asphalt; never pure black or full pink wash.  
- **High-sat pink/cyan** reserved for: motivated signs, tubes, pickups, supers, UI ownership—not entire façades.  
- Chapter 2 (east side southbound) may open already at “full neon dusk”; Ch1 is the ramp.

### Palette stops (sky / haze anchors)

| Profile feel | Rough sky bands | Accent |
|--------------|-----------------|--------|
| L1 golden | `#f2baa4` → `#de875e` → `#8f5a46` | amber lamps |
| L2 synth approach | orange–magenta–violet horizon, cool underpass interior | sparse pink practicals |
| L3 blue hour | `#171a33` → `#29304e` + warm residual `#d2876f` | cyan wash / Revive |
| L4 neon dusk | `#0d0f2a` → `#17223d` → `#263c68` + pink rim `#ff78b8` | glass + electric outline language |

---

## 5. Character art consistency (presentation)

- Rooted whole-cel pixel heroes; tall readable silhouettes; deep-ink edges.  
- Black Dave identity (when poses are approved for use): slim muscular build, backward black cap, black tank, small gold rectangular glasses, diamond studs, baggy blue jeans, high-tops, Bluetooth speaker hip prop; fist flames only as separate VFX.  
- Upper-left key, lower-right contact shade; contact shadow on floor always.  
- **Pose policy for direction renders:** only use Black Dave (or any hero) **authored pose sheets created for the current review window**. Do not silently restyle old atlas rows as “new.” If no fresh poses exist, ship **setpiece-only** or clearly mark character as **style stand-in, not pose-approved.**

---

## 6. Neon / synthwave craft (pixel-safe)

| Allowed | Forbidden |
|---------|-----------|
| 1–3 px tube cores + limited glow halo | Soft airbrush bloom over whole frame |
| Magenta/cyan on glass, signs, wet chips | Recoloring entire storefront into plastic neon slabs |
| Underpass as cool “canyon” with warm exit portal | Blade-Runner skyscraper inserts that break El Cajon massing |
| Atmosphere-driven haze phase | Animated noise that destroys pixel silhouette |

---

## 7. Review gates (approve / request edits)

A frame or level strip passes only if:

1. **Place** — a local can name the block or landmark family.  
2. **Depth** — floor plane, playable setback, and at least one near occluder read as 2.5D.  
3. **Fightability** — hero silhouette clear on asphalt; neon not washing midtones.  
4. **Progression** — level’s synth step matches the table (not L4 neon on L1).  
5. **Setpiece test** — removing the “pretty sky” still leaves usable architecture and floor.  
6. **Pose provenance** — any hero shown cites allowed authored sources for that review.

---

## 8. Deliverable types (definitions)

| Term | What it is | What it is not |
|------|------------|----------------|
| **Visual bible** | Locked rules for style, progression, and engine presentation (this doc). | A single pretty picture. |
| **Proof brief** | Short written assignment for one setpiece: goals, layer plan, palette stop, must-show list, pass/fail checks. Used to commission art or a target render. | The image itself. |
| **Target render** | One **aspirational still** of how a setpiece should look in-engine (composition, depth, lighting, character scale). Reviewers approve look-dev direction from it. | A shipped gameplay asset, atlas cel, or byte-identical runtime frame. |
| **Runtime plate** | Final 640×360 (or full world-width) art that the game loads after bake/lock. | A freeform concept illustration that ignores projection. |

**Relationship:** Proof brief → Target render (optional but ideal) → Authoring/bake → Runtime plate → QA capture.

The underpass package below includes **both** a proof brief and a target render.

---

## 9. Open production notes

- Ch1 location-lock + bake + atmosphere pipelines from FoF1 remain the intended technical path.  
- Grow neon as **additive emissive layers** and atmosphere profiles before repainting every main plate.  
- East-side Chapter 2 art remains the large content cliff after Ch1 synth ramp is approved.
