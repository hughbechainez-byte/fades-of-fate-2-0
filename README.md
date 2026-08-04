# The Fades of Fate — Foundation Demo

This is a Windows foundation for a 1–4 player, shared-screen arcade beat-em-up. **All four Chapter 1 levels are playable in order**: Sprouts parking lot → El Cilantro; 7-Eleven → I-8 underpass; Soapy Joe's → Revive approach; and the Couch boss showdown in the Awaken Church parking lot. Each level owns its own world width, walk rails, prop collision, encounter gates, camera locks, landmark theme, and results screen.

The researched animation audit, real-world corridor inventory, and canonical Chapter 1/Chapter 2 route are in [SECOND_STREET_AND_ANIMATION_KNOWLEDGE_BASE.md](SECOND_STREET_AND_ANIMATION_KNOWLEDGE_BASE.md).

Every project task must verify the persistent requirements in [ToDoList.md](ToDoList.md) unless the user explicitly waives them.

## Agent and developer sync contract (mandatory)

**Source of truth:** `https://github.com/hughbechainez-byte/the-fades-of-fate` branch `main`.

Any agent or worker (local Windows machine, Grok, Codex, CI, or remote session) must keep local and online trees synchronized. Do not treat a sandbox checkout, a previous chat, or an unpushed desktop folder as authoritative.

### Before starting work

1. Pull the newest `main` (or fetch and hard-reset only if the user explicitly allows discarding local drift).
2. Inspect the latest commit SHA on `origin/main` and the latest **Windows Build and Validate** Actions run for that SHA.
3. Read this section, `ToDoList.md`, and any task-specific notes in the knowledge base.

### While working

1. Prefer targeted commits on `main` (or a short-lived branch that is merged and deleted promptly).
2. Code, data JSON, tools, tests, and workflow YAML are edited in-repo and pushed so every other agent can pull them.
3. **Large binary Chapter 1 panoramas** (`assets/stage/chapter1_location_locked/ch1_l*_main_v2.png` and matching far/near) are produced only by the local bake tool. Non-display agents must change the bake source/tooling, push that code, and leave an explicit handoff for a local agent to run:

```powershell
git pull origin main
.\tools\rebake-and-commit.ps1 -Commit
git push origin main
```

4. Full desktop packaging remains local: `tools\Build-Windows.ps1` (PyInstaller + Desktop install). CI does **not** ship the `.exe`; it validates the same gates the package script uses before packaging.

### After finishing work

1. Commit and **push to `origin/main`** (or open a PR that is merged before handoff).
2. Confirm the push triggered **Windows Build and Validate** and that the run is green for the new SHA.
3. Report: commit SHA, GitHub URL, CI run URL/status, whether panorama rebake is still outstanding, and any local-only package step remaining.

### Bidirectional rule

| Direction | Required action |
|---|---|
| Online → local | `git pull origin main` (or clone) before continuing |
| Local → online | `git push origin main` after every completed change set |
| Tooling-only (no display) → local art | Push bake-tool changes; local agent runs `rebake-and-commit.ps1 -Commit` then pushes PNGs |
| Local art → online | Rebake commits the PNGs; push so CI and other agents see identical assets |

If local and `origin/main` diverge, stop and reconcile before further feature work. Silent dual trees are a defect.

The demo contains two selectable adult heroes, their autonomous allies, and two blacked-out **COMING SOON** roster cards:

- **Black Dave:** slim, lean and muscular; backward black cap and matching tank top; small gold-trim rectangular glasses; diamond studs; fists that ignite for ten seconds after six fast attack presses (+20% damage); a finite-ammo lane-shot BB gun; Bluetooth-speaker shockwave super.
- **Shelly:** shorter, fair-skinned and naturally soft with a small waist, fuller hips and a rounder rear silhouette; brunette bun; crop top and cargo pants; torch lighter; refill/cigarette/petting downtime; Chief companion and frenzy super.
- **Chief:** light-brown pit bull with a diamond-set gold Cuban-link collar. He rests when Dave and Shelly are settled, independently bites nearby threats, intercepts attackers pressuring Dave, responds to each hero's dedicated command meter, accepts a safe-moment pet, and goes into a full frenzy during Shelly's super.
- **KO:** a lean, dark-skinned Somali support fighter in a white lab coat and MMA gloves. He travels only on his skateboard, patiently selects a quiet opponent, rotates two punches and a kick every 20–30 combat seconds with a distinct lightning signature on each strike, dazes each target before the knockout, and periodically clears the active crowd in a blue-white speed blitz.

## Start playing

Double-click **The Fades of Fate** Desktop shortcut or `The Fades of Fate.exe` inside the demo folder. On the roster screen, confirm a hero and press confirm/Start again after everyone is ready. A one-human run defaults to player-controlled Black Dave plus CPU Shelly and Chief; choosing Shelly instead swaps in CPU Dave. Human players replace the CPU party in 2–4 player games.

Clearing Level 1 introduces Jerry, a skinny old man with shoulder-length wiry white hair, a low black cowboy hat, leather trench coat and walker. He warns the party that he saw Couch by the 7-Eleven while coming to El Cilantro next to Goodwill. Choose **Start Level 2/3/4** on each results screen; a named travel card makes the I-8, Broadway, and Awaken transitions explicit. Couch, her comic confrontation, the BMX prop and the hug/treat/BMX sunset celebration are reserved for the Level 4 Awaken Church finale.

### Keyboard (Player 1)

| Action | Keys |
|---|---|
| Move | WASD or arrow keys |
| Light combo | X (J or Z aliases) |
| Heavy / contextual throw | C (K alias) |
| Jump / air attack | Space, then light |
| Dodge | Left Shift (L or V aliases) |
| Super | Q (I or F aliases) |
| Call Chief | R |
| BB gun (Dave only) | G |
| Revive / pet Chief | Hold E nearby |
| Join / confirm | Enter or Space |
| Pause menu | Escape |
| Debug overlay | F3 |
| Fullscreen | F11 |
| Screenshot | F12 |

### Controller

| Action | Xbox-style layout |
|---|---|
| Move | Left stick or D-pad |
| Light combo | X |
| Heavy / contextual throw | Y |
| Jump / confirm | A |
| Dodge / back | B |
| Super | RB |
| Call Chief | RT (R3 fallback) |
| BB gun (Dave only) | LT (L3 fallback) |
| Revive teammate | Hold LB nearby |
| Join / pause | Start |

Escape or controller Start opens the in-game menu. It includes Resume, a keyboard/controller Controls page, Exit to Main Menu, and Exit Game; both exit choices require confirmation.

Controllers can be connected or removed while the game is running. Up to four unique controllers can join; the keyboard is one additional source but total active players remain capped at four.

The title and roster use the supplied Friday Activities KLICKAUD instrumental, packaged cleanly as `friday_activities_klickaud_menu.ogg`; starting Second Street hard-stops that stream and switches to `red_2nd_track_stage_8bit.ogg`. Returning to the main menu restores exactly one title loop. Both tracks are packaged in `assets\audio`.

## Easy customization

`data\gameplay.json` is loaded from beside the executable before the bundled copy. It controls:

- hero health, movement, jump, dodge, development-mode unlimited lives, revive time, weapons and supers;
- orthographic/oblique projection, camera dead zone/look-ahead/pan speed, screen shake, collision radii and crowd separation;
- walkable lane rails, physical scenery footprints, depth-sorted props and encounter camera-lock positions;
- every attack’s startup/active/recovery time, damage, range, stun and knockback;
- enemy health, damage, speed, range, telegraph time, cooldown, score and attack-token cost;
- CPU companion follow, engage, dodge, attack, Chief-command, charged-super, revive, and pet-idle behavior;
- Chief’s per-player meter cost/recharge, command damage/speed, follow speed, guard radius, autonomous pursuit, return pet timing, and frenzy damage/timing;
- Dave's BB ammo capacity, cooldown, damage, speed, lane tolerance, pickup size, CPU aim rules, and deterministic 2–4 eligible-KO drop window;
- Chapter/level route order, active-level landmarks, encounter rosters, trigger points, enemy caps, player-count scaling, finale boss placement, and the pre-Couch loading handoff;
- score/rank rules, completion-celebration timing, separate menu/stage music filenames, and audio volumes.

Authored animation atlases live in `assets\sprites`; transparent replacement PNGs with the same grid and dimensions are picked up automatically. `tools\build_sprite_atlas.py` normalizes newly generated transparent sheets into those runtime grids.

## Android content + release workflow

`tools/build_content_release.py` creates:
- `dist/content/fades-of-fate-content-pack.zip` with all `assets/` and `data/` payload;
- `dist/content/fades-of-fate-content-manifest.json` with revision + pack hash metadata.

The game checks the GitHub release feed on startup (`--content-feed`) and applies a newer content pack into `FADES_OF_FATE_CONTENT_ROOT` automatically, so PC and Android consume the same content snapshot.

`.github/workflows/android-apk-release.yml` builds the APK through Buildozer and uploads both the APK and content feed assets on tag pushes. `.github/workflows/windows-desktop-release.yml` builds and validates the PyInstaller package on a Windows runner, archives the complete onedir package, and uploads `The-Fades-of-Fate-<tag>-Windows-x64.zip` to the same GitHub Release.

The Windows build also checks the latest release's `fades-of-fate-app-manifest.json` when it opens. If a newer verified package is available, the title screen asks before updating; `--auto-update` applies it without prompting. The update helper downloads only the HTTPS GitHub package named by the manifest, verifies its size and SHA-256, waits for the game to exit, swaps in the complete onedir package, and relaunches it. Network or validation failures leave the current game usable.

To publish a PC update, update the game version metadata, commit and push `main`, then create and push a matching `v*` tag. Every such tag now receives the Windows ZIP automatically; extract it and launch `The Fades of Fate.exe`. The ZIP is required because the executable depends on its bundled `_internal`, `assets`, and `data` folders.

Restart the game after changing the JSON. Keep a backup before large edits.

### Turn any music file into the stage track

Drag an FFmpeg-readable music file (MP3, WAV, FLAC, M4A, and similar) onto `Convert Music to 8-Bit.cmd`. It creates a bitcrushed OGG in `assets\audio`, updates `data\gameplay.json`, and installs it as Second Street’s track. Restart the game afterward. The lower-level `tools\Convert-Music-To-8Bit.ps1` also supports explicit output paths, sample rates, crusher bit depth, and sample-hold values.

## Crash and QA logs

Every run writes searchable breadcrumbs to `logs\latest.log` beside the executable and also keeps a timestamped session log. An uncaught crash creates `logs\crash-*.log` containing the traceback plus the latest gameplay breadcrumbs. Double-click `Open Crash Logs.cmd` to open that folder.

`Run Foundation Self-Test.cmd` checks keyboard/controller mappings, live Chief/BB commands, off-screen Chief recall, unlimited development respawns, combat/collision/camera behavior, solo Dave + CPU Shelly, local 2–4 player creation, every Chapter 1 route and its encounter gates, Level 1's Jerry outro, inter-level handoffs, Level 4's Awaken Church Couch transition/boss completion, the BMX sunset strip, singleton music switching, rendering, and log creation. Its result is saved to `build\self_test_report.json` with Level 1–3, finale, and Dave fire-fist screenshots.

## Foundation architecture

- Pygame CE / SDL 2, 640×360 logical canvas, integer nearest-neighbor letterboxing, configurable fixed simulation rate, and one-shot input edges consumed exactly once per simulation step.
- A reusable orthographic/oblique 2.5D world separates stage X, floor depth and elevation; billboard sprites keep constant pixel size while scenery, actors, projectiles and physical props sort by their floor anchors.
- Union-aware lane rails remove internal seam walls; swept scenery collision, ally pass-through, deterministic enemy pushboxes, stable obstacle detours and spatial hashing prevent crowd/AI correction stutter.
- Attacks query their entire active window once per target with forgiving data-driven lane assist; layered hit sparks, impact rings, damage numbers, hitstop, flash and synchronized world shake make contact clear.
- Data-driven move timing and stats; five street-enemy roles including post-clear Security details, plus Couch; global attack-token limits; wave and boss scaling by player count.
- Contextual throws, four-hit chains, aerials, dodge invulnerability, hit-built super meter, separate rechargeable Chief meters, finite BB ammo with non-solid drops, revive window, score multipliers and hot-plug input.
- A four-level Chapter 1 campaign swaps data-backed geometry and themes at each results-screen handoff; deterministic outro and completion timelines freeze performance statistics before results, while the I-8-to-Soapy bridge appears as an explicit travel card.
- Ninety-eight canonical clips provide 900 rooted authored keys—8–16 meaningful drawings per clip—on a capture-safe 30 Hz presentation timeline while combat remains fixed at 60 Hz. Dave and Shelly use twelve true stride keys at 15 poses per second for a 0.8-second gait; KO adds 64 strict actor-specific poses across idle, skateboard travel, preparation, two punches, a kick, and his speed-blitz super. Phase advances from applied travel and survives brief stops. Manifest-backed tests reject duplicates, translation filler, foot-line drift, placeholder aliases, or uneven synthetic in-betweens.
- Level-aware procedural pixel art and physical props share fixed world anchors, so Sprouts, 7-Eleven, Madison Plaza, I-8, Soapy Joe's, Broadway, Revive, and Awaken Church track progress one-to-one instead of floating.
- Original parody storefront signage and generated character/stage art; no commercial game art, logos, or fonts are copied. The title music and synthesized voice/SFX library are original; the stage track remains the local 8-bit conversion selected for Second Street.

## Research basis

The foundation borrows genre principles, not copyrighted assets: simple Simpsons/TMNT-style onboarding; TMNT: Shredder’s Revenge depth forgiveness, short waves and hit-built supers; Streets of Rage positioning, enemy-role cooperation and readable attack counts; Final Fight contextual grabs; Castle Crashers four-player local co-op. Useful primary/developer references:

- [The Simpsons arcade operator manual](https://www.arcade-museum.com/manuals-videogames/S/Simpsons-Operators-Manual.pdf)
- [TMNT arcade operator manual](https://www.arcade-museum.com/manuals-videogames/T/Teenage_Mutant_Ninja_Turtles__1989__Konami.pdf)
- [TMNT: Shredder’s Revenge developer deep dive](https://www.gamedeveloper.com/design/deep-dive-how-tmnt-s-shredder-s-revenge-was-built-from-nostalgia-and-new-ideas)
- [Streets of Rage 4 developer interview](https://blog.playstation.com/2020/04/30/streets-of-rage-4-how-three-studios-revived-a-legendary-series/)
- [Streets of Rage 4 making-of](https://www.nintendolife.com/news/2020/12/feature_the_making_of_streets_of_rage_4_by_the_people_who_made_it-happen)
- [Final Fight at Capcom Town](https://captown.capcom.com/en/classic_games/17)
- [Castle Crashers on Steam](https://store.steampowered.com/app/204360/Castle_Crashers/)
- [Fight’N Rage on Steam](https://store.steampowered.com/app/674520/FightN_Rage/)
- [GameDev StackExchange: side-scrolling beat-em-up perspective in Unreal Engine](https://gamedev.stackexchange.com/questions/173495/how-can-you-create-a-side-scrolling-beat-em-up-perspective-in-unreal-engine)

Level 1 is a fictionalized July 2026 snapshot of the west/even-address side from Sprouts at 152 N 2nd Street to El Cilantro by Madison, with the opposite side used only as distant bearings. Durable massing, parking setbacks, cart returns, driveway rhythm and intersection order are retained; lettering and logos are original game art. Hostile characters are a fictional road-raider/scavenger gang rather than depictions of identifiable unhoused people.
