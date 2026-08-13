# Fades of Fate 2.0 — OpenBOR Layered 2.5D Stage Creation Standard

**Status:** production standard for stage concept, authored pixel art, OpenBOR integration, traversal, and review

**Research reviewed:** 2026-08-13

**Engine authority:** OpenBOR 4.0 Build 7949

**Project authority:** [`2.0_CHARTER.md`](../2.0_CHARTER.md) and [`OPENBOR_COMPATIBILITY_STANDARD.md`](OPENBOR_COMPATIBILITY_STANDARD.md)

**Current content boundary:** the I-8 underpass setpiece only unless the project charter is explicitly expanded

## Technical summary

A Fades of Fate 2.0 stage is a traversable 2.5D setpiece, not a photograph behind the fighters. The player must read a floor plane, usable lane depth, thresholds, foreground occlusion, landmarks, collision, and a changing visual journey as the camera moves. Depth is built from authored panels, `bglayer` parallax, the world-locked panel plane, depth-sorted entities, and `fglayer` occluders. Gameplay geometry remains in level data; painted walls and holes do not become physical merely because they look solid.

For the pinned underpass demo, production uses indexed, non-interlaced 640×360 `panel` sections. Large concept art may be wider, but it must be sliced into equal runtime panels and tested in the PAK. Do not ship a single stretched panorama or the wide `background` directive that previously crashed after level load. A small tested sky/background holder and separate layers may be used only in the exact Build 7949 syntax proven by launch and log evidence.

Atmosphere comes from composition, layer speed, color hierarchy, motivated light, sparse environmental motion, occlusion, unique landmarks, and audio/event timing. It does not require soft full-screen blur, giant alpha videos, or dozens of animated layers. OpenBOR background layers do not natively provide ordinary frame-by-frame animation; moving life should use tested model entities or a narrowly proven layer-control script.

## 1. What “2.5D” means in this project

The term describes a 2D sprite presentation with a navigable depth axis and layered perspective.

- **X** is travel along the stage.
- **Z** is lane depth from the back of the combat floor toward the camera.
- **Altitude** is jump/fall height above the current base.
- **Panels** establish the authoritative world-locked floor and architecture.
- **Background layers** move slower than the panels to imply distance.
- **Foreground layers** move faster or draw over actors to imply near depth.
- **Entities** provide fighters, props, effects, hazards, and optional animated scenery.
- **Level geometry** supplies walls, holes, platforms, spawn points, scroll limits, and waits.

The illusion succeeds when a player can answer: Where can I stand? What is in front of me? What is far away? What blocks movement? Where does the next screen lead?

## 2. Lessons from strong beat-'em-up stages

| Reference | Stage lesson | Fades rule |
|---|---|---|
| [**Streets of Rage 2 / 4**](https://www.dotemu.com/need-more-of-streets-of-rage-4-check-out-our-dev-diaries/) | The Streets of Rage 4 art team emphasized a detailed city, strong linework, movement, and new interactive setpiece ideas while preserving the series' neon urban identity. | Each screen needs an authored landmark, foreground/midground/background separation, a readable combat floor, and at least one change in composition or event—not just a palette-swapped tile. |
| [**Konami TMNT arcade games**](https://www.konami.com/games/eu/en/products/teenage_mutant_ninja_turtles/) | Sewer, street, base, and time-travel settings are distinguished by silhouette, floor treatment, props, hazards, and transitions. The Cowabunga Collection also preserves development art and sketches, showing that scene design precedes final pixels. | Make a stage beat map and value thumbnail before painting runtime panels. The environment must change shape and play rhythm, not only texture. |
| [**TMNT: Shredder's Revenge**](https://www.dotemu.com/tmnt-shredders-revenge-behind-the-scenes-3-the-art-of-the-turtles/) | Tribute Games balanced legacy recognition with new ideas and expressive pixel presentation. | Reference a place through authored shapes, palette, and activity; avoid copying or stretching source photography. Add fresh interaction and motion that suit the new stage. |
| [**The Simpsons Arcade Game**](https://www.youtube.com/watch?v=6CYoUYF7z0Y) | Observable in gameplay trailers: props, signage, hazards, foreground gags, and scene-specific enemies make each segment feel like an episode rather than a repeating corridor. | Give atmospheric details a scene job: navigation, comedy, danger, depth, or story. Decorative noise without a job is removed. |
| [**Marvel Cosmic Invasion**](https://www.marvel.com/articles/games/marvel-cosmic-invasion-launch-trailer-available-now-pc-and-consoles) | Modern pixel beat-'em-up stages use distinct cosmic/local silhouettes, layered effects, readable floors, and effects that support large character powers. | Protect fighter readability under VFX. Background saturation and value cannot compete with player silhouettes or flame-hand contacts. |
| [**OpenBOR**](https://github.com/DCurrent/openbor), [**Paintown**](https://paintown.org/), and [**CC0 study assets**](https://opengameart.org/content/streets-of-fight) | Data-driven and open-source examples show the practical value of separate stage tiles/panels, parallax, foreground elements, props, and scripts. | Keep runtime assets modular and replaceable, but bake them into the Build 7949 panel/layer model rather than importing another engine's map format. |

## 3. Binding Build 7949 stage contract

### 3.1 Runtime images

- Logical viewport: 640×360.
- Underpass production panels: non-interlaced 8-bit indexed PNG, 640×360 each.
- Every level `background.png`: non-interlaced 8-bit indexed PNG.
- Other background-only RGB/RGBA files are permitted only when the exact directive and image have passed Build 7949 launch testing; indexed is the default.
- `data/video.txt` contains exactly one parser-compatible `video WIDTHxHEIGHT` directive. Shorthand such as `a1280x720` is rejected.
- Paths are forward-slash, ASCII, case-stable `data/...` paths and exist in both source and PAK.

### 3.2 Panel rules

- Author a long master if useful, then slice it into equal 640×360 panels.
- Every production panel in the underpass stage is unique unless a repeat is explicitly justified for a low-information transition.
- Panels must meet edge-to-edge with no overlap, blank seam, duplicate column, or one-pixel phase error.
- Declare panels and an `order` string that matches the intended traversal.
- Keep the runtime panel count within OpenBOR's supported `a`–`z` definitions.
- Do not stretch one 640×360 image across multiple screens.
- Do not use a wide `background` directive as a substitute for panels in the Build 7949 underpass demo.

### 3.3 Layer rules

Use only the argument counts and directives accepted by the pinned runtime.

- `background` or the tested base image establishes the farthest visual plane and may also carry palette authority.
- `bglayer` creates distant or middle planes in front of the base and behind actors/panels as configured.
- `panel` creates the world-locked stage plane and determines maximum horizontal traversal.
- `fglayer` creates near planes and actor occlusion.
- Declaration order affects draw order.
- `xratio` and `zratio` control relative scrolling; 1.0 follows the panel plane, lower values read farther away, and values above 1.0 read nearer.
- Transparency, alpha, neon, water, quake, and automatic motion options are not assumed safe merely because the current manual documents them. Test the exact Build 7949 form.

The OpenBOR manual documents up to 100 background layers and up to 26 panel definitions, but those are engine ceilings, not an art target. Start with the fewest layers that create clear depth and add more only when gameplay captures show a missing visual job.

### 3.4 Geometry rules

- Art never silently defines collision.
- A painted wall receives a matching level `wall` or approved entity collision only if it is meant to block.
- A painted hole receives a matching `hole` only if falling is intended and fully tested.
- Platforms, elevation changes, walk rails, Z bounds, waits, blockades, and scroll limits live in level data.
- Actor feet must align to the same projected floor plane used to place collision and props.
- Near occluders may cover feet or lower legs briefly; they may not hide attack contact or the entire fighter.

## 4. Stage planning before pixels

### 4.1 Write the one-screen promise

Define the stage in one sentence that combines place, traversal, and dramatic change. For example: a player crosses an authored underpass corridor from warm exterior light into a cool compressed concrete canyon and back toward a visible exit.

The promise must describe a visual journey. “A wide underpass photo” is not a stage concept.

### 4.2 Build a beat map

Plan the stage in 640-pixel screen units before painting. Each beat records:

- panel index and world X range;
- primary landmark/silhouette;
- floor width and Z range;
- entrance and exit threshold;
- light direction and dominant value group;
- near occluder;
- physical prop or geometry if approved;
- ambient motion family;
- encounter/wait position if applicable;
- view forward to the next beat and backward to the previous beat.

For a three-panel underpass, the minimum useful rhythm is:

1. **Approach:** establish exterior scale, mouth of the underpass, and clear entry.
2. **Compression:** lower ceiling, cooler fill, stronger supports/occlusion, and the deepest atmosphere.
3. **Release:** visible exit light, widening floor, and a distinct final silhouette.

Do not make three panels that differ only in grime placement.

### 4.3 Define the playable floor first

Before background detail:

1. mark the horizon or architectural convergence;
2. mark the top and bottom of the playable Z band;
3. draw floor guides through every panel;
4. place Dave at back, middle, and front Z positions;
5. verify that feet remain grounded and scale remains constant;
6. mark any wall, hole, platform, or prop footprint in world coordinates.

The floor must remain readable after removing sky, signs, haze, and foreground decoration.

### 4.4 Value and color thumbnail

Reduce the stage to four or five value masses:

- far sky/void;
- distant silhouette;
- main architecture;
- combat floor;
- near occluder.

The fighter should remain readable in every screen without a permanent outline halo. Reserve the brightest and most saturated colors for motivated lights, exits, effects, pickups, and UI ownership.

## 5. Recommended layer architecture

The ratios below are **starting ranges**, not engine guarantees. Tune them in the pinned runtime and retain the exact values only after forward/back traversal captures pass.

| Plane | Visual job | Starting X ratio | Content rules |
|---|---|---:|---|
| Base sky/void | full-bleed color and deepest atmosphere | 0.0–0.2 or tested static base | no transparency needed; no stretched landmark detail |
| Far silhouette | skyline, distant columns, hills, far wall | 0.2–0.4 | broad shapes, low contrast, little/no high-frequency texture |
| Mid distance | opposite architecture, light pools, distant infrastructure | 0.45–0.75 | moderate detail; must not look walkable if it is not |
| Panel plane | floor, curbs, walls, world-locked landmarks | 1.0 | authoritative perspective and traversal surface |
| World entities | props, hazards, animated scenery | world coordinates | depth sorted; collision explicit if physical |
| Actors and combat VFX | gameplay | world coordinates | highest local readability and contact contrast |
| Near fglayer | rail, curb lip, fence, column edge, hanging object | 1.05–1.25 | sparse, transparent index 0, purposeful occlusion |

### Depth cues that work in pixel art

- slower motion in distant planes;
- reduced contrast and saturation with distance;
- smaller, denser shapes in the far plane;
- overlapping silhouettes with clean separation;
- converging curb, beam, fence, or shadow lines;
- nearer objects crossing the screen edge;
- foreground elements briefly covering feet;
- lighting pools that wrap across the floor plane;
- repeated architecture that changes scale/spacing according to perspective rather than copy-paste frequency.

Do not scale the player with Z depth. OpenBOR actors remain readable constant-size sprites in this project; the floor projection and occlusion sell depth.

## 6. Creating original stage art instead of stretched photography

Photography may be used as private reference only when its rights and project scope allow. The production image is redrawn from structure.

### 6.1 Extract structure, not pixels

From reference, record:

- major masses and negative spaces;
- column spacing and beam rhythm;
- floor slope and curb lines;
- material families;
- motivated light sources;
- identifiable but legally/creatively appropriate signage shapes;
- atmospheric depth and color temperature.

Then rebuild the scene with original pixel clusters, new wear patterns, new props, and stage-specific composition. Do not run a photograph through a pixelation filter and call it authored art.

### 6.2 Reuse a material language, not a screen

Reusable elements may include:

- concrete texture clusters;
- seam and joint motifs;
- curb edge patterns;
- bolt and conduit shapes;
- haze/noise tiles with low information;
- color ramps;
- small debris families.

The following remain unique per panel:

- primary landmark silhouette;
- large shadow shape;
- floor damage arrangement;
- foreground occluder footprint;
- entrance/exit framing;
- sign or light grouping;
- composition of large props.

This produces consistency without obvious wallpaper repetition.

### 6.3 Avoid visible tiling

- Never repeat a high-contrast stain, crack, sign, or pillar at a fixed camera interval.
- Offset low-information texture motifs and break their edges with unique shapes.
- Keep haze tiles larger than their most recognizable cluster or vary them through separate approved layers.
- Review a full forward walk and a full backward walk; reverse traversal exposes repetitions that a still does not.
- Check panel seams with and without haze/foreground layers so effects cannot hide a broken base.

## 7. Atmospheric stage construction

### 7.1 Atmosphere hierarchy

Build atmosphere in this order:

1. **architecture and floor readability;**
2. **large light and shadow masses;**
3. **parallax separation;**
4. **local practical lights;**
5. **sparse haze or dust;**
6. **animated life;**
7. **small story detail.**

If a later layer makes the floor or fighter harder to read, reduce or remove it.

### 7.2 Motivated lighting

Every colored accent identifies a source: exit light, tube, sign, opening, reflected floor patch, or effect. Avoid uniform magenta/cyan overlays across the entire stage.

- Keep the combat floor in a middle value range.
- Place bright exit portals away from common character contact areas when possible.
- Use rim accents on architecture to frame traversal, not to outline every object.
- Reflected light on the floor follows the floor projection.
- Local haze may reveal a light beam, but it cannot become a soft full-frame bloom.

### 7.3 Haze, dust, steam, and weather

Use multiple jobs rather than one opaque filter:

- far haze lowers distant contrast;
- a thin mid layer separates architecture from the panel plane;
- sparse near particles cross actors briefly;
- steam or dust entities occupy world positions and may be occluded correctly;
- contact dust appears only at movement/impact events.

Each family gets its own palette and timing. Do not animate giant full-screen haze textures at character-frame cadence.

### 7.4 Environmental animation within OpenBOR

OpenBOR background layers do not natively act like ordinary frame animations. Use one of these paths:

1. **Built-in layer motion/effects:** only for documented options that pass Build 7949.
2. **Animated model entity:** preferred for localized lights, steam, birds, signs, debris, or silhouettes because it uses the normal animation system and can be positioned in world/layer space.
3. **Narrow script-controlled layer sequence:** allowed only after a dedicated compatibility probe; enable one layer at a time and keep timing independent of combat.

Do not create dozens of alternate full-stage panels to fake animation. That multiplies memory, packaging risk, palette risk, and seam risk.

### 7.5 Neon and palette cycling

OpenBOR documents neon cycling through palette entries 128–135 on compatible background/panel layers. Treat those indices as a reserved stage subsystem only if the exact panel palette, command, and Build 7949 behavior pass a dedicated probe.

- Do not let ordinary architecture accidentally use cycling entries.
- Do not assume a layer with a different palette will cycle correctly.
- Prefer static authored practical lights when cycling adds little.
- Record the stage palette identity and reserved indices in the manifest.

## 8. Props, occluders, and interaction

### 8.1 Physical props

A prop is physical only when art, world position, draw order, collision, and gameplay behavior agree.

- Place it at a defined X/Z coordinate.
- Give it a stable ground/contact point.
- Define collision only if it should block or receive hits.
- Provide broken/damaged states only if gameplay supports them.
- Test actors behind, in front of, and adjacent to it.
- Confirm that a four-player cluster cannot disappear entirely behind it.

### 8.2 Near occluders

Good near occluders prove depth with minimal obstruction:

- curb lips;
- low rails;
- fence sections;
- column edges;
- hanging foreground shapes;
- floor-edge debris.

Keep their coverage sparse. The player should understand why legs are hidden and recover full silhouette quickly while moving.

### 8.3 Visual geometry versus gameplay geometry

Every major visual barrier receives one classification:

- **background-only:** never reachable;
- **walkable floor:** inside Z bounds;
- **solid wall/prop:** explicit collision;
- **platform/elevation:** explicit altitude behavior;
- **hole/drop:** explicit failure behavior;
- **foreground-only:** draw-order cue, no collision.

If the classification is unclear, stop before final painting. Ambiguous art leads to players trying to walk through solid-looking walls or avoiding harmless painted shadows.

## 9. Panel authoring and export workflow

### Phase 1 — Source master

- Work on a source canvas whose width is an exact multiple of 640 and height is 360 for the underpass runtime strip.
- Keep groups for guides, base, far, mid, panel, props, lighting, haze, and near layers.
- Keep world-X and panel-boundary guides locked.
- Use tilemaps or reusable brushes only as authoring tools; OpenBOR consumes baked panel/layer images, not an Aseprite tilemap file.

### Phase 2 — Seam-safe painting

- Paint large perspective lines across panel boundaries before slicing.
- Keep one-pixel line phases and dither patterns continuous.
- Ensure the final column of panel A and first column of panel B do not duplicate or skip world pixels.
- Avoid placing a high-contrast landmark directly on a seam unless its continuity is verified at runtime.

### Phase 3 — Layer export

Export each runtime job separately:

- base sky/background holder;
- far `bglayer`;
- optional mid `bglayer`;
- panel A/B/C…;
- optional haze layer proven in runtime;
- near `fglayer`;
- localized animated scenery as model sprites.

Flatten guides and references out of all exports. Convert with one deliberate stage palette plan and no accidental soft alpha.

### Phase 4 — Level data

- Declare supported graphics directives in draw order.
- Declare panels and correct `order`.
- Define direction, spawn locations, Z bounds, waits, and scroll limits.
- Add physical geometry from the classification map.
- Add entity props and environmental models at world coordinates.
- Reject unsupported directives, including `shadow_coords`.

### Phase 5 — Runtime iteration

Test the smallest complete stage in Build 7949:

1. load and spawn;
2. walk to every panel boundary;
3. walk back to the start;
4. traverse back/middle/front Z lanes;
5. jump at seams and occluders;
6. fight in the darkest and busiest areas;
7. inspect start/end camera edges;
8. review logs and memory behavior.

Fix the base/panel plane before adding more atmospheric layers.

## 10. Recommended file organization

```text
content/setpieces/<setpiece>/
  art_source/
  lookdev/
  reference/
  metadata/
  review/

openbor/data/levels/<setpiece>.txt
openbor/data/levels/<setpiece>/
  background.png
  panels/
    <setpiece>_a.png
    <setpiece>_b.png
    <setpiece>_c.png
  art/
    far.png
    mid.png
    haze.png
    near.png
  entities/
```

The setpiece manifest should record source art identity, panel order, dimensions, palette hashes, layer ratios, directive arguments, geometry map revision, runtime build, source commit, PAK hash, packaged file count, and gameplay evidence paths.

## 11. Review gates

### 11.1 Static art gate

- [ ] Removing atmospheric effects still leaves readable architecture and floor.
- [ ] Each 640-pixel screen has a unique large composition.
- [ ] Panel seams are clean at 100% and nearest-neighbor scale.
- [ ] Far, panel, actor, and near values separate clearly.
- [ ] Dave remains readable at back, middle, and front Z positions.
- [ ] The stage contains no stretched photo, obvious high-information tile, or repeated landmark.
- [ ] Every solid-looking feature has a geometry classification.
- [ ] Near occluders prove depth without hiding combat.

### 11.2 OpenBOR compatibility gate

- [ ] `background.png` and panels are indexed, non-interlaced PNGs.
- [ ] `video.txt` contains exactly one valid `video WIDTHxHEIGHT` directive.
- [ ] All layer paths and argument counts resolve in source and PAK.
- [ ] The underpass uses 640×360 panels and does not ship the crashing wide background layout.
- [ ] No unsupported directive is present.
- [ ] `python tools/Preflight-OpenBOR-Assets.py --data openbor/data` passes before packing.
- [ ] `python tools/Build-OpenBOR-Package.py` runs preflight, packs, and verifies the PAK.
- [ ] Post-pack preflight, source payload hashes, packaged entries, and file counts match.

### 11.3 Traversal and gameplay gate

Capture actual Build 7949 gameplay showing:

- stage load and player spawn;
- full forward traversal;
- full backward traversal when the direction allows it;
- back/middle/front Z movement;
- every panel seam and camera edge;
- jump and landing at representative seams;
- actors passing behind and in front of props/occluders;
- combat at the darkest, brightest, and most detailed regions;
- effects against all major stage value groups;
- any wall, hole, platform, wait, or scroll limit in use;
- sustained non-black gameplay with no log errors or early exit.

A target render, full panorama, layer preview, animated GIF, preflight, or successful PAK build is not sufficient approval.

## 12. Failure patterns to reject

Reject a stage when any of these are true:

- one image is stretched across the whole level;
- a photo is merely pixelated or posterized;
- the same storefront/pillar/stain repeats every screen;
- parallax layers move but the panel plane has no traversable depth logic;
- decorative art implies walls or holes that do not exist in gameplay;
- foreground art hides the player for long periods;
- haze or bloom erases pixel edges;
- every layer has the same contrast and saturation;
- animated effects compete with hit flashes or flame-hand readability;
- giant background frames are swapped to fake environmental animation;
- a still looks good but forward/back traversal exposes seams, void, or camera-edge failure;
- current upstream OpenBOR behavior is cited without a Build 7949 runtime pass.

## 13. Sources and evidence boundaries

### Engine and project authority

- [Fades of Fate 2.0 OpenBOR compatibility standard](OPENBOR_COMPATIBILITY_STANDARD.md)
- [OpenBOR official repository](https://github.com/DCurrent/openbor)
- [OpenBOR graphics overview](https://chronocrash.com/obor/wiki/graphics-overview/)
- [OpenBOR legacy manual — panels, background layers, foreground layers, camera, geometry, and scroll limits](https://chronocrash.com/obor/wiki/legacy-manual/)
- [OpenBOR layer animation example by project lead Damon Caskey](https://gist.github.com/DCurrent/0eb07a9e015be464c5be20a6ed6ffcdd)

### Stage art and genre evidence

- [Streets of Rage 4 developer diaries — gameplay and background art direction](https://www.dotemu.com/need-more-of-streets-of-rage-4-check-out-our-dev-diaries/)
- [TMNT: Shredder's Revenge — The Art of the Turtles](https://www.dotemu.com/tmnt-shredders-revenge-behind-the-scenes-3-the-art-of-the-turtles/)
- [Konami TMNT Cowabunga Collection and preserved development art](https://www.konami.com/games/eu/en/products/teenage_mutant_ninja_turtles/)
- [Marvel Cosmic Invasion launch overview](https://www.marvel.com/articles/games/marvel-cosmic-invasion-launch-trailer-available-now-pc-and-consoles)
- [The Simpsons Arcade Game re-release trailer](https://www.youtube.com/watch?v=6CYoUYF7z0Y)
- [Paintown open-source project](https://paintown.org/)
- [CC0 Streets of Fight pack with stage tiles, parallax, foregrounds, props, and animations](https://opengameart.org/content/streets-of-fight)

### Authoring workflow evidence

- [Aseprite layers](https://www.aseprite.org/docs/layers/)
- [Aseprite tilemaps](https://www.aseprite.org/docs/tilemap/)
- [Aseprite indexed color](https://www.aseprite.org/docs/color-mode/)
- [Aseprite command-line and layer export](https://www.aseprite.org/docs/cli/)

Layer ratios and panel-beat recommendations in this document are Fades production starting points, not claims about proprietary game internals. Build 7949 gameplay remains the final authority for every directive, layer order, palette, scroll ratio, and animated technique.
