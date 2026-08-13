# Fades of Fate 2.0 — OpenBOR Entity Pixel Art and Animation Standard

**Status:** production standard for entity art planning, drawing, integration, and review

**Research reviewed:** 2026-08-13

**Engine authority:** OpenBOR 4.0 Build 7949

**Project authority:** [`2.0_CHARTER.md`](../2.0_CHARTER.md) and [`OPENBOR_COMPATIBILITY_STANDARD.md`](OPENBOR_COMPATIBILITY_STANDARD.md)

**Current content boundary:** Black Dave only unless the project charter is explicitly expanded

## Technical summary

Smooth beat-'em-up animation is not the same as maximizing the number of drawings. The strongest results come from readable silhouettes, clear anticipation, decisive contact poses, controlled holds, follow-through, accurate collision timing, and effects that reinforce rather than obscure the body. [Mariel Cartwright's GDC animation guidance](https://media.gdcvault.com/GDC2014/Presentations/Cartwright_Muriel_Animation_Bootcamp_Fluid.pdf) makes the same production point: favor keys, use anticipation and smears to bridge large motion, vary holds, implement rough animation in the game before finishing it, and remove redundant in-betweens when they weaken impact.

For Fades of Fate 2.0, every entity must be designed as an OpenBOR model from the start. Art must use rooted whole-body cels on a stable canvas, a single identical 256-entry indexed palette for every frame in the model, palette index 0 for transparency, integer placement, and hard pixel edges. Gameplay movement belongs to entity coordinates, not shifting frame offsets. Collision, cancel windows, hitstop, sound, and VFX events must be designed alongside the poses and verified in Build 7949.

The project simulation runs at 60 Hz and authored pose selection is based on a 30 Hz pose clock. That does **not** require a new drawing every two simulation ticks. A pose may be deliberately held for multiple pose ticks. Black Dave's locomotion should prioritize a readable stride cadence over rapid pose flashing, while attacks may accelerate through a smear and hold the contact key long enough to read.

This document defines planning ranges, not a command to pad every action with drawings. A five-cel animation with excellent keys and timing can outperform a twelve-cel animation full of weak in-betweens. Extra cels are approved only when they improve silhouette, spacing, personality, or gameplay communication in an actual OpenBOR capture.

## 1. What the best genre examples teach

The games below are references for principles, not sources of reusable art. Do not trace, rip, recolor, or reproduce proprietary frames. Study how actions read at game speed, then create original poses from new reference and the entity's own anatomy, costume, and combat language.

| Reference | Evidence-backed lesson | Standard adopted here |
|---|---|---|
| [**Marvel Cosmic Invasion**](https://www.marvel.com/articles/games/marvel-cosmic-invasion-launch-trailer-available-now-pc-and-consoles) | Marvel and Tribute Games present it as a tag-team beat-'em-up with fifteen distinct heroes, full-color pixel art, dynamic combos, and lush animation. Its main production lesson is identity through motion: a fighter's movement vocabulary must express powers, mass, anatomy, and temperament rather than placing every character on one generic brawler cycle. | Every entity receives original silhouettes, locomotion weight, attacks, reactions, and effect anchors. A shared technical pipeline is allowed; a shared body performance is not. |
| [**Marvel vs. Capcom / Capcom 2D fighters**](https://media.gdcvault.com/GDC2014/Presentations/Cartwright_Muriel_Animation_Bootcamp_Fluid.pdf) | Cartwright's GDC examples specifically use Captain America to demonstrate smear frames and Capcom characters to demonstrate overshoot, extreme keys, and readable collision. These are fighting games rather than lane-based beat-'em-ups, so their pose craft transfers more directly than their locomotion or balance. | Superhuman motion may bend anatomy for one transitional cel, but the contact key, root, hurt region, and facing must remain legible in a crowded 2.5D scene. |
| [**Streets of Rage 2 and Streets of Rage 4**](https://www.dotemu.com/need-more-of-streets-of-rage-4-check-out-our-dev-diaries/) | The Streets of Rage 4 developers treated Streets of Rage 2 as their gameplay benchmark. Lizardcube emphasized linework and movement, while [later balance notes](https://www.dotemu.com/streets-of-rage-4-new-balancing-patch-now-available/) show that startup, recovery, invulnerability, hitboxes, hit freeze, and jump timing were tuned together. | Animation is a gameplay asset. Rough poses must be tested with movement, hitboxes, recovery, cancels, and hitstop before polish. Stage contrast and character silhouette are reviewed together. |
| [**The Simpsons Arcade Game**](https://www.youtube.com/watch?v=6CYoUYF7z0Y) | Observable in the official re-release trailer: identity is carried by large prop silhouettes, comic anticipation, broad swing arcs, exaggerated reactions, and cooperative actions that read instantly in four-player clutter. | Comedy and personality need specific keys, not extra idle noise. Pickups, team actions, and prop moves require a clean silhouette at their interaction frame. |
| [**Konami TMNT arcade games**](https://www.konami.com/games/eu/en/products/teenage_mutant_ninja_turtles/) | The Cowabunga Collection preserves the arcade games and their development art. The classic games demonstrate economical loops, clear weapon arcs, readable falls, and strong color separation at arcade scale. | Weapon reach must be communicated by the body pose and attack box; the visible arc and collision volume must agree without tracing the weapon sprite itself. |
| [**TMNT: Shredder's Revenge**](https://www.dotemu.com/tmnt-shredders-revenge-behind-the-scenes-3-the-art-of-the-turtles/) | Tribute Games' animation supervisor describes balancing legacy recognition with new ideas, fluid pixel animation, and distinct personalities. | A modern pixel entity should preserve instant readability while adding transition poses, secondary motion, and expressive reactions only where they survive gameplay speed. |
| [**OpenBOR / Beats of Rage**](https://github.com/DCurrent/openbor) | OpenBOR is a sprite-based side-scrolling engine whose models, animations, boxes, panels, and scripts are data-driven. It proves that a strong brawler can be assembled from explicit poses and state data without a 3D rig. | Author to OpenBOR's native state and frame model; do not create a separate renderer, skeletal runtime, or incompatible atlas-only presentation path. |
| [**Paintown**](https://paintown.org/) and [**CC0 beat-'em-up packs**](https://opengameart.org/content/streets-of-fight) | Paintown is an open-source side-scrolling action project with modular graphics and scripting. The CC0 Streets of Fight pack exposes a small practical set of character animations, props, tiles, parallax, and foreground pieces. These are useful for studying organization and minimum viable coverage, not a quality ceiling. | Keep source organization modular and auditable, but require original art, complete state coverage, and the stronger gameplay gates in this document. |

### The shared conclusion

Across these references, smoothness comes from five linked qualities:

1. **Pose clarity:** the action can be identified from a single contact or direction-change key.
2. **Timing contrast:** anticipation, acceleration, impact, and recovery do not all receive equal time.
3. **Spatial continuity:** feet, hips, hands, weapons, and effects travel on intentional arcs without accidental snapping.
4. **Gameplay agreement:** the visible contact, attack box, hurt box, movement, hitstop, and sound occur together.
5. **Character specificity:** the action could not be swapped onto a different entity without looking wrong.

## 2. Binding OpenBOR art contract

### 2.1 Runtime format

- Character and effect sprites are non-interlaced 8-bit indexed PNGs.
- Every frame in one model uses the **same 256 palette entries in the same order**.
- Palette index 0 is reserved for transparency on every frame.
- Transparent padding contains index 0 only. Do not use semitransparent antialiasing around body pixels.
- Export nearest-neighbor. Do not blur, resample, or independently quantize frames.
- Source art may retain layers and guides, but the shipping frame is a flattened indexed PNG.

OpenBOR derives a model palette base from its first frame in high-color modes. Independent per-frame quantization can therefore load the wrong colors even when every PNG appears correct in isolation. Palette equality is a model-level acceptance gate, not an aesthetic preference.

### 2.2 Canvas, root, and offset

- Choose one canvas and one ground/root location before drawing the first animation.
- Keep the root under the character's planted support point. For a two-foot stance, use the designed midpoint between contacts.
- Use one uniform `offset` convention. OpenBOR recommends avoiding per-frame offset changes, and this project forbids using offset changes to fake movement.
- The entity's world X/Z/altitude supplies travel. The drawing supplies body mechanics around that root.
- Preserve the same scale, head size, shoulder width, limb length, costume landmarks, and outline language across every action.
- A crouch may lower the hips relative to the root; it may not shrink the whole body.

Black Dave's current generated OpenBOR canvas/root contract is recorded by his source manifest. Any future canvas change is a model migration requiring regeneration, box review, palette review, and full gameplay recapture—not a per-clip convenience edit.

### 2.3 Timing authority

- Simulation: fixed 60 Hz.
- Authored pose clock: 30 Hz.
- Locomotion: deliberately held keys; avoid flashing through every authored cel at 30 changes per second.
- Attacks: variable holds based on startup, active, recovery, and contact readability.
- State changes occur on entry. Do not restart the same animation every update.
- When a script owns frame selection, freeze or bypass native frame advancement so two clocks cannot fight over the pose.
- A pose timeline is authored in integer simulation ticks even if the design brief also lists seconds.

OpenBOR's `delay` is expressed in centiseconds, but the Fades controller may select frames directly from the 60/30 Hz timing model. The model file, route metadata, and controller must agree on which system owns each animation. No clip may be driven by both at once.

### 2.4 Native animation names and the slot ceiling

Build 7949 is the naming authority. Custom labels in an art manifest are not automatically valid engine animation constants.

Use native animations where they express the state:

- `SPAWN`, `RESPAWN`, `IDLE`, `WALK`, optional `UP`, `DOWN`, `BACKWALK`, and `TURN`
- `JUMP`, optional `JUMPDELAY`, `FORWARDJUMP`, and `JUMPLAND`
- `ATTACK1` through the declared attack limit, plus explicitly banked special actions
- `BLOCK`, `BLOCKPAIN`, and `GUARDBREAK`
- `PAIN`, `FALL`, `RISE`, and optional reaction variants
- `DEATH` and approved numbered variants
- `GET` for item pickup

Build 7949 exposes only eight safe native freespecial constants. Do not invent `freespecial9+` or arbitrary animation constants. The Fades route-bank design allocates authored combo steps across `freespecial1` through `freespecial7`; the eighth slot remains within the engine ceiling but must not be consumed casually. Any implementation must verify this binding in its generated manifest and full model. A route bank must declare sufficient `maxfreespecials`, and the player model must explicitly define a valid `atchain`.

### 2.5 Collision and event ownership

- `bbox` is the body region that can receive hits. It must remain broad, stable, and inside the frame.
- An attack box is active only on the intended contact frame or contact hold.
- Clear the attack immediately after the active phase; OpenBOR retains an attack definition until it is replaced or disabled.
- Use Z-depth deliberately. A visually horizontal strike with an excessively deep attack box feels dishonest in a lane-based brawler.
- Collision boxes describe gameplay volumes, not every contour pixel. A few readable boxes are stronger than many decorative micro-boxes.
- Hitstop, hit flash, sound, shake, recoil, and contact VFX are emitted from a confirmed hit event. A flame or spark sprite never decides whether a hit occurred.
- Effects do not change the fighter's root, body scale, hurt box, attack box, or authoritative state.

## 3. Required entity design packet before final drawing

Do not begin by polishing an idle frame. Define the complete playable state and the gameplay needs first.

### 3.1 Identity sheet

The identity sheet establishes:

- height in pixels relative to the approved cast scale;
- build, head-to-body ratio, shoulder and hip widths;
- costume front/side landmarks and asymmetry;
- three value groups that remain readable under the stage grade;
- outline and interior-cluster rules;
- hand, foot, head, weapon, and effect anchor conventions;
- one neutral stance, one locomotion contact key, one attack contact key, one pain key, and one downed key.

Each key must pass at 100% size, mirrored facing, and on the darkest approved combat floor. If the silhouette cannot identify the action without effects, redesign it before animation.

### 3.2 State inventory

Every playable entity must declare whether each state is **required**, **not used**, or **deferred by approved scope**. Missing art may not silently fall back to an unrelated pose.

| Family | Baseline states |
|---|---|
| Entry and neutral | spawn, respawn/revive, idle, low-health idle if used |
| Ground movement | walk start, walk loop, walk stop, turn/reverse; optional up/down-specific cycles |
| Air movement | takeoff, rise, apex, fall, land; forward or running jump if used |
| Defense | block enter/hold/release, block impact, guard break if guard points are used |
| Combat | every light, kick, power, air, ranged, grab, throw, and special route actually reachable by controls |
| Reactions | light pain, heavy pain/knockback, fall, down hold, rise/recovery, death/zero health |
| Interaction | item pickup; weapon pickup/hold/use/drop only if the gameplay design includes weapons |
| Presentation | select, waiting, victory, or scripted actions only when the product scope requires them |

### 3.3 Move timing sheet

Before rough animation, each actionable move records:

- input and native animation slot;
- total simulation ticks;
- startup ticks;
- active ticks;
- recovery ticks;
- world movement and altitude change;
- cancel-open and cancel-close ticks;
- attack type, damage intent, knockdown intent, and Z reach;
- body box changes if any;
- hand/foot/weapon anchor path;
- sound, trail, contact, burst, and camera events;
- facing and mirroring rules;
- allowed next states.

The art timeline follows this sheet. If the move design changes, update timing first and then decide whether a pose must be redrawn.

## 4. Production workflow: rough, implement, finish, implement

### Phase 1 — Reference and thumbnails

1. Record or gather lawful movement reference for the action. Use multiple bodies and angles when the motion is unusual.
2. Identify the action line, center of mass, support foot, force direction, and endpoint.
3. Draw small black silhouettes for anticipation, contact, and recovery.
4. Compare them at game scale. Eliminate poses that differ only in interior detail.
5. Choose keys that express this entity's personality and mass.

Reference is for mechanics, not tracing. Superhuman moves should combine real weight transfer with intentionally exaggerated arcs.

### Phase 2 — Rooted rough cels

1. Place the ground root and a reference bounding rectangle on every frame.
2. Draw the contact feet and pelvis first, then torso, head, limbs, clothing, and props.
3. Create the minimum key set: anticipation, transition/smear, main key, overshoot or follow-through, return.
4. Check onion-skin arcs for head, hands, hips, knees, and feet.
5. Play the rough with the intended variable holds—not equal timing by default.

Use full-body rough cels. Do not construct ordinary fighters from separately rotated limbs; OpenBOR supports full user-defined sprites, and the project standard is rooted whole-cel authored animation.

### Phase 3 — First OpenBOR implementation

1. Export rough indexed or temporary palette-safe frames.
2. Map them to a supported native animation or approved freespecial bank.
3. Add provisional body and attack boxes.
4. Test input response, movement, facing, Z alignment, cancel timing, hitstop, and state exits.
5. Capture actual gameplay at normal speed and frame-step the action around contact.

Do not wait for polished pixels to discover that anticipation is too long, the root slides, or the contact frame occurs after the hitbox.

### Phase 4 — Pixel finish

Finish in this order:

1. silhouette and anatomy;
2. root and contact points;
3. large light/shadow masses;
4. costume landmarks;
5. facial and hand indications that survive at game scale;
6. secondary motion;
7. effect anchor cleanup;
8. palette and cluster cleanup.

Avoid single-pixel chatter that changes randomly between frames. Interior clusters should deform with the form rather than sparkle independently.

### Phase 5 — Final integration and capture

- Rebuild Black Dave model outputs with `python tools/Build-OpenBOR-Black-Dave.py` when his source art or routing changes.
- Run `python tools/Preflight-OpenBOR-Assets.py --data openbor/data`.
- Package with `python tools/Build-OpenBOR-Package.py`, which must run and verify preflight against the source and PAK.
- Launch the pinned executable from the clean package directory with no loose `data/` shadow tree.
- Review logs and sustained gameplay.
- Capture every required state in the real stage, not only on a transparent atlas or GIF.

## 5. Action-by-action drawing standard

The cel ranges below are **planning targets for unique drawings**, not mandatory padding. Repeated holds do not count as new art. Existing approved five-cel Black Dave clips remain reviewable if they meet the timing, silhouette, and gameplay gates.

| Action | Recommended unique-cel range | Essential pose structure | OpenBOR target |
|---|---:|---|---|
| Idle | 4–6 | neutral, inhale/up, settle, exhale/down; restrained asymmetry | `IDLE` |
| Walk loop | 8 preferred; 6 acceptable; 10–12 for justified secondary motion | left contact, recoil/down, passing, high point, right contact, recoil/down, passing, high point | `WALK`; optional `UP`/`DOWN` |
| Walk start/stop/turn | 2–4 each | lean and first push; braking plant and settle; head/hips lead turn | native transition if supported or controller-driven frame range |
| Light attack | 5–7 | anticipation, acceleration/smear, contact, overshoot, recovery | `ATTACK#` or banked `FREESPECIAL#` |
| Heavy/power attack | 7–10 | larger load, stronger smear, readable contact hold, recoil/follow-through, committed recovery | banked `FREESPECIAL#` |
| Jump family | 7–12 across the family | compression, launch, rise, apex, fall, pre-contact, impact crouch, settle | `JUMPDELAY`, `JUMP`/`FORWARDJUMP`, `JUMPLAND` or approved controller mapping |
| Block | 3–5 guard plus 2–4 impact | enter, protected hold, release; separate recoil on blocked hit | `BLOCK`, `BLOCKPAIN` |
| Guard break | 3–6 | shield/arms displaced, torso opened, vulnerable settle | `GUARDBREAK` |
| Pain | 3–5 | instant directional recoil, peak compression/twist, return or fall handoff | `PAIN` |
| Knockdown/fall | 5–8 plus down hold | launch/recoil, airborne rotation, ground contact, bounce/settle, readable down silhouette | `FALL` then engine down state |
| Rise/recovery | 4–7 | brace, knee/hip recovery, guarded stand, neutral handoff | `RISE` |
| Zero health/death | 6–10 | decisive defeat, ground impact, final readable pose; no accidental return posture | `DEATH` or configured lethal `FALL` |
| Respawn/revive | 6–10 | first sign of life, brace, partial rise, stable stance, control-ready handoff | `RESPAWN` for built-in life recovery |
| Item pickup | 3–6 | reach/stoop, contact, secure/consume, return | `GET` |

### 5.1 Walking

#### Required mechanics

- The support foot remains visually planted during its contact hold.
- The pelvis travels through a shallow vertical arc; it does not bob the whole body by moving the canvas.
- Arms oppose the legs unless the entity's personality or carried object justifies another rhythm.
- The head is stabilized relative to the torso; excessive head bob makes a fighter look weightless.
- The near and far limbs separate by value or outline so they do not merge into one column.
- Clothing, hair, straps, and flames follow the body by a beat; they do not lead the pelvis.
- The first and last cels form a seamless loop without a root jump.

#### 2.5D direction handling

OpenBOR can reuse `WALK` for vertical lane movement. Draw separate `UP` and `DOWN` cycles only when the design needs visible directional body rotation and the engine mapping is verified. Native `UP` and `DOWN` must have the same frame count as `WALK`. If the entity remains profile-facing while moving in Z, keep the same planted-foot logic and let world coordinates create lane movement.

#### Cadence

For Black Dave, start review around the project-proven readable cadence rather than changing pose every 30 Hz pose tick. Tune stride cadence with actual world speed so feet do not skate. A faster character may travel farther per cycle; that does not automatically require more pose changes.

### 5.2 Fighting

Build every attack from gameplay phases:

1. **Anticipation:** show direction and force. Player moves keep it short enough to remain responsive; enemy telegraphs may hold longer.
2. **Acceleration:** one strong transition or smear can cover a large arc better than several evenly spaced weak cels.
3. **Contact:** the strike is fully extended or compressed, the attack box is active, and the hand/foot/weapon meets the target region.
4. **Overshoot/follow-through:** force continues after contact. Clothing and flames may lag.
5. **Recovery:** the entity regains balance and exposes the intended commitment window.
6. **Return/cancel:** the pose hands off cleanly to idle, walk, the next combo step, or an allowed cancel.

#### Attack originality test

An attack fails the unique-art standard when it is merely an idle torso with a pasted arm, a generic pose recolored for another entity, or the same contact key reused across unrelated moves. Combo steps may share a stance family, but each step needs its own force direction, contact silhouette, footwork, and recovery logic.

#### Contact agreement test

At the first active tick:

- the visible striking surface overlaps the intended target region;
- the attack box begins no earlier than the visible strike;
- the body box still represents the fighter's vulnerable mass;
- the Z reach matches the visible lane reach;
- the contact flash and flame burst spawn at the recorded anchor;
- confirmed hitstop freezes both combatants once, not once per effect layer.

### 5.3 Jumping

OpenBOR moves the entity through altitude; the art should describe force and orientation, not paint the character higher inside the canvas.

1. **Takeoff:** compress hips and knees while the root stays on the floor.
2. **Launch:** extend through the support leg as altitude begins.
3. **Rise:** taper the extension; limbs follow the center of mass.
4. **Apex:** create a compact, readable silhouette and allow aerial attack branching.
5. **Fall:** prepare the feet and torso for contact without moving the root upward in the image.
6. **Land:** show ground impact with knee/hip compression.
7. **Settle:** return control without an unnecessary long flourish.

Aerial attacks need their own anticipation, contact, and recovery poses. Do not freeze one facing or one airborne cel for the whole arc. Do not bake world travel into offsets.

### 5.4 Blocking

The guard silhouette must visibly cover the target region before the block becomes active. Hands, forearms, shoulders, and stance should form one protected mass rather than an idle pose with raised wrists.

- `BLOCK` supplies enter/hold/release.
- `BLOCKPAIN` communicates a successful but forceful block.
- `GUARDBREAK` communicates lost defense and must end in a vulnerable, non-guard silhouette.
- A block flash belongs at the contact surface, not the center of the torso by default.
- Fire effects should contract toward the fists during guard so they do not make the protected body unreadable.

### 5.5 Taking damage, knockdown, and rise

Pain animation communicates attack direction and severity. The first reaction cel should be an immediate, readable displacement; do not spend the first cel easing gently into pain.

- Light pain: sharp recoil with feet mostly retained.
- Heavy pain: larger torso fold or twist that clearly hands off to `FALL`.
- Fall: use a clean airborne silhouette and one decisive ground-contact key.
- Down: preserve an unmistakable body orientation and head location for target/readability systems.
- Rise: lead with a brace, recover the base of support, and end guarded enough to avoid an awkward idle snap.

Create alternate front/back or elemental reactions only when gameplay actually distinguishes them. Do not multiply reaction art for nonexistent attack types.

### 5.6 Fainting and zero health

OpenBOR terminology matters: `FAINT` is a low-health idle used at one quarter health or below. It is **not** the zero-health or unconscious animation.

- Use `FAINT` only if the design wants a visibly weakened low-health stance.
- Use `DEATH` or the configured lethal `FALL` path for zero health.
- The final pose should read as defeated at game scale and should not resemble an attack anticipation or a recoverable crouch.
- Let the engine's approved death/respawn behavior control removal or life loss. Do not draw a custom disappearance mechanic before it is implemented and tested.

### 5.7 Revive and respawn

Build 7949 provides `RESPAWN` for a player returning after losing a life. A teammate-driven in-place revive is a custom gameplay feature, not an automatic meaning of the animation name.

The art standard for either presentation is:

1. no-motion down hold;
2. visible reactivation cue separated from the body;
3. hand or elbow brace;
4. knee/hip recovery;
5. guarded standing pose;
6. explicit control-ready handoff.

Until a teammate-revive mechanic is approved and proven in the pinned runtime, author revival art to the native `RESPAWN` path or keep additional concepts non-shipping. A custom revive must define invulnerability, collision, input lock, body persistence, co-op interruption, and camera behavior before final cels are commissioned.

### 5.8 Item pickups

Use the native `GET` animation for a standard pickup. The contact key must coincide with the engine taking the item.

- Quick pickup: short reach, contact, return.
- Ground pickup: hip and knee bend around the fixed root; do not scale the torso downward.
- Consumable: secure/contact pose followed by a brief use pose only if the gameplay delay exists.
- Weapon pickup: only author weapon-hold and weapon-attack states after the weapon model path is approved; OpenBOR weapons can require separate model data and memory.

The item remains readable until the contact frame. If multiple items overlap, the animation still needs a clear hand-to-ground interaction rather than a generic celebration pose.

## 6. Pixel craft and model consistency

### 6.1 Work in large forms first

- Read silhouette at 100%, 200%, and against the runtime backdrop.
- Keep the darkest outline separate from the darkest clothing where necessary.
- Use clustered shadow shapes instead of noisy checkerboard texture.
- Reserve the brightest values for face/hand cues, metal, eyes, powered areas, and impact—not every edge.
- Reduce facial detail during fast motion; preserve head angle and key features.
- Use selective sub-clusters for fingers only when they survive in motion.

### 6.2 Pixel motion rules

- Prefer intentional 1–3 pixel shifts over fractional scaling.
- Keep line thickness coherent as forms rotate.
- Avoid automatic tweening, rotation, and resampling on final pixels.
- A smear is a separately drawn transitional shape, not a blurred copy.
- An overshoot is one deliberate key past the endpoint, not random jitter.
- Secondary motion follows mass: cap brim, clothing, straps, and flames react after the torso changes direction.

### 6.3 Mirroring and asymmetry

OpenBOR normally flips a character to face the other direction. Check all asymmetrical features under mirroring:

- lettering and logos;
- one-sided accessories;
- hair parting;
- weapon hand;
- effect anchor order;
- visible near/far limbs.

If an asymmetry cannot be mirrored acceptably, the design must provide an engine-supported facing solution before more art is drawn.

## 7. Flame hands and other pixelated effects

### 7.1 Effects are separate entities or layers

Dave's flame hands must never be baked into a way that obscures body review, changes his scale, or becomes combat authority. Keep body frames and effect frames separate. Each effect model receives its own indexed palette contract with index 0 transparency.

Use per-frame fist anchors as the attachment source. The body animation defines where the hand is; the effect animation defines how flame reacts around that position.

### 7.2 Recommended flame stack

From back to front:

1. **Under-glow:** a small, dim halo behind the fist; optional and runtime-tested.
2. **Trailing lick:** one or two directional flame shapes behind the hand, delayed from the hand arc.
3. **Body sprite:** Dave remains fully opaque and readable.
4. **Flame shell:** hard-edged flame around the outside of the fist, leaving knuckles/palm visible.
5. **Hot core accents:** a few bright pixels at the flame base, not a solid bright disk over the hand.
6. **Contact burst:** a separate short-lived effect at confirmed impact.
7. **Embers/smoke:** sparse follow-through particles after the strike; never a permanent cloud over the face or torso.

The goal is **dimmer, layered flame with visible hands**, not a single opaque orange ball. Limit bright coverage and increase shape variety, separation, and timing.

### 7.3 Flame motion by state

| State | Flame behavior |
|---|---|
| Idle | compact upward flicker; low brightness; no large trail |
| Walk | slight backward lean from motion; hands remain readable through alternating arm depth |
| Anticipation | flame contracts toward the hand as energy gathers |
| Fast strike | one directional smear/trail behind the hand |
| Contact | brief core expansion and separate impact burst |
| Recovery | broken embers continue along the old arc while the core returns to the fist |
| Block | tight shell toward the protected hands; impact flash at the guarded surface |
| Hurt/down | flame weakens, detaches, or extinguishes only if the gameplay/presentation design specifies it |
| Respawn | relight is a presentation cue after body recovery begins, not the cause of resurrection |

### 7.4 Alpha and blending

OpenBOR supports several transparency methods in general, but Build 7949 and the exact project directive are the authority. Start with hard-edged indexed flame shapes that already read without blending. Add alpha, overlay, or scripted layer changes only after the exact effect survives:

- parser/load;
- palette inspection;
- normal and dark background review;
- mirrored facing;
- four-actor clutter;
- PAK launch and log review.

Never use full-frame blur or soft glow that destroys pixel clusters. Any glow is local, motivated, and subordinate to the body silhouette.

### 7.5 General impact presentation

For a strong hit, coordinate rather than stack indiscriminately:

- one contact key;
- one confirmed hitstop latch;
- one impact sound family;
- one flash or spark at the true contact point;
- recoil on the victim;
- limited camera shake appropriate to attack tier;
- a trail that describes the incoming arc;
- debris/embers that continue after the freeze.

More layers do not automatically mean more impact. Each layer needs a different spatial or temporal job.

## 8. OpenBOR mapping checklist

Before an animation is considered engine-ready, confirm:

- [ ] The art clip has an approved gameplay state and timing sheet.
- [ ] Its OpenBOR animation name is native to Build 7949 or mapped into `freespecial1`–`freespecial8`.
- [ ] The model's `maxattacks` and `maxfreespecials` cover the mapping.
- [ ] The player has an explicit valid `atchain`.
- [ ] State entry selects the animation once; update logic does not restart it.
- [ ] Only one timing system owns frame advancement.
- [ ] Frame paths are ASCII, forward-slash, case-stable `data/...` paths.
- [ ] All model frames share the identical 256-entry palette.
- [ ] Index 0 is transparent and no edge pixels are semitransparent.
- [ ] Canvas, root, scale, and offset are consistent.
- [ ] Body and attack boxes are inside frame bounds and intentional in Z.
- [ ] The attack box clears after the active phase.
- [ ] Hand/foot/weapon/effect anchors exist for event frames.
- [ ] VFX never decides hit confirmation or modifies body geometry.
- [ ] The state exits to a valid next state without a pose snap.

## 9. Acceptance gates

### Art review gate

Pass only if:

- the action reads in silhouette without effects;
- identity and anatomy remain consistent across all cels;
- root and planted feet do not slide;
- arcs are smooth under onion skin and at runtime timing;
- palette and pixel clusters are clean;
- mirrored facing is acceptable;
- effects preserve hand and body readability.

### Engine gate

Pass only if:

- the OpenBOR asset preflight succeeds;
- the PAK builder verifies source/package payloads;
- Build 7949 loads the full model, not a reduced compatibility shim;
- no parser warning, missing asset, script error, access violation, or early termination appears;
- input reaches every intended state;
- frame ownership is stable with no flicker or bank mixing;
- attacks connect only on intended ticks and Z lanes;
- block, pain, fall, rise, death, respawn, and pickup transitions execute correctly.

### Gameplay evidence gate

The final evidence set must show actual OpenBOR gameplay for:

- spawn and idle;
- horizontal and depth movement;
- walk start/loop/stop and facing change;
- jump, apex, fall, and land;
- every reachable attack route at whiff and confirmed contact;
- block, block impact, and guard break if used;
- light pain, knockdown, down, and rise;
- zero health and respawn/revive presentation;
- item pickup;
- flame layers at idle, motion, contact, and recovery;
- the entity on both the brightest and darkest approved stage areas.

An atlas, pose board, GIF, generator result, preflight result, or build success is supporting evidence only. None replaces gameplay capture.

## 10. Recommended source organization

Keep layered authoring sources and design metadata under the approved content area, and generated engine assets under `openbor/data/`.

```text
content/characters/<entity>/
  art_source/
  metadata/
  reference/
  sprites/

openbor/data/chars/<entity>/
  <entity>.txt
  <entity>_manifest.json
  sprites/
  effects/
```

The source manifest should record canvas, offset/root, palette identity, clip names, ordered frames, intended timing, engine bindings, anchors, source hashes, and generator version. Generated files are regenerated rather than hand-patched when a generator owns them.

## 11. Sources and evidence boundaries

### Engine and project authority

- [Fades of Fate 2.0 OpenBOR compatibility standard](OPENBOR_COMPATIBILITY_STANDARD.md)
- [OpenBOR official repository](https://github.com/DCurrent/openbor)
- [OpenBOR animation overview](https://chronocrash.com/obor/wiki/animations-overview/)
- [OpenBOR legacy manual — animation types, animation data, collision, and item pickup](https://chronocrash.com/openbor/wiki/legacy-manual/)
- [OpenBOR collision reference](https://chronocrash.com/obor/wiki/collision/)
- [OpenBOR graphics overview](https://chronocrash.com/obor/wiki/graphics-overview/)

### Animation process and professional practice

- [Mariel Cartwright, “Fluid and Powerful Animation within Frame Restrictions,” GDC](https://media.gdcvault.com/GDC2014/Presentations/Cartwright_Muriel_Animation_Bootcamp_Fluid.pdf)
- [GDC Animation Bootcamp — live 2D game animation process](https://www.gdcvault.com/play/1021788/Animation-Bootcamp-Introduction-Live-2D)
- [Shawn Allen, “Animating a Complex 2D Fighting Game 3 Frames at a Time,” GDC](https://www.gdcvault.com/play/1027466/Animation-Summit-Animating-a-Complex)
- [Aseprite onion-skinning documentation](https://www.aseprite.org/docs/onion-skinning/)
- [Aseprite indexed color documentation](https://www.aseprite.org/docs/color-mode/)
- [Aseprite export and sprite-sheet documentation](https://www.aseprite.org/docs/cli/)

### Genre reference evidence

- [Marvel Cosmic Invasion launch overview](https://www.marvel.com/articles/games/marvel-cosmic-invasion-launch-trailer-available-now-pc-and-consoles)
- [TMNT: Shredder's Revenge — The Art of the Turtles](https://www.dotemu.com/tmnt-shredders-revenge-behind-the-scenes-3-the-art-of-the-turtles/)
- [Streets of Rage 4 developer diaries](https://www.dotemu.com/need-more-of-streets-of-rage-4-check-out-our-dev-diaries/)
- [Streets of Rage 4 balance notes showing animation/gameplay coupling](https://www.dotemu.com/streets-of-rage-4-new-balancing-patch-now-available/)
- [Konami TMNT Cowabunga Collection and preserved development material](https://www.konami.com/games/eu/en/products/teenage_mutant_ninja_turtles/)
- [The Simpsons Arcade Game re-release trailer](https://www.youtube.com/watch?v=6CYoUYF7z0Y)
- [Paintown open-source project](https://paintown.org/)
- [CC0 Streets of Fight study pack](https://opengameart.org/content/streets-of-fight)

Claims about exact proprietary frame counts were intentionally excluded because authoritative production sheets were not available for every title. The cel counts in this standard are Fades production planning ranges derived from animation principles and OpenBOR needs, not measurements copied from those games.
