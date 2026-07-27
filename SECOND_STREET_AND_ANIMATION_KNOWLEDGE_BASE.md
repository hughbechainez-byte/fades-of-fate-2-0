# The Fades of Fate: Second Street and Animation Knowledge Base

Research snapshot: **July 18, 2026**  
Scope: animation-fluidity audit, both sides of North 2nd Street in El Cajon, and the canonical level route for Chapters 1 and 2.

Implementation update: the frame audit below preserves the pre-upgrade baseline for comparison. The current build uses 91 manifest-backed clips and 828 rooted authored keys—at least eight meaningful phases per active animation—with duplicate, translation-only, gait-delta, ground-line, and 30/60 FPS sampling checks.

Business occupancy and signs can change. Treat the street inventory as a researched art reference, then recheck the supplied map links immediately before producing final background panels.

## Decisions now locked

- **Chapter 1 travels north on the west/left/even-address side of North 2nd Street.** The playable pavement and parking lots stay on that side; the east side remains visible across the road but is not walkable.
- **Level 1:** Sprouts parking lot at 152 N 2nd St to El Cilantro at the Madison Avenue corner.
- **Level 2:** 7-Eleven at 500 N 2nd St to the I-8 underpass.
- **Level 3:** Soapy Joe's at 816 N 2nd St to Revive Pathway at 1240 Broadway. The route turns slightly west along Broadway at the end.
- **Level 4:** the Couch boss fight. The retained working location is the Awaken Church parking lot at 950 N 2nd St, matching the prior game outline; only the boss arena is required for this level.
- **Chapter 2 reverses direction and travels south on the east/right/odd-address side.** Its first confirmed segment begins at the Bostonia Post Office at 867 N 2nd St and ends at the I-8 underpass.
- Chapter 2 art must be separately authored for the east side. It must not be a horizontally mirrored Chapter 1 image because addresses, signs, driveways, typography, and building shapes would all be wrong.

## Why the current animation reads as choppy

The game runs its simulation at 60 Hz, but most playable-character action art is sampled at 30 ticks per second. That is enough display time for fluid animation; the limiting factor is the number of genuinely different drawings.

The current atlases often show one to three authored body poses for an entire action, then hold the last pose until the mechanic finishes. Small one- or two-pixel whole-sprite translations add motion but do not add a new pose, silhouette, limb arc, facial change, anticipation, impact, or recovery. Those offsets therefore are not counted as animation frames below.

There are also three structural causes of uneven motion:

1. Action clocks are inconsistent: player actions generally use 30 Hz, Chief commonly advances on the 60 Hz render counter, and ordinary enemies use another divided render counter.
2. Anticipation, contact, follow-through, recoil, knockdown, and get-up drawings are missing from many states.
3. Shelly's explicit refill and pants-pull sequences exist, but gameplay does not set those named states; her renderer instead runs them through a fixed 18-second idle schedule. `butane_anim` is updated by entity logic but is not used to select the rendered frames.

The authoritative current mappings are in [`src/sprite_atlas.py`](src/sprite_atlas.py), while action duration and clocks are in [`src/entities.py`](src/entities.py) and [`src/game.py`](src/game.py).

## Exact current frame audit

“Authored” means distinct atlas cells used by the state. “Slots” includes repeated cells used to hold timing. The counts are not estimates.

### Black Dave and Shelly shared action atlas

Each hero has a 20-cell base atlas. Most combat mappings are shared by both heroes.

| Animation/state | Authored drawings | Timing slots | What the game currently shows |
|---|---:|---:|---|
| Hurt / hitstun | 1 | 1 | One reaction drawing held for the hurt duration |
| Down / dead | 1 | 1 | Rotated hurt image; downed state does not advance its animation clock |
| Super / special | 1 | 1 | One power pose held for roughly the full move |
| Air attack | 1 | 1 | One attack pose in the air |
| Jump | 1 | 1 | One static jump pose |
| Pet Chief | 1 | 1 | One static interaction pose |
| Heavy / contextual throw | 2 | 6 | Two drawings with repeated holds |
| BB gun / ranged | 2 | 4 | Two reused combat drawings rather than a dedicated aim/fire/recoil set |
| Light hit 1 | 3 | 4 | Three drawings, with the middle drawing reused |
| Light hit 2 | 3 | 4 | Three drawings, with the middle drawing reused |
| Uppercut / hit 3 | 3 | 4 | Three drawings, with one reused on return |
| Finisher / hit 4 | 3 | 4 | Three drawings, with one reused on return |
| Dodge / dash | 4 | 6 | Four drawings, two duplicated holds |
| Walk / run | 5 | 12 | Five drawings arranged into a 0.40-second loop |
| Dave neutral idle | 4 | 10 | Four drawings in a 0.67-second repeated loop |

### Shelly personality idle

| Sequence | Authored drawings | Timing slots | Current duration/behavior |
|---|---:|---:|---|
| Torch refill | 8 | 16 | About 0.8 seconds in the explicit state; slowed and repeated inside the long idle schedule |
| Pants pull | 8 | 15 | About 0.75 seconds in the explicit state; slowed inside the long idle schedule |
| Cigarette beat | 1 | 1 | A single held pose |
| Complete scheduled idle | 17 | 18-second macro cycle | Refill dominates about 12 seconds, cigarette holds about 2 seconds, pants pull about 1.5 seconds, then refill resumes |

Shelly has 20 base cells plus 16 extended-idle cells, but only 17 distinct cells participate in the scheduled personality loop.

### Chief

Chief has 15 atlas cells in total.

| Animation/state | Authored drawings | Timing slots |
|---|---:|---:|
| Bite | 2 | 4 |
| Frenzy | 2 | 4 |
| Pet response | 1 | 1 |
| Guard | 1 | 1 |
| Sit / settle | 2 | 6 |
| Run / follow / hunt | 5 | 8 |
| Idle | 5 | 6 |

### Standard enemies

There are four archetypes—stick, cart, whip, and pipe—with five authored cells each, for 20 total enemy cells.

| Per-archetype state | Authored drawings |
|---|---:|
| Idle | 1 |
| Walk / chase | 2 |
| Attack / throw / charge | 1 |
| Recovery | 0 new; reuses the attack drawing |
| Hurt / down / dead | 1 shared drawing |

### Couch

Couch has ten atlas cells in total.

| Animation/state | Authored drawings | Timing slots |
|---|---:|---:|
| Hurt / down | 1 | 1 |
| Bike-pump attack | 1 | 1 |
| Recovery | 1 | 1 |
| Stick swing | 2 | 4 |
| Waddle | 2 | 8 |
| Laugh | 3 | 5 |
| Idle | 4 | 6 |

### Whole-demo total

The current runtime has **105 authored actor cells**: Dave 20, Shelly 20, Shelly extended idle 16, Chief 15, four ordinary-enemy rows 20, Couch 10, and four victory images. The README's older “85 frames” statement excludes the extended Shelly idle and victory strip.

## Comparison with polished beat-'em-ups

These references use different art pipelines, so the comparison is for order of magnitude and action coverage—not a claim that every exported image is a hand-drawn keyframe.

| Reference | Evidence | Useful lesson for this demo |
|---|---|---|
| Streets of Rage 4 | Art director Ben Fiquet reports about **1,000 hand-drawn frames per playable hero** and **300–400 per enemy**, drawn frame by frame in Photoshop. [Official PlayStation interview](https://blog.playstation.com/2020/04/23/how-lizardcube-redesigned-the-characters-of-streets-of-rage-4-out-april-30/) | This is a finished-production ceiling, not the next demo milestone. Its fluidity comes from extensive anticipation, transitions, reactions, and character acting—not merely a higher playback rate. |
| TMNT: Shredder's Revenge | A representative community-extracted Leonardo set shows idle 8, secondary idle 10, walk 6, sprint 6, common combo attacks about 6–8, heavy 12, hitstun 6, taunt 16, and a special around 17 distinct images. [Sprite archive](https://www.spriters-resource.com/pc_computer/teenagemutantninjaturtlesshreddersrevenge/asset/177455/) and [Dotemu art feature](https://www.dotemu.com/tmnt-shredders-revenge-behind-the-scenes-3-the-art-of-the-turtles/) | A modern pixel beat-'em-up can feel fluid with much smaller individual sequences than Streets of Rage 4 when poses are strong, holds are intentional, and hit events are tied to the contact drawings. |
| River City Girls | A representative community-extracted Misako set shows idle 16, walk 12, run 16, combo attacks from roughly 5–12, heavy 19, get-up 9, common hit 4, specials 13–18, and throws 18–22. [Sprite archive](https://www.spriters-resource.com/pc_computer/rivercitygirls/asset/121031/) and [WayForward feature](https://www.nintendolife.com/news/2019/08/feature_wayforward-on-river-city-girls-its-crazy-interpretation-of-the-kunio-kun-brand) | Personality animation and transitions consume as many drawings as the attacks themselves. |
| TMNT arcade (1989) | Community-preserved sheets visibly use roughly 4–6 drawings for many common movement and attack actions. [Archival sheet](https://www.spriters-resource.com/arcade/tmnt/asset/50886/) | A classic-arcade minimum is possible, but the current one- to three-drawing attacks still fall below it. |
| The Simpsons arcade (1991) | Community-preserved Bart material commonly shows about 3–7 visible drawings in walks and attacks; layered body parts make an exact authoritative action count unreliable. [Archival sheet](https://www.spriters-resource.com/arcade/simpsons/asset/1/page-1/) | Strong silhouettes can carry fewer drawings, but attack anticipation and recoil still need dedicated art. |

The extracted TMNT, River City Girls, classic TMNT, and Simpsons counts are inspection results from preservation sheets, not official developer-published totals. Mariel Cartwright's [GDC animation presentation](https://www.gdcvault.com/play/1021657/Powerful-and-Effective-Animation-for) is a useful production reference for readable keys, smears, spacing, and purposeful holds.

## Recommended fluid-demo animation budget

Keep combat logic and hit detection at 60 Hz. Present roughly 12–15 genuinely different drawings per second during fast action, with variable holds for anticipation, impact, and recovery. Do not lengthen the actual attack merely to show more art; bind damage, sound, hit-stop, trails, and camera shake to named animation events.

### Hero targets and immediate gaps

| Animation | Current authored | Fluid-demo target | Additional drawings needed |
|---|---:|---:|---:|
| Neutral idle | Dave 4; Shelly lacks a full neutral loop | 8–12 | Dave +4–8; Shelly +8–12 |
| Personality idle, each | Refill 8; pants 8; cigarette 1 | 10–16 refill/pants; 8–12 cigarette | +2–8, +2–8, +7–11 |
| Walk / run | 5 | 8–12 | +3–7 |
| Jab / first combo hit | 3 | 6–8 | +3–5 |
| Second combo hit | 3 | 7–9 | +4–6 |
| Uppercut / finisher | 3 | 10–14 | +7–11 |
| Heavy | 2 | 12–18 | +10–16 |
| BB gun / ranged | 2 | 8–12 | +6–10 |
| Air attack | 1 | 8–12 | +7–11 |
| Jump suite | 1 | 10–15 across takeoff/rise/apex/fall/land | +9–14 |
| Super | 1 | 18–30, plus separate VFX | +17–29 |
| Hurt | 1 | 5–8 | +4–7 |
| Knockdown | 1 | 10–16 | +9–15 |
| Get-up | 0 | 8–12 | +8–12 |
| Dodge | 4 | 6–10 | +2–6 |
| Grab / throw | 2 reused heavy poses | 12–20 | +10–18 |
| Pet / interaction | 1 | 6–10 | +5–9 |

Because several current cells are reused by multiple actions, the table cannot be summed row by row as if every cell were exclusive. A practical first production pass is **about 100–180 new drawings per hero**: Dave near the lower end and Shelly near the upper end because her longer personality actions need separate transitions.

### Other actor targets

| Actor | Current total | Fluid-demo target | Approximate new drawings |
|---|---:|---:|---:|
| Chief | 15 | 45–60 | +30–45 |
| Each ordinary enemy archetype | 5 | 30–40 | +25–35 each |
| Couch | 10 | 70–90 | +60–80 |

For each ordinary enemy, budget 4–6 idle, 6–8 walk, 6–10 attack, 3–5 recovery, 4–6 hurt, and 8–12 knockdown/get-up drawings. Couch needs a 6–8 drawing squat waddle, 10–14 drawing stick and pump attacks, 5–8 reactions, and a 10–14 drawing laugh in addition to her boss transitions.

The resulting demo will land near **600 authored actor drawings**, roughly **500 more than the current 105**. That is enough for a convincing modern-pixel foundation without trying to match Streets of Rage 4's approximately 1,000 drawings for every hero.

## Second Street orientation

The researched corridor is approximately 0.8 miles from the Sprouts/Walgreens area to Awaken. When facing north:

- **West/left side:** generally even North 2nd Street addresses. This is Chapter 1's playable side.
- **East/right side:** generally odd North 2nd Street addresses. This is Chapter 2's playable side.
- Large asphalt parking setbacks are a defining visual feature. Most stores are not flush to the curb.
- The road, traffic, signs, driveways, parking rows, palms, utility elements, and distant hills must remain stable world anchors as the camera moves.

The base map is [OpenStreetMap centered on the corridor](https://www.openstreetmap.org/#map=16/32.8026/-116.9358). Official locations confirm [Sprouts at 152 N 2nd St](https://www.sprouts.com/store/ca/el-cajon/n-2nd-st/), [7-Eleven at 500 N 2nd St](https://www.7-eleven.com/locations/ca/el-cajon/500-n-2nd-st-36485), [Soapy Joe's at 816 N 2nd St](https://soapyjoescarwash.com/location/el-cajon-n-2nd-st/), [Bostonia Post Office at 867 N 2nd St](https://tools.usps.com/locations/details/1355473), [Revive Pathway at 1240 Broadway](https://rp.health/about/), and [Awaken at 950 N 2nd St](https://awakenchurch.com/service-locations/el-cajon-campus/).

## Both-side landmark inventory

This is ordered south to north. A “secondary” entry can be simplified, combined, or used only as distant signage, but its massing and lot footprint should remain recognizable.

| Corridor band | West/left/even side | East/right/odd side |
|---|---|---|
| South entrance to Madison | **Sprouts, 152**; Wells Fargo, 250; **Walmart Neighborhood Market, 300**; **Town & Country center, roughly 328–420** with Baskin-Robbins, Country Wine, former Grocery Outlet shell, Eyeglass World, mobile-phone shops, Pho, Dollar Tree, and Goodwill; **El Cilantro, 1285 E Madison**, on the west side of the Madison corner | Romeo's Car Wash, 195; **Walgreens, 215**; McDonald's, 281; Moneytree, 303; T-Shirt Mart, 317; Arby's, 325; No Dry Car Wash, 329; Taco Bell, 335; Subway, 341; small salons/insurance; Carquest, 391; Firestone, 435 |
| Madison to I-8 | Gas Depot, 490; **7-Eleven, 500**; Carl's Jr., 520; **Madison Plaza, roughly 526–574**, with small food/nails/payday/barber units and Petco at 540; Union Bank shell, 580; Valvoline, 610; west-side freeway ramp and Forester Creek edge | Jack in the Box, 495; Learn4Life, 511; Jiffy Lube, 539; KFC, 555; taco shop, 569; Western Dental, 583; El Compadre, 595; Shell/Food Mart area around 601; east-side freeway ramps |
| I-8 to Broadway/Awaken | Powersports/showroom shell around 690; Rocket/76 and smog, 710; **Soapy Joe's, 816**; **Starbucks drive-through, 850**; Marechiaro, 854; Carl's Boot & Leather, 862; CVS at the southwest Broadway corner; **Revive Pathway, 1240 Broadway**, west of 2nd; **Awaken, 950** | **Arco/ampm, 725**; **Bank of America, 845**; **Bostonia Post Office, 867**; east-Broadway service and clinic frontage |

### Time-sensitive storefront notes

- The Town & Country center's individual tenants change, but its cream/tan flat roof, raised parapets, tan columns, glass bands, and broad asphalt lot are durable composition anchors. Current property references: [Retail Insite](https://riretail.com/property/350-north-2nd-street/) and [NewMark Merrill](https://newmarkmerrill.com/property/el-cajon-town-country/).
- The 690 N 2nd powersports/showroom brand is time-sensitive. Preserve the low commercial shell and red-awning/showroom geometry; verify the current tenant before drawing readable signage.
- Walmart's exterior was recently remodeled, including a mural; use a dated reference rather than the existing generic in-game storefront. [Remodel report and exterior reference](https://timesofsandiego.com/business/2025/08/01/remodeled-el-cajon-walmart-market-debuts-new-features-mural/)
- El Cilantro is at 1285 E Madison, so Level 1's finish should bend visually toward the Madison corner rather than pretending the restaurant is a straight North 2nd Street storefront. [Center leasing reference](https://www.newmarkmerrill.com/wp-content/uploads/2021/03/El_Cajon_LB_10-25-23v2.pdf)
- Revive is on Broadway, west of North 2nd. Level 3 should make the Broadway turn readable with a street sign, intersection, and short lateral approach. Its address is also confirmed by the [California DHCS directory](https://www.dhcs.ca.gov/individuals/Documents/NTP-Provider-Clinic-Directory.pdf).

## Canonical level-by-level backdrop plan

### Chapter 1 — west side, northbound

#### Level 1: Sprouts parking lot → El Cilantro

Playable-side sequence:

1. Start deep enough inside the **Sprouts parking lot** to establish parked-car rows, cart returns, green store identity, and the large setback from North 2nd.
2. Wells Fargo pad and driveway break.
3. Walmart Neighborhood Market's large lot and remodeled storefront/mural.
4. Long Town & Country strip: repeating tan columns and parapets make a stable progress ruler.
5. Madison Avenue intersection and the **El Cilantro** corner finish.

Across the street, Romeo's, Walgreens, McDonald's, Arby's, No Dry Car Wash, Taco Bell, and the smaller east-side signs should pass in the far background. They are visual bearings, not combat platforms.

#### Level 2: 7-Eleven → I-8 underpass

Playable-side sequence:

1. Start on the **7-Eleven** pad at 500 N 2nd, with canopy/store massing and lot driveway.
2. Carl's Jr. and its parking/drive-through edge.
3. Madison Plaza's warm yellow/green stucco, large parking field, and Petco anchor.
4. Union Bank shell and Valvoline service bays.
5. Freeway approach: retaining walls, ramps, creek edge, concrete columns, and expanding shadow.
6. End inside the **I-8 underpass** shadow, not after it.

The current stage places “I-8” before “Madison Plaza.” That order is geographically wrong for northbound travel and must not survive the level split.

#### Inter-level bridge: I-8 → Soapy Joe's

The real corridor includes the 690 showroom/powersports shell and the 710 fuel/smog area before Soapy Joe's. For the current scope, cover this gap with a brief non-combat travel panel or loading montage. Do not silently teleport while displaying a locked camera.

#### Level 3: Soapy Joe's → Revive Pathway

Playable-side sequence:

1. Start in front of the real **Soapy Joe's**: white structure, vivid blue roof/logo band, palms, and the long white arched vacuum-canopy row.
2. Starbucks freestanding drive-through pad at 850.
3. Marechiaro, Carl's Boot & Leather, and the southwest Broadway commercial edge.
4. CVS/Broadway intersection establishes the turn.
5. Turn west along Broadway and finish at **Revive Pathway**, using the former medical-office massing rather than a generic storefront.

The Soapy Joe's reference image is available on its [official location page](https://soapyjoescarwash.com/location/el-cajon-n-2nd-st/). It must not be represented as the current generic turquoise two-bay car wash.

#### Level 4: Couch arena

Use the **Awaken Church parking lot** as the retained boss location:

- broad gray concrete façade;
- black trim and black entrances;
- warm wood accents;
- two-story glass grid;
- white lettering and orange/red gradient “A” mark;
- a large parking field suitable for the boss camera lock;
- Dave's BMX positioned as a persistent, readable story prop behind Couch.

The exterior can be checked against [Awaken's campus page](https://awakenchurch.com/service-locations/el-cajon-campus/) and this [dated exterior photograph](https://coronadotimes.com/wp-content/uploads/2023/05/Awaken-Church-El-Cajon.jpg).

### Chapter 2 — east side, southbound

#### Confirmed opening level: Bostonia Post Office → I-8 underpass

Playable-side sequence:

1. Start at the **Bostonia Post Office, 867 N 2nd St**, with its lot, postal façade cues, driveway, and fixed address-side orientation.
2. Bank of America at 845 and the surrounding service-lot rhythm.
3. Arco/ampm at 725 as the major fuel-canopy anchor.
4. Descend toward the east-side freeway ramps and concrete underpass.
5. End at the I-8 shadow from the opposite approach used in Chapter 1.

Across the road, Chapter 1 landmarks—Soapy Joe's, the 690 showroom shell, and west-side fuel/smog businesses—should now pass in reverse order. Later Chapter 2 endpoints south of I-8 remain deliberately open until the route is specified.

## Visual identity checklist for background production

Every panel should answer all of these before it is accepted:

- Which side of the street is playable?
- Which direction is the party traveling?
- What real address or intersection anchors the panel?
- Is the storefront at the correct curb setback, or is there a real parking lot in front?
- Can the player recognize the next anchor before reaching it?
- Do road stripes, traffic, driveways, parked cars, utility features, palms, freeway structures, and hills maintain continuity?
- Is the opposite side visible at the correct distance and moving with slower parallax?
- Are signs and building masses based on dated references rather than memory?

Recommended layers:

1. Near/playable-side curbs, parking aisles, props, and façades.
2. North 2nd Street lanes, traffic, medians, and crossing details.
3. Opposite-side lots and façades.
4. Freeway structures, utility lines, palms, hills, and sky.

## Current backdrop mismatches to remove

The existing images in [`assets/stage`](assets/stage) and the current landmark order in [`data/gameplay.json`](data/gameplay.json) are generic rather than location-authentic:

- Pharmacy, overpass, car-wash, and church imagery lacks the corridor's actual parking-lot setbacks and neighboring context.
- The generic car wash does not resemble Soapy Joe's blue/white building and arched vacuum canopy.
- Props float relative to the scenery because they are not registered to persistent address/intersection anchors.
- The world currently labels broad zones as Wallie's, I-8, Madison, and Waken, with I-8 before Madison. The real northbound order is Madison first, then I-8.
- A single long westbound-looking strip cannot support the newly defined four-level Chapter 1 and reverse-side Chapter 2 route.

## Data structure recommended for future implementation

Create independent level strips rather than stretching the existing single-stage arrays. A landmark record should resemble:

```json
{
  "id": "lvl1_town_country",
  "chapter": 1,
  "level": 1,
  "travel_direction": "northbound",
  "street_side": "west",
  "real_address": "350 N 2nd St",
  "cross_street": "between E Park Ave and E Madison Ave",
  "route_position": 0.72,
  "playable_setback": "large_parking_lot",
  "near_layer_asset": "lvl1_town_country_near.png",
  "opposite_anchor_ids": ["tshirt_mart", "arbys", "no_dry_car_wash"],
  "source_date": "2026-07-18",
  "confidence": "high"
}
```

Required level fields:

- chapter and level ID;
- travel direction and playable street side;
- start/end landmark IDs;
- world length and normalized landmark positions;
- intersection and driveway positions;
- separate near-road/opposite-road/far-sky art layers;
- camera-lock encounter regions that never overwrite landmark coordinates;
- loading/travel-card transitions for omitted real-world gaps;
- source URLs, source date, and confidence for each façade.

Use real business names in this research table, while keeping a separate `display_name` field for whatever fictional or parody signage is finally selected. That prevents art geometry and route accuracy from being lost when labels change.

## Manual visual-review links

These links open the route or a Street View panorama in Google Maps. Pan both directions and check the date shown by Google before approving final art.

- [Full walking route: Walgreens area to Awaken](https://www.google.com/maps/dir/?api=1&origin=215+N+2nd+St,+El+Cajon,+CA+92021&destination=950+N+2nd+St,+El+Cajon,+CA+92021&travelmode=walking)
- [Sprouts search/lot](https://www.google.com/maps/search/?api=1&query=Sprouts+Farmers+Market+152+N+2nd+St+El+Cajon+CA)
- [Walgreens east-side panorama](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=32.7969,-116.93575&heading=90&pitch=0&fov=90)
- [Town & Country west-side panorama](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=32.79869,-116.93575&heading=270&pitch=0&fov=90)
- [El Cilantro search/corner](https://www.google.com/maps/search/?api=1&query=El+Cilantro+1285+E+Madison+Ave+El+Cajon+CA)
- [7-Eleven search/lot](https://www.google.com/maps/search/?api=1&query=7-Eleven+500+N+2nd+St+El+Cajon+CA)
- [Madison Plaza/Petco panorama](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=32.80115,-116.93570&heading=270&pitch=0&fov=90)
- [I-8 underpass panorama](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=32.80275,-116.93582&heading=0&pitch=0&fov=90)
- [Soapy Joe's west-side panorama](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=32.80554,-116.93573&heading=270&pitch=0&fov=90)
- [Bostonia Post Office search/lot](https://www.google.com/maps/search/?api=1&query=Bostonia+Post+Office+867+N+2nd+St+El+Cajon+CA)
- [Revive Pathway search/façade](https://www.google.com/maps/search/?api=1&query=Revive+Pathway+1240+Broadway+El+Cajon+CA)
- [Awaken west-side panorama](https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=32.80844,-116.93570&heading=270&pitch=0&fov=90)

## Acceptance targets for the next art/engine pass

- One side of North 2nd remains playable for the whole level; no accidental street crossing.
- Level starts and finishes match the five locked anchors exactly.
- Landmark order matches real northbound or southbound travel.
- At least three fixed visual anchors remain visible or recently passed at any camera position.
- Parking-lot depth and storefront setbacks are encoded in both art and collision geometry.
- No foreground prop drifts independently of the landmark it belongs to.
- Hero action sets meet the target ranges above before additional cosmetic particles are counted as animation improvement.
- Animation events, not elapsed-time guesses, drive hitboxes, projectile release, footstep audio, hit-stop, and super VFX.

## Chapter 1 production visual style guide

This is the production contract for the four Chapter 1 strips, the route cards, the HUD, and the sunset finale. It deliberately turns the existing illustrated street plates into a coherent high-detail **pixel-art** presentation through authored pixel clusters, layered depth, and localized light; it does not permit a global pixelation or sharpening pass.

### Resolution, scale, and line language

- The logical canvas is **640x360** (16:9). Render gameplay at that resolution first, use nearest-neighbor integer scaling whenever the viewport allows it, and use a centered aspect-fit fallback only when the window is smaller.
- Actors retain their authored atlas density and use integer-aligned feet roots. Environment source art is resampled once into cached, nearest-scaled depth bands; it is never re-scaled inside the frame loop.
- Silhouettes use a 1–2 logical-pixel deep-ink edge, selective interior line breaks, and 2–4 pixel material clusters. Avoid smooth airbrush gradients, vector-perfect geometry, and thin anti-aliased UI strokes.
- Hero proportions stay tall and readable at a glance; ordinary enemies are compact but have a clearly different weapon or accessory silhouette; Couch stays broad, low, and waddling rather than oversized.

### Palette, lighting, and material rules

- Keep a warm Southwestern sunset base: amber/orange focal lamps, rose-to-violet sky, teal/cyan practical lights, charcoal asphalt, and near-black ink. Reserve high-saturation cyan, gold, pink, and orange for player ownership, pickups, danger, and supers.
- All grounded actors receive a contact shadow. Its width and alpha contract while jumping and widen slightly for heavy knockback. Wet stages add short broken reflection marks—not full mirror duplicates.
- Light is motivated per zone: warm store/setting-sun rims, cool car-wash and underpass fills, cyan signage accents, and orange flame flicker. Shading is applied per material (skin, denim, metal, glass, fire, fur), with upper-left rim and lower-right contact shade.
- Background hierarchy is: readable sky/mountains, less-contrasty distant lots, strong playable-side architecture, clear gameplay props, and sparse near occluders after actors. World anchors and collision props move 1:1; decorative far/mid/near bands may parallax.

### VFX, camera, and interface rules

- VFX use compact pixel clusters: white/yellow contact cores, directionally biased sparks, brick/gray debris, cyan support, and orange/red fire. Effects must leave a readable head/torso silhouette and have bounded counts, lifetime, shake, and flash intensity.
- Named animation events own contact, projectile release, planted footsteps, trails, hit spark, sound, hit-stop, shake, ground impact, and recovery. Simulation remains 60 Hz; presentation may use purposeful holds but never translation-only fake frames.
- Camera composition leads travel slightly, locks only to human-controlled party authority, and uses short bounded impact shake. Boss/landmark cards may frame a reveal but never make four-player combat unreadable.
- UI uses deep-navy panels, 1–2 px cyan/gold/pink ownership borders, supported bitmap-font glyphs, compact icon-first bars, and short route cards. UI never blocks the combat lanes; its scale/opacity and effects density are configurable.

### Cutscenes and results

- Dialogue uses portrait/color ownership, a compact comic-panel border, fresh-edge advance, and an explicit previously-viewed skip. It is a visual beat, not a full-screen text interruption.
- Results and route cards share the same deep-ink panel, gold top rule, cyan route accent, small landmark icon field, and crisp type. The BMX finale uses layered Chapter 1 sunset scenery, grounded wheel contact, parallax, and code-rendered character motion rather than a flat placeholder illustration.
