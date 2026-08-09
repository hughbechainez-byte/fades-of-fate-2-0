from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pygame

from . import sprite_atlas
from .animation_manifest import ANIMATION_CLIPS, total_authored_poses
from .config import LOGICAL_SIZE, campaign_levels, executable_root, resource_path
from .entities import AmmoPickup, Enemy, SuperButanePickup
from .game import COUCH_DOPE_OFFER_TAUNT, FadesGame, SOLO_CPU_COMPANIONS, SelectSlot
from .input_manager import InputManager, InputSnapshot
from .level_outro import JERRY_LEVEL_ONE_BEATS
from .logger import breadcrumb, get_log_paths
from .world_engine import WorldPoint


def _check(condition: bool, name: str, report: dict[str, Any], detail: str = "") -> None:
    if not condition:
        raise AssertionError(f"{name}: {detail or 'condition failed'}")
    report["checks"].append({"name": name, "status": "pass", "detail": detail})


def _translation_normalized_signature(surface: pygame.Surface) -> tuple[tuple[int, int], bytes]:
    """Hash visible shape and pixels without rewarding translation-only filler."""

    bounds = surface.get_bounding_rect(min_alpha=1)
    if not bounds.w or not bounds.h:
        raise AssertionError("authored animation pose is empty")
    cropped = surface.subsurface(bounds).copy()
    return cropped.get_size(), pygame.image.tobytes(cropped, "RGBA")


def _sprite_detail(surface: pygame.Surface) -> tuple[int, int, int]:
    """Return visible-pixel, color, and blue-detail counts for art QA."""

    visible = 0
    colors: set[tuple[int, int, int]] = set()
    blue_detail = 0
    for x in range(surface.get_width()):
        for y in range(surface.get_height()):
            pixel = surface.get_at((x, y))
            if pixel.a < 16:
                continue
            visible += 1
            colors.add((pixel.r, pixel.g, pixel.b))
            if pixel.b > pixel.r * 1.25 and pixel.b > pixel.g * 1.08:
                blue_detail += 1
    return visible, len(colors), blue_detail


def _configure_campaign_level(game: FadesGame, level: dict[str, Any]) -> None:
    """Select a full authored runtime snapshot for direct mechanics QA."""

    game._select_campaign_level(str(level["id"]))


def _exercise_nonfinal_campaign_stage(
    game: FadesGame,
    manager: InputManager,
    report: dict[str, Any],
    level: dict[str, Any],
    output_dir: Path,
) -> Path:
    """Travel every trigger, clear every wave, and prove a normal stage ends."""

    _configure_campaign_level(game, level)
    game._start_stage()
    manager.clear_held_state()
    screenshot = output_dir / f"self_test_level_{int(level['number'])}_gameplay.png"
    canvas = pygame.Surface(LOGICAL_SIZE)
    game.draw(canvas)
    pygame.image.save(canvas, screenshot)
    _check(
        screenshot.is_file() and screenshot.stat().st_size > 5_000,
        f"level_{int(level['number'])}_background_render",
        report,
        f"{level['title']} renders its {level['background_theme']} route",
    )
    human = next(player for player in game.players if not player.is_cpu)
    for encounter_index, encounter in enumerate(level["encounters"]):
        human.x = float(encounter["trigger_x"])
        game._update_encounters(0.0)
        _check(
            game.encounter_active and game.encounter_index == encounter_index,
            f"level_{int(level['number'])}_encounter_{encounter_index + 1}_triggered",
            report,
            str(encounter["name"]),
        )
        # A regular encounter may promote one or more authored post-clear
        # reinforcements.  Keep draining its queues and clearing every live
        # foe until the shared gate actually opens, rather than assuming one
        # base list describes the full combat chain.
        for _ in range(540):
            while game.spawn_queue:
                game._spawn_enemy(game.spawn_queue.pop(0))
            for spawned in list(game.enemies):
                if spawned.alive:
                    spawned.state = "chase"
                    spawned.take_damage(100_000, game, game.players[0], knockdown=True)
            manager.process_events([])
            game.update(1.0 / 60.0)
            manager.consume_pressed()
            if not game.encounter_active:
                break
        _check(
            not game.encounter_active and game.encounter_index == encounter_index + 1,
            f"level_{int(level['number'])}_encounter_{encounter_index + 1}_cleared",
            report,
            f"{encounter['name']} clears through its authored gate",
        )
    _check(
        game.state == "complete" and game.level_stats.finished and game.completion_stats is not None,
        f"level_{int(level['number'])}_completion",
        report,
        f"{level['title']} reaches its playable results screen",
    )
    return screenshot


class _MusicProbe:
    """Record music lifecycle calls without requiring an audio device."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.current_track: str | None = None

    def play_music_file(self, filename: str | Path, *, loop: bool = True) -> bool:
        self.current_track = Path(filename).name
        self.calls.append(("play", self.current_track, loop))
        return True

    def stop_music(self, fade_ms: int = 250) -> None:
        self.calls.append(("stop", int(fade_ms)))
        self.current_track = None

    def shutdown(self) -> None:
        self.calls.append(("shutdown",))
        self.current_track = None


def run_foundation_self_test(output_dir: Path | None = None) -> dict[str, Any]:
    """Exercise input, combat, all Chapter 1 stages, finale, and rendering."""
    started = time.perf_counter()
    report: dict[str, Any] = {
        "title": "The Fades of Fate",
        "suite": "foundation",
        "status": "running",
        "checks": [],
    }
    output_dir = output_dir or executable_root() / "build"
    output_dir.mkdir(parents=True, exist_ok=True)

    manager = InputManager(discover_controllers=False)
    game: FadesGame | None = None
    try:
        manager.add_synthetic_controller(77, name="QA Virtual Xbox Layout", mapped=True)
        controller_binding = {"type": "controller", "instance_id": 77}
        keyboard_binding = {"type": "keyboard"}

        controller_light = pygame.event.Event(
            getattr(pygame, "CONTROLLERBUTTONDOWN", pygame.JOYBUTTONDOWN),
            {"instance_id": 77, "button": pygame.CONTROLLER_BUTTON_X},
        )
        manager.process_events([controller_light])
        snap = manager.snapshot(controller_binding)
        _check("light" in snap.pressed, "controller_x_light", report, "synthetic SDL controller X maps to light attack")

        controller_axis = pygame.event.Event(
            getattr(pygame, "CONTROLLERAXISMOTION", pygame.JOYAXISMOTION),
            {"instance_id": 77, "axis": pygame.CONTROLLER_AXIS_LEFTX, "value": 0.82},
        )
        manager.process_events([controller_axis])
        _check(manager.snapshot(controller_binding).move_x > 0.65, "controller_left_stick", report, "left stick produces rightward movement")

        controller_action_events = [
            pygame.event.Event(getattr(pygame, "CONTROLLERBUTTONDOWN", pygame.JOYBUTTONDOWN), {"instance_id": 77, "button": button})
            for button in (
                pygame.CONTROLLER_BUTTON_Y,
                pygame.CONTROLLER_BUTTON_A,
                pygame.CONTROLLER_BUTTON_B,
                pygame.CONTROLLER_BUTTON_RIGHTSHOULDER,
                pygame.CONTROLLER_BUTTON_LEFTSHOULDER,
                pygame.CONTROLLER_BUTTON_START,
            )
        ]
        manager.process_events(controller_action_events)
        manager.process_events([
            pygame.event.Event(
                getattr(pygame, "CONTROLLERAXISMOTION", pygame.JOYAXISMOTION),
                {
                    "instance_id": 77,
                    "axis": pygame.CONTROLLER_AXIS_TRIGGERRIGHT,
                    "value": 0.82,
                },
            ),
            pygame.event.Event(
                getattr(pygame, "CONTROLLERAXISMOTION", pygame.JOYAXISMOTION),
                {
                    "instance_id": 77,
                    "axis": pygame.CONTROLLER_AXIS_TRIGGERLEFT,
                    "value": 0.82,
                },
            ),
        ])
        mapped_actions = manager.snapshot(controller_binding).pressed
        _check(
            {"heavy", "jump", "dodge", "super", "chief", "secondary", "interact", "pause"}.issubset(mapped_actions),
            "controller_action_layout",
            report,
            "Y/A/B/RB/RT/LT/LB/Start map to combat, Chief, secondary, interact, and pause",
        )

        key_event = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_j, "repeat": False})
        manager.process_events([key_event])
        _check("light" in manager.snapshot(keyboard_binding).pressed, "keyboard_light", report, "J maps to light attack")
        manager.process_events([pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_r, "repeat": False})])
        _check("chief" in manager.snapshot(keyboard_binding).pressed, "keyboard_chief_command", report, "R maps to the dedicated Chief command")
        manager.process_events([pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_g, "repeat": False})])
        _check("secondary" in manager.snapshot(keyboard_binding).pressed, "keyboard_secondary", report, "G maps to the contextual secondary")

        manager.clear_held_state()
        game = FadesGame(manager, mute=True)
        provenance_path = output_dir / "runtime_provenance.json"
        provenance_path.write_text(
            json.dumps(game.provenance, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        packaged_provenance = game.provenance["build_provenance_path"] != "source"
        _check(
            game.provenance["all_assets_resolved"]
            and not game.provenance["noncanonical_asset_used"]
            and not game.provenance["fallback_asset_used"]
            and (not packaged_provenance or game.provenance["artifact_match"] is True),
            "runtime_provenance",
            report,
            f"scene/assets resolved from one root; artifact_match={game.provenance['artifact_match']}",
        )

        chapter_one_levels = campaign_levels(game.data)
        route_manifest = [
            (str(level["start"]["id"]), str(level["end"]["id"]))
            for level in chapter_one_levels
        ]
        _check(
            [int(level["number"]) for level in chapter_one_levels] == [1, 2, 3, 4]
            and [str(level["background_theme"]) for level in chapter_one_levels]
            == [
                "sprouts_el_cilantro",
                "seven_eleven_underpass",
                "soapy_joes_revive",
                "awaken_church_finale",
            ]
            and route_manifest
            == [
                ("sprouts_parking_lot", "el_cilantro_madison"),
                ("seven_eleven", "i8_underpass"),
                ("soapy_joes", "revive_pathway"),
                ("awaken_church_lot", "daves_bmx"),
            ],
            "chapter_one_route_manifest",
            report,
            "Levels run Sprouts→El Cilantro, 7-Eleven→I-8, Soapy Joe's→Revive approach, then Awaken Church finale",
        )
        level_one = chapter_one_levels[0]
        landmark_ids = [str(landmark["id"]) for landmark in level_one["landmarks"]]
        _check(
            landmark_ids
            == [
                "sprouts_parking_lot",
                "wells_fargo_pad",
                "walmart_neighborhood_market",
                "town_country",
                "goodwill_frontage",
                "madison_intersection",
                "el_cilantro_madison",
            ]
            and str(level_one["end"]["real_name"]) == "El Cilantro",
            "level_one_landmark_manifest",
            report,
            "ordered west-side landmarks terminate beside Goodwill at El Cilantro",
        )
        couch_locations = [
            (int(level["number"]), encounter_index)
            for level in chapter_one_levels
            for encounter_index, encounter in enumerate(level["encounters"])
            for kind in encounter["base"]
            if kind == "couch"
        ]
        finale = chapter_one_levels[-1]
        _check(
            couch_locations == [(4, len(finale["encounters"]) - 1)]
            and all(
                level.get("boss") is None
                and not bool(level.get("chapter_finale", False))
                and not bool(level.get("boss_transition", False))
                for level in chapter_one_levels[:-1]
            )
            and finale.get("boss") == "couch"
            and bool(finale.get("chapter_finale", False))
            and bool(finale.get("boss_transition", False))
            and finale["encounters"][-1]["base"] == ["couch"],
            "sole_couch_awaken_finale",
            report,
            "Couch exists only as Chapter 1 Level 4's final Awaken Church wave",
        )
        regular_levels = chapter_one_levels[:3]
        regular_populations = [
            sum(
                len(encounter["base"])
                + sum(
                    len(reinforcement["base"])
                    for reinforcement in encounter.get("post_clear_reinforcements", ())
                )
                for encounter in level["encounters"]
            )
            for level in regular_levels
        ]
        security_populations = [
            sum(
                kind == "security"
                for encounter in level["encounters"]
                for reinforcement in encounter.get("post_clear_reinforcements", ())
                for kind in reinforcement["base"]
            )
            for level in regular_levels
        ]
        security_speech = [
            str(reinforcement.get("speech", ""))
            for level in regular_levels
            for encounter in level["encounters"]
            for reinforcement in encounter.get("post_clear_reinforcements", ())
        ]
        finale_security = [
            kind
            for encounter in finale["encounters"]
            for kind in encounter["base"]
        ] + [
            kind
            for encounter in finale["encounters"]
            for reinforcement in encounter.get("post_clear_reinforcements", ())
            for kind in reinforcement["base"]
        ]
        security_stats = game.data["enemies"].get("security", {})
        _check(
            float(security_stats.get("health", 0)) > float(game.data["enemies"]["cart"]["health"])
            and float(security_stats.get("damage", 0)) > float(game.data["enemies"]["cart"]["damage"])
            and regular_populations == sorted(regular_populations)
            and security_populations == sorted(security_populations)
            and security_populations[0] > 0
            and len(security_speech) == len(set(security_speech))
            and "security" not in finale_security
            and not finale["encounters"][-1].get("post_clear_reinforcements"),
            "security_reinforcement_escalation",
            report,
            "Levels 1-3 add increasingly dense post-clear security mini-waves with unique warnings; Couch's finale has none",
        )
        _check(
            game.level_id == "chapter_1_level_1"
            and game.level_title == "Sprouts to El Cilantro"
            and len(game.data["encounters"]) == 3
            and [encounter["name"] for encounter in game.data["encounters"]]
            == ["Sprouts Parking Lot", "Town & Country", "El Cilantro at Madison"]
            and not game.level_has_couch
            and not game.level_is_chapter_finale
            and not bool(game.data["transitions"]["boss_loading"]["enabled"])
            and all(
                kind != "couch"
                for encounter in game.data["encounters"]
                for kind in encounter["base"]
            ),
            "active_level_one_contract",
            report,
            "playable Level 1 has exactly three encounters, Jerry outro, and no Couch/loading handoff",
        )

        animation_floor_failures: list[str] = []
        for clip in ANIMATION_CLIPS:
            poses = sprite_atlas.animation_frames(clip.actor, clip.state)
            meaningful = {_translation_normalized_signature(pose) for pose in poses}
            if len(poses) < 5 or len(set(clip.phases)) < 5 or len(meaningful) < 5:
                animation_floor_failures.append(f"{clip.actor}:{clip.state}")
        _check(
            len(ANIMATION_CLIPS) == 202
            and total_authored_poses() == 1836
            and not animation_floor_failures,
            "animation_floor_202_clips_1836_poses",
            report,
            "all 202 active clips provide 8-16 rooted, translation-normalized authored keys (1836 total) on a 30 Hz presentation clock",
        )
        foundation_rows = {
            (character, state): sprite_atlas.foundation_character_frames(character, state)
            for character in ("jermaine", "white_dave")
            for state in ("idle", "walk", "attack_1")
        }
        foundation_expected = {
            ("jermaine", "idle"): 8,
            ("jermaine", "walk"): 8,
            ("jermaine", "attack_1"): 8,
            ("white_dave", "idle"): 8,
            ("white_dave", "walk"): 12,
            ("white_dave", "attack_1"): 8,
        }
        _check(
            all(len(foundation_rows[key]) == expected for key, expected in foundation_expected.items())
            and all(
                set(pygame.image.tobytes(frame, "RGBA")[3::4]) <= {0, 255}
                and frame.get_bounding_rect(min_alpha=1).bottom
                == sprite_atlas.foundation_character_ground_y(character) + 1
                for (character, _state), frames in foundation_rows.items()
                for frame in frames
            )
            and resource_path("assets/portraits/white_dave_portrait_pixel_v2.png").is_file()
            and resource_path("assets/portraits/jermaine_portrait_pixel_v1.png").is_file(),
            "foundation_character_authored_runtime",
            report,
            "Jermaine and White Dave load hard-alpha authored idle/walk/attack rows on the uniformly scaled rooted ground line with White Dave's matching menu portrait",
        )
        fist_cell_size, fist_metadata = sprite_atlas._load_dave_fist_metadata()
        _check(
            fist_cell_size == (128, 128)
            and len(fist_metadata) == 17
            and sum(len(phases) for phases in fist_metadata.values()) == 144
            and sprite_atlas._dave_fist_anchors("idle", 4) == ((50, 48), (85, 49))
            and sprite_atlas._dave_fist_anchors("heavy", 4) == ((39, 62), (93, 30))
            and sprite_atlas._dave_fist_anchors("down", 6) == ((83, 98), (93, 129)),
            "dave_semantic_fist_landmarks",
            report,
            "packaged metadata maps both hands for all 144 Dave poses and rejects the prior idle-bicep, kick-sneaker, and downed-face/shoe anchors",
        )

        jerry_beat_names = [beat.name for beat in JERRY_LEVEL_ONE_BEATS]
        jerry_dialogue = " ".join(beat.dialogue for beat in JERRY_LEVEL_ONE_BEATS)
        jerry_state_signatures = {
            tuple(
                _translation_normalized_signature(frame)
                for frame in sprite_atlas.animation_frames("jerry", state)
            )
            for state in ("idle", "support", "talk", "point")
        }
        _check(
            jerry_beat_names == ["arrival", "warning", "clarification", "reaction", "finished"]
            and len({beat.jerry_pose for beat in JERRY_LEVEL_ONE_BEATS}) == 5
            and "Couch" in jerry_dialogue
            and "7-Eleven" in jerry_dialogue
            and "El Cilantro" in jerry_dialogue
            and "Goodwill" in jerry_dialogue
            and len(jerry_state_signatures) == 4,
            "jerry_dialogue_and_pose_library",
            report,
            "five-beat warning names Couch/7-Eleven/El Cilantro/Goodwill and uses four distinct twenty-four-pose art states",
        )

        sunset_frames = tuple(sprite_atlas.sunset_frame(index) for index in range(8))
        sunset_ready = all(frame is not None for frame in sunset_frames)
        sunset_art = tuple(frame for frame in sunset_frames if frame is not None)
        sunset_signatures = {
            _translation_normalized_signature(frame)
            for frame in sunset_art
        }
        sunset_detail = [_sprite_detail(frame) for frame in sunset_art]
        _check(
            sunset_ready
            and len(sunset_art) == 8
            and len(sunset_signatures) == 8
            and all(visible > 3_500 and colors > 100 and blue > 180 for visible, colors, blue in sunset_detail),
            "refined_sunset_bmx_strip",
            report,
            "eight detailed Dave/Shelly/Chief authored BMX keys replace the old rectangle placeholder",
        )

        audio_config = game.data["audio"]
        menu_music = str(audio_config["menu_music"])
        stage_music = str(audio_config["stage_music"])
        music_paths = tuple(resource_path(f"assets/audio/{filename}") for filename in (menu_music, stage_music))
        _check(
            menu_music != stage_music
            and all(path.is_file() and path.read_bytes()[:4] == b"OggS" for path in music_paths),
            "menu_stage_music_assets",
            report,
            f"distinct packaged OGG tracks: {menu_music} -> {stage_music}",
        )
        game.audio_manager.shutdown()
        music_probe = _MusicProbe()
        game.audio_manager = music_probe  # type: ignore[assignment]
        game.mute = False
        _check(
            game._play_menu_music() and music_probe.current_track == menu_music,
            "menu_music_lifecycle",
            report,
            f"title/select loop starts {menu_music}",
        )

        # KO is an explicit CPU-only roster choice. He retains the dedicated
        # low-frequency companion state machine and never becomes a Player.
        game.select_slots = [
            SelectSlot(
                keyboard_binding,
                character_index=0,
                confirmed=True,
                cpu_companion_index=2,
            )
        ]
        game._start_stage()
        _check(
            len(game.players) == 1
            and game.ko_companion is not None
            and game.ko_companion.owner is game.players[0]
            and not any(player.character == "ko" for player in game.players),
            "solo_ko_cpu_selection",
            report,
            "start-screen KO choice creates one authored CPU support fighter and no Player placeholder",
        )

        game.select_slots = [
            SelectSlot(
                keyboard_binding,
                character_index=0,
                confirmed=True,
                cpu_companion_index=SOLO_CPU_COMPANIONS.index("white_dave"),
            )
        ]
        game._start_stage()
        _check(
            SOLO_CPU_COMPANIONS[2] == "ko"
            and len(game.players) == 2
            and game.players[1].is_cpu
            and game.players[1].character == "white_dave"
            and game.ko_companion is None,
            "solo_white_dave_cpu_selection",
            report,
            "start-screen White Dave choice creates a standard Player CPU while KO remains roster index 2",
        )

        # Solo still defaults to human Dave plus CPU Shelly and Chief, without
        # silently increasing encounter scaling to a two-human budget.
        game.select_slots = [SelectSlot(keyboard_binding, character_index=0, confirmed=True)]
        game._start_stage()
        _check(
            music_probe.current_track == stage_music
            and ("play", stage_music, True) in music_probe.calls,
            "stage_music_lifecycle",
            report,
            f"starting Second Street switches to {stage_music}",
        )
        _check(
            len(game.players) == 2 and not game.players[0].is_cpu and game.players[1].is_cpu,
            "solo_cpu_party",
            report,
            "human Black Dave plus CPU Shelly created",
        )
        _check(
            [player.character for player in game.players] == ["black_dave", "shelly"] and game._scaling_index() == 0,
            "solo_default_roster",
            report,
            "solo uses Dave/Shelly while retaining one-player encounter scaling",
        )
        _check(
            len(game.chiefs) == 1 and game.chiefs[0].owner is game.players[1],
            "solo_chief_owner",
            report,
            "Chief stays assigned to CPU Shelly",
        )
        _check(
            game.players[0].bb_ammo == int(game.data["bb_gun"]["start_ammo"])
            and game.players[1].bb_ammo == 0,
            "solo_dave_bb_ammo",
            report,
            "Dave alone starts with finite BB ammo",
        )
        near = game.projection.project(WorldPoint(100.0, 245.0), camera_depth=game._projection_depth_origin)
        far = game.projection.project(WorldPoint(100.0, 315.0), camera_depth=game._projection_depth_origin)
        _check(
            near.sprite_scale == far.sprite_scale == 1.0 and near.y != far.y,
            "orthographic_depth_projection",
            report,
            "lane depth changes screen position without resizing pixel sprites",
        )
        player_radius_x = float(game.data["engine"]["physics"]["player_radius_x"])
        blocked = game.stage_geometry.resolve_move(
            WorldPoint(420.0, 247.0),
            120.0,
            0.0,
            radius=player_radius_x,
        )
        _check(
            blocked.x <= 430.0,
            "physical_sprouts_cart_return",
            report,
            "shared world collision prevents walking through the Sprouts parking-lot cart return",
        )
        seam_crossings = [
            game.stage_geometry.resolve_move(WorldPoint(seam - 10.0, 275.0), 20.0, 0.0, radius=7.0).x
            for seam in (800.0, 1600.0, 2400.0)
        ]
        _check(
            all(result > seam for result, seam in zip(seam_crossings, (800.0, 1600.0, 2400.0))),
            "sprouts_route_lane_seams",
            report,
            "all three Sprouts-to-El-Cilantro rail joins are traversable",
        )
        human_x, cpu_x = game.players[0].x, game.players[1].x
        game.players[1].x = 620.0
        game._update_camera(0.5)
        _check(game.camera_x == 0.0, "human_camera_authority", report, "CPU companion cannot pull the camera away from Dave")
        game.players[0].x, game.players[1].x = human_x, cpu_x
        game._spawn_enemy("stick")
        solo_enemy = game.enemies[-1]
        solo_enemy.state = "chase"
        solo_enemy.x = game.players[1].x + 22.0
        solo_enemy.y = game.players[1].y
        cpu_snapshot = game._cpu_snapshot(game.players[1], 1.0 / 60.0)
        _check(
            bool(cpu_snapshot.pressed & {"light", "heavy", "super", "chief"}),
            "cpu_companion_combat",
            report,
            "CPU Shelly independently selects an attack or Chief command",
        )
        dave, shelly = game.players
        chief = game.chiefs[0]
        shelly.set_state("idle")
        shelly.cpu_action_cooldown = 0.0
        shelly.super_meter = 0.0
        shelly.chief_meter = float(game.data["chief"]["command_meter_max"])
        solo_enemy.x, solo_enemy.y = shelly.x + 100.0, shelly.y
        cpu_chief_snapshot = game._cpu_snapshot(shelly, 1.0 / 60.0)
        _check(
            "chief" in cpu_chief_snapshot.pressed,
            "cpu_chief_command_choice",
            report,
            "CPU companion spends its own Chief meter when an enemy is in command range",
        )
        game.enemies.clear()
        game._spawn_enemy("stick")
        chief_target = game.enemies[-1]
        chief_target.state = "chase"
        chief_target.cooldown = 99.0
        chief_target.x, chief_target.y = chief.x + 65.0, chief.y
        chief.attack_cooldown = 0.0
        chief_before = chief_target.health
        for _ in range(90):
            chief.update(game, 1.0 / 60.0)
            if chief_target.health < chief_before:
                break
        _check(
            chief_target.health < chief_before,
            "chief_autonomous_bite",
            report,
            "Chief independently closes distance and bites a nearby threat",
        )
        game.enemies.clear()
        shelly.set_state("idle")
        dave.set_state("idle")
        shelly.idle_time = dave.idle_time = 1.0
        chief.x, chief.y = shelly.x - 28.0, shelly.y + 10.0
        settled_position = (chief.x, chief.y)
        chief.update(game, 1.0 / 60.0)
        _check(
            chief.state == "sit" and (chief.x, chief.y) == settled_position,
            "chief_party_idle_settle",
            report,
            "Chief enters his sit state and stays still when Dave and Shelly are both idle",
        )
        chief.x, chief.y, chief.pet_cooldown = dave.x + 25.0, dave.y + 8.0, 0.0
        dave.idle_time = 4.0
        game._frame_snapshots = {dave.slot: InputSnapshot(pressed=frozenset({"interact"}))}
        game._update_chief_petting()
        _check(chief.state == "pet" and dave.state == "pet", "chief_pet_interaction", report, "Dave can pet Chief during a safe moment")

        manager.clear_held_state()
        game.select_slots = [SelectSlot(controller_binding, character_index=0, confirmed=True)]
        game._start_stage()
        controller_dave = game.players[0]
        controller_bb_before = controller_dave.bb_ammo
        game.hitstop_remaining = 0.08
        controller_bb_trigger = pygame.event.Event(
            getattr(pygame, "CONTROLLERAXISMOTION", pygame.JOYAXISMOTION),
            {"instance_id": 77, "axis": pygame.CONTROLLER_AXIS_TRIGGERLEFT, "value": 0.82},
        )
        manager.process_events([controller_bb_trigger])
        game.update(1.0 / 60.0)
        manager.consume_pressed()
        _check(
            controller_dave.bb_ammo == controller_bb_before - 1
            and any(projectile.kind == "bb" for projectile in game.projectiles),
            "controller_bb_gun_live",
            report,
            "controller LT fires one finite-ammo BB through live gameplay during hitstop",
        )
        manager.process_events([
            pygame.event.Event(
                getattr(pygame, "CONTROLLERAXISMOTION", pygame.JOYAXISMOTION),
                {"instance_id": 77, "axis": pygame.CONTROLLER_AXIS_TRIGGERLEFT, "value": -1.0},
            )
        ])
        game._go_title()
        _check(
            music_probe.current_track == menu_music,
            "return_to_menu_music",
            report,
            "leaving gameplay restores the configured menu loop",
        )

        game.state = "title"
        keyboard_join = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN, "repeat": False})
        manager.process_events([keyboard_join])
        game.handle_events([keyboard_join])
        controller_join = pygame.event.Event(
            getattr(pygame, "CONTROLLERBUTTONDOWN", pygame.JOYBUTTONDOWN),
            {"instance_id": 77, "button": pygame.CONTROLLER_BUTTON_A},
        )
        manager.process_events([controller_join])
        game.handle_events([controller_join])
        _check(game.state == "character_select" and len(game.select_slots) == 2, "join_and_select_flow", report, "keyboard Enter and controller A join through the real menu event path")
        game.select_slots[0].confirmed = True
        game.select_slots[1].confirmed = True
        game._start_stage()
        _check(len(game.players) == 2, "two_player_start", report, "keyboard plus controller players created")
        _check([p.character for p in game.players] == ["black_dave", "shelly"], "both_heroes_playable", report, "Black Dave and Shelly selected")
        _check(len(game.chiefs) == 1 and game.chiefs[0].owner.character == "shelly", "chief_companion", report, "Chief follows Shelly")
        _check(
            all(player.chief_meter == float(game.data["chief"]["command_meter_max"]) for player in game.players),
            "independent_chief_meters",
            report,
            "Dave and Shelly each start with their own ready Chief meter",
        )
        saved_positions = [(player.x, player.y) for player in game.players]
        game.players[0].x = game.players[1].x = 220.0
        game.players[0].y = game.players[1].y = 270.0
        game._resolve_actor_separation()
        _check(
            (game.players[0].x, game.players[0].y) == (game.players[1].x, game.players[1].y),
            "allied_hero_passthrough",
            report,
            "Dave and Shelly no longer body-block each other",
        )
        for player, (saved_x, saved_y) in zip(game.players, saved_positions):
            player.x, player.y = saved_x, saved_y

        escape_event = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE, "repeat": False})
        manager.process_events([escape_event])
        game.handle_events([escape_event])
        _check(game.pause and game.pause_page == "menu", "escape_pause_menu", report, "gameplay opens the full pause menu")
        game.pause_page = "controls"
        pause_canvas = pygame.Surface(LOGICAL_SIZE)
        game.draw(pause_canvas)
        _check(pause_canvas.get_at((320, 36)) != pause_canvas.get_at((0, 0)), "pause_controls_render", report, "keyboard/controller controls page renders")
        game._resume_from_pause(source="self_test")
        manager.clear_held_state()
        start_event = pygame.event.Event(
            getattr(pygame, "CONTROLLERBUTTONDOWN", pygame.JOYBUTTONDOWN),
            {"instance_id": 77, "button": pygame.CONTROLLER_BUTTON_START},
        )
        manager.process_events([start_event])
        game.update(1.0 / 60.0)
        _check(game.pause, "controller_pause_menu", report, "controller Start opens the same pause menu")
        game._resume_from_pause(source="self_test")
        manager.clear_held_state()

        game._spawn_enemy("stick")
        enemy = game.enemies[-1]
        enemy.state = "chase"
        enemy.x = game.players[0].x + 24
        enemy.y = game.players[0].y
        before = enemy.health
        game.effects.clear()
        game.player_attack(game.players[0], game.data["moves"]["light_combo"][0], "light")
        _check(enemy.health < before, "black_dave_fist_damage", report, f"enemy health {before:.0f}->{enemy.health:.0f}")
        _check(
            {"hit", "impact", "text"}.issubset({effect.kind for effect in game.effects}),
            "layered_combat_feedback",
            report,
            "confirmed hits emit a spark, impact ring and damage number",
        )

        # Fire fists are deliberately driven by attack edges, not hits: six
        # air presses ignite Dave, then the active bonus is checked against a
        # fresh target before its ten-second timer cools down.
        dave = game.players[0]
        game.enemies.clear()
        dave.set_state("idle")
        for _ in range(6):
            dave.update(
                InputSnapshot(held=frozenset({"light"}), pressed=frozenset({"light"})),
                game,
                1.0 / 60.0,
            )
            dave.set_state("idle")
        fire_without_target = dave.flaming_fists and not game.enemies
        flame_idle_canvas = pygame.Surface(LOGICAL_SIZE)
        game.draw(flame_idle_canvas)
        flame_idle_screenshot = output_dir / "self_test_dave_flaming_idle.png"
        pygame.image.save(flame_idle_canvas, flame_idle_screenshot)
        dave.facing = -1
        flame_left_canvas = pygame.Surface(LOGICAL_SIZE)
        game.draw(flame_left_canvas)
        flame_left_screenshot = output_dir / "self_test_dave_flaming_left.png"
        pygame.image.save(flame_left_canvas, flame_left_screenshot)
        dave.facing = 1
        game._spawn_enemy("stick")
        flame_target = game.enemies[-1]
        flame_target.state = "chase"
        flame_target.x, flame_target.y = dave.x + 24.0, dave.y
        flame_before = flame_target.health
        light_damage = float(game.data["moves"]["light_combo"][0]["damage"])
        game.player_attack(dave, game.data["moves"]["light_combo"][0], "light")
        flame_bonus_damage = flame_target.health == flame_before - light_damage * 1.20
        flame_feedback_kinds = {effect.kind for effect in game.effects}
        flame_feedback_complete = {
            "flame_trail_right",
            "flame_burst",
            "scorch",
            "ember",
        }.issubset(flame_feedback_kinds)
        visual_only_ignition = (
            game._dave_flame_visuals.get(flame_target.enemy_id, 0.0) > 0.0
            and flame_target.burn_time == 0.0
        )
        dave.set_state("light", 0.22)
        dave.state_clock = 0.09
        flame_strike_canvas = pygame.Surface(LOGICAL_SIZE)
        game.draw(flame_strike_canvas)
        flame_strike_screenshot = output_dir / "self_test_dave_flaming_strike.png"
        pygame.image.save(flame_strike_canvas, flame_strike_screenshot)
        dave.update(InputSnapshot(), game, float(game.data["players"]["black_dave"]["fist_flames"]["active_seconds"]) + 0.1)
        _check(
            fire_without_target
            and flame_bonus_damage
            and not dave.flaming_fists
            and flame_idle_screenshot.is_file()
            and flame_left_screenshot.is_file()
            and flame_strike_screenshot.is_file()
            and flame_idle_screenshot.stat().st_size > 5_000
            and flame_left_screenshot.stat().st_size > 5_000
            and flame_strike_screenshot.stat().st_size > 5_000,
            "dave_flaming_fists_chain",
            report,
            "six air presses ignite Dave, fists deal +20%, the ten-second timer cools without a four-press refresh, and both-facing/strike flame renders save",
        )
        _check(
            flame_feedback_complete and visual_only_ignition,
            "dave_flaming_contact_feedback",
            report,
            "flame contact emits a trail, embers, burst and scorch plus an enemy-following visual without applying burn damage",
        )
        # Restore the shared probe used by the following BB-gun contract.
        game._dave_flame_visuals.clear()
        game.enemies = [enemy]

        dave, shelly = game.players
        enemy.x, enemy.y = dave.x + 90.0, dave.y
        enemy.state = "chase"
        bb_health_before = enemy.health
        ally_health_before = shelly.health
        bb_ammo_before = dave.bb_ammo
        game.hitstop_remaining = 0.08
        bb_key = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_g, "repeat": False})
        manager.process_events([bb_key])
        game.update(1.0 / 60.0)
        manager.consume_pressed()
        _check(
            dave.bb_ammo == bb_ammo_before - 1 and any(projectile.kind == "bb" for projectile in game.projectiles),
            "bb_gun_hitstop_dispatch",
            report,
            "G fires one finite-ammo BB even during hitstop",
        )
        game.hitstop_remaining = 0.0
        bb_shot = next(projectile for projectile in reversed(game.projectiles) if projectile.kind == "bb")
        bb_shot.update(game, 0.30)
        _check(
            enemy.health < bb_health_before and shelly.health == ally_health_before,
            "bb_lane_hit_no_friendly_fire",
            report,
            "straight BB hits its aligned enemy and cannot hurt Shelly",
        )
        manager.process_events([pygame.event.Event(pygame.KEYUP, {"key": pygame.K_g})])

        preserved_enemies = list(game.enemies)
        game.ammo_pickups.clear()
        game.bb_eligible_kos = 0
        game.bb_drop_index = 0
        game.bb_next_drop_at = game._bb_drop_interval(0)
        drop_kos: list[int] = []
        for ko_number in range(1, 10):
            game._spawn_enemy("stick")
            defeated = game.enemies.pop()
            before_drops = len(game.ammo_pickups)
            game.enemy_defeated(defeated, dave)
            if len(game.ammo_pickups) > before_drops:
                drop_kos.append(ko_number)
        _check(
            drop_kos == [2, 6, 9]
            and game.bb_next_drop_at == 12
            and game.bb_eligible_kos == 9,
            "bb_deterministic_drop_schedule",
            report,
            "eligible Level 1 KOs drop BB tins at 2/6/9 and schedule 12 next",
        )
        game.enemies.clear()
        dave.bb_cooldown = 0.0
        dave.bb_ammo = max(1, dave.bb_ammo)
        _check(game.fire_bb_gun(dave, feedback=False), "bb_range_probe_fired", report, "range probe BB fired")
        range_shot = game.projectiles[-1]
        range_start = range_shot.x
        configured_range = float(game.data["bb_gun"]["range"])
        range_shot.update(game, range_shot.ttl + 0.75)
        _check(
            range_shot.spent and abs(abs(range_shot.x - range_start) - configured_range) < 1e-5,
            "bb_range_clamp",
            report,
            "oversized frame time cannot extend a BB past its configured range",
        )
        game.enemies[:] = preserved_enemies

        dave.bb_ammo = int(game.data["bb_gun"]["max_ammo"]) - 1
        pickup = AmmoPickup(dave.x, dave.y, amount=3)
        game.ammo_pickups = [pickup]
        pickup.update(game, 1.0 / 60.0)
        _check(
            pickup.spent and dave.bb_ammo == int(game.data["bb_gun"]["max_ammo"]),
            "bb_pickup_clamp",
            report,
            "Dave-only pickup collects without exceeding maximum ammo",
        )

        # Shelly's secondary is intentionally a separate drop-fed resource;
        # it must not share Dave's BB inventory or ordinary super meter.
        manager.clear_held_state()
        shelly.set_state("idle")
        shelly.super_butane_meter = float(game.data["shelly_propane"]["meter_max"])
        enemy.state = "chase"
        enemy.x, enemy.y = shelly.x + 118.0, shelly.y
        propane_health_before = enemy.health
        propane_before = shelly.super_butane_meter
        propane_trigger = pygame.event.Event(
            getattr(pygame, "CONTROLLERAXISMOTION", pygame.JOYAXISMOTION),
            {"instance_id": 77, "axis": pygame.CONTROLLER_AXIS_TRIGGERLEFT, "value": 0.82},
        )
        manager.process_events([propane_trigger])
        game.update(1.0 / 60.0)
        manager.consume_pressed()
        _check(
            shelly.state == "propane"
            and shelly.super_butane_meter < propane_before
            and enemy.health < propane_health_before,
            "shelly_propane_secondary_live",
            report,
            "controller LT starts Shelly's long-range flame and consumes only Super Butane",
        )
        manager.process_events([
            pygame.event.Event(
                getattr(pygame, "CONTROLLERAXISMOTION", pygame.JOYAXISMOTION),
                {"instance_id": 77, "axis": pygame.CONTROLLER_AXIS_TRIGGERLEFT, "value": -1.0},
            )
        ])
        game.update(1.0 / 60.0)
        manager.clear_held_state()

        game.super_butane_pickups.clear()
        game.super_butane_eligible_kos = 0
        game.super_butane_drop_index = 0
        game.super_butane_next_drop_at = game._super_butane_drop_interval(0)
        butane_drop_kos: list[int] = []
        for ko_number in range(1, 8):
            game._spawn_enemy("stick")
            defeated = game.enemies.pop()
            before_drops = len(game.super_butane_pickups)
            game.enemy_defeated(defeated, shelly)
            if len(game.super_butane_pickups) > before_drops:
                butane_drop_kos.append(ko_number)
        super_butane_pickup = SuperButanePickup(shelly.x, shelly.y, amount=52.0)
        shelly.super_butane_meter = 97.0
        super_butane_pickup.update(game, 1.0 / 60.0)
        _check(
            butane_drop_kos == [2, 5, 7]
            and super_butane_pickup.spent
            and shelly.super_butane_meter == float(game.data["shelly_propane"]["meter_max"]),
            "shelly_super_butane_drops",
            report,
            "separate Super Butane drops arrive every 2-3 KOs and clamp only Shelly's flame bar",
        )
        # Restore the shared target used by the following Chief-command
        # contract; flame burn is intentionally persistent in gameplay.
        enemy.health = enemy.max_health
        enemy.burn_time = 0.0
        enemy.burn_tick = 0.0
        enemy.state = "chase"
        shelly.set_state("idle")

        chief = game.chiefs[0]
        chief.x, chief.y = enemy.x - 10.0, enemy.y
        command_before = enemy.health
        shelly_meter_before = shelly.chief_meter
        game.hitstop_remaining = 0.08
        chief_key = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_r, "repeat": False})
        manager.process_events([chief_key])
        game.update(1.0 / 60.0)
        manager.consume_pressed()
        _check(chief.command_caller is dave, "chief_command_dispatch", report, "Dave's R command dispatches even during hitstop")
        game.hitstop_remaining = 0.0
        chief.update(game, 1.0 / 60.0)
        _check(
            enemy.health == command_before - float(game.data["chief"]["command_damage"])
            and shelly.chief_meter == shelly_meter_before,
            "chief_command_bite",
            report,
            "command delivers one weaker bite without spending Shelly's meter",
        )
        chief.x, chief.y = dave.x + dave.facing * 23.0, dave.y + 8.0
        chief.update(game, 1.0 / 60.0)
        _check(chief.state == "pet" and dave.state == "pet", "chief_command_return_pet", report, "Chief returns to a safe caller for a pet")
        manager.process_events([pygame.event.Event(pygame.KEYUP, {"key": pygame.K_r})])

        game.hitstop_remaining = 0.08
        chief_trigger = pygame.event.Event(
            getattr(pygame, "CONTROLLERAXISMOTION", pygame.JOYAXISMOTION),
            {"instance_id": 77, "axis": pygame.CONTROLLER_AXIS_TRIGGERRIGHT, "value": 0.82},
        )
        manager.process_events([chief_trigger])
        game.update(1.0 / 60.0)
        manager.consume_pressed()
        _check(chief.command_caller is shelly, "controller_chief_command_live", report, "controller RT commands Chief through live gameplay")
        chief._clear_command()
        game.hitstop_remaining = 0.0
        manager.process_events([
            pygame.event.Event(
                getattr(pygame, "CONTROLLERAXISMOTION", pygame.JOYAXISMOTION),
                {"instance_id": 77, "axis": pygame.CONTROLLER_AXIS_TRIGGERRIGHT, "value": -1.0},
            )
        ])
        dave.set_state("idle")
        chief.pet_timer = 0.0
        chief.pet_partner = None

        health_before_jump = dave.health
        dave.z = 60.0
        game.enemy_attack(enemy, range_x=40.0, range_y=20.0, damage=7.0)
        _check(dave.health == health_before_jump, "elevation_aware_combat", report, "ground strike misses Dave above its vertical hit volume")
        dave.z = 0.0
        game.hitstop_remaining = 0.0

        game._spawn_enemy("whip")
        super_enemy = game.enemies[-1]
        super_enemy.state = "chase"
        super_enemy.x = game.players[0].x + 60
        super_enemy.y = game.players[0].y + 5
        before = super_enemy.health
        game.activate_super(game.players[0])
        _check(super_enemy.health < before, "speaker_shockwave", report, "Black Dave super damages nearby enemies")

        game.enemies.clear()
        shelly_burst_targets: list[Enemy] = []
        for index in range(4):
            game._spawn_enemy("stick")
            target = game.enemies[-1]
            target.state = "chase"
            target.x = game.players[1].x + 38.0 + index * 19.0
            target.y = game.players[1].y + (index % 2) * 6.0
            shelly_burst_targets.append(target)
        game.activate_super(game.players[1])
        frenzy_cinematic = game.shelly_frenzy_cinematic
        cinematic_canvas = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        game._draw_gameplay(cinematic_canvas)
        frenzy_started = game.chiefs[0].frenzy > 7.5
        if frenzy_cinematic is not None:
            game._advance_shelly_frenzy_cinematic(frenzy_cinematic.comic_seconds)
            game._advance_shelly_frenzy_cinematic(frenzy_cinematic.flash_seconds)
        _check(
            frenzy_started
            and all(target.state == "dead" for target in shelly_burst_targets)
            and frenzy_cinematic is not None
            and game.chiefs[0].state == "pet"
            and pygame.mask.from_surface(cinematic_canvas).count() > 1_000,
            "chief_frenzy_super_cinematic_burst",
            report,
            "Shelly's super plays the approved comic strip, flashes to a downed crowd, then pets Chief",
        )
        if frenzy_cinematic is not None:
            game._advance_shelly_frenzy_cinematic(frenzy_cinematic.recovery_seconds)
        _check(
            game.shelly_frenzy_cinematic is None and not game.enemies,
            "chief_frenzy_recovery_cleanup",
            report,
            "dust reveal removes the exact pre-super non-boss crowd before combat resumes",
        )

        for _ in range(180):
            manager.process_events([])
            game.update(1.0 / 60.0)
        _check(game.frame >= 180, "fixed_step_simulation", report, "180 fixed 60 Hz frames completed")

        canvas = pygame.Surface(LOGICAL_SIZE)
        game.draw(canvas)
        screenshot = output_dir / "self_test_gameplay.png"
        pygame.image.save(canvas, screenshot)
        _check(screenshot.is_file() and screenshot.stat().st_size > 5_000, "gameplay_render", report, str(screenshot))

        manager.add_synthetic_controller(78, name="QA Virtual Pad 2", mapped=True)
        manager.add_synthetic_controller(79, name="QA Virtual Pad 3", mapped=True)
        game.select_slots = [
            SelectSlot(keyboard_binding, character_index=0, confirmed=True),
            SelectSlot(controller_binding, character_index=1, confirmed=True),
            SelectSlot({"type": "controller", "instance_id": 78}, character_index=0, confirmed=True),
            SelectSlot({"type": "controller", "instance_id": 79}, character_index=1, confirmed=True),
        ]
        game._start_stage()
        manager.clear_held_state()
        _check(len(game.players) == 4, "four_player_start", report, "one keyboard plus three controller players created")
        _check(sum(player.character == "black_dave" for player in game.players) == 2 and sum(player.character == "shelly" for player in game.players) == 2, "four_player_roster", report, "all four slots use the two available heroes")

        encounters = list(game.data["encounters"])
        _check(
            len(encounters) == 3,
            "level_one_three_encounters",
            report,
            "Sprouts Parking Lot, Town & Country, and El Cilantro at Madison are the complete Level 1 combat route",
        )
        tent_event = next(
            event
            for event in game.runtime_chapter_content.get("environmental_events", ())
            if isinstance(event, dict) and event.get("id") == "wells_drive_tent_camp"
        )
        _check(
            any("homeless" in group.get("runtime_kinds", ()) for group in tent_event.get("spawn_groups", ())),
            "level_one_tent_camp_runtime_homeless",
            report,
            "the tent camp environmental beat resolves to homeless runtime kinds",
        )
        game._begin_environment_event(tent_event, float(tent_event.get("trigger_x", 0.0)) + 16.0)
        while game.spawn_queue:
            game._spawn_enemy(game.spawn_queue.pop(0))
        _check(
            any(enemy.kind == "homeless" for enemy in game.enemies),
            "level_one_tent_camp_spawns_homeless",
            report,
            "the tent camp ambush spawns a homeless enemy wave",
        )
        game.enemies.clear()
        game.encounter_active = False
        game.active_gate = None
        game.spawn_queue.clear()
        game._post_clear_reinforcements.clear()
        game._content_event_ambush_active = False
        game._content_event_ambush_name = ""
        for encounter_index, encounter in enumerate(encounters):
            _check(
                game.encounter_index == encounter_index,
                f"level_one_encounter_{encounter_index + 1}_ready",
                report,
                str(encounter["name"]),
            )
            game._begin_encounter(encounter)
            saw_security_reinforcement = False
            saw_security_bubble = False
            for _ in range(540):
                while game.spawn_queue:
                    game._spawn_enemy(game.spawn_queue.pop(0))
                # Retired guards stay on the field for their brief death pose.
                # Only a live guard belongs to this encounter's spawn bark.
                guards = [
                    enemy
                    for enemy in game.enemies
                    if enemy.kind == "security" and enemy.alive
                ]
                if guards:
                    saw_security_reinforcement = True
                    # Guards remain in the defeat presentation briefly after
                    # their spawn bark expires. Preserve the verified spawn
                    # moment instead of letting a later corpse frame turn a
                    # valid speech-bubble observation into a false failure.
                    saw_security_bubble = saw_security_bubble or all(
                        bool(game._security_speech_by_enemy.get(guard.enemy_id, ("", 0.0))[0])
                        for guard in guards
                    )
                for spawned in list(game.enemies):
                    if spawned.alive:
                        spawned.state = "chase"
                        spawned.take_damage(100_000, game, game.players[0], knockdown=True)
                manager.process_events([])
                game.update(1.0 / 60.0)
                manager.consume_pressed()
                if not game.encounter_active:
                    break
            _check(
                not game.encounter_active and game.encounter_index == encounter_index + 1,
                f"level_one_encounter_{encounter_index + 1}_cleared",
                report,
                f"{encounter['name']} clears without a boss handoff",
            )
            reinforcements = encounter.get("post_clear_reinforcements", [])
            if reinforcements:
                _check(
                    saw_security_reinforcement and saw_security_bubble,
                    f"level_one_encounter_{encounter_index + 1}_security_reinforcement",
                    report,
                    f"{encounter['name']} holds its gate for a speaking security mini-wave",
                )

        _check(
            game.state == "gameplay"
            and game.encounter_index == len(encounters)
            and game.boss_transition is None
            and game.level_outro is not None
            and game.level_outro_frame is not None
            and game.level_outro_frame.beat == "arrival"
            and not any(enemy.kind == "couch" for enemy in game.enemies),
            "level_one_jerry_handoff",
            report,
            "final El Cilantro wave freezes gameplay into Jerry's arrival with no Couch or loading overlay",
        )
        jerry_canvas = pygame.Surface(LOGICAL_SIZE)
        game.draw(jerry_canvas)
        jerry_screenshot = output_dir / "self_test_jerry_outro.png"
        pygame.image.save(jerry_canvas, jerry_screenshot)
        _check(
            jerry_screenshot.is_file() and jerry_screenshot.stat().st_size > 5_000,
            "jerry_outro_render",
            report,
            str(jerry_screenshot),
        )
        assert game.level_outro is not None
        # Jerry deliberately waits at every text beat. Prove a huge time step
        # cannot skip it, then exercise four distinct confirmation edges.
        game._update_level_outro(game.level_outro.arrival_seconds, [])
        _check(
            game.level_outro is not None
            and game.level_outro_frame is not None
            and game.level_outro_frame.beat == "arrival"
            and game.level_outro_frame.awaiting_continue,
            "jerry_outro_requires_player_continue",
            report,
            "arrival settles and waits; no dialogue beat has a timer skip",
        )
        for index in range(4):
            game._update_level_outro(0.0, [InputSnapshot(pressed={"confirm"})])
            if index < 3:
                game._update_level_outro(0.0, [InputSnapshot()])
        _check(
            game.state == "complete"
            and game.level_outro is None
            and game.completion_stats is not None
            and game.level_stats.finished
            and game.victory_frame.phase == "results"
            and game.victory_frame.show_results,
            "level_one_generic_results",
            report,
            "Jerry finishes before Level 1 opens its ordinary score card without a finale celebration",
        )
        assert game.completion_stats is not None
        _check(
            game.completion_stats.combined_score == sum(player.score for player in game.players)
            and game.completion_stats.kos == sum(player.ko_count for player in game.players)
            and bool(game.completion_stats.rank),
            "level_one_complete_stats",
            report,
            "Level 1 freezes score, KO, hit, damage, rating, and rank statistics",
        )
        completion_canvas = pygame.Surface(LOGICAL_SIZE)
        game.draw(completion_canvas)
        completion_screenshot = output_dir / "self_test_level_one_complete.png"
        pygame.image.save(completion_canvas, completion_screenshot)
        _check(
            completion_screenshot.is_file() and completion_screenshot.stat().st_size > 5_000,
            "level_one_complete_render",
            report,
            str(completion_screenshot),
        )
        game._open_epilogue()
        level_one_options_canvas = pygame.Surface(LOGICAL_SIZE)
        game.draw(level_one_options_canvas)
        _check(
            game.state == "epilogue"
            and not game.level_is_chapter_finale
            and game.level_data.get("boss") is None
            and pygame.mask.from_surface(level_one_options_canvas).count() > 10_000,
            "level_one_generic_options_no_bmx",
            report,
            "Level 1 shows Sprouts-to-El-Cilantro route options; BMX sunset remains finale-only",
        )

        # Follow the live completion menu through Levels 2 and 3.  This
        # verifies the campaign does not merely contain dormant descriptors:
        # every route swaps its own geometry/theme and reaches a results card.
        level_two, level_three = chapter_one_levels[1:3]
        game.epilogue_selection = 0
        game._activate_epilogue_selection()
        _check(
            game.state == "interlevel"
            and game.pending_level_id == level_two["id"]
            and game.interlevel_travel_panel is not None
            and game.interlevel_travel_panel["id"] == "travel_el_cilantro_to_seven_eleven"
            and game.interlevel_travel_panel["presentation"] == "route_card",
            "level_one_to_two_interlevel",
            report,
            "Level 1 route card queues the playable 7-Eleven-to-I-8 stage",
        )
        game._start_pending_level(source="self_test")
        _check(
            game.state == "gameplay"
            and game.level_id == level_two["id"]
            and game.level_theme == level_two["background_theme"]
            and game.data["stage_geometry"] == level_two["stage_geometry"],
            "level_two_runtime_snapshot",
            report,
            "Level 2 activates its own 7-Eleven/I-8 geometry and theme",
        )
        level_two_screenshot = _exercise_nonfinal_campaign_stage(
            game, manager, report, level_two, output_dir
        )

        game._open_epilogue()
        game.epilogue_selection = 0
        game._activate_epilogue_selection()
        _check(
            game.state == "interlevel"
            and game.pending_level_id == level_three["id"]
            and game.interlevel_travel_panel is not None
            and game.interlevel_travel_panel["id"] == "travel_i8_to_soapy_joes"
            and game.interlevel_travel_panel["presentation"] == "moving_panel"
            and [
                waypoint["display_name"]
                for waypoint in game.interlevel_travel_panel["waypoints"]
            ]
            == [
                "I-8 UNDERPASS",
                "690 SHOWROOM SHELL",
                "710 FUEL / SMOG ROW",
                "SOAPY JOE'S",
            ],
            "level_two_to_three_interlevel",
            report,
            "I-8 transfer card queues the playable Soapy Joe's-to-Revive route",
        )
        game._start_pending_level(source="self_test")
        _check(
            game.state == "gameplay"
            and game.level_id == level_three["id"]
            and game.level_theme == level_three["background_theme"]
            and game.data["stage_geometry"] == level_three["stage_geometry"],
            "level_three_runtime_snapshot",
            report,
            "Level 3 activates Soapy Joe's/Broadway/Revive geometry and theme",
        )
        level_three_screenshot = _exercise_nonfinal_campaign_stage(
            game, manager, report, level_three, output_dir
        )

        game._open_epilogue()
        game.epilogue_selection = 0
        game._activate_epilogue_selection()
        _check(
            game.state == "interlevel"
            and game.pending_level_id == finale["id"]
            and game.interlevel_travel_panel is not None
            and game.interlevel_travel_panel["id"] == "travel_revive_to_awaken"
            and game.interlevel_travel_panel["presentation"] == "moving_panel",
            "level_three_to_four_interlevel",
            report,
            "Revive-to-Awaken moving panel queues the playable Awaken Church Couch finale",
        )
        game._start_pending_level(source="self_test")
        _check(
            game.state == "gameplay"
            and game.level_id == finale["id"]
            and game.level_title == "Awaken Church Showdown"
            and game.level_is_chapter_finale
            and game.level_has_couch
            and game.data["stage_geometry"] == finale["stage_geometry"]
            and bool(game.data["transitions"]["boss_loading"]["enabled"]),
            "level_four_runtime_snapshot",
            report,
            "Level 4 arrives at the Awaken Church parking-lot finale through campaign flow",
        )

        # Restart the now-live finale as a solo Dave + CPU Shelly run so the
        # companion's Couch-specific decision logic remains deterministic.
        game.select_slots = [SelectSlot(keyboard_binding, character_index=0, confirmed=True)]
        game._start_stage()
        manager.clear_held_state()
        _check(
            game.level_id == "chapter_1_level_4"
            and game.level_title == "Awaken Church Showdown"
            and game.level_data is finale
            and game.level_is_chapter_finale
            and game.level_has_couch
            and game.data["encounters"] == finale["encounters"]
            and bool(game.data["transitions"]["boss_loading"]["enabled"]),
            "awaken_finale_configured",
            report,
            "all Couch checks use the live Chapter 1 Level 4 Awaken Church transition",
        )

        finale_dave, finale_shelly = game.players
        finale_chief = game.chiefs[0]
        game._spawn_enemy("couch")
        solo_boss = game.enemies[-1]
        solo_boss.state = "chase"
        solo_boss.x, solo_boss.y = finale_shelly.x + 28.0, finale_shelly.y
        solo_boss.cooldown = 99.0
        finale_shelly.set_state("idle")
        finale_shelly.cpu_action_cooldown = 0.0
        finale_shelly.super_meter = float(game.data["players"]["global"]["super_cost"])
        for _ in range(14):
            manager.process_events([])
            game.update(1.0 / 60.0)
            manager.consume_pressed()
            if finale_shelly.state == "idle":
                break
        _check(
            finale_chief.frenzy == 0.0 and finale_shelly.super_meter == float(game.data["players"]["global"]["super_cost"]),
            "cpu_shelly_awaken_boss_super_rejected",
            report,
            "charged CPU Shelly keeps Chief frenzy unavailable during the Couch boss fight",
        )
        finale_chief.frenzy = 0.0
        game.enemies.clear()

        eligible_before_boss = game.bb_eligible_kos
        drops_before_boss = len(game.ammo_pickups)
        game._spawn_enemy("couch")
        excluded_boss = game.enemies.pop()
        _check(
            excluded_boss.kind == "couch" and excluded_boss.max_health >= 620,
            "awaken_couch_spawn",
            report,
            f"Awaken Church Couch HP={excluded_boss.max_health:.0f}",
        )
        game.enemy_defeated(excluded_boss, finale_dave)
        _check(
            game.bb_eligible_kos == eligible_before_boss
            and len(game.ammo_pickups) == drops_before_boss,
            "awaken_couch_bb_drop_exclusion",
            report,
            "Couch never advances the ordinary-enemy BB-ammo drop schedule",
        )

        game._start_stage()
        manager.clear_held_state()
        boss_index = len(game.data["encounters"]) - 1
        game.encounter_index = boss_index - 1
        game.encounter_active = True
        game.spawn_queue.clear()
        game.enemies.clear()
        game._update_encounters(0.0)
        transition = game.boss_transition
        _check(
            transition is not None
            and game.encounter_index == boss_index
            and not game.encounter_active,
            "awaken_boss_loading_handoff",
            report,
            "clearing Awaken's front lot starts Level 4's explicit Couch handoff",
        )
        assert transition is not None
        game._update_boss_transition(transition.duration_seconds)
        _check(
            game.boss_transition is None
            and game.encounter_active
            and game.spawn_queue == ["couch"],
            "awaken_boss_loading_finished",
            report,
            "the enabled Awaken transition completes directly into Couch's wave",
        )
        game._update_encounters(0.0)
        loaded_boss = next(
            (candidate for candidate in game.enemies if candidate.kind == "couch" and candidate.alive),
            None,
        )
        expected_boss_health = float(game.data["enemies"]["couch"]["health"]) * float(
            game.data["scaling"]["boss_health"][game._scaling_index()]
        )
        _check(
            loaded_boss is not None and loaded_boss.max_health == expected_boss_health,
            "awaken_boss_loaded_from_encounter",
            report,
            f"Couch loads from the live Level 4 Awaken encounter with solo HP={expected_boss_health:.0f}",
        )
        assert loaded_boss is not None
        loaded_boss.update(game, loaded_boss.state_duration)
        retreat_contract_ok = True
        retreat_wave_kinds: list[list[str]] = []
        for retreat_number in (1, 2):
            loaded_boss.take_damage(100_000, game, game.players[0], knockdown=True)
            retreat_contract_ok = retreat_contract_ok and (
                loaded_boss.state == "bike_retreat" and not loaded_boss.targetable
            )
            loaded_boss.update(game, 20.0)
            retreat = game.couch_retreat
            if retreat is None:
                retreat_contract_ok = False
                break
            adds = [enemy for enemy in game.enemies if enemy.enemy_id in retreat.add_enemy_ids]
            retreat_wave_kinds.append([enemy.kind for enemy in adds])
            retreat_contract_ok = retreat_contract_ok and (
                loaded_boss.state == "bike_refuge"
                and bool(adds)
                and all(enemy.alive for enemy in adds)
                and retreat.taunt == COUCH_DOPE_OFFER_TAUNT
            )
            for add in adds:
                add._set_state("chase")
                add.take_damage(100_000, game, game.players[0])
            loaded_boss.update(game, float(loaded_boss.stats["retreat_minimum_refuge_seconds"]))
            loaded_boss.update(game, 20.0)
            retreat_contract_ok = retreat_contract_ok and (
                game.couch_retreat is None and loaded_boss.targetable
            )
        _check(
            retreat_contract_ok
            and retreat_wave_kinds == loaded_boss.stats["retreat_add_waves"],
            "awaken_couch_retreat_waves",
            report,
            "Couch performs two health-gated BMX refuges with the exact dope offer, live crews, and targetable returns",
        )
        loaded_boss.take_damage(100_000, game, game.players[0], knockdown=True)
        game._update_encounters(0.0)
        _check(
            game.state == "complete"
            and game.level_stats.finished
            and game.completion_stats is not None
            and game.victory_frame.phase == "hug"
            and not game.victory_frame.show_results,
            "awaken_finale_completion",
            report,
            "defeating Couch at Awaken Church starts the finale hug/treat celebration",
        )
        for _ in range(360):
            manager.process_events([])
            game.update(1.0 / 60.0)
            manager.consume_pressed()
            if game.victory_frame.show_results:
                break
        _check(
            game.victory_frame.phase == "results" and game.victory_frame.show_results,
            "awaken_finale_results",
            report,
            "the Awaken finale celebration deterministically reaches results",
        )
        game._open_epilogue()
        finale_epilogue_canvas = pygame.Surface(LOGICAL_SIZE)
        game.draw(finale_epilogue_canvas)
        finale_screenshot = output_dir / "self_test_awaken_sunset.png"
        pygame.image.save(finale_epilogue_canvas, finale_screenshot)
        _check(
            game.state == "epilogue"
            and game.level_is_chapter_finale
            and pygame.mask.from_surface(finale_epilogue_canvas).count() > 10_000
            and finale_screenshot.is_file()
            and finale_screenshot.stat().st_size > 5_000,
            "awaken_refined_sunset_render",
            report,
            str(finale_screenshot),
        )

        paths = get_log_paths()
        _check(paths.latest.is_file(), "crash_log_ready", report, str(paths.latest))
        report["controller_metadata"] = manager.connected_controllers
        report["log_path"] = str(paths.latest)
        report["screenshot"] = str(screenshot)
        report["jerry_screenshot"] = str(jerry_screenshot)
        report["completion_screenshot"] = str(completion_screenshot)
        report["flame_idle_screenshot"] = str(flame_idle_screenshot)
        report["flame_left_screenshot"] = str(flame_left_screenshot)
        report["flame_strike_screenshot"] = str(flame_strike_screenshot)
        report["level_two_screenshot"] = str(level_two_screenshot)
        report["level_three_screenshot"] = str(level_three_screenshot)
        report["finale_screenshot"] = str(finale_screenshot)
        report["status"] = "pass"
    except Exception as error:
        report["status"] = "fail"
        report["error"] = f"{type(error).__name__}: {error}"
        breadcrumb("self_test_failed", error=report["error"])
        raise
    finally:
        if game is not None:
            game.close()
        manager.close()
        report["duration_seconds"] = round(time.perf_counter() - started, 3)
        report_path = output_dir / "self_test_report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    breadcrumb("self_test_passed", checks=len(report["checks"]), duration=report["duration_seconds"])
    return report
