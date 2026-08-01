from __future__ import annotations

import math
import os
import random
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

import pygame

from . import location_lock, pixel_art, sprite_atlas
from .animation_manifest import (
    ANIMATION_PLAYBACK_HZ,
    action_segment_tick,
    timed_action_tick,
)
from .atmosphere import AtmosphereState
from .audio import AudioManager
from .chapter_content import compile_level_content, load_chapter_content
from .combat_engine import (
    AABB2,
    AttackQueryReport,
    AttackRejectionReason,
    HitBox,
    HurtBox,
    PushBody,
    StageBounds,
    StageObstacle,
    query_attack,
    query_attack_detailed,
    separate_push_bodies,
)
from .config import (
    LOGICAL_SIZE,
    activate_campaign_level,
    active_campaign_level,
    campaign_levels,
    load_gameplay,
    resource_path,
)
from .entities import (
    COUCH_RETREAT_STATES,
    AmmoPickup,
    Chief,
    Effect,
    Enemy,
    Player,
    Projectile,
    SuperButanePickup,
    clamp,
    move_toward,
    normalized,
)
from .input_manager import InputManager, InputSnapshot
from .logger import breadcrumb, get_log_paths
from .level_complete import CompletionStats, LevelCompleteTimeline, LevelStatTracker, RankRules
from .level_outro import JerryLevelOneOutro, LevelOutroFrame
from .progression import GameOptions, RunStats, SaveData, SaveRepository
from .stage_transition import BossLoadingTransition, TransitionFrame
from .world_engine import (
    BeatEmUpProjection,
    CameraDirector,
    CameraView,
    CameraZone,
    ProjectionConfig,
    RectObstacle,
    StageGeometry,
    WalkableRegion,
    WorldPoint,
)


PLAYER_COLORS = (
    (79, 218, 255),
    (255, 102, 176),
    (255, 218, 76),
    (139, 255, 116),
)

PAUSE_MENU_ITEMS = (
    ("resume", "RESUME"),
    ("controls", "CONTROLS"),
    ("main_menu", "EXIT TO MAIN MENU"),
    ("exit_game", "EXIT GAME"),
)

KEYBOARD_CONTROLS = (
    ("MOVE", "WASD / ARROWS"),
    ("LIGHT ATTACK", "X  (J / Z)"),
    ("HEAVY ATTACK", "C  (K)"),
    ("JUMP", "SPACE"),
    ("DODGE", "LEFT SHIFT"),
    ("SUPER", "Q  (I / F)"),
    ("CALL CHIEF", "R"),
    ("SECONDARY: BB / PROPANE", "G"),
    ("REVIVE / INTERACT", "E"),
    ("PAUSE MENU", "ESC"),
)

CONTROLLER_CONTROLS = (
    ("MOVE", "LEFT STICK / D-PAD"),
    ("LIGHT ATTACK", "X"),
    ("HEAVY ATTACK", "Y"),
    ("JUMP / CONFIRM", "A"),
    ("DODGE / BACK", "B"),
    ("SUPER", "RB"),
    ("CALL CHIEF", "RT  (R3)"),
    ("SECONDARY: BB / PROPANE", "LT  (L3)"),
    ("REVIVE / INTERACT", "LB"),
    ("PAUSE", "START"),
)

COUCH_DOPE_OFFER_TAUNT = "I'LL GIVE YOU DOPE IF YOU BEAT THEM UP!"


def _default_save_path() -> Path:
    """Return a user-writable save location outside the packaged game tree."""

    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if not base:
        base = str(Path.home() / "AppData" / "Local")
    return Path(base) / "The Fades of Fate" / "chapter1_save.json"


@dataclass(slots=True)
class SelectSlot:
    binding: dict[str, object]
    character_index: int = 0
    confirmed: bool = False
    nav_cooldown: float = 0.0


@dataclass(slots=True)
class ShellyFrenzyCinematic:
    """A brief comic-book emphasis frame for Shelly and Chief's super."""

    player_slot: int
    chief_owner_slot: int
    duration_seconds: float
    elapsed_seconds: float = 0.0

    @property
    def progress(self) -> float:
        return clamp(self.elapsed_seconds / max(0.001, self.duration_seconds), 0.0, 1.0)

    @property
    def active(self) -> bool:
        return self.elapsed_seconds < self.duration_seconds

    def advance(self, dt: float) -> None:
        self.elapsed_seconds += max(0.0, dt)


@dataclass(slots=True)
class CouchRetreat:
    """One health-gated, visibly staged BMX/add-wave intermission."""

    boss: Enemy
    number: int
    origin_x: float
    origin_y: float
    refuge_x: float
    refuge_y: float
    phase: str = "retreat"
    elapsed_seconds: float = 0.0
    add_enemy_ids: tuple[int, ...] = ()
    taunt: str = COUCH_DOPE_OFFER_TAUNT


class AudioAdapter:
    """Expose one forgiving ``play`` method to gameplay code."""

    _ALIASES = {
        "dodge": "dodge",
        "land": "land",
        "hurt": "hit",
        "revive": "pickup",
        "heavy": "heavy_hit",
    }

    def __init__(self, manager: AudioManager, *, disabled: bool = False) -> None:
        self.manager = manager
        self.disabled = disabled

    def play(self, name: str) -> bool:
        if self.disabled:
            return False
        target = self._ALIASES.get(name, name)
        try:
            return self.manager.play_sfx(target)
        except (KeyError, pygame.error):
            return False

    def play_character(self, character: str, event: str) -> bool:
        """Play an original character voice without coupling entities to the mixer."""

        if self.disabled:
            return False
        try:
            return self.manager.play_character_voice(character, event)
        except (KeyError, pygame.error):
            return False


class FadesGame:
    VERSION = "0.15.0-visual-overhaul-4.3"

    def __init__(self, input_manager: InputManager, *, mute: bool = False) -> None:
        self.data = load_gameplay()
        location_manifest_path = resource_path("data/chapter1_location_lock.json")
        self.location_manifest = location_lock.load_location_lock(
            location_manifest_path,
            project_root=location_manifest_path.parent.parent,
        )
        # Production-facing Chapter content stays separate from the compact
        # combat configuration.  Validating it at boot catches a broken route
        # contract before a player reaches a later stage.
        self.chapter_content = load_chapter_content(gameplay=self.data)
        self.runtime_chapter_content: dict[str, Any] = {}
        self._content_major_by_hook: dict[str, dict[str, Any]] = {}
        self._content_optional: dict[str, Any] | None = None
        self._content_optional_prompt = ""
        self._content_optional_trigger_x = 0.0
        self._content_optional_active = False
        self._content_optional_completed: set[str] = set()
        self._content_event_index = 0
        self._content_event_seen: set[str] = set()
        self.save_repository = SaveRepository(_default_save_path())
        self.save_load_result = self.save_repository.load()
        self.save_data: SaveData = self.save_load_result.data
        self.options: GameOptions = self.save_data.options
        # Keep the live atmosphere mutable without mutating the immutable save
        # snapshot held by SaveData.  A fresh detached copy is written back at
        # explicit save points.
        self.atmosphere = AtmosphereState.from_mapping(
            self.save_data.atmosphere.to_mapping()
        )
        self.meta = self.data["meta"]
        self.level_data = active_campaign_level(self.data)
        self.level_id = str(self.level_data["id"])
        self.level_number = int(self.level_data["number"])
        self.level_title = str(self.level_data["title"])
        self.level_theme = str(self.level_data["background_theme"])
        self.location_route = location_lock.route_for_level(
            self.level_id,
            self.location_manifest,
        )
        self._validate_location_route_binding()
        self.atmosphere.set_profile_for_route(self.level_id)
        self.level_is_chapter_finale = bool(self.level_data.get("chapter_finale", False))
        self.level_has_couch = self.level_data.get("boss") == "couch"
        self.development_unlimited_lives = bool(
            self.data.get("players", {}).get("global", {}).get("unlimited_lives", False)
        )
        self.input = input_manager
        self.mute = mute
        # Headless and mute-based foundation tests should exercise the same
        # progression model without leaving test-run state in a real player's
        # AppData folder.  Normal interactive play always persists.
        self.persistence_enabled = not mute
        self.audio_manager = AudioManager()
        self.audio = AudioAdapter(self.audio_manager, disabled=mute)
        audio_config = self.data.get("audio", {})
        if not mute:
            self.audio_manager.set_music_volume(float(audio_config.get("music_volume", 0.42)))
            self.audio_manager.set_sfx_volume(float(audio_config.get("sfx_volume", 0.76)))
            self.audio_manager.initialize()

        self.font_tiny = pygame.font.Font(None, 12)
        self.font_small = pygame.font.Font(None, 16)
        self.font = pygame.font.Font(None, 22)
        self.font_big = pygame.font.Font(None, 39)
        self.font_huge = pygame.font.Font(None, 58)
        for font in (self.font_tiny, self.font_small, self.font, self.font_big, self.font_huge):
            font.set_bold(True)

        key_art_source = pygame.image.load(str(resource_path("assets/fades_of_fate_key_art.png"))).convert()
        self.key_art = pygame.transform.smoothscale(key_art_source, LOGICAL_SIZE)
        portrait_rects = {
            "black_dave": pygame.Rect(455, 170, 405, 750),
            "shelly": pygame.Rect(715, 165, 450, 755),
        }
        portrait_assets = {
            "black_dave": "assets/portraits/dave_portrait_lean_young_v2.png",
            "shelly": "assets/portraits/shelly_portrait_curvy_v1.png",
        }
        self.character_portraits: dict[str, pygame.Surface] = {}
        for name, rect in portrait_rects.items():
            # The title art remains a resilient fallback, but the character
            # cards use their dedicated portraits so the playable heroes read
            # with the same material detail as the enemies.
            portrait = key_art_source.subsurface(rect.clip(key_art_source.get_rect())).copy()
            try:
                authored_portrait = pygame.image.load(str(resource_path(portrait_assets[name]))).convert()
            except (OSError, pygame.error):
                pass
            else:
                # The authored images are square.  A center cover-crop keeps
                # faces and torso readable in the established tall card slot
                # without stretching their proportions.
                source_rect = authored_portrait.get_rect()
                crop_width = min(source_rect.width, round(source_rect.height * 90 / 145))
                crop_left = max(0, (source_rect.width - crop_width) // 2)
                portrait = authored_portrait.subsurface(
                    pygame.Rect(crop_left, 0, crop_width, source_rect.height)
                ).copy()
            self.character_portraits[name] = pygame.transform.smoothscale(portrait, (90, 145))
        self.state = "loading"
        self.loading_timer = 1.75
        self.select_slots: list[SelectSlot] = []
        self.select_start_armed = False
        self.pause = False
        self.pause_page = "menu"
        self.pause_selection = 0
        self.pause_confirm_selection = 0
        self.pause_nav_cooldown = 0.0
        self.pause_release_guard = False
        self.pause_opened_at = 0.0
        self.debug = False
        self.running = True
        self.elapsed = 0.0
        self.frame = 0
        self.controller_notice = 0.0
        self.music_started = False
        self.mouse_position: tuple[int, int] | None = None

        self.players: list[Player] = []
        self._frame_snapshots: dict[int, InputSnapshot] = {}
        self.enemies: list[Enemy] = []
        self.chiefs: list[Chief] = []
        self.projectiles: list[Projectile] = []
        self.ammo_pickups: list[AmmoPickup] = []
        self.super_butane_pickups: list[SuperButanePickup] = []
        self.effects: list[Effect] = []
        # Presentation-only burn timers for enemies struck by Dave's ignited
        # fists. These never feed Enemy.burn_time or damage simulation.
        self._dave_flame_visuals: dict[int, float] = {}
        self.bb_eligible_kos = 0
        self.bb_drop_index = 0
        self.bb_next_drop_at = 0
        self.super_butane_eligible_kos = 0
        self.super_butane_drop_index = 0
        self.super_butane_next_drop_at = 0
        self.enemy_sequence = 0
        self.camera_x = 0.0
        self._render_camera_x = 0.0
        self._camera_shake_y = 0.0
        self._last_camera_view: CameraView | None = None
        self._pending_camera_lock: float | None = None
        self.hitstop_remaining = 0.0
        # New action edges remain live across global hit-stop. Without this
        # latch the main loop consumed the edge while combat simulation was
        # frozen, making fast combo presses disappear.
        self._hitstop_pressed_by_slot: dict[int, set[str]] = {}
        self.impact_flash = 0.0
        self._debug_last_attack: HitBox | None = None
        self._debug_last_contacts: tuple[Any, ...] = ()
        self._debug_last_evaluations: tuple[Any, ...] = ()
        self._debug_last_result = "NONE"
        self._debug_last_rejection = "NONE"
        self._debug_last_query_frame = -1
        self._debug_logged_rejections: set[tuple[Any, Any, str]] = set()
        self.shelly_frenzy_cinematic: ShellyFrenzyCinematic | None = None
        # CPU Shelly has a small, per-level showtime reserve. It only charges
        # while a real non-boss crowd is present, so the companion earns two
        # useful Chief frenzies across an ordinary route instead of wasting
        # meter on a lone straggler.
        self._cpu_shelly_frenzy_uses: dict[int, int] = {}
        self._cpu_shelly_frenzy_charge: dict[int, float] = {}
        self._cpu_shelly_frenzy_rearm: dict[int, float] = {}
        self.active_gate: float | None = None
        self.encounter_index = 0
        self.encounter_active = False
        self.spawn_queue: list[str] = []
        # Reinforcements are intentionally held outside the base spawn queue:
        # they only become active after every regular enemy has been cleared.
        self._post_clear_reinforcements: list[dict[str, Any]] = []
        self._security_spawn_speech = ""
        self._security_speech_by_enemy: dict[int, tuple[str, float]] = {}
        self.spawn_timer = 0.0
        # Focused encounters cap the complete normal queue and trade bodies
        # for durability, keeping hitbox/response reads visible in solo and
        # co-op play.
        self._encounter_enemy_durability_scale = 1.0
        self._encounter_enemy_damage_scale = 1.0
        self._encounter_enemy_score_scale = 1.0
        self.attack_tokens_used = 0
        self.stage_banner = ""
        self.stage_banner_timer = 0.0
        # Level introductions have a dedicated presentation timer so that a
        # route card cannot get replaced early by ordinary encounter copy.
        self.route_card_timer = 0.0
        self.route_card_objective = ""
        self.complete_timer = 0.0
        completion_config = self.data.get("completion", {})
        self.level_stats = LevelStatTracker(
            RankRules.from_mapping(completion_config.get("rank_rules", {}))
        )
        self.completion_stats: CompletionStats | None = None
        self.victory_timeline = LevelCompleteTimeline(
            hug_seconds=float(completion_config.get("hug_seconds", 1.25)),
            treat_toss_seconds=float(completion_config.get("treat_toss_seconds", 1.15)),
            treat_release_seconds=float(completion_config.get("treat_release_seconds", 0.38)),
        )
        self.victory_frame = self.victory_timeline.current_frame()
        self.epilogue_timer = 0.0
        self.epilogue_selection = 0
        self.epilogue_notice = ""
        self.epilogue_page = "menu"
        self.pending_level_id: str | None = None
        self.interlevel_source_id: str | None = None
        self.interlevel_travel_panel: Mapping[str, Any] | None = None
        self.interlevel_timer = 0.0
        self.interlevel_duration = 1.75
        self.boss_transition: BossLoadingTransition | None = None
        self.boss_transition_frame: TransitionFrame | None = None
        self.couch_retreat: CouchRetreat | None = None
        self.level_outro: JerryLevelOneOutro | None = None
        self.level_outro_frame: LevelOutroFrame | None = None
        # Mouse clicks are events rather than retained input state. Latch one
        # until the next fixed update so the dialogue consumes it only once.
        self._level_outro_mouse_advance_pending = False
        self.autoplay = False
        self._last_controller_count = self.input.controller_count
        self._configure_engine()
        self._play_menu_music()
        breadcrumb("game_created", version=self.VERSION, controllers=self.input.connected_controllers)

    def _validate_location_route_binding(self) -> None:
        """Reject gameplay width/theme drift before constructing the stage."""

        expected_theme = str(self.location_route["theme"])
        expected_width = int(self.location_route["world_width"])
        if self.level_theme != expected_theme:
            raise location_lock.LocationLockError(
                f"{self.level_id} runtime theme {self.level_theme!r} disagrees with "
                f"location manifest theme {expected_theme!r}"
            )
        if int(float(self.meta["stage_width"])) != expected_width:
            raise location_lock.LocationLockError(
                f"{self.level_id} runtime width disagrees with location manifest"
            )

    def _landmark_record(self, landmark_id: str) -> Mapping[str, Any]:
        return location_lock.landmark_for_id(self.location_route, landmark_id)

    def _landmark_world_x(self, landmark_id: str) -> float:
        return float(self._landmark_record(landmark_id)["world_x"])

    def _configure_engine(self) -> None:
        """Build the data-driven 2.5D world used by simulation and rendering."""

        engine = self.data["engine"]
        projection_override = engine["projection"]
        profile_id = str(projection_override.get("profile_id", "")).strip()
        projection_profiles = engine.get("projection_profiles", {})
        if profile_id:
            profile = projection_profiles.get(profile_id)
            if not isinstance(profile, Mapping):
                raise ValueError(
                    f"engine projection profile {profile_id!r} is unavailable"
                )
            projection = dict(profile)
            projection.update(
                {
                    key: value
                    for key, value in projection_override.items()
                    if key != "profile_id"
                }
            )
        else:
            projection = dict(projection_override)
        self._projection_profile_id = profile_id or "inline"
        mode = str(projection.get("mode", "orthographic"))
        self._projection_depth_origin = float(projection.get("depth_origin", 280.0))
        self.projection = BeatEmUpProjection(ProjectionConfig(
            mode=mode,
            screen_origin_x=float(projection.get("screen_origin_x", 0.0)),
            floor_screen_y=float(projection.get("screen_y_origin", self._projection_depth_origin)),
            pixels_per_world_x=float(projection.get("world_x_scale", 1.0)),
            pixels_per_depth=float(projection.get("depth_scale", 1.0)),
            pixels_per_elevation=float(projection.get("elevation_scale", 1.0)),
            oblique_x_per_depth=float(projection.get("oblique_x_shear", 0.0)),
            pixel_snap=bool(projection.get("pixel_snap", True)),
        ))

        geometry = self.data["stage_geometry"]
        self.stage_geometry = StageGeometry(
            regions=tuple(
                WalkableRegion.rectangular(
                    float(segment["start_x"]),
                    float(segment["end_x"]),
                    float(segment["far_depth"]),
                    float(segment["near_depth"]),
                    name=f"second_street_{index}",
                    priority=index,
                )
                for index, segment in enumerate(geometry["rails"])
            ),
            obstacles=tuple(
                RectObstacle(
                    float(item["x"]) - float(item["half_width"]),
                    float(item["x"]) + float(item["half_width"]),
                    float(item["depth"]) - float(item["half_depth"]),
                    float(item["depth"]) + float(item["half_depth"]),
                    str(item["id"]),
                )
                for item in geometry.get("obstacles", ())
            ),
        )
        self._combat_bounds = StageBounds(
            0.0,
            float(self.meta["stage_width"]),
            min(float(segment["far_depth"]) for segment in geometry["rails"]),
            max(float(segment["near_depth"]) for segment in geometry["rails"]),
        )
        self._combat_obstacles = tuple(
            StageObstacle(
                str(item["id"]),
                AABB2(
                    float(item["x"]) - float(item["half_width"]),
                    float(item["x"]) + float(item["half_width"]),
                    float(item["depth"]) - float(item["half_depth"]),
                    float(item["depth"]) + float(item["half_depth"]),
                ),
                max_elevation=34.0 if str(item.get("kind")) in {"road_barrier", "bollards"} else 80.0,
            )
            for item in geometry.get("obstacles", ())
        )

        camera = engine["camera"]
        zones = tuple(
            CameraZone(
                name=str(zone["name"]),
                x_min=float(zone["start_x"]),
                x_max=float(zone["end_x"]),
                entry_pan_seconds=0.16,
                priority=index,
            )
            for index, zone in enumerate(geometry.get("camera_zones", ()))
        )
        self.camera = CameraDirector(
            viewport_width=float(LOGICAL_SIZE[0]),
            stage_min_x=0.0,
            stage_max_x=float(self.meta["stage_width"]),
            zones=zones,
            dead_zone_left=float(camera.get("dead_zone_left", 238.0)),
            dead_zone_right=float(camera.get("dead_zone_right", 398.0)),
            follow_speed=float(camera.get("follow_speed", 250.0)),
            lookahead_seconds=0.18,
            max_lookahead=float(camera.get("look_ahead", 50.0)),
            pixel_snap=bool(projection.get("pixel_snap", True)),
        )

    def close(self) -> None:
        self.audio_manager.shutdown()

    def log_breadcrumb(self, event: str, **details: Any) -> None:
        breadcrumb(event, state=self.state, frame=self.frame, **details)

    def handle_events(self, events: Iterable[pygame.event.Event]) -> None:
        events = list(events)
        for event in events:
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.MOUSEMOTION:
                self.mouse_position = tuple(map(int, event.pos))
                self._update_mouse_hover()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.mouse_position = tuple(map(int, event.pos))
                self._handle_mouse_click()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F3:
                    self.debug = not self.debug
                    self.audio.play("menu")
                elif event.key == pygame.K_ESCAPE:
                    if self.state == "gameplay":
                        if self.pause:
                            self._pause_back()
                        else:
                            self._open_pause_menu(source="keyboard_escape")
                    elif self.state == "complete":
                        if self.victory_frame.show_results:
                            self._open_epilogue()
                    elif self.state == "epilogue":
                        self._go_title()
                    elif self.state == "interlevel":
                        self.pending_level_id = None
                        self.interlevel_source_id = None
                        self.interlevel_travel_panel = None
                        self.interlevel_timer = 0.0
                        self.state = "epilogue"
                        self.audio.play("menu")
                        self.log_breadcrumb("interlevel_cancelled", source="keyboard_escape")
                    elif self.state in {"character_select", "game_over"}:
                        self._go_title()
                    else:
                        self.running = False

            source = self.input.source_from_event(event)
            if source is None:
                continue
            if self.state in {"loading", "title"}:
                self.loading_timer = 0.0
                self.state = "character_select"
                self._join_source(source)
                self.audio.play("menu")
                self.log_breadcrumb("character_select_opened", source=source)
            elif self.state == "character_select":
                self._join_source(source)

    def _keyboard_select_slot(self) -> SelectSlot:
        """Return the keyboard's lobby slot, adding it for mouse navigation."""

        keyboard = {"type": "keyboard"}
        for slot in self.select_slots:
            if slot.binding == keyboard:
                return slot
        self._join_source(keyboard)
        return self.select_slots[-1]

    def _open_character_select_from_mouse(self) -> None:
        if self.state not in {"loading", "title"}:
            return
        self.loading_timer = 0.0
        self.state = "character_select"
        self._keyboard_select_slot()
        self.audio.play("menu")
        self.log_breadcrumb("character_select_opened", source="mouse")

    def _activate_pause_selection(self, *, source: str) -> None:
        """Apply the selected pause action for keyboards, pads, and clicks."""

        action = PAUSE_MENU_ITEMS[self.pause_selection][0]
        if action == "resume":
            self._resume_from_pause(source=source)
        elif action == "controls":
            self.pause_page = "controls"
            self.pause_nav_cooldown = 0.0
            self.pause_release_guard = False
            self.audio.play("menu")
            self.log_breadcrumb("pause_controls_opened")
        elif action in {"main_menu", "exit_game"}:
            self.pause_page = f"confirm_{action}"
            self.pause_confirm_selection = 0
            self.pause_nav_cooldown = 0.0
            self.pause_release_guard = False
            self.audio.play("menu")
            self.log_breadcrumb("pause_confirmation_opened", destination=action)

    def _handle_mouse_click(self) -> None:
        if self.mouse_position is None:
            return
        point = self.mouse_position
        if self.state == "gameplay" and self.level_outro is not None and not self.pause:
            self._level_outro_mouse_advance_pending = True
            return
        if self.state in {"loading", "title"}:
            if pygame.Rect(145, 307, 350, 39).collidepoint(point):
                self._open_character_select_from_mouse()
            return
        if self.state == "character_select":
            for index in range(2):
                if pygame.Rect(16 + index * 156, 39, 144, 177).collidepoint(point):
                    slot = self._keyboard_select_slot()
                    slot.character_index = index
                    slot.confirmed = False
                    self.audio.play("menu")
                    self.log_breadcrumb("character_selected", player=1, character=("black_dave", "shelly")[index], source="mouse")
                    return
            if pygame.Rect(16, 229, 144, 91).collidepoint(point):
                slot = self._keyboard_select_slot()
                if slot.confirmed:
                    self._start_stage()
                else:
                    slot.confirmed = True
                    self.audio.play("menu")
                    self.log_breadcrumb("character_confirmed", player=1, character=("black_dave", "shelly")[slot.character_index], source="mouse")
            return
        if self.state == "complete":
            if self.victory_frame.show_results:
                self._open_epilogue()
            return
        if self.state == "epilogue":
            for index in range(4):
                if pygame.Rect(382, 128 + index * 35, 214, 28).collidepoint(point):
                    self.epilogue_selection = index
                    self._activate_epilogue_selection()
                    return
            return
        if self.state == "interlevel":
            self._start_pending_level(source="mouse")
            return
        if self.state == "game_over":
            self._go_title()
            return
        if self.state != "gameplay" or not self.pause:
            return
        if self.pause_page == "menu":
            for index, _ in enumerate(PAUSE_MENU_ITEMS):
                if pygame.Rect(183, 88 + index * 47, 274, 38).collidepoint(point):
                    self.pause_selection = index
                    self._activate_pause_selection(source="mouse")
                    return
        elif self.pause_page == "controls":
            self._pause_back()
        elif self.pause_page.startswith("confirm_"):
            for index in range(2):
                if pygame.Rect(154 + index * 178, 190, 154, 43).collidepoint(point):
                    self.pause_confirm_selection = index
                    if index == 0:
                        self._pause_back()
                    else:
                        destination = "main_menu" if self.pause_page == "confirm_main_menu" else "exit_game"
                        self.log_breadcrumb("pause_exit_confirmed", destination=destination, source="mouse")
                        if destination == "main_menu":
                            self._go_title()
                        else:
                            self.running = False
                    return

    def _update_mouse_hover(self) -> None:
        """Keep click targets visibly responsive without changing gameplay input."""

        if self.mouse_position is None:
            return
        if self.state == "epilogue" and self.epilogue_page == "menu":
            for index in range(4):
                if pygame.Rect(382, 128 + index * 35, 214, 28).collidepoint(self.mouse_position):
                    self.epilogue_selection = index
                    return
        if not (self.state == "gameplay" and self.pause):
            return
        if self.pause_page == "menu":
            for index, _ in enumerate(PAUSE_MENU_ITEMS):
                if pygame.Rect(183, 88 + index * 47, 274, 38).collidepoint(self.mouse_position):
                    self.pause_selection = index
                    return
        elif self.pause_page.startswith("confirm_"):
            for index in range(2):
                if pygame.Rect(154 + index * 178, 190, 154, 43).collidepoint(self.mouse_position):
                    self.pause_confirm_selection = index
                    return

    def update(self, dt: float) -> None:
        dt = min(dt, 1.0 / 20.0)
        self.elapsed += dt
        self.frame += 1
        self.controller_notice = max(0.0, self.controller_notice - dt)
        if self.state in {"gameplay", "complete", "epilogue", "interlevel"}:
            self.atmosphere.advance(
                dt,
                paused=self.state == "gameplay" and self.pause,
            )
        if self.input.controller_count != self._last_controller_count:
            self._last_controller_count = self.input.controller_count
            self.controller_notice = 3.0
            self.log_breadcrumb("controller_count_changed", count=self.input.controller_count, devices=self.input.connected_controllers)

        if self.state == "loading":
            self.loading_timer -= dt
            if self.loading_timer <= 0.0:
                self.state = "title"
                self.log_breadcrumb("title_ready")
        elif self.state == "character_select":
            self._update_character_select(dt)
        elif self.state == "gameplay":
            if not self.pause:
                self._update_gameplay(dt)
            else:
                self._update_pause_menu(dt)
        elif self.state == "complete":
            self.complete_timer += dt
            if self.level_is_chapter_finale:
                self.victory_frame = self.victory_timeline.advance(dt)
                if "treat_release" in self.victory_frame.events:
                    self.audio.play("dog")
                    self.log_breadcrumb("victory_treats_tossed")
            if not self.victory_frame.show_results:
                return
            for slot in self.select_slots:
                snap = self.input.snapshot(slot.binding)
                if snap.pressed & {"confirm", "join", "light", "jump", "pause"}:
                    self._open_epilogue()
                    break
        elif self.state == "epilogue":
            self.epilogue_timer += dt
            self._update_epilogue(dt)
        elif self.state == "interlevel":
            self._update_interlevel(dt)
        elif self.state == "game_over":
            self.complete_timer += dt
            for slot in self.select_slots:
                snap = self.input.snapshot(slot.binding)
                if snap.pressed & {"confirm", "join", "light", "jump", "pause"}:
                    self._go_title()
                    break

    def _next_campaign_level(self) -> dict[str, Any] | None:
        """Return the authored successor of the currently completed level."""

        levels = campaign_levels(self.data)
        current_index = next(
            (index for index, level in enumerate(levels) if str(level.get("id")) == self.level_id),
            -1,
        )
        if 0 <= current_index < len(levels) - 1:
            return levels[current_index + 1]
        return None

    def _select_campaign_level(self, level_id: str) -> None:
        """Switch the live in-memory stage snapshot to an authored level."""

        self.data = activate_campaign_level(self.data, level_id)
        self.meta = self.data["meta"]
        self.level_data = active_campaign_level(self.data)
        self.level_id = str(self.level_data["id"])
        self.level_number = int(self.level_data["number"])
        self.level_title = str(self.level_data["title"])
        self.level_theme = str(self.level_data["background_theme"])
        self.location_route = location_lock.route_for_level(
            self.level_id,
            self.location_manifest,
        )
        self._validate_location_route_binding()
        self.atmosphere.set_profile_for_route(self.level_id)
        self.level_is_chapter_finale = bool(self.level_data.get("chapter_finale", False))
        self.level_has_couch = self.level_data.get("boss") == "couch"
        self.log_breadcrumb(
            "campaign_level_selected",
            level_id=self.level_id,
            number=self.level_number,
            theme=self.level_theme,
            stage_width=self.meta["stage_width"],
        )

    def _begin_interlevel(self, next_level: dict[str, Any]) -> None:
        """Begin the manifest-authored non-combat handoff to the next route."""

        self.pending_level_id = str(next_level["id"])
        self.interlevel_source_id = self.level_id
        # Begin the palette handoff during travel so the destination does not
        # open on several seconds of the prior route's sky.
        self.atmosphere.set_profile_for_route(self.pending_level_id)
        self.interlevel_travel_panel = location_lock.travel_panel_between(
            self.interlevel_source_id,
            self.pending_level_id,
            self.location_manifest,
        )
        self.interlevel_duration = (
            3.8
            if str(self.interlevel_travel_panel["presentation"]) == "moving_panel"
            else 1.75
        )
        self.interlevel_timer = self.interlevel_duration
        self.state = "interlevel"
        self.audio.play("menu")
        self.log_breadcrumb(
            "interlevel_started",
            from_level=self.interlevel_source_id,
            to_level=self.pending_level_id,
            travel_panel=self.interlevel_travel_panel["id"],
        )

    def _start_pending_level(self, *, source: str) -> None:
        level_id = self.pending_level_id
        if not level_id:
            self.state = "epilogue"
            return
        self.pending_level_id = None
        self.interlevel_source_id = None
        self.interlevel_travel_panel = None
        self.interlevel_timer = 0.0
        self._select_campaign_level(level_id)
        self._start_stage()
        self.log_breadcrumb("interlevel_finished", level_id=level_id, source=source)

    def _update_interlevel(self, dt: float) -> None:
        snapshots = self._active_menu_snapshots()
        if any(snapshot.pressed & {"back", "dodge", "pause"} for snapshot in snapshots):
            if self.interlevel_source_id:
                self.atmosphere.set_profile_for_route(self.interlevel_source_id)
            self.pending_level_id = None
            self.interlevel_source_id = None
            self.interlevel_travel_panel = None
            self.interlevel_timer = 0.0
            self.state = "epilogue"
            self.audio.play("menu")
            self.log_breadcrumb("interlevel_cancelled")
            return
        self.interlevel_timer = max(0.0, self.interlevel_timer - dt)
        departure_pressed = any(
            snapshot.pressed & {"confirm", "join", "light", "heavy", "jump", "interact", "super", "chief", "secondary"}
            for snapshot in snapshots
        )
        if departure_pressed or self.interlevel_timer <= 0.0:
            self._start_pending_level(source="input" if departure_pressed else "timer")

    def _open_epilogue(self) -> None:
        """Reveal the sunset ride and post-demo choices after the score card."""

        if self.state != "complete" or not self.victory_frame.show_results:
            return
        self.state = "epilogue"
        self.epilogue_timer = 0.0
        self.epilogue_selection = 0
        self.epilogue_notice = ""
        self.epilogue_page = "menu"
        self.audio.play("menu")
        self.log_breadcrumb("victory_epilogue_opened")

    def _activate_epilogue_selection(self) -> None:
        action = ("next_level", "replay", "main_menu", "options")[self.epilogue_selection]
        if action == "next_level":
            next_level = self._next_campaign_level()
            if next_level is not None and str(next_level.get("status", "")).lower() == "playable":
                self._begin_interlevel(next_level)
                self.log_breadcrumb("epilogue_action", action=action, level_id=next_level["id"])
                return
            if next_level is None:
                self.epilogue_notice = "CHAPTER COMPLETE"
            else:
                self.epilogue_notice = f"LEVEL {next_level['number']} IS LOCKED"
        elif action == "replay":
            self._start_stage()
            self.log_breadcrumb("epilogue_action", action=action, level_id=self.level_id)
            return
        elif action == "main_menu":
            self._go_title()
            self.log_breadcrumb("epilogue_action", action=action)
            return
        else:
            self.epilogue_page = "options"
        self.audio.play("menu")
        self.log_breadcrumb("epilogue_action", action=action)

    def _update_epilogue(self, dt: float) -> None:
        snapshots = self._active_menu_snapshots()
        if not snapshots:
            return
        if any(snapshot.pressed & {"back", "dodge", "pause"} for snapshot in snapshots):
            if self.epilogue_page == "options":
                self.epilogue_page = "menu"
            else:
                self._go_title()
            return
        if self.epilogue_page == "options":
            if any(snapshot.pressed & {"confirm", "jump", "light"} for snapshot in snapshots):
                self.epilogue_page = "menu"
            return
        navigation = next((1 if snapshot.move_y > 0.55 else -1 if snapshot.move_y < -0.55 else 0 for snapshot in snapshots if abs(snapshot.move_y) > 0.55), 0)
        if navigation:
            self.epilogue_selection = (self.epilogue_selection + navigation) % 4
            self.audio.play("menu")
            return
        if any(snapshot.pressed & {"confirm", "jump", "light"} for snapshot in snapshots):
            self._activate_epilogue_selection()

    def _active_menu_snapshots(self) -> list[InputSnapshot]:
        """Return keyboard plus one snapshot per unique active player binding."""

        # Keep keyboard menu control available even in a controller-only run so
        # a tester can always recover without reconnecting a specific gamepad.
        bindings: list[dict[str, object]] = [{"type": "keyboard"}]
        bindings.extend(player.binding for player in self.players if not player.is_cpu)
        if not self.players:
            bindings.extend(slot.binding for slot in self.select_slots)
        snapshots: list[InputSnapshot] = []
        seen: set[tuple[str, int]] = set()
        for binding in bindings:
            binding_type = str(binding.get("type", ""))
            binding_id = int(binding.get("instance_id", -1))
            key = (binding_type, binding_id)
            if key in seen:
                continue
            seen.add(key)
            snapshots.append(self.input.snapshot(binding))
        return snapshots

    def _open_pause_menu(self, *, source: str, require_release: bool = False) -> None:
        if self.state != "gameplay" or self.pause:
            return
        self.pause = True
        self.pause_page = "menu"
        self.pause_selection = 0
        self.pause_confirm_selection = 0
        self.pause_nav_cooldown = 0.0
        self.pause_release_guard = require_release
        self.pause_opened_at = self.elapsed
        self.audio.play("menu")
        self.log_breadcrumb("pause_opened", source=source)

    def _resume_from_pause(self, *, source: str, require_release: bool = False) -> None:
        if not self.pause:
            return
        paused_for = max(0.0, self.elapsed - self.pause_opened_at)
        self.pause = False
        self.pause_page = "menu"
        self.pause_selection = 0
        self.pause_confirm_selection = 0
        self.pause_nav_cooldown = 0.0
        self.pause_release_guard = require_release
        self.audio.play("menu")
        self.log_breadcrumb("pause_resumed", source=source, paused_seconds=round(paused_for, 3))

    def _pause_back(self, *, require_release: bool = False) -> None:
        """Back out of a pause subpage, or resume from the root pause menu."""

        if not self.pause:
            return
        if self.pause_page == "menu":
            self._resume_from_pause(source="back", require_release=require_release)
            return
        previous_page = self.pause_page
        self.pause_page = "menu"
        self.pause_confirm_selection = 0
        self.pause_nav_cooldown = 0.0
        self.audio.play("menu")
        self.log_breadcrumb("pause_page_back", page=previous_page)

    @staticmethod
    def _pause_input_is_neutral(snapshots: list[InputSnapshot]) -> bool:
        # InputManager keeps ``pressed`` edges for every fixed update belonging
        # to one rendered frame. Guard only those edges; waiting for every held
        # stick/button would let one co-op partner lock the menu for everyone.
        menu_actions = {"confirm", "jump", "back", "dodge", "pause"}
        return all(
            not (snapshot.pressed & menu_actions)
            for snapshot in snapshots
        )

    def _update_pause_menu(self, dt: float) -> None:
        snapshots = self._active_menu_snapshots()
        if not snapshots:
            return

        if self.pause_release_guard:
            if self._pause_input_is_neutral(snapshots):
                self.pause_release_guard = False
            return

        self.pause_nav_cooldown = max(0.0, self.pause_nav_cooldown - dt)
        confirm_pressed = any(
            bool(snapshot.pressed & {"confirm", "jump"}) for snapshot in snapshots
        )
        back_pressed = any(
            bool(snapshot.pressed & {"back", "dodge"})
            or ("pause" in snapshot.pressed and not (snapshot.pressed & {"confirm", "jump"}))
            for snapshot in snapshots
        )

        if back_pressed:
            self._pause_back(require_release=True)
            self.pause_release_guard = True
            return

        navigation = 0
        if self.pause_nav_cooldown <= 0.0:
            for snapshot in snapshots:
                axis = snapshot.move_y
                if self.pause_page.startswith("confirm_") and abs(snapshot.move_x) > abs(axis):
                    axis = snapshot.move_x
                if abs(axis) > 0.55:
                    navigation = 1 if axis > 0.0 else -1
                    break

        if navigation:
            if self.pause_page == "menu":
                self.pause_selection = (self.pause_selection + navigation) % len(PAUSE_MENU_ITEMS)
            elif self.pause_page.startswith("confirm_"):
                self.pause_confirm_selection = (self.pause_confirm_selection + navigation) % 2
            self.pause_nav_cooldown = 0.18
            self.audio.play("menu")
            return

        if not confirm_pressed:
            return

        if self.pause_page == "controls":
            self._pause_back()
            self.pause_release_guard = True
            return

        if self.pause_page.startswith("confirm_"):
            if self.pause_confirm_selection == 0:
                self._pause_back()
                self.pause_release_guard = True
                return
            destination = "main_menu" if self.pause_page == "confirm_main_menu" else "exit_game"
            self.log_breadcrumb("pause_exit_confirmed", destination=destination)
            self.audio.play("menu")
            if destination == "main_menu":
                self._go_title()
            else:
                self.running = False
            return

        self._activate_pause_selection(source="confirm")
        self.pause_release_guard = True

    def _play_menu_music(self) -> bool:
        """Start the configured title/select loop without disturbing mute mode."""

        if self.mute:
            self.music_started = False
            return False
        filename = str(self.data.get("audio", {}).get("menu_music", ""))
        if not filename:
            self.music_started = False
            return False
        self.music_started = self.audio_manager.play_music_file(filename, loop=True)
        self.log_breadcrumb("menu_music_selected", filename=filename, started=self.music_started)
        return self.music_started

    def _go_title(self) -> None:
        # A fresh title-screen run always begins at the authored Chapter 1
        # opener instead of retaining a previously completed route segment.
        first_level = campaign_levels(self.data)[0]
        if self.level_id != str(first_level["id"]):
            self._select_campaign_level(str(first_level["id"]))
        self.state = "title"
        self.pause = False
        self.pause_page = "menu"
        self.pause_selection = 0
        self.pause_confirm_selection = 0
        self.pause_release_guard = False
        self.select_slots.clear()
        self.players.clear()
        self.enemies.clear()
        self.chiefs.clear()
        self.projectiles.clear()
        self.ammo_pickups.clear()
        self.super_butane_pickups.clear()
        self.effects.clear()
        self._dave_flame_visuals.clear()
        self.bb_eligible_kos = 0
        self.bb_drop_index = 0
        self.bb_next_drop_at = 0
        self.super_butane_eligible_kos = 0
        self.super_butane_drop_index = 0
        self.super_butane_next_drop_at = 0
        self._post_clear_reinforcements.clear()
        self._security_spawn_speech = ""
        self._security_speech_by_enemy.clear()
        self.shelly_frenzy_cinematic = None
        self._cpu_shelly_frenzy_uses.clear()
        self._cpu_shelly_frenzy_charge.clear()
        self._cpu_shelly_frenzy_rearm.clear()
        self.boss_transition = None
        self.boss_transition_frame = None
        self.couch_retreat = None
        self.level_outro = None
        self.level_outro_frame = None
        self.completion_stats = None
        self.victory_timeline.reset()
        self.victory_frame = self.victory_timeline.current_frame()
        self.epilogue_timer = 0.0
        self.epilogue_notice = ""
        self.epilogue_page = "menu"
        self.pending_level_id = None
        self.interlevel_source_id = None
        self.interlevel_travel_panel = None
        self.interlevel_timer = 0.0
        self._play_menu_music()
        self.log_breadcrumb("returned_to_title")

    def _join_source(self, source: dict[str, object]) -> None:
        if any(slot.binding == source for slot in self.select_slots):
            return
        if len(self.select_slots) >= 4:
            return
        self.select_slots.append(SelectSlot(dict(source), character_index=len(self.select_slots) % 2))
        self.audio.play("menu")
        self.log_breadcrumb("player_joined", player=len(self.select_slots), binding=source)

    def _selection_footer_lines(self) -> tuple[str, str]:
        """Describe actual local ownership without implying a fixed solo lead."""

        controller_line = f"{self.input.controller_count} CONTROLLER(S) DETECTED"
        if len(self.select_slots) == 1:
            controlled_index = self.select_slots[0].character_index
            controlled = ("BLACK DAVE", "SHELLY")[controlled_index]
            companion = ("SHELLY", "BLACK DAVE")[controlled_index]
            return (
                f"YOU CONTROL: {controlled}  •  CPU COMPANION: {companion}",
                f"CHIEF IS SHARED AI SUPPORT  •  {controller_line}",
            )
        return (
            "EACH PLAYER CONTROLS THE HERO SHOWN  •  CHIEF IS SHARED AI SUPPORT",
            controller_line,
        )

    def _prepare_runtime_chapter_content(self) -> None:
        """Compile the authored Chapter record for the live human roster.

        The existing ``gameplay.json`` remains the collision and combat source
        of truth.  This layer enriches it with route cards, distinct optional
        branches, reusable environmental beats, and authored enemy roles.
        """

        human_count = max(1, sum(not player.is_cpu for player in self.players))
        compiled = compile_level_content(self.chapter_content, self.level_id, human_count)
        self.runtime_chapter_content = compiled
        self._content_major_by_hook = {
            str(fight.get("runtime_hook", "")).strip().lower(): fight
            for fight in compiled.get("major_fights", ())
            if isinstance(fight, dict)
        }
        optionals = [
            entry for entry in compiled.get("ambush_or_optional", ()) if isinstance(entry, dict)
        ]
        self._content_optional = optionals[0] if optionals else None
        self._content_optional_prompt = ""
        self._content_optional_active = False
        self._content_optional_completed.clear()
        self._content_event_index = 0
        self._content_event_seen.clear()

        landmarks = [
            item for item in self.level_data.get("landmarks", ())
            if isinstance(item, dict) and "x" in item
        ]
        landmark_index = min(max(1, len(landmarks) // 2), max(0, len(landmarks) - 1))
        fallback = float(self.meta.get("stage_width", LOGICAL_SIZE[0])) * 0.45
        self._content_optional_trigger_x = float(landmarks[landmark_index].get("x", fallback)) if landmarks else fallback

    def _route_card_objective(self) -> str:
        """Return short, non-obstructive objective copy for the active strip."""

        story = self.runtime_chapter_content.get("story_beats", ())
        if isinstance(story, list) and story and isinstance(story[0], dict):
            description = str(story[0].get("description", "")).strip()
            if description:
                words = description.upper().split()
                return " ".join(words[:11])
        return {
            "chapter_1_level_1": "CLEAR THE LOT • FIND COUCH'S TRAIL",
            "chapter_1_level_2": "FOLLOW THE CLUE NORTH TO I-8",
            "chapter_1_level_3": "CROSS THE WASH • TURN FOR REVIVE",
            "chapter_1_level_4": "HOLD THE LOT • FACE COUCH AT THE BMX",
        }.get(self.level_id, "KEEP THE ROUTE MOVING NORTH")

    def _update_character_select(self, dt: float) -> None:
        if not self.select_slots:
            return
        start_requested = False
        for index, slot in enumerate(self.select_slots):
            slot.nav_cooldown = max(0.0, slot.nav_cooldown - dt)
            snapshot = self.input.snapshot(slot.binding)
            if not slot.confirmed and slot.nav_cooldown <= 0.0 and abs(snapshot.move_x) > 0.55:
                slot.character_index = (slot.character_index + (1 if snapshot.move_x > 0 else -1)) % 2
                slot.nav_cooldown = 0.22
                self.audio.play("menu")
            if snapshot.pressed & {"confirm", "light", "jump"}:
                if slot.confirmed:
                    start_requested = True
                else:
                    slot.confirmed = True
                    self.audio.play("menu")
                    self.log_breadcrumb("character_confirmed", player=index + 1, character=("black_dave", "shelly")[slot.character_index])
            if "back" in snapshot.pressed or "dodge" in snapshot.pressed:
                if slot.confirmed:
                    slot.confirmed = False
                elif len(self.select_slots) > 1:
                    self.select_slots.pop(index)
                    break
            if "pause" in snapshot.pressed and slot.confirmed:
                start_requested = True

        if start_requested and self.select_slots and all(slot.confirmed for slot in self.select_slots):
            self._start_stage()

    def _start_stage(self) -> None:
        # Tests and debug tools may select an authored level before invoking
        # the normal menu flow.  Keep the runtime snapshot synchronized with
        # that explicit selection before rebuilding geometry/camera state.
        if str(active_campaign_level(self.data).get("id")) != self.level_id:
            self._select_campaign_level(self.level_id)
        self.state = "gameplay"
        self.pause = False
        self.pause_page = "menu"
        self.pause_selection = 0
        self.pause_confirm_selection = 0
        self.pause_release_guard = False
        self.players.clear()
        self.enemies.clear()
        self.chiefs.clear()
        self.projectiles.clear()
        self.ammo_pickups.clear()
        self.super_butane_pickups.clear()
        self.effects.clear()
        self._dave_flame_visuals.clear()
        self.bb_eligible_kos = 0
        self.bb_drop_index = 0
        self.bb_next_drop_at = self._bb_drop_interval(0)
        self.super_butane_eligible_kos = 0
        self.super_butane_drop_index = 0
        self.super_butane_next_drop_at = self._super_butane_drop_interval(0)
        self.camera_x = 0.0
        self._render_camera_x = 0.0
        self._camera_shake_y = 0.0
        self._last_camera_view = None
        self._pending_camera_lock = None
        self.hitstop_remaining = 0.0
        self._hitstop_pressed_by_slot.clear()
        self.impact_flash = 0.0
        self._debug_last_attack = None
        self._debug_last_contacts = ()
        self._debug_last_evaluations = ()
        self._debug_last_result = "NONE"
        self._debug_last_rejection = "NONE"
        self._debug_last_query_frame = -1
        self._debug_logged_rejections.clear()
        self.shelly_frenzy_cinematic = None
        self._cpu_shelly_frenzy_uses.clear()
        self._cpu_shelly_frenzy_charge.clear()
        self._cpu_shelly_frenzy_rearm.clear()
        self._configure_engine()
        self.active_gate = None
        self.encounter_index = 0
        self.encounter_active = False
        self.spawn_queue.clear()
        self._post_clear_reinforcements.clear()
        self._security_spawn_speech = ""
        self._security_speech_by_enemy.clear()
        self._encounter_enemy_durability_scale = 1.0
        self._encounter_enemy_damage_scale = 1.0
        self._encounter_enemy_score_scale = 1.0
        self.attack_tokens_used = 0
        self.stage_banner = f"LEVEL {self.level_number}  •  {self.level_title}".upper()
        self.stage_banner_timer = 2.4
        self.complete_timer = 0.0
        self.level_stats.reset()
        self.completion_stats = None
        self.victory_timeline.reset()
        self.victory_frame = self.victory_timeline.current_frame()
        self.epilogue_timer = 0.0
        self.epilogue_notice = ""
        self.epilogue_page = "menu"
        self.pending_level_id = None
        self.interlevel_source_id = None
        self.interlevel_travel_panel = None
        self.interlevel_timer = 0.0
        self.boss_transition = None
        self.boss_transition_frame = None
        self.couch_retreat = None
        self.level_outro = None
        self.level_outro_frame = None

        characters = ("black_dave", "shelly")
        for index, slot in enumerate(self.select_slots):
            character = characters[slot.character_index]
            player = Player(
                slot=index,
                character=character,
                binding=dict(slot.binding),
                x=105.0 + index * 34.0,
                y=258.0 + index * 18.0,
                config=self.data["players"],
                moves=self.data["moves"],
                color_index=index,
                is_cpu=False,
            )
            self.players.append(player)

        # A solo run defaults to Dave plus CPU Shelly. Choosing Shelly remains
        # available and swaps in CPU Dave, preserving both playable options.
        if len(self.select_slots) == 1:
            human = self.players[0]
            companion_character = "shelly" if human.character == "black_dave" else "black_dave"
            companion = Player(
                slot=1,
                character=companion_character,
                binding={"type": "cpu", "instance_id": -2},
                x=human.x - 42.0,
                y=human.y + 18.0,
                config=self.data["players"],
                moves=self.data["moves"],
                color_index=1,
                is_cpu=True,
            )
            self.players.append(companion)

        chief_cfg = self.data["chief"]
        chief_meter_start = float(chief_cfg.get("command_start_meter", 100.0))
        chief_meter_max = float(chief_cfg.get("command_meter_max", 100.0))
        for player in self.players:
            player.chief_meter = min(chief_meter_max, chief_meter_start)

        bb_cfg = self.data.get("bb_gun", {})
        bb_max_ammo = max(0, int(bb_cfg.get("max_ammo", 6)))
        bb_start_ammo = max(0, int(bb_cfg.get("start_ammo", 4)))
        for player in self.players:
            player.bb_ammo = min(bb_max_ammo, bb_start_ammo) if player.character == "black_dave" else 0
            player.bb_cooldown = 0.0

        propane_cfg = self.data.get("shelly_propane", {})
        propane_max = max(0.0, float(propane_cfg.get("meter_max", 100.0)))
        propane_start = max(0.0, float(propane_cfg.get("start_meter", 0.0)))
        for player in self.players:
            player.super_butane_meter = min(propane_max, propane_start) if player.character == "shelly" else 0.0
            player.propane_tick = 0.0

        # Chief is one shared teammate. He anchors to the first Shelly when
        # present, while all players retain their own command meter.
        if self.players:
            chief_owner = next((player for player in self.players if player.character == "shelly"), self.players[0])
            self.chiefs.append(Chief(chief_owner, chief_cfg, chief_owner.x - 28.0, chief_owner.y + 9.0))

        self._prepare_runtime_chapter_content()
        self.route_card_timer = 2.7
        self.route_card_objective = self._route_card_objective()

        if not self.mute:
            filename = str(self.data.get("audio", {}).get("stage_music", "second_street_loop.wav"))
            self.music_started = self.audio_manager.play_music_file(filename, loop=True)
            self.log_breadcrumb("stage_music_selected", filename=filename, started=self.music_started)
        self.log_breadcrumb(
            "stage_started",
            stage="second_street",
            players=[
                {"slot": p.slot + 1, "character": p.character, "binding": p.binding, "cpu": p.is_cpu}
                for p in self.players
            ],
        )

    def _update_gameplay(self, dt: float) -> None:
        self.route_card_timer = max(0.0, self.route_card_timer - dt)
        human_players = [player for player in self.players if not player.is_cpu]
        human_snapshot_by_slot = {
            player.slot: self.input.snapshot(player.binding)
            for player in human_players
        }
        human_snapshots = list(human_snapshot_by_slot.values())
        # Dialogue owns normal action buttons so Enter/Start's menu alias
        # cannot pre-empt a requested continuation. Escape still opens pause
        # directly in ``handle_events``.
        if self.level_outro is not None:
            self._update_level_outro(dt, human_snapshots)
            return
        if self.pause_release_guard:
            if self._pause_input_is_neutral(human_snapshots):
                self.pause_release_guard = False
            return
        for player in human_players:
            snapshot = human_snapshot_by_slot[player.slot]
            if "pause" in snapshot.pressed:
                source = "keyboard_enter" if player.binding.get("type") == "keyboard" else f"controller_{player.slot + 1}_start"
                self._open_pause_menu(source=source, require_release=True)
                return

        if self.boss_transition is not None:
            self._update_boss_transition(dt)
            for effect in self.effects:
                effect.update(dt)
            self.effects = [effect for effect in self.effects if effect.alive]
            self.stage_banner_timer = max(0.0, self.stage_banner_timer - dt)
            return
        self.level_stats.advance(dt)
        self._advance_shelly_frenzy_cinematic(dt)

        # Support actions are dispatched before hitstop so a valid trigger edge
        # cannot be consumed while combat is temporarily frozen.
        for player in human_players:
            pressed = human_snapshot_by_slot[player.slot].pressed
            if "chief" in pressed:
                self.command_chief(player, feedback=True)
            if "secondary" in pressed:
                self.fire_secondary(player, feedback=True)

        self.impact_flash = max(0.0, self.impact_flash - dt)
        if self.hitstop_remaining > 0.0:
            # A short global freeze gives attacks weight while camera shake and
            # controller polling continue deterministically. Action edges are
            # retained for the first unfrozen simulation step.
            buffered_actions = frozenset(
                {"light", "heavy", "jump", "dodge", "super", "interact"}
            )
            for player in human_players:
                pressed = human_snapshot_by_slot[player.slot].pressed & buffered_actions
                if pressed:
                    self._hitstop_pressed_by_slot.setdefault(player.slot, set()).update(pressed)
            self.hitstop_remaining = max(0.0, self.hitstop_remaining - dt)
            self._update_camera(dt)
            return

        for player in human_players:
            buffered = self._hitstop_pressed_by_slot.pop(player.slot, set())
            if not buffered:
                continue
            snapshot = human_snapshot_by_slot[player.slot]
            human_snapshot_by_slot[player.slot] = InputSnapshot(
                move_x=snapshot.move_x,
                move_y=snapshot.move_y,
                held=snapshot.held,
                pressed=snapshot.pressed | frozenset(buffered),
            )

        self._frame_snapshots = {
            player.slot: (self._cpu_snapshot(player, dt) if player.is_cpu else human_snapshot_by_slot[player.slot])
            for player in self.players
        }
        for player in (candidate for candidate in self.players if candidate.is_cpu):
            if "chief" in self._frame_snapshots[player.slot].pressed:
                self.command_chief(player, feedback=False)
            if "secondary" in self._frame_snapshots[player.slot].pressed:
                self.fire_secondary(player, feedback=False)
        for player in self.players:
            player.update(self._frame_snapshots[player.slot], self, dt)
            player.advance_animation(dt)
        self._update_revives(dt)
        self._update_chief_petting()
        for chief in self.chiefs:
            chief.update(self, dt)
            chief.advance_animation(dt)
        for enemy in list(self.enemies):
            enemy.update(self, dt)
            enemy.advance_animation(dt)
        self._resolve_actor_separation()
        for projectile in self.projectiles:
            projectile.update(self, dt)
        for pickup in self.ammo_pickups:
            pickup.update(self, dt)
        for pickup in self.super_butane_pickups:
            pickup.update(self, dt)
        for effect in self.effects:
            effect.update(dt)
        self._update_dave_flame_visuals(dt)

        self.enemies = [enemy for enemy in self.enemies if enemy.state != "dead" or enemy.state_clock < enemy.state_duration]
        self.projectiles = [projectile for projectile in self.projectiles if not projectile.spent]
        self.ammo_pickups = [pickup for pickup in self.ammo_pickups if not pickup.spent]
        self.super_butane_pickups = [pickup for pickup in self.super_butane_pickups if not pickup.spent]
        self.effects = [effect for effect in self.effects if effect.alive]
        self.stage_banner_timer = max(0.0, self.stage_banner_timer - dt)

        self._update_stage_content(dt, human_snapshot_by_slot)
        self._update_encounters(dt)
        self._update_camera(dt)
        if (
            self.state == "gameplay"
            and self.players
            and not self.development_unlimited_lives
            and all(player.state == "eliminated" for player in self.players)
        ):
            self.state = "game_over"
            self.complete_timer = 0.0
            self.audio_manager.stop_music(500)
            self.log_breadcrumb("game_over")

    @staticmethod
    def _anti_clone_order(kinds: Iterable[str]) -> list[str]:
        """Reorder a deterministic wave so adjacent silhouettes do not clone."""

        remaining = [str(kind) for kind in kinds]
        ordered: list[str] = []
        while remaining:
            previous = ordered[-1] if ordered else ""
            choice_index = next(
                (index for index, kind in enumerate(remaining) if kind != previous),
                0,
            )
            ordered.append(remaining.pop(choice_index))
        return ordered

    @classmethod
    def _focused_enemy_wave(cls, kinds: Iterable[str], limit: int) -> list[str]:
        """Keep a compact, varied encounter roster for hitbox-focused play.

        The first pass preserves authored role variety; only then does it use
        duplicates to fill the configured cap.  This keeps a four-enemy test
        wave legible without flattening every encounter into the same enemy.
        """

        source = [str(kind) for kind in kinds]
        if not source:
            return []
        limit = max(1, int(limit))
        selected: list[str] = []
        for kind in source:
            if kind not in selected:
                selected.append(kind)
            if len(selected) >= limit:
                return cls._anti_clone_order(selected)
        for kind in source:
            if len(selected) >= limit:
                break
            selected.append(kind)
        return cls._anti_clone_order(selected)

    def _update_stage_content(
        self,
        dt: float,
        snapshots_by_slot: dict[int, InputSnapshot],
    ) -> None:
        """Advance small authored route events and a safe optional branch.

        Events are deliberately lightweight: they add story, landmark, and
        environmental cadence without creating a hidden wall or stealing
        camera authority from the local human party.
        """

        del dt
        living_humans = [player for player in self.players if not player.is_cpu and player.alive]
        if not living_humans:
            return
        leader_x = max(player.x for player in living_humans)
        stage_width = max(float(LOGICAL_SIZE[0]), float(self.meta.get("stage_width", LOGICAL_SIZE[0])))

        events = self.runtime_chapter_content.get("environmental_events", ())
        if isinstance(events, list):
            while self._content_event_index < len(events):
                event = events[self._content_event_index]
                if not isinstance(event, dict):
                    self._content_event_index += 1
                    continue
                event_id = str(event.get("id", f"event_{self._content_event_index}"))
                trigger = stage_width * (0.22 + 0.27 * self._content_event_index)
                if leader_x < trigger:
                    break
                self._content_event_seen.add(event_id)
                self._content_event_index += 1
                label = event_id.replace("_", " ").upper()
                self.stage_banner = f"SET PIECE • {label}"
                self.stage_banner_timer = 1.0
                self.add_effect(
                    "text",
                    min(stage_width - 64.0, leader_x + 88.0),
                    188.0,
                    text=label,
                    color=(123, 224, 248),
                    duration=0.9,
                )
                self.log_breadcrumb(
                    "chapter_environment_event",
                    level_id=self.level_id,
                    content_event=event_id,
                )

        optional = self._content_optional
        if (
            optional is None
            or self._content_optional_active
            or self.encounter_active
            or str(optional.get("id", "")) in self._content_optional_completed
        ):
            self._content_optional_prompt = ""
            return
        if leader_x < self._content_optional_trigger_x:
            return
        title = str(optional.get("title", "SIDE ROUTE")).upper()
        self._content_optional_prompt = f"INTERACT • {title}"
        if not any("interact" in snapshot.pressed for snapshot in snapshots_by_slot.values()):
            return
        self._begin_optional_content(optional, leader_x)

    def _begin_optional_content(self, optional: dict[str, Any], leader_x: float) -> None:
        """Enter a short side encounter that always rejoins the main route."""

        wave = [
            str(kind)
            for group in optional.get("spawn_groups", ())
            if isinstance(group, dict)
            for kind in group.get("runtime_kinds", ())
        ]
        if not wave:
            return
        self._content_optional_active = True
        self._content_optional_prompt = ""
        self.encounter_active = True
        self.active_gate = min(
            float(self.meta["stage_width"]) - 12.0,
            max(leader_x + 160.0, self._content_optional_trigger_x + 160.0),
        )
        self._pending_camera_lock = None
        self.camera.clear_encounter_lock()
        self._post_clear_reinforcements.clear()
        self.spawn_queue = self._anti_clone_order(wave)
        self.spawn_timer = 0.0
        scaling = self.runtime_chapter_content.get("runtime_scaling", {})
        self._encounter_enemy_durability_scale = float(scaling.get("enemy_health_multiplier", 1.0))
        self._encounter_enemy_damage_scale = float(scaling.get("enemy_damage_multiplier", 1.0))
        self._encounter_enemy_score_scale = float(scaling.get("reward_multiplier", 1.0))
        self.stage_banner = f"OPTIONAL • {str(optional.get('title', 'SIDE ROUTE')).upper()}"
        self.stage_banner_timer = 1.45
        self.log_breadcrumb(
            "chapter_optional_started",
            level_id=self.level_id,
            optional_id=str(optional.get("id", "")),
            enemies=self.spawn_queue,
        )

    def _finish_optional_content(self) -> None:
        optional = self._content_optional
        if optional is None:
            return
        optional_id = str(optional.get("id", ""))
        self._content_optional_completed.add(optional_id)
        self._content_optional_active = False
        self.encounter_active = False
        self.active_gate = None
        self._pending_camera_lock = None
        self.camera.clear_encounter_lock()
        for player in self.players:
            if player.combat_active:
                player.health = min(player.max_health, player.health + 14.0)
                player.chief_meter = min(
                    float(self.data.get("chief", {}).get("command_meter_max", 100.0)),
                    player.chief_meter + 18.0,
                )
                player.score += 250
        self.add_effect(
            "text",
            LOGICAL_SIZE[0] * 0.5,
            128.0,
            text="SUPPLY CACHE • ROUTE REJOINED",
            color=(113, 255, 173),
            duration=1.25,
            world_space=False,
        )
        self.stage_banner = "OPTIONAL CLEAR • SUPPLIES FOUND"
        self.stage_banner_timer = 1.35
        self.log_breadcrumb("chapter_optional_cleared", level_id=self.level_id, optional_id=optional_id)

    def _advance_shelly_frenzy_cinematic(self, dt: float) -> None:
        """Expire the presentation-only focus card on the fixed 60 Hz clock."""

        cinematic = self.shelly_frenzy_cinematic
        if cinematic is None:
            return
        cinematic.advance(dt)
        if not cinematic.active:
            self.shelly_frenzy_cinematic = None

    def _advance_cpu_shelly_frenzy_reserve(
        self,
        player: Player,
        dt: float,
        normal_targets: list[Enemy],
    ) -> None:
        """Ready the CPU's next Chief frenzy only for a live street crowd.

        Two reserved activations give solo Dave a dependable companion moment
        during every normal multi-wave level. The reservation is intentionally
        conditional on a close-to-playable group rather than a timer that
        fires in empty travel space or against Couch alone.
        """

        if not player.is_cpu or player.character != "shelly":
            return
        cfg = self.data.get("companion_ai", {})
        goal = max(0, int(cfg.get("cpu_shelly_frenzy_goal", 2)))
        uses = self._cpu_shelly_frenzy_uses.get(player.slot, 0)
        rearm = max(0.0, self._cpu_shelly_frenzy_rearm.get(player.slot, 0.0) - dt)
        self._cpu_shelly_frenzy_rearm[player.slot] = rearm
        if uses >= goal:
            self._cpu_shelly_frenzy_charge[player.slot] = 0.0
            return

        group_minimum = max(2, int(cfg.get("cpu_shelly_frenzy_group_min", 3)))
        chief_busy = any(chief.frenzy > 0.0 for chief in self.chiefs)
        if len(normal_targets) < group_minimum or chief_busy or rearm > 0.0:
            self._cpu_shelly_frenzy_charge[player.slot] = 0.0
            return

        charge_seconds = max(0.0, float(cfg.get("cpu_shelly_frenzy_charge_seconds", 0.45)))
        charge = self._cpu_shelly_frenzy_charge.get(player.slot, 0.0) + max(0.0, dt)
        if charge < charge_seconds:
            self._cpu_shelly_frenzy_charge[player.slot] = charge
            return

        super_cost = float(self.data["players"]["global"]["super_cost"])
        if player.super_meter < super_cost:
            player.super_meter = super_cost
            self.add_effect(
                "text",
                player.x,
                player.y - 70.0,
                text="CHIEF READY!",
                color=(255, 227, 102),
                duration=0.72,
            )
            self.log_breadcrumb(
                "cpu_shelly_frenzy_reserved",
                slot=player.slot + 1,
                uses=uses,
                crowd=len(normal_targets),
            )
        # Keep the ready meter armed until the attack input actually starts;
        # otherwise a momentary range correction could consume a new reserve.
        self._cpu_shelly_frenzy_charge[player.slot] = charge_seconds

    def _cpu_snapshot(self, player: Player, dt: float) -> InputSnapshot:
        """Build a deterministic combat snapshot for a solo CPU companion."""

        cfg = self.data.get("companion_ai", {})
        player.cpu_action_cooldown = max(0.0, player.cpu_action_cooldown - dt)
        player.cpu_heavy_cooldown = max(0.0, player.cpu_heavy_cooldown - dt)
        player.cpu_dodge_cooldown = max(0.0, player.cpu_dodge_cooldown - dt)
        if not player.combat_active:
            return InputSnapshot()

        # A companion prioritizes reviving a human over dealing damage.
        downed_human = next(
            (candidate for candidate in self.players if not candidate.is_cpu and candidate.state == "downed"),
            None,
        )
        if downed_human is not None:
            dx, dy = downed_human.x - player.x, downed_human.y - player.y
            if abs(dx) <= 31.0 and abs(dy) <= 18.0:
                return InputSnapshot(held=frozenset({"interact"}))
            return InputSnapshot(
                move_x=clamp(dx / 34.0, -1.0, 1.0),
                move_y=clamp(dy / 24.0, -1.0, 1.0),
            )

        leader = next((candidate for candidate in self.players if not candidate.is_cpu and candidate.alive), None)
        nearest = self.nearest_enemy(player.x, player.y)
        engage_range = float(cfg.get("engage_range", 215.0))
        attack_range = float(cfg.get("attack_range", 38.0))
        depth_range = float(cfg.get("depth_range", 18.0))
        normal_targets = [
            enemy
            for enemy in self.enemies
            if enemy.targetable and enemy.kind != "couch"
        ]
        self._advance_cpu_shelly_frenzy_reserve(player, dt, normal_targets)

        # Retain the previous target through small distance-order changes. This
        # prevents the CPU companion from alternating direction between two
        # nearly equidistant enemies every simulation tick.
        retained = next(
            (
                enemy
                for enemy in self.enemies
                if enemy.targetable and enemy.enemy_id == player.cpu_target_enemy_id
            ),
            None,
        )
        target = retained or nearest
        if retained is not None:
            retain_distance = math.hypot(retained.x - player.x, (retained.y - player.y) * 1.6)
            if retain_distance > engage_range + float(cfg.get("target_hysteresis", 54.0)):
                target = nearest
        if target is not None and target.enemy_id != player.cpu_target_enemy_id:
            player.cpu_target_enemy_id = target.enemy_id
            lane_offset = float(cfg.get("lane_offset", 9.0))
            player.cpu_lane_offset = lane_offset if (target.enemy_id + player.slot) % 2 == 0 else -lane_offset
        elif target is None:
            player.cpu_target_enemy_id = -1
            player.cpu_lane_offset = 0.0

        # Never let companion combat pull the camera far away from the human.
        if leader is not None and math.hypot(player.x - leader.x, (player.y - leader.y) * 1.5) > 245.0:
            target = None
        if target is not None:
            target_distance = math.hypot(target.x - player.x, (target.y - player.y) * 1.6)
            if target_distance > engage_range and not self.encounter_active:
                target = None

        if target is not None:
            dx = target.x - player.x
            target_dy = target.y - player.y
            navigation_dy = target.y + player.cpu_lane_offset - player.y
            close = abs(dx) <= attack_range and abs(target_dy) <= depth_range
            # Once CPU Shelly commits her limited Super Butane, keep the
            # secondary input held until the bar is empty instead of emitting
            # one frame of flame and immediately cancelling it.
            if player.character == "shelly" and player.state == "propane" and player.super_butane_meter > 0.0:
                return InputSnapshot(held=frozenset({"secondary"}))
            if (
                target.state == "windup"
                and close
                and player.cpu_dodge_cooldown <= 0.0
                and player.state in {"idle", "walk"}
            ):
                player.cpu_dodge_cooldown = float(cfg.get("dodge_cooldown", 2.6))
                player.last_input_vector = normalized(-dx, -target_dy)
                return InputSnapshot(
                    move_x=player.last_input_vector[0],
                    move_y=player.last_input_vector[1],
                    held=frozenset({"dodge"}),
                    pressed=frozenset({"dodge"}),
                )

            ready_to_act = player.state in {"idle", "walk"} and player.cpu_action_cooldown <= 0.0
            targetable_count = sum(enemy.targetable for enemy in self.enemies)
            super_ready = player.super_meter >= float(self.data["players"]["global"]["super_cost"])
            cpu_shelly_group_minimum = max(2, int(cfg.get("cpu_shelly_frenzy_group_min", 3)))
            cpu_shelly_crowd_ready = (
                player.is_cpu
                and player.character == "shelly"
                and len(normal_targets) >= cpu_shelly_group_minimum
            )
            regular_super_appropriate = (
                cpu_shelly_crowd_ready
                if player.is_cpu and player.character == "shelly"
                else targetable_count >= int(cfg.get("super_min_enemies", 2))
            )
            super_appropriate = (
                regular_super_appropriate
                or (bool(cfg.get("super_on_boss", True)) and target.kind == "couch")
                or player.health <= player.max_health * float(cfg.get("super_low_health_ratio", 0.45))
            )
            propane_cfg = self.data.get("shelly_propane", {})
            chief_super_available = any(chief.frenzy <= 0.0 for chief in self.chiefs)
            super_range = (
                max(attack_range, float(propane_cfg.get("cpu_chief_super_range", 300.0)))
                if player.character == "shelly"
                else attack_range
            )
            if (
                ready_to_act
                and super_ready
                and super_appropriate
                and target_distance <= super_range
                and (player.character != "shelly" or chief_super_available)
            ):
                player.cpu_action_cooldown = 1.0
                self.log_breadcrumb(
                    "cpu_super_selected",
                    slot=player.slot + 1,
                    character=player.character,
                    enemies=targetable_count,
                    target=target.kind,
                )
                return InputSnapshot(held=frozenset({"super"}), pressed=frozenset({"super"}))

            propane_ready = (
                player.character == "shelly"
                and player.super_butane_meter >= float(propane_cfg.get("activation_minimum", 18.0))
            )
            propane_in_lane = abs(target_dy) <= float(propane_cfg.get("cpu_lane_tolerance", 42.0))
            propane_in_range = (
                float(propane_cfg.get("cpu_min_range", 58.0))
                <= abs(dx)
                <= float(propane_cfg.get("cpu_max_range", 310.0))
            )
            if ready_to_act and propane_ready and propane_in_lane and propane_in_range:
                player.facing = 1 if target.x >= player.x else -1
                player.cpu_action_cooldown = float(propane_cfg.get("cpu_action_cooldown", 0.85))
                self.log_breadcrumb(
                    "cpu_propane_selected",
                    slot=player.slot + 1,
                    enemy_id=target.enemy_id,
                    butane=round(player.super_butane_meter, 1),
                )
                return InputSnapshot(held=frozenset({"secondary"}), pressed=frozenset({"secondary"}))

            bb_cfg = self.data.get("bb_gun", {})
            bb_ready = (
                player.character == "black_dave"
                and player.bb_ammo > 0
                and player.bb_cooldown <= 0.0
            )
            bb_hit_depth = float(bb_cfg.get("lane_tolerance", 10.0)) + float(
                self.data["engine"]["physics"].get("enemy_radius_depth", 7.0)
            )
            bb_in_lane = abs(target.y - player.y) <= min(
                float(bb_cfg.get("cpu_lane_tolerance", bb_hit_depth)),
                bb_hit_depth,
            )
            bb_in_range = (
                float(bb_cfg.get("cpu_min_range", 62.0))
                <= abs(target.x - player.x)
                <= float(bb_cfg.get("cpu_max_range", 255.0))
            )
            if ready_to_act and bb_ready and bb_in_lane and bb_in_range:
                player.facing = 1 if target.x >= player.x else -1
                player.cpu_action_cooldown = float(bb_cfg.get("cpu_action_cooldown", 0.45))
                self.log_breadcrumb(
                    "cpu_bb_gun_selected",
                    slot=player.slot + 1,
                    enemy_id=target.enemy_id,
                    ammo=player.bb_ammo,
                )
                return InputSnapshot(held=frozenset({"secondary"}), pressed=frozenset({"secondary"}))

            chief_cfg = self.data.get("chief", {})
            chief_ready = player.chief_meter >= float(chief_cfg.get("command_cost", 50.0))
            chief_available = any(
                chief.frenzy <= 0.0 and chief.command_caller is None
                for chief in self.chiefs
            )
            if (
                ready_to_act
                and chief_ready
                and chief_available
                and target_distance <= float(cfg.get("chief_command_range", 205.0))
            ):
                player.cpu_action_cooldown = float(cfg.get("chief_command_cooldown", 0.75))
                return InputSnapshot(held=frozenset({"chief"}), pressed=frozenset({"chief"}))

            if close:
                if player.state == "light" and player.cpu_action_cooldown <= 0.0:
                    player.cpu_action_cooldown = float(cfg.get("light_cooldown", 0.20))
                    return InputSnapshot(held=frozenset({"light"}), pressed=frozenset({"light"}))
                if player.state in {"idle", "walk"} and player.cpu_action_cooldown <= 0.0:
                    action = "light"
                    if player.cpu_heavy_cooldown <= 0.0:
                        action = "heavy"
                        player.cpu_heavy_cooldown = float(cfg.get("heavy_cooldown", 1.75))
                        player.cpu_action_cooldown = 0.62
                    else:
                        player.cpu_action_cooldown = float(cfg.get("light_cooldown", 0.20))
                    return InputSnapshot(held=frozenset({action}), pressed=frozenset({action}))
                return InputSnapshot()

            move_x = 0.0 if abs(dx) <= attack_range * 0.82 else clamp(dx / 48.0, -1.0, 1.0)
            move_y = 0.0 if abs(navigation_dy) <= depth_range * 0.58 else clamp(navigation_dy / 28.0, -1.0, 1.0)
            return InputSnapshot(move_x=move_x, move_y=move_y)

        if leader is None:
            return InputSnapshot()
        follow_distance = float(cfg.get("follow_distance", 47.0))
        follow_x = leader.x - leader.facing * follow_distance
        follow_y = leader.y + float(cfg.get("follow_depth_offset", 18.0))
        dx, dy = follow_x - player.x, follow_y - player.y
        if abs(dx) + abs(dy) <= 10.0:
            player.cpu_idle_time += dt
            return InputSnapshot()
        player.cpu_idle_time = 0.0
        return InputSnapshot(
            move_x=0.0 if abs(dx) < 9.0 else clamp(dx / 42.0, -1.0, 1.0),
            move_y=0.0 if abs(dy) < 7.0 else clamp(dy / 26.0, -1.0, 1.0),
        )

    def _update_chief_petting(self) -> None:
        """Let Dave pet Chief on E and during occasional safe idle moments."""

        idle_seconds = float(self.data.get("companion_ai", {}).get("pet_idle_seconds", 3.0))
        dave = next((player for player in self.players if player.character == "black_dave" and player.combat_active), None)
        if dave is None:
            return
        for chief in self.chiefs:
            if chief.frenzy > 0.0 or chief.pet_timer > 0.0:
                continue
            close = abs(chief.x - dave.x) <= 48.0 and abs(chief.y - dave.y) <= 23.0
            if not close:
                continue
            danger = any(
                enemy.targetable
                and min(
                    math.hypot(enemy.x - dave.x, (enemy.y - dave.y) * 1.5),
                    math.hypot(enemy.x - chief.x, (enemy.y - chief.y) * 1.5),
                ) < 125.0
                for enemy in self.enemies
            )
            if danger:
                continue
            snapshot = self._frame_snapshots.get(dave.slot, InputSnapshot())
            requested = "interact" in snapshot.pressed or "interact" in snapshot.held
            calm_moment = dave.idle_time >= idle_seconds and chief.pet_cooldown <= 0.0
            if requested or calm_moment:
                chief.start_pet(dave, self)
                break

    def alert_chief(self, threatened_player: Player, source: Any) -> None:
        """Have Chief immediately respond when Dave or Shelly is struck."""

        if threatened_player.character not in {"black_dave", "shelly"}:
            return
        for chief in self.chiefs:
            chief.protect(source)

    def fire_secondary(self, caller: Player, *, feedback: bool = True) -> bool:
        """Dispatch the dedicated G/LT secondary by the active hero."""

        if caller.character == "black_dave":
            return self.fire_bb_gun(caller, feedback=feedback)
        if caller.character == "shelly":
            return self.start_propane(caller, feedback=feedback)
        return False

    def start_propane(self, caller: Player, *, feedback: bool = True) -> bool:
        """Start Shelly's held, long-range Super Butane flamethrower."""

        cfg = self.data.get("shelly_propane", {})
        if not caller.combat_active:
            self._propane_rejected(caller, "CAN'T FLAME", "inactive", feedback)
            return False
        if caller.character != "shelly":
            self._propane_rejected(caller, "SHELLY ONLY", "character", feedback)
            return False
        if caller.state == "propane":
            return True
        required = float(cfg.get("activation_minimum", 18.0))
        if caller.super_butane_meter + 1e-6 < required:
            self._propane_rejected(caller, "BUTANE LOW", "meter", feedback)
            return False
        if caller.state not in {"idle", "walk"}:
            self._propane_rejected(caller, "CAN'T FLAME", "state", feedback)
            return False

        caller.propane_tick = 0.0
        caller.set_state("propane")
        self.add_effect("text", caller.x, caller.y - 56, text="PROPANE!", color=(255, 177, 72), duration=0.45)
        self.add_effect("flame", caller.x + caller.facing * 24.0, caller.y - 30.0, color=(255, 146, 50), radius=24, duration=0.16)
        self.audio.play("heavy")
        self.log_breadcrumb(
            "propane_started",
            player=caller.slot + 1,
            butane=round(caller.super_butane_meter, 1),
            facing=caller.facing,
        )
        return True

    def _propane_rejected(
        self,
        caller: Player,
        label: str,
        reason: str,
        feedback: bool,
    ) -> None:
        if feedback:
            self.add_effect("text", caller.x, caller.y - 54, text=label, color=(255, 176, 81), duration=0.55)
            self.audio.play("menu")
        self.log_breadcrumb(
            "propane_rejected",
            player=caller.slot + 1,
            character=caller.character,
            reason=reason,
            butane=round(caller.super_butane_meter, 1),
        )

    def apply_propane_flame(self, player: Player) -> int:
        """Apply one expensive flame tick to all enemies in Shelly's lane."""

        cfg = self.data.get("shelly_propane", {})
        flame_range = max(1.0, float(cfg.get("range", 310.0)))
        lane = max(1.0, float(cfg.get("lane_tolerance", 42.0)))
        damage = max(0.0, float(cfg.get("damage_per_tick", 20.0)))
        hitstun = max(0.0, float(cfg.get("hitstun", 0.16)))
        knockback = max(0.0, float(cfg.get("knockback", 16.0)))
        targets = [
            enemy
            for enemy in self.enemies
            if enemy.targetable
            and 0.0 <= (enemy.x - player.x) * player.facing <= flame_range
            and abs(enemy.y - player.y) <= lane
        ]
        for enemy in targets:
            enemy.take_damage(
                damage,
                self,
                player,
                hitstun=hitstun,
                knockback=knockback,
                burn=True,
            )
        # Three short-lived world-space fire puffs make the continuous lane
        # legible without introducing a second projectile/hitbox system.
        for fraction, radius in ((0.10, 20.0), (0.46, 28.0), (0.82, 24.0)):
            self.add_effect(
                "flame",
                player.x + player.facing * flame_range * fraction,
                player.y - 28.0,
                color=(255, 128, 40),
                radius=radius,
                duration=0.12,
            )
        return len(targets)

    def fire_bb_gun(self, caller: Player, *, feedback: bool = True) -> bool:
        """Fire Dave's finite-ammo, straight-lane BB gun."""

        cfg = self.data.get("bb_gun", {})
        if not caller.combat_active:
            self._bb_gun_rejected(caller, "CAN'T FIRE", "inactive", feedback)
            return False
        if caller.character != "black_dave":
            self._bb_gun_rejected(caller, "DAVE ONLY", "character", feedback)
            return False
        if caller.bb_ammo <= 0:
            self._bb_gun_rejected(caller, "OUT OF BBs", "ammo", feedback)
            return False
        if caller.bb_cooldown > 0.0:
            self._bb_gun_rejected(caller, "BB NOT READY", "cooldown", feedback)
            return False

        speed = max(1.0, float(cfg.get("speed", 420.0)))
        distance = max(1.0, float(cfg.get("range", 500.0)))
        caller.bb_ammo -= 1
        caller.bb_cooldown = max(0.0, float(cfg.get("cooldown", 0.38)))
        if caller.state in {"idle", "walk"}:
            caller.set_state("ranged", float(cfg.get("animation_seconds", 0.26)))
        muzzle_x = caller.x + caller.facing * float(cfg.get("muzzle_offset", 22.0))
        shot_height = float(cfg.get("shot_height", 28.0))
        self.projectiles.append(Projectile(
            x=muzzle_x,
            y=caller.y,
            z=shot_height,
            vx=caller.facing * speed,
            vy=0.0,
            vz=0.0,
            damage=float(cfg.get("damage", 12.0)),
            owner_team="player",
            kind="bb",
            ttl=distance / speed,
            owner_player=caller,
            lane_tolerance=float(cfg.get("lane_tolerance", 10.0)),
            hitstun=float(cfg.get("hitstun", 0.20)),
            knockback=float(cfg.get("knockback", 10.0)),
        ))
        self.add_effect(
            "impact",
            muzzle_x,
            caller.y - shot_height,
            color=(213, 244, 255),
            radius=8,
            duration=0.12,
        )
        self.audio.play("bb_gun")
        self.log_breadcrumb(
            "bb_gun_fired",
            player=caller.slot + 1,
            ammo=caller.bb_ammo,
            facing=caller.facing,
        )
        return True

    def _bb_gun_rejected(
        self,
        caller: Player,
        label: str,
        reason: str,
        feedback: bool,
    ) -> None:
        if feedback:
            self.add_effect(
                "text",
                caller.x,
                caller.y - 54,
                text=label,
                color=(140, 219, 255),
                duration=0.55,
            )
            self.audio.play("menu")
        self.log_breadcrumb(
            "bb_gun_rejected",
            player=caller.slot + 1,
            character=caller.character,
            reason=reason,
            ammo=caller.bb_ammo,
        )

    def bb_projectile_hit(self, projectile: Projectile, old_x: float, new_x: float) -> bool:
        """Resolve the nearest enemy crossed by one straight BB segment."""

        cfg = self.data.get("bb_gun", {})
        radius_x = float(cfg.get("hit_radius_x", 14.0))
        enemy_depth = float(self.data["engine"]["physics"].get("enemy_radius_depth", 7.0))
        segment_left = min(old_x, new_x) - radius_x
        segment_right = max(old_x, new_x) + radius_x
        candidates = [
            enemy
            for enemy in self.enemies
            if enemy.targetable
            and segment_left <= enemy.x <= segment_right
            and abs(enemy.y - projectile.y) <= projectile.lane_tolerance + enemy_depth
        ]
        if not candidates:
            return False
        target = min(candidates, key=lambda enemy: (abs(enemy.x - old_x), enemy.enemy_id))
        landed = target.take_damage(
            projectile.damage,
            self,
            projectile.owner_player,
            hitstun=projectile.hitstun,
            knockback=projectile.knockback,
        )
        if landed:
            self.log_breadcrumb(
                "bb_gun_hit",
                player=(projectile.owner_player.slot + 1 if projectile.owner_player else None),
                enemy=target.kind,
                enemy_id=target.enemy_id,
                damage=projectile.damage,
            )
        return landed

    def _bb_drop_interval(self, drop_index: int) -> int:
        """Return a deterministic interval inside the configured KO window."""

        cfg = self.data.get("bb_gun", {})
        low = max(1, int(cfg.get("drop_ko_min", 2)))
        high = max(low, int(cfg.get("drop_ko_max", 4)))
        span = high - low + 1
        offset = (max(0, int(drop_index)) * 2 + max(0, int(drop_index)) // span) % span
        return low + offset

    def _register_bb_eligible_ko(self, enemy: Enemy) -> None:
        cfg = self.data.get("bb_gun", {})
        if not any(player.character == "black_dave" for player in self.players):
            return
        excluded = {str(kind) for kind in cfg.get("drop_excluded_kinds", ("couch",))}
        if enemy.kind in excluded:
            return
        self.bb_eligible_kos += 1
        if self.bb_next_drop_at <= 0:
            self.bb_next_drop_at = self._bb_drop_interval(self.bb_drop_index)
        if self.bb_eligible_kos < self.bb_next_drop_at:
            return

        amount = max(1, int(cfg.get("pickup_amount", 3)))
        self.ammo_pickups.append(AmmoPickup(
            x=enemy.x,
            y=enemy.y,
            amount=amount,
            ttl=max(0.1, float(cfg.get("pickup_ttl", 18.0))),
        ))
        self.bb_drop_index += 1
        self.bb_next_drop_at += self._bb_drop_interval(self.bb_drop_index)
        self.add_effect("text", enemy.x, enemy.y - 38, text="BB AMMO!", color=(124, 224, 255), duration=0.75)
        self.log_breadcrumb(
            "bb_ammo_dropped",
            enemy_id=enemy.enemy_id,
            amount=amount,
            eligible_kos=self.bb_eligible_kos,
            next_drop_at=self.bb_next_drop_at,
        )

    def collect_bb_ammo(self, pickup: AmmoPickup) -> bool:
        """Collect a non-solid pickup with the closest eligible Dave."""

        cfg = self.data.get("bb_gun", {})
        maximum = max(0, int(cfg.get("max_ammo", 6)))
        radius_x = float(cfg.get("pickup_radius_x", 23.0))
        radius_depth = float(cfg.get("pickup_radius_depth", 15.0))
        candidates = [
            player
            for player in self.players
            if player.combat_active
            and player.character == "black_dave"
            and player.bb_ammo < maximum
            and abs(player.x - pickup.x) <= radius_x
            and abs(player.y - pickup.y) <= radius_depth
        ]
        if not candidates:
            return False
        collector = min(
            candidates,
            key=lambda player: (
                abs(player.x - pickup.x) + abs(player.y - pickup.y) * 1.5,
                player.slot,
            ),
        )
        before = collector.bb_ammo
        collector.bb_ammo = min(maximum, collector.bb_ammo + max(0, pickup.amount))
        pickup.spent = True
        self.add_effect("text", collector.x, collector.y - 54, text=f"BB +{collector.bb_ammo - before}", color=(129, 232, 255), duration=0.65)
        self.audio.play("pickup")
        self.log_breadcrumb(
            "bb_ammo_collected",
            player=collector.slot + 1,
            gained=collector.bb_ammo - before,
            ammo=collector.bb_ammo,
        )
        return True

    def _super_butane_drop_interval(self, drop_index: int) -> int:
        """Return a deterministic 2-3 KO interval for Shelly's fuel drops."""

        cfg = self.data.get("shelly_propane", {})
        low = max(1, int(cfg.get("drop_ko_min", 2)))
        high = max(low, int(cfg.get("drop_ko_max", 3)))
        span = high - low + 1
        # Alternate the configured 2-3 KO window so fuel remains predictably
        # regular without being granted after every defeated enemy.
        offset = max(0, int(drop_index)) % span
        return low + offset

    def _register_super_butane_eligible_ko(self, enemy: Enemy) -> None:
        """Spawn readable Super Butane drops independently from Dave's BB tins."""

        cfg = self.data.get("shelly_propane", {})
        if not any(player.character == "shelly" for player in self.players):
            return
        excluded = {str(kind) for kind in cfg.get("drop_excluded_kinds", ("couch",))}
        if enemy.kind in excluded:
            return
        self.super_butane_eligible_kos += 1
        if self.super_butane_next_drop_at <= 0:
            self.super_butane_next_drop_at = self._super_butane_drop_interval(self.super_butane_drop_index)
        if self.super_butane_eligible_kos < self.super_butane_next_drop_at:
            return

        amount = max(1.0, float(cfg.get("pickup_amount", 52.0)))
        self.super_butane_pickups.append(SuperButanePickup(
            x=enemy.x,
            y=enemy.y,
            amount=amount,
            ttl=max(0.1, float(cfg.get("pickup_ttl", 18.0))),
        ))
        self.super_butane_drop_index += 1
        self.super_butane_next_drop_at += self._super_butane_drop_interval(self.super_butane_drop_index)
        self.add_effect("text", enemy.x, enemy.y - 38, text="SUPER BUTANE!", color=(255, 178, 73), duration=0.75)
        self.log_breadcrumb(
            "super_butane_dropped",
            enemy_id=enemy.enemy_id,
            amount=round(amount, 1),
            eligible_kos=self.super_butane_eligible_kos,
            next_drop_at=self.super_butane_next_drop_at,
        )

    def collect_super_butane(self, pickup: SuperButanePickup) -> bool:
        """Collect a non-solid Super Butane drop with the closest eligible Shelly."""

        cfg = self.data.get("shelly_propane", {})
        maximum = max(0.0, float(cfg.get("meter_max", 100.0)))
        radius_x = float(cfg.get("pickup_radius_x", 24.0))
        radius_depth = float(cfg.get("pickup_radius_depth", 16.0))
        candidates = [
            player
            for player in self.players
            if player.combat_active
            and player.character == "shelly"
            and player.super_butane_meter < maximum
            and abs(player.x - pickup.x) <= radius_x
            and abs(player.y - pickup.y) <= radius_depth
        ]
        if not candidates:
            return False
        collector = min(
            candidates,
            key=lambda player: (
                abs(player.x - pickup.x) + abs(player.y - pickup.y) * 1.5,
                player.slot,
            ),
        )
        before = collector.super_butane_meter
        collector.super_butane_meter = min(maximum, collector.super_butane_meter + max(0.0, pickup.amount))
        pickup.spent = True
        gained = collector.super_butane_meter - before
        self.add_effect("text", collector.x, collector.y - 54, text=f"BUTANE +{int(round(gained))}", color=(255, 182, 76), duration=0.65)
        self.audio.play("pickup")
        self.log_breadcrumb(
            "super_butane_collected",
            player=collector.slot + 1,
            gained=round(gained, 1),
            butane=round(collector.super_butane_meter, 1),
        )
        return True

    def command_chief(self, caller: Player, *, feedback: bool = True) -> bool:
        """Spend only the caller's meter and sic Chief on their nearest foe."""

        cfg = self.data.get("chief", {})
        cost = float(cfg.get("command_cost", 50.0))
        if not caller.combat_active:
            return False
        if caller.chief_meter + 1e-6 < cost:
            if feedback:
                self._chief_command_rejected(caller, "METER LOW", "meter")
            return False
        target = self.nearest_enemy(caller.x, caller.y)
        if target is None:
            if feedback:
                self._chief_command_rejected(caller, "NO TARGET", "target")
            return False
        if not self.chiefs:
            if feedback:
                self._chief_command_rejected(caller, "CHIEF AWAY", "missing")
            return False
        chief = min(
            self.chiefs,
            key=lambda candidate: abs(candidate.x - caller.x) + abs(candidate.y - caller.y) * 1.5,
        )
        if chief.frenzy > 0.0:
            if feedback:
                self._chief_command_rejected(caller, "CHIEF FRENZY", "frenzy")
            return False
        if self._chief_needs_recall(chief, caller, urgent=True):
            self.recall_chief_near(chief, caller, reason="command")
        previous_caller = chief.command_caller
        if not chief.start_command(caller, target, self):
            if feedback:
                self._chief_command_rejected(caller, "NO TARGET", "target_changed")
            return False
        # A retarget transfers the one reserved command charge instead of
        # making another player pay for a bite that Chief will never deliver.
        if previous_caller is not None:
            maximum = float(cfg.get("command_meter_max", 100.0))
            previous_caller.chief_meter = min(maximum, previous_caller.chief_meter + cost)
        caller.chief_meter = max(0.0, caller.chief_meter - cost)
        self.audio.play_character(caller.character, "chief")
        return True

    def _chief_needs_recall(self, chief: Chief, anchor: Player, *, urgent: bool) -> bool:
        """Return whether Chief is off-camera or too far from the active party."""

        cfg = self.data.get("chief", {})
        if urgent:
            margin = float(cfg.get("offscreen_recall_margin", 80.0))
            distance_limit = float(cfg.get("command_recall_distance", 460.0))
        else:
            margin = float(cfg.get("watchdog_recall_margin", 160.0))
            distance_limit = float(cfg.get("watchdog_recall_distance", 560.0))
        offscreen = (
            chief.x < self.camera_x - margin
            or chief.x > self.camera_x + float(LOGICAL_SIZE[0]) + margin
        )
        party_distance = math.hypot(chief.x - anchor.x, (chief.y - anchor.y) * 1.5)
        return offscreen or party_distance > distance_limit

    def recall_chief_near(self, chief: Chief, anchor: Player, *, reason: str) -> None:
        """Place Chief at a safe walkable point near a caller or party anchor."""

        _, half_depth, _, _ = self._actor_extents(chief)
        offsets = (
            (-anchor.facing * 30.0, 10.0),
            (anchor.facing * 30.0, 10.0),
            (-anchor.facing * 24.0, -14.0),
            (anchor.facing * 24.0, -14.0),
        )
        candidates: list[tuple[float, WorldPoint]] = []
        for index, (offset_x, offset_depth) in enumerate(offsets):
            desired = WorldPoint(anchor.x + offset_x, anchor.y + offset_depth)
            point = self.stage_geometry.clamp_to_walkable(desired, radius=half_depth)
            displacement = math.hypot(point.x - desired.x, point.depth - desired.depth)
            candidates.append((displacement + index * 0.001, point))
        point = min(candidates, key=lambda item: item[0])[1]
        chief.x = point.x
        chief.y = point.depth
        chief.state = "follow"
        chief.pursuit_timer = 0.0
        chief.protect_enemy_id = -1
        if chief.pet_partner is not None and chief.pet_partner.state == "pet":
            chief.pet_partner.set_state("idle")
        chief.pet_partner = None
        chief.pet_timer = 0.0
        self.log_breadcrumb(
            "chief_recalled",
            reason=reason,
            player=anchor.slot + 1,
            x=round(chief.x, 1),
            y=round(chief.y, 1),
        )

    def keep_chief_with_party(self, chief: Chief) -> None:
        """Recover a stranded Chief without interrupting valid on-screen play."""

        anchor = chief.command_caller if chief.command_caller is not None and chief.command_caller.combat_active else None
        if anchor is None and chief.owner.combat_active:
            anchor = chief.owner
        if anchor is None:
            anchor = self.nearest_player(chief.x, chief.y)
        if anchor is not None and self._chief_needs_recall(chief, anchor, urgent=False):
            self.recall_chief_near(chief, anchor, reason="offscreen_watchdog")

    def _chief_command_rejected(self, caller: Player, label: str, reason: str) -> None:
        """Make an unavailable command visible instead of silently ignoring it."""

        self.add_effect("text", caller.x, caller.y - 54, text=label, color=(255, 183, 83), duration=0.55)
        self.audio.play("menu")
        self.log_breadcrumb("chief_command_rejected", player=caller.slot + 1, reason=reason)

    def player_under_attack(self, player: Player) -> bool:
        """Return whether an enemy is actively telegraphing/charging at player."""

        return any(
            enemy.targetable
            and enemy.target_slot == player.slot
            and enemy.state in {"windup", "charge"}
            for enemy in self.enemies
        )

    def _actor_extents(self, actor: Any) -> tuple[float, float, float, float]:
        """Return half width, half depth, body height, and push mass."""

        physics = self.data["engine"]["physics"]
        if isinstance(actor, Player):
            return (
                float(physics["player_radius_x"]),
                float(physics["player_radius_depth"]),
                52.0,
                1.2,
            )
        if isinstance(actor, Enemy):
            if actor.kind == "couch":
                return (
                    float(physics["boss_radius_x"]),
                    float(physics["boss_radius_depth"]),
                    58.0,
                    3.2,
                )
            return (
                float(physics["enemy_radius_x"]),
                float(physics["enemy_radius_depth"]),
                48.0,
                1.0,
            )
        return (
            float(physics["chief_radius_x"]),
            float(physics["chief_radius_depth"]),
            25.0,
            0.65,
        )

    def move_actor(self, actor: Any, dx: float, ddepth: float) -> tuple[float, float]:
        """Move any fighter through shared rails and physical scenery."""

        start_x = float(actor.x)
        start_depth = float(actor.y)
        half_width, half_depth, _, _ = self._actor_extents(actor)
        elevation = float(getattr(actor, "z", 0.0))
        start = WorldPoint(float(actor.x), float(actor.y), elevation)
        moved = self.stage_geometry.resolve_move(
            start,
            float(dx),
            float(ddepth),
            radius=half_depth,
            max_step=5.0,
        )
        x = clamp(moved.x, half_width, float(self.meta["stage_width"]) - half_width)

        if isinstance(actor, Player):
            # Players remain visible; CPU companions and co-op partners cannot
            # drag camera authority away from the human-controlled group.
            x = clamp(x, self.camera_x + half_width, self.camera_x + LOGICAL_SIZE[0] - half_width)
            if self.active_gate is not None:
                x = min(x, self.active_gate - half_width)
            humans = [player for player in self.players if not player.is_cpu and player.alive and player is not actor]
            if humans:
                tether = float(self.data["engine"]["camera"].get("group_tether_width", 552.0))
                x = clamp(x, max(player.x for player in humans) - tether, min(player.x for player in humans) + tether)

        actor.x = x
        actor.y = moved.depth
        return actor.x - start_x, actor.y - start_depth

    def _navigation_blocker(self, enemy: Enemy, target: Player) -> RectObstacle | None:
        """Return the first scenery footprint crossing an enemy's direct path."""

        dx = target.x - enemy.x
        if abs(dx) <= 1.0:
            return None
        half_width, half_depth, _, _ = self._actor_extents(enemy)
        direction = 1.0 if dx > 0.0 else -1.0
        candidates: list[tuple[float, str, RectObstacle]] = []
        for obstacle in self.stage_geometry.obstacles:
            near_x = obstacle.x_min - half_width if direction > 0.0 else obstacle.x_max + half_width
            if direction > 0.0:
                if not enemy.x <= near_x <= target.x:
                    continue
            elif not target.x <= near_x <= enemy.x:
                continue
            centre_x = (obstacle.x_min + obstacle.x_max) * 0.5
            amount = clamp((centre_x - enemy.x) / dx, 0.0, 1.0)
            path_depth = enemy.y + (target.y - enemy.y) * amount
            if obstacle.depth_min - half_depth <= path_depth <= obstacle.depth_max + half_depth:
                candidates.append((abs(near_x - enemy.x), obstacle.name, obstacle))
        return min(candidates, key=lambda item: (item[0], item[1]))[2] if candidates else None

    def _choose_enemy_detour_depth(self, enemy: Enemy, target: Player, obstacle: RectObstacle) -> float | None:
        """Choose a stable, deterministic lane on either side of a prop."""

        half_width, half_depth, _, _ = self._actor_extents(enemy)
        clearance = float(self.data["engine"]["physics"].get("enemy_obstacle_clearance", 3.0))
        direction = 1.0 if target.x >= enemy.x else -1.0
        probe_x = (
            obstacle.x_min - half_width - 1.0
            if direction > 0.0
            else obstacle.x_max + half_width + 1.0
        )
        depths = (
            obstacle.depth_min - half_depth - clearance,
            obstacle.depth_max + half_depth + clearance,
        )
        viable = [
            depth
            for depth in depths
            if self.stage_geometry.is_walkable(WorldPoint(probe_x, depth), radius=half_depth)
        ]
        if not viable:
            return None
        return min(
            viable,
            key=lambda depth: (abs(depth - enemy.y) + abs(depth - target.y) * 0.2, depth),
        )

    def move_enemy_toward(
        self,
        enemy: Enemy,
        target: Player,
        dx: float,
        ddepth: float,
        dt: float,
    ) -> tuple[float, float]:
        """Apply direct movement plus a latched obstacle detour lane."""

        obstacle = next(
            (item for item in self.stage_geometry.obstacles if item.name == enemy.nav_detour_obstacle),
            None,
        )
        direction = 1.0 if target.x >= enemy.x else -1.0
        if obstacle is not None:
            half_width, _, _, _ = self._actor_extents(enemy)
            passed = (
                enemy.x > obstacle.x_max + half_width
                if direction > 0.0
                else enemy.x < obstacle.x_min - half_width
            )
            if passed:
                enemy.nav_detour_obstacle = ""
                enemy.nav_detour_depth = None
                obstacle = None

        if obstacle is None:
            blocker = self._navigation_blocker(enemy, target)
            if blocker is not None:
                detour_depth = self._choose_enemy_detour_depth(enemy, target, blocker)
                if detour_depth is not None:
                    enemy.nav_detour_obstacle = blocker.name
                    enemy.nav_detour_depth = detour_depth
                    obstacle = blocker

        if obstacle is not None and enemy.nav_detour_depth is not None:
            lane_delta = enemy.nav_detour_depth - enemy.y
            lane_dead_zone = float(self.data["engine"]["physics"].get("enemy_detour_dead_zone", 1.5))
            if abs(lane_delta) > lane_dead_zone:
                speed = float(enemy.stats["speed"])
                ddepth = clamp(lane_delta, -1.0, 1.0) * speed * 0.72 * dt
            else:
                ddepth = 0.0

        return self.move_actor(enemy, dx, ddepth)

    def _resolve_actor_separation(self) -> None:
        """Keep fighters apart while companion Chief navigates non-blockingly."""

        actors: list[tuple[tuple[str, int], Any]] = []
        actors.extend((("player", player.slot), player) for player in self.players if player.combat_active)
        actors.extend((("enemy", enemy.enemy_id), enemy) for enemy in self.enemies if enemy.targetable)
        if len(actors) < 2:
            return

        bodies: list[PushBody] = []
        by_id: dict[tuple[str, int], Any] = {}
        for entity_id, actor in actors:
            half_width, half_depth, height, mass = self._actor_extents(actor)
            is_player = entity_id[0] == "player"
            bodies.append(PushBody(
                entity_id,
                float(actor.x),
                float(actor.y),
                elevation=float(getattr(actor, "z", 0.0)),
                half_width=half_width,
                half_depth=half_depth,
                height=height,
                mass=mass,
                # Heroes pass freely through allied heroes. Enemies still
                # maintain contact against heroes and other enemies.
                layer=0x1 if is_player else 0x2,
                mask=0x2 if is_player else 0x3,
            ))
            by_id[entity_id] = actor

        physics = self.data["engine"]["physics"]
        separate_push_bodies(
            bodies,
            crowd_spacing=1.0,
            bounds=self._combat_bounds,
            obstacles=self._combat_obstacles,
            iterations=max(6, int(physics.get("separation_iterations", 8))),
            cell_size=float(physics.get("spatial_cell_size", 72.0)),
        )
        for body in bodies:
            actor = by_id[body.entity_id]
            self.move_actor(actor, body.x - float(actor.x), body.depth - float(actor.y))

    def _enemy_hurtboxes(self) -> tuple[HurtBox, ...]:
        boxes: list[HurtBox] = []
        for enemy in self.enemies:
            if not enemy.targetable:
                continue
            half_width, half_depth, height, _ = self._actor_extents(enemy)
            tags = {enemy.kind}
            if enemy.state == "down":
                tags.add("downed")
            if bool(enemy.stats.get("armor", False)):
                tags.add("armor")
            if bool(enemy.stats.get("grab_immune", False)) or enemy.kind == "couch":
                tags.add("grab_immune")
            boxes.append(HurtBox(
                ("enemy", enemy.enemy_id),
                "enemy",
                enemy.x,
                enemy.y,
                half_width=half_width,
                half_depth=half_depth,
                height=height,
                vulnerable=enemy.wake_invulnerable <= 0.0,
                grounded=True,
                tags=frozenset(tags),
                sweep_from_x=enemy.hitbox_sweep_x,
                sweep_from_depth=enemy.hitbox_sweep_y,
            ))
        return tuple(boxes)

    def _player_hurtboxes(self) -> tuple[HurtBox, ...]:
        boxes: list[HurtBox] = []
        for player in self.players:
            if player.state in {"dead", "eliminated"}:
                continue
            half_width, half_depth, height, _ = self._actor_extents(player)
            tags = {player.character}
            if player.state == "downed":
                tags.add("downed")
            boxes.append(HurtBox(
                ("player", player.slot),
                "player",
                player.x,
                player.y,
                elevation=player.z,
                half_width=half_width,
                half_depth=half_depth,
                height=height,
                vulnerable=player.invulnerable <= 0.0,
                grounded=player.z <= 0.5,
                tags=frozenset(tags),
                sweep_from_x=player.hitbox_sweep_x,
                sweep_from_depth=player.hitbox_sweep_y,
            ))
        return tuple(boxes)

    def _record_attack_report(self, attack: HitBox, report: AttackQueryReport) -> None:
        """Keep the most recent authoritative query visible to F3 diagnostics."""

        self._debug_last_attack = attack
        self._debug_last_contacts = tuple(report.results)
        self._debug_last_evaluations = tuple(report.evaluations)
        self._debug_last_query_frame = self.frame
        preferred_rejection = next(
            (
                rejection
                for rejection in report.rejected
                if rejection.reason is AttackRejectionReason.TARGET_CAP
            ),
            report.rejected[0] if report.rejected else None,
        )
        if preferred_rejection is None:
            self._debug_last_rejection = "NONE"
        elif preferred_rejection.reason is None:
            self._debug_last_rejection = "predicate"
        else:
            self._debug_last_rejection = preferred_rejection.reason.value
        if report.results:
            self._debug_last_result = f"HIT {report.results[0].target_id}"
        elif report.rejected:
            self._debug_last_result = "MISS"
        else:
            self._debug_last_result = "NO TARGETS"
        if not self.debug:
            return
        for rejection in report.rejected:
            reason = rejection.reason.value if rejection.reason is not None else "predicate"
            log_key = (attack.attack_id, rejection.target_id, reason)
            if log_key in self._debug_logged_rejections:
                continue
            if len(self._debug_logged_rejections) >= 256:
                self._debug_logged_rejections.clear()
            self._debug_logged_rejections.add(log_key)
            self.log_breadcrumb(
                "combat_contact_rejected",
                attack_id=repr(attack.attack_id),
                target_id=repr(rejection.target_id),
                reason=reason,
                horizontal_gap=round(rejection.horizontal_gap, 3),
                depth_gap=round(rejection.depth_gap, 3),
                elevation_gap=round(rejection.elevation_gap, 3),
            )

    @staticmethod
    def _target_cap_report(report: AttackQueryReport) -> AttackQueryReport:
        """Turn otherwise valid contacts into structured lifetime-cap rejects."""

        return AttackQueryReport(
            (),
            tuple(
                replace(
                    evaluation,
                    accepted=False,
                    reason=AttackRejectionReason.TARGET_CAP,
                )
                if evaluation.accepted
                else evaluation
                for evaluation in report.evaluations
            ),
        )

    def _apply_combat_impact(self, result: Any) -> None:
        self.hitstop_remaining = max(self.hitstop_remaining, float(result.hitstop.seconds))
        self.impact_flash = max(
            self.impact_flash,
            min(0.08, float(result.hitstop.seconds)) * self.options.flash_intensity,
        )
        self.camera.trigger_shake(
            float(result.camera.strength) * self.options.shake_intensity,
            float(result.camera.seconds),
            vertical_strength=float(result.camera.strength) * 0.3 * self.options.shake_intensity,
        )

    def _update_revives(self, dt: float) -> None:
        for downed in (player for player in self.players if player.state == "downed"):
            helper_active = False
            for helper in self.players:
                if helper is downed or not helper.combat_active:
                    continue
                snapshot = self._frame_snapshots.get(helper.slot, InputSnapshot())
                if "interact" in snapshot.held and abs(helper.x - downed.x) < 34 and abs(helper.y - downed.y) < 20:
                    helper_active = True
                    downed.revive_progress += dt
                    if downed.revive_progress >= float(self.data["players"]["global"]["revive_hold"]):
                        downed.revive(self)
                        helper.score += 100
                        self.log_breadcrumb("player_revived", helper=helper.slot + 1, player=downed.slot + 1)
                    break
            if not helper_active:
                downed.revive_progress = max(0.0, downed.revive_progress - dt * 0.6)

    def _update_camera(self, dt: float) -> None:
        # CPU Shelly/Dave may follow and fight, but only human players author
        # camera travel and encounter progression.
        active = [player for player in self.players if not player.is_cpu and player.alive]
        if not active:
            active = [player for player in self.players if player.alive]
        if not active:
            return
        speed = float(self.data["players"]["global"]["x_speed"])
        velocity_x = sum(player.last_input_vector[0] * speed for player in active) / len(active)
        view = self.camera.update(dt, [WorldPoint(player.x, player.y, player.z) for player in active], velocity_x=velocity_x)
        self.camera_x = view.x
        self._render_camera_x = view.render_x
        self._camera_shake_y = view.shake_y * self.options.shake_intensity
        self._last_camera_view = view
        if self._pending_camera_lock is not None and not self.camera.panning:
            target = self._pending_camera_lock
            self.camera.set_encounter_lock(target, target)
            self._pending_camera_lock = None

    def _scaling_index(self) -> int:
        """Scale encounters by human players; the solo CPU companion is free."""

        human_count = sum(not player.is_cpu for player in self.players)
        return min(3, max(0, human_count - 1))

    def _scaling_value(self, key: str, default: float) -> float:
        """Read a per-player tuning list without hard-coding a player count."""

        raw = self.data.get("scaling", {}).get(key, default)
        index = self._scaling_index()
        if isinstance(raw, (list, tuple)):
            if not raw:
                return float(default)
            raw = raw[min(index, len(raw) - 1)]
        try:
            return float(raw)
        except (TypeError, ValueError):
            return float(default)

    def _update_encounters(self, dt: float) -> None:
        if self._security_speech_by_enemy:
            self._security_speech_by_enemy = {
                enemy_id: (speech, remaining - dt)
                for enemy_id, (speech, remaining) in self._security_speech_by_enemy.items()
                if remaining - dt > 0.0
            }
        if self.encounter_active:
            if self.spawn_queue:
                self.spawn_timer -= dt
                alive_count = sum(enemy.alive for enemy in self.enemies)
                cap = int(self.data["scaling"]["enemy_caps"][self._scaling_index()])
                if self.spawn_timer <= 0.0 and alive_count < cap:
                    self._spawn_enemy(self.spawn_queue.pop(0))
                    self.spawn_timer = 0.34
            if not self.spawn_queue and not any(enemy.alive for enemy in self.enemies):
                if self._content_optional_active:
                    self._finish_optional_content()
                    return
                if self._post_clear_reinforcements:
                    self._begin_post_clear_reinforcement()
                    return
                name = self.data["encounters"][self.encounter_index]["name"]
                self.encounter_active = False
                self.active_gate = None
                self._pending_camera_lock = None
                self.camera.clear_encounter_lock()
                self.encounter_index += 1
                self.stage_banner = f"{name.upper()} CLEAR"
                self.stage_banner_timer = 1.7
                self.log_breadcrumb("encounter_cleared", name=name, index=self.encounter_index)
                if self.encounter_index >= len(self.data["encounters"]):
                    self._finish_level()
                else:
                    next_encounter = self.data["encounters"][self.encounter_index]
                    boss_loading_enabled = bool(
                        self.data.get("transitions", {}).get("boss_loading", {}).get("enabled", False)
                    )
                    if (
                        self.level_has_couch
                        and boss_loading_enabled
                        and list(next_encounter.get("base", ())) == ["couch"]
                    ):
                        self._start_boss_transition()
            return

        if self.encounter_index >= len(self.data["encounters"]):
            return
        leader_x = max((player.x for player in self.players if not player.is_cpu and player.alive), default=0.0)
        encounter = self.data["encounters"][self.encounter_index]
        if leader_x >= float(encounter["trigger_x"]):
            self._begin_encounter(encounter)

    def _start_boss_transition(self) -> None:
        """Freeze play behind an explicit handoff before Couch's arena."""

        enabled = bool(self.data.get("transitions", {}).get("boss_loading", {}).get("enabled", False))
        if (
            not self.level_has_couch
            or not enabled
            or self.boss_transition is not None
            or self.encounter_index >= len(self.data["encounters"])
        ):
            return
        config = self.data.get("transitions", {}).get("boss_loading", {})
        self.boss_transition = BossLoadingTransition(
            duration_seconds=float(config.get("duration_seconds", 2.4)),
            relocate_seconds=float(config.get("relocate_seconds", 1.05)),
        )
        self.boss_transition_frame = self.boss_transition.current_frame()
        self.active_gate = None
        self._pending_camera_lock = None
        self.camera.clear_encounter_lock()
        self.projectiles.clear()
        self.stage_banner = ""
        self.stage_banner_timer = 0.0
        for player in self.players:
            if player.state not in {"eliminated", "downed"}:
                player.set_state("idle")
        for chief in self.chiefs:
            chief.state = "sit"
        self.log_breadcrumb("boss_loading_started", encounter_index=self.encounter_index)

    def _update_boss_transition(self, dt: float) -> None:
        transition = self.boss_transition
        if transition is None:
            return
        frame = transition.advance(dt)
        self.boss_transition_frame = frame
        if "relocate" in frame.events:
            config = self.data.get("transitions", {}).get("boss_loading", {})
            party_x = float(config.get("party_x", 2945.0))
            party_depth = float(config.get("party_depth", 266.0))
            radius = float(self.data["engine"]["physics"].get("player_radius_depth", 7.0))
            for index, player in enumerate(self.players):
                point = self.stage_geometry.clamp_to_walkable(
                    WorldPoint(party_x + index * 30.0, party_depth + index * 13.0),
                    radius=radius,
                )
                player.x = point.x
                player.y = point.depth
                player.z = 0.0
                player.vz = 0.0
                if player.state not in {"eliminated", "downed"}:
                    player.set_state("idle")
            for chief in self.chiefs:
                point = self.stage_geometry.clamp_to_walkable(
                    WorldPoint(chief.owner.x - 28.0, chief.owner.y + 10.0),
                    radius=float(self.data["engine"]["physics"].get("chief_radius_depth", 6.0)),
                )
                chief.x = point.x
                chief.y = point.depth
                chief.state = "sit"
            camera_target = float(self.data["encounters"][self.encounter_index].get("camera_x", 2960.0))
            self.camera.pan_to(camera_target, 0.0)
            self.camera_x = self.camera.x
            self._render_camera_x = self.camera.x
            self._camera_shake_y = 0.0
            self.log_breadcrumb(
                "boss_loading_relocated",
                party=[(round(player.x, 1), round(player.y, 1)) for player in self.players],
                camera=round(self.camera_x, 1),
            )
        if "finished" in frame.events:
            encounter = self.data["encounters"][self.encounter_index]
            self.boss_transition = None
            self._begin_encounter(encounter)
            self.log_breadcrumb("boss_loading_finished", encounter=encounter["name"])

    def _start_level_outro(self) -> None:
        """Freeze combat and stage Jerry's route warning at El Cilantro."""

        if self.level_outro is not None:
            return
        self.level_outro = JerryLevelOneOutro()
        self.level_outro_frame = self.level_outro.current_frame()
        self._level_outro_mouse_advance_pending = False
        self.encounter_active = False
        self.spawn_queue.clear()
        self.enemies.clear()
        self.active_gate = None
        self._pending_camera_lock = None
        self.camera.clear_encounter_lock()
        self.projectiles.clear()
        self.ammo_pickups.clear()
        self.super_butane_pickups.clear()
        self.effects.clear()
        self._dave_flame_visuals.clear()
        self.couch_retreat = None
        party_depth = 270.0
        party_start = float(self.meta["stage_width"]) - 515.0
        player_radius = float(self.data["engine"]["physics"].get("player_radius_depth", 7.0))
        for index, player in enumerate(self.players):
            point = self.stage_geometry.clamp_to_walkable(
                WorldPoint(party_start + index * 34.0, party_depth + index * 10.0),
                radius=player_radius,
            )
            player.x, player.y, player.z, player.vz = point.x, point.depth, 0.0, 0.0
            if player.state not in {"downed", "eliminated"}:
                player.set_state("idle")
        for chief in self.chiefs:
            point = self.stage_geometry.clamp_to_walkable(
                WorldPoint(chief.owner.x - 32.0, chief.owner.y + 12.0),
                radius=float(self.data["engine"]["physics"].get("chief_radius_depth", 6.0)),
            )
            chief.x, chief.y, chief.state = point.x, point.depth, "sit"
        camera_target = max(0.0, float(self.meta["stage_width"]) - LOGICAL_SIZE[0])
        self.camera.pan_to(camera_target, 0.55)
        self.stage_banner = "EL CILANTRO  •  JERRY"
        self.stage_banner_timer = 1.4
        self.log_breadcrumb("level_outro_started", level_id=self.level_id, npc="jerry")

    def _update_level_outro(self, dt: float, snapshots: list[InputSnapshot]) -> None:
        timeline = self.level_outro
        if timeline is None:
            return
        mouse_advance = self._level_outro_mouse_advance_pending
        self._level_outro_mouse_advance_pending = False
        # Any deliberate gameplay/confirm action can continue the scene. The
        # timeline filters raw held input to one edge, and the input manager
        # already filters keyboard auto-repeat and catch-up simulation steps.
        advance = mouse_advance or any(
            snapshot.pressed
            & {
                "confirm",
                "join",
                "light",
                "heavy",
                "jump",
                "interact",
                "super",
                "chief",
                "secondary",
            }
            for snapshot in snapshots
        )
        skip = any(snapshot.pressed & {"back", "dodge"} for snapshot in snapshots)
        frame = timeline.advance(dt, advance_input=advance, skip_input=skip)
        self.level_outro_frame = frame
        self.stage_banner_timer = max(0.0, self.stage_banner_timer - dt)
        self._update_camera(dt)
        for event in frame.events:
            self.log_breadcrumb("level_outro_event", outro_event=event, beat=frame.beat)
            if event in {"warning_started", "clarification_started", "reaction_started"}:
                self.audio.play("menu")
        if frame.finished:
            self.level_outro = None
            self.level_outro_frame = None
            self._finish_level(after_outro=True)

    def _finish_level(self, *, after_outro: bool = False) -> None:
        if self.state == "complete":
            return
        if self.level_data.get("outro") == "jerry_warning" and not after_outro:
            self._start_level_outro()
            return
        self.state = "complete"
        self.complete_timer = 0.0
        self.completion_stats = self.level_stats.finish(self.players)
        self._persist_completed_level()
        self.victory_timeline.reset()
        if self.level_is_chapter_finale:
            self.victory_frame = self.victory_timeline.current_frame()
        else:
            self.victory_timeline.elapsed_seconds = (
                self.victory_timeline.hug_seconds + self.victory_timeline.treat_toss_seconds
            )
            self.victory_frame = self.victory_timeline.current_frame()
        self.audio_manager.stop_music(850)
        self.music_started = False
        self.log_breadcrumb(
            "level_completed",
            level_id=self.level_id,
            chapter_finale=self.level_is_chapter_finale,
            **self.completion_stats.as_dict(),
        )

    def _persist_completed_level(self) -> None:
        """Record one completed level without making a save failure fatal."""

        if self.completion_stats is None:
            return
        next_level = self._next_campaign_level()
        try:
            run = RunStats.from_completion(
                self.completion_stats,
                difficulty=self.options.difficulty,
            )
            self.save_data = self.save_data.record_run(
                self.level_id,
                run,
                next_level_id=(str(next_level["id"]) if next_level is not None else None),
            )
            self.save_data = replace(
                self.save_data,
                atmosphere=AtmosphereState.from_mapping(
                    self.atmosphere.to_mapping()
                ),
            )
            if self.persistence_enabled:
                self.save_repository.save(self.save_data)
                self.log_breadcrumb(
                    "chapter_progress_saved",
                    level_id=self.level_id,
                    unlocked=list(self.save_data.progression.unlocked_level_ids),
                )
            else:
                self.log_breadcrumb(
                    "chapter_progress_recorded",
                    level_id=self.level_id,
                    unlocked=list(self.save_data.progression.unlocked_level_ids),
                )
        except (OSError, ValueError, TypeError) as error:
            # A locked cloud-sync folder cannot be allowed to discard a just
            # completed run. The live results remain valid and the next run
            # will retry an atomic save.
            self.log_breadcrumb("chapter_progress_save_failed", error=str(error)[:120])

    def _begin_encounter(self, encounter: dict[str, Any]) -> None:
        self.encounter_active = True
        self.active_gate = float(encounter["gate_x"])
        camera_target = float(encounter.get("camera_x", self.camera_x))
        pan_speed = float(self.data["engine"]["camera"].get("scripted_pan_speed", 335.0))
        pan_seconds = clamp(abs(camera_target - self.camera.x) / max(1.0, pan_speed), 0.20, 1.05)
        self.camera.clear_encounter_lock()
        self.camera.pan_to(camera_target, pan_seconds)
        self._pending_camera_lock = camera_target
        self._post_clear_reinforcements = [
            dict(reinforcement)
            for reinforcement in encounter.get("post_clear_reinforcements", [])
            if isinstance(reinforcement, dict)
        ]
        self._security_spawn_speech = ""
        self._security_speech_by_enemy.clear()
        base = list(encounter["base"])
        content_fight = self._content_major_by_hook.get(str(encounter.get("name", "")).strip().lower())
        if base != ["couch"] and content_fight is not None:
            authored_roles = [
                str(kind)
                for group in content_fight.get("spawn_groups", ())
                if isinstance(group, dict)
                for kind in group.get("runtime_kinds", ())
            ]
            # The content contract contributes role variety, then the focused
            # roster pass below caps the encounter before it becomes a noisy
            # parade of overlapping targets.
            if authored_roles:
                base = self._anti_clone_order([*base, *authored_roles])
        if base == ["couch"]:
            self.spawn_queue = base
            self._encounter_enemy_durability_scale = 1.0
            self._encounter_enemy_damage_scale = 1.0
            self._encounter_enemy_score_scale = 1.0
        else:
            # Hitbox work is easier to evaluate against a small, distinct
            # roster. The cap limits the complete queued fight (not merely the
            # number visible at once), while durability retains real combat
            # time on each target.
            focused_cap = max(1, int(self._scaling_value("focused_enemy_queue_cap", len(base))))
            focused_base = self._focused_enemy_wave(base, focused_cap)
            budget_scale = self._scaling_value("wave_budget", 1.0)
            density = max(1.0, self._scaling_value("encounter_density_multiplier", 1.0))
            total = min(
                focused_cap,
                max(len(focused_base), round(len(focused_base) * budget_scale * density)),
            )
            inverse_density = 1.0 / density
            self._encounter_enemy_durability_scale = max(
                0.05,
                self._scaling_value("enemy_durability_scale", inverse_density),
            )
            self._encounter_enemy_damage_scale = max(
                0.05,
                self._scaling_value("enemy_damage_scale", inverse_density),
            )
            self._encounter_enemy_score_scale = max(
                0.05,
                self._scaling_value("enemy_score_scale", inverse_density),
            )
            self.spawn_queue = self._anti_clone_order(
                focused_base[index % len(focused_base)] for index in range(total)
            )
        self.spawn_timer = 0.0
        self.stage_banner = encounter["name"].upper()
        self.stage_banner_timer = 1.5
        self.log_breadcrumb(
            "encounter_started",
            name=encounter["name"],
            enemies=self.spawn_queue,
            density=round(self._scaling_value("encounter_density_multiplier", 1.0), 3),
            focused_cap=int(self._scaling_value("focused_enemy_queue_cap", len(base))),
            durability_scale=round(self._encounter_enemy_durability_scale, 3),
            damage_scale=round(self._encounter_enemy_damage_scale, 3),
            gate=self.active_gate,
            camera_target=camera_target,
        )

    def _begin_post_clear_reinforcement(self) -> None:
        """Promote the next authored mini-wave without opening its gate."""

        reinforcement = self._post_clear_reinforcements.pop(0)
        base = [str(kind) for kind in reinforcement.get("base", [])]
        # Config validation guarantees usable entries. Keeping this guard
        # makes the runtime still recover safely from a hand-edited JSON file.
        if not base:
            return
        self.spawn_queue = base
        self.spawn_timer = 0.0
        self._security_spawn_speech = str(reinforcement.get("speech", "")).strip()
        name = str(reinforcement.get("name", "SECURITY DETAIL"))
        self.stage_banner = name.upper()
        self.stage_banner_timer = 1.35
        self.add_effect(
            "text",
            LOGICAL_SIZE[0] * 0.5,
            128.0,
            text="SECURITY REINFORCEMENTS!",
            color=(255, 215, 87),
            duration=0.82,
            world_space=False,
        )
        self.log_breadcrumb(
            "post_clear_reinforcement_started",
            name=name,
            enemies=base,
            remaining=len(self._post_clear_reinforcements),
            gate=self.active_gate,
        )

    def next_couch_retreat_health(self, boss: Enemy) -> float | None:
        """Return the next mandatory health gate for the live finale Couch."""

        if (
            not self.level_has_couch
            or self.couch_retreat is not None
            or boss.kind != "couch"
            or not any(candidate is boss for candidate in self.enemies)
        ):
            return None
        ratios = tuple(float(value) for value in boss.stats.get("retreat_health_ratios", ()))
        index = boss.couch_retreats_started
        if not 0 <= index < len(ratios):
            return None
        return boss.max_health * ratios[index]

    def start_couch_retreat(self, boss: Enemy) -> bool:
        """Make Couch visibly jump to the manifest BMX before her next crew."""

        gate_health = self.next_couch_retreat_health(boss)
        if gate_health is None or boss.health > gate_health + 0.001:
            return False
        config = boss.stats
        waves = tuple(tuple(str(kind) for kind in wave) for wave in config.get("retreat_add_waves", ()))
        index = boss.couch_retreats_started
        if not 0 <= index < len(waves):
            return False

        self.release_attack_token(boss)
        boss.token_held = 0
        boss.knockback_vx = 0.0
        boss.burn_time = 0.0
        boss.burn_tick = 0.0
        boss.attack_pattern = ""
        boss.couch_retreats_started += 1
        boss._set_state("bike_retreat")
        self._dave_flame_visuals.pop(boss.enemy_id, None)

        refuge_x = clamp(
            self._landmark_world_x("daves_bmx"),
            0.0,
            float(self.meta["stage_width"]),
        )
        refuge_y = clamp(
            float(config.get("retreat_refuge_depth", 244.0)),
            float(self.meta["lane_top"]),
            float(self.meta["lane_bottom"]),
        )
        self.couch_retreat = CouchRetreat(
            boss=boss,
            number=boss.couch_retreats_started,
            origin_x=boss.x,
            origin_y=boss.y,
            refuge_x=refuge_x,
            refuge_y=refuge_y,
        )
        boss.facing = 1 if refuge_x >= boss.x else -1
        self.stage_banner = f"COUCH RETREAT {boss.couch_retreats_started}/2"
        self.stage_banner_timer = 1.1
        self.add_effect(
            "text",
            LOGICAL_SIZE[0] * 0.5,
            124.0,
            text="COUCH JUMPS BACK TO DAVE'S BMX!",
            color=(255, 153, 218),
            duration=0.95,
            world_space=False,
        )
        self.log_breadcrumb(
            "couch_retreat_started",
            retreat=boss.couch_retreats_started,
            health=round(boss.health, 2),
            gate=round(gate_health, 2),
            add_wave=waves[index],
        )
        return True

    def update_couch_retreat(self, boss: Enemy, dt: float) -> None:
        """Advance the exact retreat/refuge/add-wave/return lifecycle."""

        retreat = self.couch_retreat
        if retreat is None or retreat.boss is not boss or not any(candidate is boss for candidate in self.enemies):
            return
        dt = max(0.0, float(dt))
        boss.state_clock += dt
        config = boss.stats

        if retreat.phase == "retreat":
            speed = max(1.0, float(config.get("retreat_jump_speed", 275.0)))
            old_x, old_y = boss.x, boss.y
            boss.x = move_toward(boss.x, retreat.refuge_x, speed * dt)
            boss.y = move_toward(boss.y, retreat.refuge_y, speed * 0.62 * dt)
            boss.facing = 1 if retreat.refuge_x >= boss.x else -1
            boss.locomotion_distance += math.hypot(boss.x - old_x, boss.y - old_y)
            if boss.x == retreat.refuge_x and boss.y == retreat.refuge_y:
                self._start_couch_refuge(retreat)
            return

        if retreat.phase == "refuge":
            retreat.elapsed_seconds += dt
            live_adds = any(
                enemy.enemy_id in retreat.add_enemy_ids and enemy.alive
                for enemy in self.enemies
            )
            minimum = max(0.0, float(config.get("retreat_minimum_refuge_seconds", 0.72)))
            if not live_adds and retreat.elapsed_seconds >= minimum:
                retreat.phase = "return"
                retreat.elapsed_seconds = 0.0
                boss._set_state("bike_return")
                boss.facing = 1 if retreat.origin_x >= boss.x else -1
                self.add_effect(
                    "text",
                    LOGICAL_SIZE[0] * 0.5,
                    124.0,
                    text="COUCH IS COMING BACK!",
                    color=(255, 194, 229),
                    duration=0.9,
                    world_space=False,
                )
                self.log_breadcrumb("couch_return_started", retreat=retreat.number)
            return

        speed = max(1.0, float(config.get("retreat_return_speed", 250.0)))
        old_x, old_y = boss.x, boss.y
        boss.x = move_toward(boss.x, retreat.origin_x, speed * dt)
        boss.y = move_toward(boss.y, retreat.origin_y, speed * 0.62 * dt)
        boss.facing = 1 if retreat.origin_x >= boss.x else -1
        boss.locomotion_distance += math.hypot(boss.x - old_x, boss.y - old_y)
        if boss.x == retreat.origin_x and boss.y == retreat.origin_y:
            retreat_number = retreat.number
            self.couch_retreat = None
            boss._set_state("chase")
            boss.cooldown = max(boss.cooldown, float(config.get("retreat_return_cooldown", 0.85)))
            self.stage_banner = "COUCH IS BACK!"
            self.stage_banner_timer = 0.9
            self.log_breadcrumb(
                "couch_return_finished",
                retreat=retreat_number,
                health=round(boss.health, 2),
                targetable=boss.targetable,
            )

    def couch_retreat_render_pose(self, boss: Enemy) -> tuple[float, float]:
        """Return continuous screen-X offset and parabolic hop height."""

        retreat = self.couch_retreat
        if retreat is None or retreat.boss is not boss:
            return 0.0, 0.0
        visual_offset = float(boss.stats.get("retreat_refuge_visual_offset_x", 54.0))
        if retreat.phase == "refuge":
            return visual_offset, 0.0
        if retreat.phase == "retreat":
            start_x, start_y = retreat.origin_x, retreat.origin_y
            end_x, end_y = retreat.refuge_x, retreat.refuge_y
        else:
            start_x, start_y = retreat.refuge_x, retreat.refuge_y
            end_x, end_y = retreat.origin_x, retreat.origin_y
        total = math.hypot(end_x - start_x, end_y - start_y)
        remaining = math.hypot(end_x - boss.x, end_y - boss.y)
        progress = clamp(1.0 - remaining / max(0.001, total), 0.0, 1.0)
        offset = visual_offset * (progress if retreat.phase == "retreat" else 1.0 - progress)
        hop_height = max(0.0, float(boss.stats.get("retreat_hop_height", 58.0)))
        return offset, hop_height * 4.0 * progress * (1.0 - progress)

    def _start_couch_refuge(self, retreat: CouchRetreat) -> None:
        """Spawn the configured live dope-fiend wave beside visible Couch."""

        boss = retreat.boss
        boss._set_state("bike_refuge")
        retreat.phase = "refuge"
        retreat.elapsed_seconds = 0.0
        waves = tuple(tuple(str(kind) for kind in wave) for wave in boss.stats.get("retreat_add_waves", ()))
        wave = waves[retreat.number - 1]
        spawned = tuple(self._spawn_enemy(kind) for kind in wave)
        retreat.add_enemy_ids = tuple(enemy.enemy_id for enemy in spawned)
        self.stage_banner = f"DOPE-FIEND WAVE {retreat.number}/2"
        self.stage_banner_timer = 1.4
        self.log_breadcrumb(
            "couch_refuge_wave_started",
            retreat=retreat.number,
            taunt=retreat.taunt,
            enemy_ids=retreat.add_enemy_ids,
            enemies=wave,
        )

    def _spawn_enemy(self, kind: str) -> Enemy:
        self.enemy_sequence += 1
        stats = dict(self.data["enemies"][kind])
        direction = -1 if self.enemy_sequence % 3 == 0 else 1
        if direction > 0:
            x = min(float(self.meta["stage_width"]) - 45.0, self.camera_x + 615.0 + random.uniform(0, 45))
        else:
            x = max(35.0, self.camera_x + random.uniform(-35, 15))
        y = random.uniform(float(self.meta["lane_top"]) + 10, float(self.meta["lane_bottom"]) - 6)
        scale = 1.0
        if kind == "couch":
            scale = float(self.data["scaling"]["boss_health"][self._scaling_index()])
            x = min(float(self.meta["stage_width"]) - 160.0, self.camera_x + 565.0)
            y = 275.0
        else:
            # A clone per spawn keeps the editable archetype pristine and
            # makes the current encounter's crowd balancing inspectable on
            # every Enemy instance.
            stats["health"] = max(1.0, float(stats["health"]) * self._encounter_enemy_durability_scale)
            stats["damage"] = max(0.1, float(stats["damage"]) * self._encounter_enemy_damage_scale)
            stats["score"] = max(1.0, float(stats["score"]) * self._encounter_enemy_score_scale)
        enemy = Enemy(self.enemy_sequence, kind, x, y, stats, difficulty_scale=scale)
        self.enemies.append(enemy)
        self.add_effect("spawn", x, y, radius=25, color=(210, 118, 255), duration=0.45)
        if kind == "security":
            speech = self._security_spawn_speech or "YOU GUYS CAN'T BE HERE!"
            self._security_speech_by_enemy[enemy.enemy_id] = (speech, 2.25)
            self.add_effect("spawn", x, y, radius=34, color=(255, 211, 91), duration=0.58)
            self.log_breadcrumb("security_guard_spawned", enemy_id=enemy.enemy_id, speech=speech)
        return enemy

    def acquire_attack_token(self, enemy: Enemy, cost: int) -> bool:
        limit = int(self.data["scaling"]["attack_tokens"][self._scaling_index()])
        if self.attack_tokens_used + cost > limit:
            return False
        self.attack_tokens_used += cost
        return True

    def release_attack_token(self, enemy: Enemy) -> None:
        if enemy.token_held:
            self.attack_tokens_used = max(0, self.attack_tokens_used - enemy.token_held)
            enemy.token_held = 0

    def nearest_player(self, x: float, y: float) -> Player | None:
        candidates = [player for player in self.players if player.combat_active]
        return min(candidates, key=lambda player: abs(player.x - x) + abs(player.y - y) * 1.8, default=None)

    def player_by_slot(self, slot: int) -> Player | None:
        return next((player for player in self.players if player.slot == slot and player.combat_active), None)

    def nearest_enemy(self, x: float, y: float) -> Enemy | None:
        candidates = [
            enemy
            for enemy in self.enemies
            if enemy.targetable
            and enemy.state != "down"
            and enemy.wake_invulnerable <= 0.0
        ]
        return min(candidates, key=lambda enemy: abs(enemy.x - x) + abs(enemy.y - y) * 1.8, default=None)

    def try_throw(self, player: Player) -> bool:
        move = self.data["moves"]["throw"]
        range_x = float(move["range_x"]) + float(move.get("reach_forgiveness", 0.0))
        range_depth = float(move["range_y"]) + float(move.get("depth_forgiveness", 0.0))
        attack = HitBox(
            ("player_throw", player.slot, player.attack_instance_sequence + 1),
            ("player", player.slot),
            "player",
            player.x + player.facing * range_x * 0.5,
            player.y,
            elevation=max(0.0, player.z),
            half_width=max(2.0, range_x * 0.5),
            half_depth=max(2.0, range_depth - float(self.data["engine"]["physics"]["enemy_radius_depth"])),
            height=46.0 + float(move.get("elevation_forgiveness", 0.0)),
            damage=float(move["damage"]),
            stun=float(move["hitstun"]),
            knockback_x=player.facing * float(move["knockback"]),
            hit_grounded=True,
            hit_airborne=False,
            blocked_tags=frozenset({"downed", "armor", "grab_immune"}),
            hitstop_seconds=float(self.data["engine"]["physics"]["heavy_hitstop"]),
            camera_strength=4.5,
            camera_seconds=0.16,
            max_targets=1,
            max_hits_per_target=1,
            facing_x=float(player.facing),
            # Grabs require the target body to be meaningfully in front, not
            # merely touching the fighter's front plane from behind.
            front_origin_x=player.x + player.facing * 4.0,
            front_origin_depth=player.y,
            rear_tolerance=0.0,
        )
        report = query_attack_detailed(attack, self._enemy_hurtboxes())
        self._record_attack_report(attack, report)
        if not report.results:
            return False
        contact = report.results[0]
        target = next(
            (enemy for enemy in self.enemies if ("enemy", enemy.enemy_id) == contact.target_id),
            None,
        )
        if target is None or not target.take_damage(
            contact.damage,
            self,
            player,
            hitstun=contact.stun,
            knockback=float(move["knockback"]),
            knockdown=True,
        ):
            return False
        self._apply_combat_impact(contact)
        self.add_effect(
            "text",
            contact.contact_x,
            contact.contact_depth - 52,
            text="THROW!",
            color=PLAYER_COLORS[player.color_index],
        )
        player.gain_super(float(move["meter"]))
        return True

    @staticmethod
    def _sample_move_hitbox(
        move: dict[str, Any],
        active_progress: float,
    ) -> dict[str, float]:
        """Interpolate the authored 2.5D volume across an active interval."""

        defaults = {
            "reach_scale": 1.0,
            "depth_scale": 1.0,
            "height_scale": 1.0,
            "offset_x": 0.0,
            "offset_depth": 0.0,
        }
        frames = move.get("hitbox_frames")
        if not isinstance(frames, list) or len(frames) < 2:
            return defaults
        progress = clamp(float(active_progress), 0.0, 1.0)
        right_index = next(
            (index for index, frame in enumerate(frames) if float(frame["at"]) >= progress),
            len(frames) - 1,
        )
        left_index = max(0, right_index - 1)
        left = frames[left_index]
        right = frames[right_index]
        span = float(right["at"]) - float(left["at"])
        blend = 0.0 if span <= 0.0 else (progress - float(left["at"])) / span
        return {
            name: float(left.get(name, defaults[name]))
            + (float(right.get(name, defaults[name])) - float(left.get(name, defaults[name]))) * blend
            for name in defaults
        }

    def player_attack(
        self,
        player: Player,
        move: dict[str, Any],
        attack_kind: str,
        *,
        already_hit: set[tuple[str, int]] | None = None,
        hit_counts: dict[tuple[str, int], int] | None = None,
        last_hit_times: dict[tuple[str, int], float] | None = None,
        attack_time: float | None = None,
        play_whiff: bool = True,
    ) -> int:
        physics = self.data["engine"]["physics"]
        active_duration = max(0.001, float(move.get("active", 0.001)))
        active_progress = (
            0.0
            if attack_time is None
            else (float(attack_time) - float(move.get("startup", 0.0))) / active_duration
        )
        sampled = self._sample_move_hitbox(move, active_progress)
        range_x = (
            float(move["range_x"])
            + float(physics.get("player_attack_reach_bonus", 0.0))
            + float(move.get("reach_forgiveness", 0.0))
        ) * sampled["reach_scale"]
        range_depth = float(move["range_y"]) * sampled["depth_scale"]
        attack_depth = player.y + sampled["offset_depth"]
        lane_assist = float(
            move.get("lane_assist", physics.get("player_attack_lane_assist", 0.0))
        )
        lunge = float(move.get("lunge", 0.0))
        depth_forgiveness = float(move.get("depth_forgiveness", 0.0))
        aim_bonus = float(
            move.get("aim_range_bonus", physics.get("player_attack_aim_range_bonus", 0.0))
        )
        # Aim forgiveness is real strike reach, not only a prefilter.  Keeping
        # acquisition and contact on one envelope prevents assisted targets
        # from being selected and then rejected by the narrower hitbox.
        range_x = max(0.0, range_x + aim_bonus)
        assist_reach = range_x + max(0.0, lunge)
        assist_depth = lane_assist + float(
            physics.get("player_attack_depth_tolerance", 0.0)
        ) + depth_forgiveness
        rear_tolerance = float(
            move.get("rear_tolerance", physics.get("player_attack_rear_tolerance", 0.0))
        )
        max_targets = max(
            1,
            int(move.get("max_targets", physics.get("player_attack_max_targets", 1))),
        )

        def _in_player_front_arc(candidate: Enemy) -> bool:
            if player.facing == 0:
                return True
            sample_x = candidate.hitbox_sweep_x
            if sample_x is None:
                sample_x = candidate.x
            half_width, _, _, _ = self._actor_extents(candidate)
            for x in (sample_x, candidate.x):
                forward_edge = x + (half_width if player.facing > 0 else -half_width)
                if (forward_edge - player.x) * player.facing >= -rear_tolerance:
                    return True
            return False

        assist_candidates = [
            enemy
            for enemy in self.enemies
            if enemy.targetable
            and enemy.state != "down"
            and enemy.wake_invulnerable <= 0.0
            and _in_player_front_arc(enemy)
            and abs(enemy.x - player.x) <= assist_reach
            and abs(enemy.y - player.y) <= range_depth + assist_depth
        ]
        assisted_group = sorted(
            assist_candidates,
            key=lambda enemy: (
                abs(enemy.x - player.x) + abs(enemy.y - player.y) * 1.5,
                abs(enemy.y - player.y),
                enemy.enemy_id,
            ),
        )[:max_targets]
        if assisted_group:
            assisted = assisted_group[0]
            if play_whiff:
                lunge = min(
                    lunge,
                    max(0.0, abs(assisted.x - player.x) - 18.0),
                )
                if lunge > 0.0:
                    player._move_world(self, player.facing * lunge, 0.0)
            group_depth = sum(enemy.y for enemy in assisted_group) / len(assisted_group)
            attack_depth += clamp(group_depth - player.y, -lane_assist, lane_assist)
        attack_x = (
            player.x
            + player.facing * (range_x * 0.5 - 5.0 + sampled["offset_x"])
        )

        finisher = bool(move.get("chain_finisher", False))
        heavy_impact = attack_kind == "heavy" or bool(move.get("knockdown", False))
        hitstop = float(physics["heavy_hitstop"] if heavy_impact else physics["light_hitstop"])
        shake = 5.2 if finisher else 4.2 if heavy_impact else 2.4 + player.combo_step * 0.35
        move_elevation_forgiveness = float(move.get("elevation_forgiveness", 0.0))
        move_temporal_forgiveness = float(move.get("temporal_forgiveness", 0.0))
        global_elevation_forgiveness = float(
            physics.get("player_attack_elevation_forgiveness", 0.0)
        )
        elevation_tolerance = move_elevation_forgiveness + global_elevation_forgiveness
        temporal_tolerance = move_temporal_forgiveness + float(
            physics.get("player_attack_temporal_forgiveness", 0.0)
        )
        hit_memory = already_hit if already_hit is not None else set()
        counts = hit_counts if hit_counts is not None else {}
        times = last_hit_times if last_hit_times is not None else {}
        remaining_targets = max_targets - len(hit_memory)
        max_hits_per_target = max(1, int(move.get("max_hits_per_target", 1)))
        attack = HitBox(
            (
                "player_attack",
                player.slot,
                player.attack_instance_id,
                attack_kind,
                player.combo_step,
            ),
            ("player", player.slot),
            "player",
            attack_x,
            attack_depth,
            elevation=max(
                0.0,
                player.z - (8.0 if attack_kind == "air_attack" else 0.0),
            ),
            half_width=range_x * 0.5 + 5.0,
            half_depth=max(
                2.0,
                range_depth - float(physics["enemy_radius_depth"]),
            ),
            depth_tolerance=(
                float(physics.get("player_attack_depth_tolerance", 0.0))
                + depth_forgiveness
            ),
            height=(34.0 if attack_kind == "air_attack" else 46.0)
            * sampled["height_scale"],
            elevation_tolerance=elevation_tolerance,
            damage=float(move["damage"]) * player.fist_damage_multiplier(),
            stun=float(move["hitstun"]),
            knockback_x=player.facing * float(move["knockback"]),
            hit_grounded=True,
            hit_airborne=attack_kind == "air_attack",
            blocked_tags=(
                frozenset({"armor", "blocking"})
                if bool(move.get("hit_downed", False))
                else frozenset({"downed", "armor", "blocking"})
            ),
            hitstop_seconds=hitstop,
            camera_strength=shake,
            camera_seconds=0.18 if finisher else 0.16 if heavy_impact else 0.10,
            max_targets=max(1, remaining_targets),
            max_hits_per_target=max_hits_per_target,
            rehit_delay=float(move.get("rehit_delay", 0.0)),
            sweep_from_x=player.attack_sweep_x,
            sweep_from_depth=player.attack_sweep_y,
            facing_x=float(player.facing),
            front_origin_x=player.x,
            front_origin_depth=player.y,
            rear_tolerance=rear_tolerance,
            temporal_forgiveness=temporal_tolerance,
        )
        player.attack_sweep_x = attack_x
        player.attack_sweep_y = attack_depth

        if remaining_targets <= 0 and max_hits_per_target <= 1:
            report = query_attack_detailed(
                attack,
                self._enemy_hurtboxes(),
                already_hit=hit_memory,
                hit_counts=counts,
                last_hit_times=times,
                now=attack_time,
            )
            self._record_attack_report(attack, self._target_cap_report(report))
            return 0
        blocked = hit_memory if max_hits_per_target <= 1 else ()
        report = query_attack_detailed(
            attack,
            self._enemy_hurtboxes(),
            already_hit=blocked,
            hit_counts=counts,
            last_hit_times=times,
            now=attack_time,
            predicate=(
                None
                if remaining_targets > 0
                else lambda hurtbox: hurtbox.entity_id in hit_memory
            ),
        )
        self._record_attack_report(attack, report)
        enemies_by_id = {("enemy", enemy.enemy_id): enemy for enemy in self.enemies}

        flaming_fists = (
            player.character == "black_dave"
            and attack_kind in {"light", "heavy", "air_attack"}
            and player.flaming_fists
        )
        combo_radius = float(move.get("combo_radius", 0.0))
        follow_through = attack_kind == "light" and player.combo_step > 0
        if play_whiff:
            # Every hero gets a readable authored-motion accent at the actual
            # attack presentation frame.  Previously only Dave's fist path
            # emitted a trail, so successful visual work was easy to miss when
            # playing Shelly or when a strike did not connect.
            accent = (
                (255, 137, 191) if player.character == "shelly"
                else (108, 226, 255)
            )
            trail_length = 24.0 if attack_kind == "light" else 34.0
            self.add_effect(
                "streak",
                player.x + player.facing * trail_length,
                player.y - (24.0 + player.z),
                color=accent,
                radius=10.0 if attack_kind == "light" else 15.0,
                duration=0.13 if attack_kind == "light" else 0.18,
                vx=player.facing * (55.0 if attack_kind == "light" else 78.0),
                vy=-8.0,
                drag=4.0,
                scale_start=0.65,
                scale_end=1.35,
                alpha_start=210,
                alpha_end=0,
                direction=player.facing,
                projected=True,
                elevation=player.z + 28.0,
            )
        if player.character == "black_dave" and play_whiff:
            fist_cfg = self.data["players"]["black_dave"].get("fist_effects", {})
            trail_x = player.x + player.facing * (range_x * 0.72)
            trail_elevation = player.z + 33.0
            self.add_effect(
                "fist",
                trail_x,
                player.y,
                color=tuple(fist_cfg.get("color", (105, 225, 255))),
                radius=float(fist_cfg.get("trail_radius", 16.0)),
                duration=0.16,
                projected=True,
                elevation=trail_elevation,
            )
            if follow_through:
                self.add_effect(
                    "shock",
                    attack_x,
                    attack_depth,
                    color=tuple(fist_cfg.get("combo_color", (151, 244, 255))),
                    radius=min(combo_radius, 30.0 + player.combo_step * 5.0),
                    duration=0.16 + player.combo_step * 0.02,
                    projected=True,
                    elevation=8.0,
                )
            if flaming_fists:
                self.add_effect(
                    f"flame_trail_{'right' if player.facing >= 0 else 'left'}",
                    trail_x,
                    player.y,
                    color=(255, 112, 30),
                    radius=26,
                    duration=0.24,
                    projected=True,
                    elevation=player.z + 34.0,
                )

        hits = 0
        for contact in report.results:
            enemy = enemies_by_id.get(contact.target_id)
            if enemy is None:
                continue
            burn = player.character == "shelly" and (
                attack_kind in {"heavy", "air_attack"} or finisher
            )
            if not enemy.take_damage(
                contact.damage,
                self,
                player,
                hitstun=contact.stun,
                knockback=float(move["knockback"]),
                knockdown=bool(move.get("knockdown", False)),
                burn=burn,
            ):
                continue
            hits += 1
            hit_memory.add(contact.target_id)
            counts[contact.target_id] = counts.get(contact.target_id, 0) + 1
            times[contact.target_id] = (
                float(attack_time) if attack_time is not None else 0.0
            )
            self._apply_combat_impact(contact)
            player.gain_super(float(move["meter"]))
            self.add_effect(
                "impact",
                contact.contact_x,
                contact.contact_depth,
                color=(255, 243, 168) if finisher else (255, 231, 92),
                radius=34 if finisher else 22 if heavy_impact else 16,
                duration=0.28 if finisher else 0.20,
                projected=True,
                elevation=30.0,
            )
            if finisher:
                self.add_effect(
                    "shock",
                    contact.contact_x,
                    contact.contact_depth,
                    color=(255, 219, 92),
                    radius=48,
                    duration=0.32,
                    projected=True,
                    elevation=4.0,
                )
            if burn:
                self.add_effect(
                    "flame",
                    enemy.x,
                    enemy.y,
                    color=(255, 118, 38),
                    duration=0.45,
                    projected=True,
                    elevation=38.0,
                )
            if player.character == "black_dave":
                fist_cfg = self.data["players"]["black_dave"].get("fist_effects", {})
                self.add_effect(
                    "fist",
                    contact.contact_x,
                    contact.contact_depth,
                    color=tuple(fist_cfg.get("contact_color", (230, 253, 255))),
                    radius=float(fist_cfg.get("contact_radius", 26.0))
                    + player.combo_step * 3.0,
                    duration=0.20,
                    projected=True,
                    elevation=34.0,
                )
                if flaming_fists:
                    self._dave_flame_visuals[enemy.enemy_id] = max(
                        self._dave_flame_visuals.get(enemy.enemy_id, 0.0),
                        0.78,
                    )
                    self.add_effect(
                        "flame_burst",
                        contact.contact_x,
                        contact.contact_depth,
                        color=(255, 105, 31),
                        radius=34,
                        duration=0.32,
                        projected=True,
                        elevation=36.0,
                    )
                    self.add_effect(
                        "scorch",
                        contact.contact_x,
                        contact.contact_depth,
                        color=(188, 71, 36),
                        radius=27,
                        duration=0.82,
                        projected=True,
                        elevation=2.0,
                    )
                    self.add_effect(
                        "ember",
                        contact.contact_x - player.facing * 8.0,
                        contact.contact_depth,
                        color=(255, 202, 65),
                        radius=10,
                        duration=0.38,
                        projected=True,
                        elevation=45.0,
                    )
        if hits:
            self.audio.play("heavy" if heavy_impact else "punch")
        elif play_whiff:
            self.audio.play("whoosh")
        return hits

    def activate_super(self, player: Player) -> None:
        self.audio.play("super")
        if player.character == "black_dave":
            cfg = self.data["players"]["black_dave"]
            full_map = bool(cfg.get("super_full_map", False))
            radius = float(cfg.get("super_radius", 190.0))
            damage = float(cfg.get("super_damage", 52.0))
            targets = [
                enemy
                for enemy in self.enemies
                if (enemy.targetable or (full_map and enemy.alive and enemy.state == "spawn"))
                and (
                    full_map
                    or math.hypot(enemy.x - player.x, (enemy.y - player.y) * 1.7) <= radius
                )
            ]
            effect_radius = float(
                cfg.get("super_effect_radius", float(self.meta["stage_width"]) if full_map else radius)
            )
            self.add_effect(
                "shock",
                player.x,
                player.y,
                radius=effect_radius,
                color=(70, 220, 255),
                duration=0.72,
            )
            self.add_effect(
                "bass_drop",
                LOGICAL_SIZE[0] * 0.5,
                LOGICAL_SIZE[1] * 0.5,
                radius=float(cfg.get("super_screen_radius", 330.0)),
                color=(91, 231, 255),
                duration=float(cfg.get("super_screen_seconds", 0.62)),
                world_space=False,
            )
            self.add_effect(
                "text",
                player.x,
                player.y - 72,
                text=str(cfg.get("super_text", "BASS DROP!")),
                color=(174, 247, 255),
                duration=0.82,
            )
            for enemy in targets:
                # Spawn telegraphs are visible enemies too.  A full-map Bass
                # Drop intentionally resolves them before their first chase
                # tick instead of letting a just-arrived raider survive the
                # screen wipe.
                if full_map and enemy.state == "spawn":
                    enemy._set_state("chase")
                enemy.take_damage(
                    damage,
                    self,
                    player,
                    hitstun=float(cfg.get("super_hitstun", 0.78)),
                    knockback=float(cfg.get("super_knockback", 96.0)),
                    knockdown=True,
                )
                self.add_effect(
                    "shock",
                    enemy.x,
                    enemy.y - 22,
                    radius=float(cfg.get("super_enemy_pulse_radius", 42.0)),
                    color=(134, 239, 255),
                    duration=0.36,
                )
            cleared_queued = 0
            if full_map and bool(cfg.get("super_clear_spawn_queue", True)):
                cleared_queued = len(self.spawn_queue)
                self.spawn_queue.clear()
                # Incoming hostile pipes cannot undermine a full-screen wipe.
                self.projectiles = [
                    projectile
                    for projectile in self.projectiles
                    if projectile.owner_team != "enemy"
                ]
            strength = float(cfg.get("super_camera_strength", 12.0))
            seconds = float(cfg.get("super_camera_seconds", 0.42))
            self.camera.trigger_shake(
                strength * self.options.shake_intensity,
                seconds,
                vertical_strength=strength * 0.48 * self.options.shake_intensity,
            )
            self.hitstop_remaining = max(
                self.hitstop_remaining,
                float(self.data["engine"]["physics"].get("super_hitstop", 0.11)),
            )
            self.impact_flash = max(self.impact_flash, float(cfg.get("super_flash_seconds", 0.14)))
            self.log_breadcrumb(
                "dave_bass_drop",
                full_map=full_map,
                enemies_hit=len(targets),
                queued_cleared=cleared_queued,
                boss_hit=any(enemy.kind == "couch" for enemy in targets),
            )
        else:
            cfg = self.data["players"]["shelly"]
            seconds = float(cfg["chief_frenzy_seconds"])
            if self.chiefs:
                chief = min(
                    self.chiefs,
                    key=lambda candidate: abs(candidate.x - player.x) + abs(candidate.y - player.y) * 1.5,
                )
                if self._chief_needs_recall(chief, player, urgent=True):
                    self.recall_chief_near(chief, player, reason="frenzy_super")
                chief.activate_frenzy(seconds, self)
                self.audio.play_character(player.character, "chief")
                burst_radius = max(1.0, float(cfg.get("frenzy_burst_radius", 390.0)))
                burst_limit = max(1, int(cfg.get("frenzy_burst_targets", 4)))
                burst_targets = sorted(
                    (
                        enemy
                        for enemy in self.enemies
                        if enemy.targetable
                        and enemy.kind != "couch"
                        and min(
                            math.hypot(enemy.x - player.x, (enemy.y - player.y) * 1.55),
                            math.hypot(enemy.x - chief.x, (enemy.y - chief.y) * 1.55),
                        )
                        <= burst_radius
                    ),
                    key=lambda enemy: (
                        min(
                            math.hypot(enemy.x - player.x, (enemy.y - player.y) * 1.55),
                            math.hypot(enemy.x - chief.x, (enemy.y - chief.y) * 1.55),
                        ),
                        enemy.enemy_id,
                    ),
                )[:burst_limit]
                burst_damage = max(1.0, float(cfg.get("frenzy_burst_damage", 260.0)))
                for enemy in burst_targets:
                    enemy.take_damage(
                        burst_damage,
                        self,
                        player,
                        hitstun=float(cfg.get("frenzy_burst_hitstun", 0.72)),
                        knockback=float(cfg.get("frenzy_burst_knockback", 78.0)),
                        knockdown=True,
                    )
                    self.add_effect(
                        "chief_frenzy",
                        enemy.x,
                        enemy.y - 28.0,
                        radius=float(cfg.get("frenzy_burst_enemy_radius", 48.0)),
                        color=(255, 221, 82),
                        duration=0.46,
                    )
                cinematic_seconds = max(0.10, float(cfg.get("frenzy_cinematic_seconds", 0.62)))
                self.shelly_frenzy_cinematic = ShellyFrenzyCinematic(
                    player_slot=player.slot,
                    chief_owner_slot=chief.owner.slot,
                    duration_seconds=cinematic_seconds,
                )
                self.add_effect(
                    "chief_frenzy",
                    player.x,
                    player.y - 24.0,
                    radius=float(cfg.get("frenzy_burst_screen_radius", 182.0)),
                    color=(255, 209, 71),
                    duration=0.72,
                )
                self.add_effect(
                    "text",
                    player.x,
                    player.y - 78.0,
                    text=str(cfg.get("super_name", "CHIEF, SIC 'EM!")),
                    color=(255, 227, 115),
                    duration=1.0,
                )
                shake_strength = float(cfg.get("frenzy_camera_strength", 9.0))
                self.camera.trigger_shake(
                    shake_strength * self.options.shake_intensity,
                    0.38,
                    vertical_strength=shake_strength * 0.45 * self.options.shake_intensity,
                )
                self.hitstop_remaining = max(
                    self.hitstop_remaining,
                    float(cfg.get("frenzy_hitstop_seconds", 0.08)),
                )
                self.impact_flash = max(self.impact_flash, float(cfg.get("frenzy_flash_seconds", 0.16)))
                if player.is_cpu:
                    self._cpu_shelly_frenzy_uses[player.slot] = self._cpu_shelly_frenzy_uses.get(player.slot, 0) + 1
                    self._cpu_shelly_frenzy_charge[player.slot] = 0.0
                    self._cpu_shelly_frenzy_rearm[player.slot] = max(
                        0.0,
                        float(self.data.get("companion_ai", {}).get("cpu_shelly_frenzy_rearm_seconds", 0.85)),
                    )
                self.log_breadcrumb(
                    "shelly_chief_frenzy",
                    player=player.slot + 1,
                    seconds=round(seconds, 2),
                    cpu=player.is_cpu,
                    burst_targets=len(burst_targets),
                    boss_excluded=any(enemy.kind == "couch" for enemy in self.enemies),
                )

    def enemy_attack(
        self,
        enemy: Enemy,
        *,
        range_x: float,
        range_y: float,
        damage: float,
        already_hit: set[tuple[str, int]] | None = None,
        hit_counts: dict[tuple[str, int], int] | None = None,
        last_hit_times: dict[tuple[str, int], float] | None = None,
        attack_time: float | None = None,
    ) -> bool:
        physics = self.data["engine"]["physics"]
        centre_offset = (
            0.0
            if enemy.state == "charge"
            else enemy.facing * (range_x * 0.5 - 4.0)
        )
        centre_x = enemy.x + centre_offset
        max_targets = max(1, int(physics.get("enemy_attack_max_targets", 1)))
        hit_memory = already_hit if already_hit is not None else set()
        counts = hit_counts if hit_counts is not None else {}
        times = last_hit_times if last_hit_times is not None else {}
        attack = HitBox(
            (
                "enemy_attack",
                enemy.enemy_id,
                enemy.attack_instance_id,
                enemy.attack_pattern or enemy.kind,
            ),
            ("enemy", enemy.enemy_id),
            "enemy",
            centre_x,
            enemy.y,
            half_width=range_x if enemy.state == "charge" else range_x * 0.5 + 4.0,
            half_depth=max(2.0, range_y - float(physics["player_radius_depth"])),
            height=38.0 if enemy.kind in {"cart", "couch"} else 32.0,
            damage=damage,
            stun=0.34,
            knockback_x=enemy.facing * (28.0 if enemy.state == "charge" else 14.0),
            hit_grounded=True,
            hit_airborne=True,
            blocked_tags=frozenset({"downed"}),
            hitstop_seconds=float(physics["heavy_hitstop"] if enemy.state == "charge" else physics["light_hitstop"]),
            camera_strength=4.0 if enemy.state == "charge" else 2.2,
            camera_seconds=0.15 if enemy.state == "charge" else 0.10,
            max_targets=max(1, max_targets - len(hit_memory)),
            max_hits_per_target=1,
            sweep_from_x=(
                None
                if enemy.hitbox_sweep_x is None
                else enemy.hitbox_sweep_x + centre_offset
            ),
            sweep_from_depth=enemy.hitbox_sweep_y,
            facing_x=float(enemy.facing),
            front_origin_x=enemy.x,
            front_origin_depth=enemy.y,
            rear_tolerance=float(physics.get("enemy_attack_rear_tolerance", 2.0)),
        )
        if len(hit_memory) >= max_targets:
            report = query_attack_detailed(
                attack,
                self._player_hurtboxes(),
                already_hit=hit_memory,
                hit_counts=counts,
                last_hit_times=times,
                now=attack_time,
            )
            self._record_attack_report(attack, self._target_cap_report(report))
            return False
        report = query_attack_detailed(
            attack,
            self._player_hurtboxes(),
            already_hit=hit_memory,
            hit_counts=counts,
            last_hit_times=times,
            now=attack_time,
        )
        self._record_attack_report(attack, report)
        players_by_id = {("player", player.slot): player for player in self.players}
        hit = False
        for contact in report.results:
            player = players_by_id.get(contact.target_id)
            if player is not None and player.take_damage(contact.damage, self, enemy):
                hit_memory.add(contact.target_id)
                counts[contact.target_id] = counts.get(contact.target_id, 0) + 1
                times[contact.target_id] = (
                    float(attack_time) if attack_time is not None else 0.0
                )
                self._apply_combat_impact(contact)
                hit = True
        return hit

    def enemy_projectile_hit(
        self,
        projectile: Projectile,
        old_x: float,
        old_y: float,
        old_z: float,
    ) -> bool:
        """Resolve a thrown pipe across its complete fixed-step trajectory."""

        radius_x = 7.0
        radius_depth = 5.0
        low_z = max(0.0, min(old_z, projectile.z) - 5.0)
        attack = HitBox(
            (
                "enemy_projectile",
                projectile.owner_id,
                projectile.attack_instance_id,
            ),
            ("enemy", projectile.owner_id),
            "enemy",
            projectile.x,
            projectile.y,
            elevation=low_z,
            half_width=radius_x,
            half_depth=radius_depth,
            height=max(10.0, abs(projectile.z - old_z) + 10.0),
            damage=projectile.damage,
            stun=0.34,
            knockback_x=(1.0 if projectile.vx >= 0.0 else -1.0) * 18.0,
            hit_grounded=True,
            hit_airborne=True,
            blocked_tags=frozenset({"downed"}),
            hitstop_seconds=float(self.data["engine"]["physics"]["light_hitstop"]),
            camera_strength=2.5,
            camera_seconds=0.10,
            max_targets=1,
            max_hits_per_target=1,
            sweep_from_x=old_x,
            sweep_from_depth=old_y,
            facing_x=0.0,
        )
        report = query_attack_detailed(attack, self._player_hurtboxes())
        self._record_attack_report(attack, report)
        if not report.results:
            return False
        players_by_id = {("player", player.slot): player for player in self.players}
        contact = report.results[0]
        player = players_by_id.get(contact.target_id)
        if player is None or not player.take_damage(contact.damage, self, projectile):
            return False
        self._apply_combat_impact(contact)
        return True

    def spawn_pipe(self, enemy: Enemy, target: Player) -> None:
        travel = 0.72
        self.projectiles.append(Projectile(
            x=enemy.x,
            y=enemy.y - 3,
            z=32.0,
            vx=(target.x - enemy.x) / travel,
            vy=(target.y - enemy.y) / travel,
            vz=105.0,
            damage=float(enemy.stats["damage"]),
            owner_team="enemy",
            kind="pipe",
            owner_id=enemy.enemy_id,
            attack_instance_id=enemy.attack_instance_id,
        ))
        self.audio.play("hit")

    def award_hit(self, player: Player, enemy: Enemy, amount: float) -> None:
        player.hit_count += 1
        player.score += int(self.data["scoring"]["hit"])
        player.combo_grace = float(self.data["scoring"]["combo_grace"])

    def enemy_defeated(self, enemy: Enemy, hitter: Player | None) -> None:
        if hitter is not None:
            hitter.ko_count += 1
            step = int(self.data["scoring"]["combo_step_hits"])
            multiplier = 1.0 + (hitter.hit_count // step) * float(self.data["scoring"]["combo_step_multiplier"])
            multiplier = min(float(self.data["scoring"]["combo_multiplier_cap"]), multiplier)
            hitter.score += round(float(enemy.stats["score"]) * multiplier)
        self.add_effect("text", enemy.x, enemy.y - 55, text="K.O.!", color=(255, 237, 91), duration=0.75)
        self._register_bb_eligible_ko(enemy)
        self._register_super_butane_eligible_ko(enemy)
        self.log_breadcrumb("enemy_defeated", enemy=enemy.kind, enemy_id=enemy.enemy_id, hitter=(hitter.slot + 1 if hitter else None))

    def add_effect(self, kind: str, x: float, y: float, **kwargs: Any) -> None:
        # Gameplay text, telegraphs, and pickup feedback are never culled.
        # Decorative particles share a strict density-scaled ceiling so the
        # cinematic preset cannot grow unbounded in four-player crowds.
        decorative = {"ember", "flame", "flame_burst", "flame_trail_left", "flame_trail_right", "scorch", "hit", "impact", "spark", "streak", "dust", "ring"}
        if kind in decorative:
            budget = max(24, int(112 * self.options.particle_density))
            current = sum(1 for effect in self.effects if effect.kind in decorative)
            if current >= budget:
                return
        expanded = bool(kwargs.pop("_expanded", False))
        self.effects.append(Effect(kind, x, y, **kwargs))
        # One centralized response stack keeps combat call sites meaningful
        # while giving different hit categories distinct, restrained accents.
        if (
            kind == "hit"
            and not expanded
            and self.options.particle_density >= 0.75
            and float(kwargs.get("duration", 0.35)) < 1.0
        ):
            color = kwargs.get("color", (255, 255, 255))
            direction = -1.0 if float(kwargs.get("direction", 1.0)) < 0.0 else 1.0
            radius = float(kwargs.get("radius", 14.0))
            strength = clamp(radius / 18.0, 0.7, 1.8)
            for index, angle in enumerate((-0.75, -0.25, 0.25, 0.75)):
                speed = (42.0 + index * 7.0) * strength
                self.add_effect(
                    "spark", x, y, color=color, radius=3.0 + strength,
                    duration=0.16 + index * 0.012, vx=direction * math.cos(angle) * speed,
                    vy=math.sin(angle) * speed - 18.0, gravity=90.0, drag=2.5,
                    scale_start=1.2, scale_end=0.35, alpha_start=235, alpha_end=0,
                    direction=direction,
                    _expanded=True,
                )
            self.add_effect("ring", x, y, color=color, radius=radius * 0.72,
                            duration=0.14, scale_start=0.55, scale_end=1.25,
                            alpha_start=180, alpha_end=0, _expanded=True)
            self.add_effect("dust", x, y + 8.0, color=(205, 171, 137), radius=radius * 0.55,
                            duration=0.24, vx=8.0 * direction, vy=-10.0,
                            gravity=24.0, drag=3.0, scale_start=0.6, scale_end=1.5,
                            alpha_start=120, alpha_end=0, direction=direction, _expanded=True)

    def _update_dave_flame_visuals(self, dt: float) -> None:
        """Advance visual-only ignition attached to enemies still in the scene."""

        if not self._dave_flame_visuals:
            return
        present_ids = {enemy.enemy_id for enemy in self.enemies}
        self._dave_flame_visuals = {
            enemy_id: remaining - dt
            for enemy_id, remaining in self._dave_flame_visuals.items()
            if enemy_id in present_ids and remaining - dt > 0.0
        }

    def record_player_damage(self, amount: float) -> None:
        """Accumulate actual health lost for the post-stage performance card."""

        if not self.level_stats.finished:
            self.level_stats.record_damage(amount)

    def draw(self, surface: pygame.Surface) -> None:
        if self.state in {"loading", "title"}:
            self._draw_title(surface)
        elif self.state == "character_select":
            self._draw_character_select(surface)
        elif self.state == "gameplay":
            self._draw_gameplay(surface)
        elif self.state in {"complete", "game_over"}:
            self._draw_end(surface)
        elif self.state == "epilogue":
            self._draw_epilogue(surface)
        elif self.state == "interlevel":
            self._draw_interlevel(surface)
        if self.controller_notice > 0.0 and not (self.state == "gameplay" and self.pause):
            message = f"CONTROLLERS CONNECTED: {self.input.controller_count}"
            self._panel(surface, pygame.Rect(212, 330, 216, 22), (11, 16, 27), (75, 218, 255))
            self._text(surface, self.font_small, message, (225, 248, 255), (320, 341), center=True)

    def _draw_title(self, surface: pygame.Surface) -> None:
        surface.blit(self.key_art, (0, 0))
        overlay = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        overlay.fill((5, 4, 16, 35))
        surface.blit(overlay, (0, 0))
        if self.state == "loading":
            self._panel(surface, pygame.Rect(178, 319, 284, 27), (9, 8, 20), (255, 208, 76))
            dots = "." * (1 + int(self.elapsed * 3) % 3)
            self._text(surface, self.font, f"LOADING SECOND STREET{dots}", (255, 238, 181), (320, 333), center=True)
        else:
            pulse = 175 + int(70 * (0.5 + 0.5 * math.sin(self.elapsed * 5.0)))
            title_button = pygame.Rect(145, 307, 350, 39)
            hovered = self.mouse_position is not None and title_button.collidepoint(self.mouse_position)
            self._panel(surface, title_button, (18, 22, 39) if hovered else (8, 7, 18), (255, 220, 104) if hovered else (70, 218, 255))
            self._text(surface, self.font, "PRESS ENTER OR CONTROLLER A / START", (pulse, 240, 255), (320, 322), center=True)
            self._text(surface, self.font_tiny, "1-4 PLAYER LOCAL CO-OP  •  FOUNDATION DEMO", (255, 221, 125), (320, 338), center=True)

    def _draw_character_select(self, surface: pygame.Surface) -> None:
        surface.blit(self.key_art, (0, 0))
        shade = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        shade.fill((4, 6, 17, 190))
        surface.blit(shade, (0, 0))
        self._text(surface, self.font_big, "CHOOSE WHO YOU CONTROL", (255, 222, 99), (320, 17), center=True)
        card_names = ("BLACK DAVE", "SHELLY + CHIEF", "LOCKED", "LOCKED")
        card_colors = ((45, 150, 190), (174, 75, 127), (25, 27, 36), (25, 27, 36))
        for index in range(4):
            x = 16 + index * 156
            rect = pygame.Rect(x, 39, 144, 177)
            hovered = self.mouse_position is not None and rect.collidepoint(self.mouse_position)
            border = (255, 222, 99) if hovered and index < 2 else ((104, 229, 255) if index < 2 else (75, 76, 88))
            self._panel(surface, rect, card_colors[index], border)
            self._text(surface, self.font_small, card_names[index], (255, 246, 210) if index < 2 else (112, 113, 125), (x + 72, 50), center=True)
            if index == 0:
                surface.blit(self.character_portraits["black_dave"], (x + 27, 59))
                pygame.draw.rect(surface, (105, 229, 255), (x + 25, 57, 94, 149), 2)
                self._text(surface, self.font_tiny, "FISTS • BASS DROP", (166, 239, 255), (x + 72, 205), center=True)
            elif index == 1:
                surface.blit(self.character_portraits["shelly"], (x + 27, 59))
                pygame.draw.rect(surface, (255, 143, 204), (x + 25, 57, 94, 149), 2)
                self._text(surface, self.font_tiny, "TORCH • CHIEF SUPPORT", (255, 188, 218), (x + 72, 205), center=True)
            else:
                pygame.draw.rect(surface, (10, 11, 16), (x + 27, 70, 90, 112))
                pygame.draw.ellipse(surface, (2, 3, 6), (x + 56, 82, 32, 36))
                pygame.draw.polygon(
                    surface,
                    (2, 3, 6),
                    ((x + 42, 174), (x + 47, 132), (x + 61, 115), (x + 83, 115), (x + 97, 132), (x + 102, 174)),
                )
                self._text(surface, self.font_huge, "?", (74, 76, 88), (x + 72, 137), center=True)
                self._text(surface, self.font_tiny, "COMING SOON", (91, 93, 106), (x + 72, 195), center=True)

        for index in range(4):
            x = 16 + index * 156
            rect = pygame.Rect(x, 229, 144, 91)
            color = PLAYER_COLORS[index]
            hovered = self.mouse_position is not None and rect.collidepoint(self.mouse_position)
            self._panel(surface, rect, (29, 35, 54) if hovered else (13, 16, 29), (255, 222, 99) if hovered else color)
            if index < len(self.select_slots):
                slot = self.select_slots[index]
                character = ("BLACK DAVE", "SHELLY")[slot.character_index]
                status = "YOU CONTROL • READY" if slot.confirmed else "YOU CONTROL • SELECTING"
                self._text(surface, self.font, f"P{index + 1}  {character}", color, (x + 72, 244), center=True)
                self._text(surface, self.font_tiny, status, (255, 240, 174), (x + 72, 267), center=True)
                self._text(surface, self.font_tiny, "< > CHOOSE  •  A/ENTER CONFIRM", (190, 200, 220), (x + 72, 288), center=True)
                self._text(surface, self.font_tiny, "PRESS AGAIN / START TO BEGIN", (150, 236, 255), (x + 72, 304), center=True)
            else:
                self._text(surface, self.font, f"P{index + 1}", color, (x + 72, 247), center=True)
                self._text(surface, self.font_small, "PRESS A / START", (212, 217, 230), (x + 72, 275), center=True)
                if index == 0:
                    self._text(surface, self.font_tiny, "OR ENTER", (155, 166, 188), (x + 72, 294), center=True)
        footer_top, footer_bottom = self._selection_footer_lines()
        self._text(surface, self.font_tiny, footer_top, (177, 229, 255), (320, 336), center=True)
        self._text(surface, self.font_tiny, footer_bottom, (145, 196, 224), (320, 348), center=True)

    def _draw_gameplay(self, surface: pygame.Surface) -> None:
        atmosphere = self.atmosphere.snapshot()
        pixel_art.draw_stage_background(
            surface,
            self._render_camera_x,
            float(self.meta["stage_width"]),
            self._camera_shake_y,
            theme=self.level_theme,
            atmosphere=atmosphere,
        )
        drawables: list[tuple[float, int, str, str, Any]] = []
        drawables.extend((chief.feet_y, 2, f"chief-{chief.owner.slot}", "chief", chief) for chief in self.chiefs)
        drawables.extend((enemy.feet_y, 2, f"enemy-{enemy.enemy_id}", "enemy", enemy) for enemy in self.enemies)
        drawables.extend((player.feet_y, 2, f"player-{player.slot}", "player", player) for player in self.players if player.state != "eliminated")
        drawables.extend((projectile.feet_y, 3, f"projectile-{index}", "projectile", projectile) for index, projectile in enumerate(self.projectiles))
        drawables.extend((pickup.feet_y, 1, f"pickup-{index}", "pickup", pickup) for index, pickup in enumerate(self.ammo_pickups))
        drawables.extend((pickup.feet_y, 1, f"butane-pickup-{index}", "pickup", pickup) for index, pickup in enumerate(self.super_butane_pickups))
        drawables.extend(
            (float(prop["depth"]), 1, str(prop["id"]), "prop", prop)
            for prop in self.data["stage_geometry"].get("obstacles", ())
        )
        drawables.extend(
            (
                float(feature["depth"]),
                1,
                str(feature["id"]),
                "scene_object",
                feature,
            )
            for feature in self.location_route.get("physical_scene_objects", ())
        )
        security_bubbles: list[tuple[float, float, int, int]] = []
        for _, _, _, kind, obj in sorted(drawables, key=lambda item: (item[0], item[1], item[2])):
            mapping_object = kind in {"prop", "scene_object"}
            world_x = (
                float(obj.get("world_x", obj.get("x")))
                if mapping_object
                else float(obj.x)
            )
            world_depth = float(obj["depth"]) if mapping_object else float(obj.y)
            elevation = (
                float(obj.get("elevation", 0.0))
                if kind == "scene_object"
                else 0.0
            )
            projected = self.projection.project(
                WorldPoint(world_x, world_depth, elevation),
                camera_x=self._render_camera_x,
                camera_depth=self._projection_depth_origin,
                screen_shake=(0.0, self._camera_shake_y),
            )
            x, y = projected.xy
            if kind == "prop":
                pixel_art.draw_stage_prop(surface, x, y, obj.get("kind", "planter"), self.frame // 4)
                continue
            if kind == "scene_object":
                pixel_art.draw_physical_scene_object(
                    surface,
                    x,
                    y,
                    obj,
                    frame=self.frame // 4,
                )
                continue
            if kind == "player":
                action_states = {"light", "heavy", "air_attack", "jump", "hurt", "downed", "super", "dodge", "pet", "ranged", "propane"}
                visual_state = (
                    f"attack_{obj.combo_step + 1}"
                    if obj.state == "light"
                    else "super" if obj.state == "propane" else obj.state
                )
                if obj.state == "light":
                    timed_move = obj._light_move()
                elif obj.state == "heavy":
                    timed_move = obj.moves["heavy"]
                elif obj.state == "air_attack":
                    timed_move = obj.moves["air"]
                else:
                    timed_move = None
                sprite_tick = (
                    999
                    if obj.state == "dead"
                    else timed_action_tick(
                        obj.character,
                        visual_state,
                        obj.state_clock,
                        float(timed_move["startup"]),
                        float(timed_move["active"]),
                        float(timed_move["recovery"]),
                    )
                    if timed_move is not None
                    else int(obj.state_clock * ANIMATION_PLAYBACK_HZ)
                    if obj.state in action_states
                    else obj.animation_tick
                )
                pixel_art.draw_player(
                    surface,
                    x,
                    y,
                    obj.z,
                    obj.facing,
                    visual_state,
                    obj.character,
                    sprite_tick,
                    PLAYER_COLORS[obj.color_index],
                    hit_flash=obj.hit_flash,
                )
                if obj.flaming_fists:
                    pixel_art.draw_fist_flames(
                        surface,
                        x,
                        y,
                        facing=obj.facing,
                        frame=self.frame,
                        z=obj.z,
                        state=visual_state,
                        sprite_tick=sprite_tick,
                    )
            elif kind == "chief":
                chief_state = obj.visual_animation_state
                chief_tick = (
                    int(max(0.0, 0.22 - min(0.22, obj.bite_flash)) * ANIMATION_PLAYBACK_HZ)
                    if obj.bite_flash > 0.0
                    else obj.animation_tick
                )
                pixel_art.draw_chief(surface, x, y, z=0, facing=obj.facing, state=chief_state, frame=chief_tick)
            elif kind == "enemy":
                if obj.kind == "couch":
                    if obj.state in {"bike_retreat", "bike_return"}:
                        # Couch visibly jumps toward/from the one authored BMX
                        # landmark. The parabolic lift is continuous with the
                        # small refuge-side offset, so invulnerability never
                        # occurs behind an ordinary grounded combat pose.
                        visual_x_offset, hop_height = self.couch_retreat_render_pose(obj)
                        pixel_art.draw_boss(
                            surface,
                            x + visual_x_offset,
                            y,
                            z=hop_height,
                            facing=obj.facing,
                            state="walk",
                            frame=int(obj.state_clock * ANIMATION_PLAYBACK_HZ),
                        )
                        continue
                    if obj.state == "bike_refuge":
                        visual_x_offset, _ = self.couch_retreat_render_pose(obj)
                        pixel_art.draw_boss(
                            surface,
                            x + visual_x_offset,
                            y,
                            z=0,
                            facing=-1,
                            state="laugh",
                            frame=int(obj.state_clock * ANIMATION_PLAYBACK_HZ),
                        )
                        continue
                    if obj.state == "recovery" and obj.attack_pattern:
                        boss_state = f"{obj.attack_pattern}_recovery"
                    else:
                        boss_state = obj.attack_pattern if obj.state in {"windup", "attack", "charge"} and obj.attack_pattern else obj.state
                    if obj.state == "windup":
                        boss_tick = action_segment_tick(
                            "couch",
                            boss_state,
                            "startup",
                            obj.state_clock,
                            obj.state_duration,
                        )
                    elif obj.state in {"attack", "charge"}:
                        boss_tick = action_segment_tick(
                            "couch",
                            boss_state,
                            "active",
                            obj.state_clock,
                            obj.state_duration,
                        )
                    elif obj.state == "recovery" and obj.attack_pattern:
                        boss_tick = action_segment_tick(
                            "couch",
                            boss_state,
                            "recovery",
                            obj.state_clock,
                            obj.state_duration,
                        )
                    else:
                        boss_action = obj.state in {"spawn", "hitstun", "down", "dead"}
                        boss_tick = int(obj.state_clock * ANIMATION_PLAYBACK_HZ) if boss_action else obj.animation_tick
                    pixel_art.draw_boss(
                        surface,
                        x,
                        y,
                        z=0,
                        facing=obj.facing,
                        state=boss_state,
                        frame=boss_tick,
                        hit_flash=obj.hit_flash,
                    )
                else:
                    enemy_state = (
                        "charge"
                        if obj.state == "charge"
                        else "attack"
                        if obj.state in {"windup", "attack", "recovery"}
                        else obj.state
                    )
                    actor_kind = "stick" if obj.kind in {"security", "security_guard", "guard"} else obj.kind
                    if obj.state == "windup":
                        enemy_tick = action_segment_tick(
                            actor_kind,
                            enemy_state,
                            "startup",
                            obj.state_clock,
                            obj.state_duration,
                        )
                    elif obj.state in {"attack", "charge"}:
                        enemy_tick = action_segment_tick(
                            actor_kind,
                            enemy_state,
                            "active",
                            obj.state_clock,
                            obj.state_duration,
                        )
                    elif obj.state == "recovery":
                        enemy_tick = action_segment_tick(
                            actor_kind,
                            enemy_state,
                            "recovery",
                            obj.state_clock,
                            obj.state_duration,
                        )
                    else:
                        enemy_action = obj.state in {"spawn", "hitstun", "down", "dead"}
                        enemy_tick = int(obj.state_clock * ANIMATION_PLAYBACK_HZ) if enemy_action else obj.animation_tick
                    pixel_art.draw_enemy(
                        surface,
                        x,
                        y,
                        z=0,
                        facing=obj.facing,
                        state=enemy_state,
                        kind=obj.kind,
                        frame=enemy_tick,
                        hit_flash=obj.hit_flash,
                    )
                    if obj.kind == "security" and obj.enemy_id in self._security_speech_by_enemy:
                        security_bubbles.append((x, y, obj.facing, obj.enemy_id))
                if self._dave_flame_visuals.get(obj.enemy_id, 0.0) > 0.0:
                    pixel_art.draw_effect(
                        surface,
                        x,
                        y - 8.0,
                        kind="enemy_fire",
                        frame=self.frame,
                        color=(255, 101, 28),
                        radius=24,
                    )
                if obj.state == "windup":
                    pygame.draw.ellipse(surface, (255, 82, 79), (int(x - 22), int(y - 4), 44, 8), 2)
            elif kind == "pickup":
                pixel_art.draw_pickup(surface, x, y, kind=obj.kind, frame=int(obj.age * 12.0))
            else:
                facing = 1 if obj.vx >= 0 else -1
                pixel_art.draw_projectile(surface, x, y, z=obj.z, facing=facing, kind=obj.kind, frame=self.frame // 2)

        for x, y, facing, enemy_id in security_bubbles:
            speech, remaining = self._security_speech_by_enemy.get(enemy_id, ("", 0.0))
            if not speech or remaining <= 0.0:
                continue
            text_width = self.font_tiny.size(speech)[0]
            bubble_width = min(220, max(96, text_width + 20))
            bubble_x = clamp(x, bubble_width * 0.5 + 3.0, LOGICAL_SIZE[0] - bubble_width * 0.5 - 3.0)
            bubble_bottom = max(44.0, y - 88.0)
            pixel_art.draw_comic_speech_bubble(
                surface,
                bubble_x,
                bubble_bottom,
                bubble_width,
                28,
                facing=facing,
            )
            self._text(surface, self.font_tiny, speech, (31, 40, 61), (bubble_x, bubble_bottom - 15), center=True)

        self._draw_effects(surface)
        pixel_art.draw_stage_foreground(
            surface,
            self._render_camera_x,
            float(self.meta["stage_width"]),
            self._camera_shake_y,
            theme=self.level_theme,
        )
        if self.impact_flash > 0.0:
            flash = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
            flash.fill(
                (
                    255,
                    244,
                    201,
                    min(56, int(self.impact_flash * 700 * self.options.flash_intensity)),
                )
            )
            surface.blit(flash, (0, 0))
        self._draw_shelly_frenzy_cinematic(surface)
        self._draw_hud(surface)
        self._draw_route_card(surface)
        if self.stage_banner_timer > 0.0 and self.route_card_timer <= 0.0:
            alpha = min(1.0, self.stage_banner_timer * 2.0)
            banner = pygame.Surface((280, 28), pygame.SRCALPHA)
            banner.fill((5, 8, 16, int(200 * alpha)))
            surface.blit(banner, (180, 102))
            self._text(surface, self.font_small, self.stage_banner, (255, 229, 111), (320, 109), center=True)
        self._draw_content_prompt(surface)
        self._draw_couch_refuge_taunt(surface)
        if self.debug:
            self._draw_debug(surface)
        if self.level_outro is not None and self.level_outro_frame is not None:
            self._draw_level_outro_overlay(surface)
        if self.boss_transition is not None:
            self._draw_boss_loading_overlay(surface)
        if self.pause:
            self._draw_pause_menu(surface)

    def _draw_couch_refuge_taunt(self, surface: pygame.Surface) -> None:
        retreat = self.couch_retreat
        if retreat is None or retreat.phase != "refuge":
            return
        taunt_seconds = max(2.0, float(retreat.boss.stats.get("retreat_taunt_seconds", 2.8)))
        if retreat.elapsed_seconds > taunt_seconds:
            return
        pixel_art.draw_comic_speech_bubble(surface, 320.0, 190.0, 408, 34, facing=-1)
        self._text(
            surface,
            self.font_small,
            retreat.taunt,
            (38, 42, 59),
            (320, 166),
            center=True,
        )

    def _draw_shelly_frenzy_cinematic(self, surface: pygame.Surface) -> None:
        """Darken the street briefly while Shelly and Chief stay fully lit."""

        cinematic = self.shelly_frenzy_cinematic
        if cinematic is None:
            return
        shelly = next(
            (player for player in self.players if player.slot == cinematic.player_slot and player.alive),
            None,
        )
        chief = next(
            (candidate for candidate in self.chiefs if candidate.owner.slot == cinematic.chief_owner_slot),
            None,
        )
        if shelly is None or chief is None:
            self.shelly_frenzy_cinematic = None
            return

        cfg = self.data["players"]["shelly"]
        pulse = 1.0 - abs(cinematic.progress * 2.0 - 1.0)
        dark_alpha = int(max(0, min(235, float(cfg.get("frenzy_cinematic_dark_alpha", 166)) * (0.78 + pulse * 0.22))))
        shade = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        shade.fill((3, 5, 14, dark_alpha))
        surface.blit(shade, (0, 0))

        def project_actor(actor: Any) -> tuple[float, float]:
            point = self.projection.project(
                WorldPoint(float(actor.x), float(actor.y)),
                camera_x=self._render_camera_x,
                camera_depth=self._projection_depth_origin,
                screen_shake=(0.0, self._camera_shake_y),
            )
            return point.xy

        shelly_x, shelly_y = project_actor(shelly)
        chief_x, chief_y = project_actor(chief)
        focus = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        radius = int(58 + pulse * 18)
        for x, y, vertical in ((shelly_x, shelly_y - 34.0, 1.15), (chief_x, chief_y - 22.0, 0.78)):
            rect = pygame.Rect(int(x - radius), int(y - radius * vertical), radius * 2, int(radius * vertical * 2))
            pygame.draw.ellipse(focus, (255, 211, 84, 36), rect)
            pygame.draw.ellipse(focus, (255, 239, 170, 195), rect, 2)
        surface.blit(focus, (0, 0))

        # Repaint the paired heroes above the tint so the eye reads a focused
        # comic panel instead of a generic global flash.
        action_states = {"light", "heavy", "air_attack", "jump", "hurt", "downed", "super", "dodge", "pet", "ranged", "propane"}
        shelly_tick = (
            999
            if shelly.state == "dead"
            else int(shelly.state_clock * ANIMATION_PLAYBACK_HZ)
            if shelly.state in action_states
            else shelly.animation_tick
        )
        shelly_state = (
            f"attack_{shelly.combo_step + 1}"
            if shelly.state == "light"
            else "super" if shelly.state == "propane" else shelly.state
        )
        pixel_art.draw_player(
            surface,
            shelly_x,
            shelly_y,
            shelly.z,
            shelly.facing,
            shelly_state,
            shelly.character,
            shelly_tick,
            PLAYER_COLORS[shelly.color_index],
        )
        chief_tick = (
            int(max(0.0, 0.22 - min(0.22, chief.bite_flash)) * ANIMATION_PLAYBACK_HZ)
            if chief.bite_flash > 0.0
            else chief.animation_tick
        )
        pixel_art.draw_chief(
            surface,
            chief_x,
            chief_y,
            z=0,
            facing=chief.facing,
            state=chief.visual_animation_state,
            frame=chief_tick,
        )

        panel = pygame.Rect(182, 18, 276, 40)
        self._panel(surface, panel, (13, 9, 20), (255, 218, 91))
        self._text(surface, self.font_big, "CHIEF, SIC 'EM!", (255, 232, 129), (320, 23), center=True)
        self._text(surface, self.font_tiny, "SHELLY + CHIEF  •  FRENZY BREAK", (255, 184, 218), (320, 47), center=True)

    def _draw_level_outro_overlay(self, surface: pygame.Surface) -> None:
        """Render Jerry's Level 1 warning with authored sprite poses and dialogue."""

        frame = self.level_outro_frame
        if frame is None:
            return
        # Dim the location first. Jerry is deliberately drawn above this tint
        # so the fully opaque atlas pixels remain solid in every cutscene pose.
        overlay = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        overlay.fill((5, 8, 15, 48))
        surface.blit(overlay, (0, 0))
        pose_state = {
            "arrival": "support",
            "warning": "talk",
            "clarification": "point",
            "reaction": "idle",
            "finished": "idle",
        }.get(frame.beat, "idle")
        jerry_provider = getattr(sprite_atlas, "jerry_frame", None)
        jerry_art = jerry_provider(pose_state, int(frame.beat_elapsed * 12.0)) if callable(jerry_provider) else None
        if jerry_art is not None:
            jerry_art = pixel_art.shade_authored_sprite(jerry_art, "jerry")
            max_height = 150
            if jerry_art.get_height() > max_height:
                scale = max_height / jerry_art.get_height()
                jerry_art = pygame.transform.scale(
                    jerry_art,
                    (max(1, int(jerry_art.get_width() * scale)), max_height),
                )
            jerry_world = self.projection.project(
                WorldPoint(float(self.meta["stage_width"]) - 118.0, 274.0),
                camera_x=self._render_camera_x,
                camera_depth=self._projection_depth_origin,
                screen_shake=(0.0, self._camera_shake_y),
            )
            surface.blit(jerry_art, jerry_art.get_rect(midbottom=(int(jerry_world.x), int(jerry_world.y))))

        panel = pygame.Rect(34, 28, 572, 110)
        accent = (244, 203, 112) if frame.speaker == "Jerry" else (98, 220, 255)
        self._panel(surface, panel, (10, 14, 24), accent)
        speaker = (frame.speaker or "EL CILANTRO • LEVEL 1 END").upper()
        self._text(surface, self.font_small, speaker, accent, (53, 40))
        dialogue_lines = {
            "arrival": (
                "A SKINNY OLD MAN IN A BLACK COWBOY HAT",
                "SETTLES HIS WALKER AT THE CURB...",
            ),
            "warning": (
                "HEY... I THINK I JUST SAW COUCH",
                "OVER BY THE 7-ELEVEN.",
            ),
            "clarification": (
                "I PASSED HER ON MY WAY HERE TO EL CILANTRO—",
                "THE MEXICAN FOOD RESTAURANT NEXT TO GOODWILL.",
            ),
            "reaction": (
                "THE 7-ELEVEN. GOT IT.",
                "THANKS, JERRY.",
            ),
            "finished": ("JERRY POINTS BACK DOWN SECOND STREET.",),
        }.get(frame.beat, (frame.dialogue.upper(),))
        for index, line in enumerate(dialogue_lines):
            self._text(surface, self.font, line, (242, 236, 211), (53, 66 + index * 24))
        if frame.awaiting_continue:
            pulse = 0.65 + 0.35 * math.sin(frame.beat_elapsed * 5.5)
            prompt_color = tuple(int(component * pulse) for component in (225, 241, 250))
            prompt_panel = pygame.Surface((376, 42), pygame.SRCALPHA)
            prompt_panel.fill((5, 8, 15, 220))
            surface.blit(prompt_panel, (132, 314))
            pygame.draw.rect(surface, (74, 154, 181), (132, 314, 376, 42), 1)
            self._text(
                surface,
                self.font_small,
                "PRESS A BUTTON TO CONTINUE",
                prompt_color,
                (320, 326),
                center=True,
            )
            self._text(
                surface,
                self.font_tiny,
                "CLICK / ENTER / A / X  •  DODGE / B SKIPS  •  ESC PAUSES",
                (174, 200, 215),
                (320, 345),
                center=True,
            )
        else:
            self._text(
                surface,
                self.font_tiny,
                "JERRY IS SETTLING IN...",
                (207, 225, 236),
                (320, 343),
                center=True,
            )

    def _draw_boss_loading_overlay(self, surface: pygame.Surface) -> None:
        frame = self.boss_transition_frame
        if frame is None:
            return
        transition = self.boss_transition
        assert transition is not None
        relocate_at = transition.relocate_seconds
        if frame.elapsed_seconds < relocate_at:
            overlay = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
            overlay.fill((3, 4, 12, 235))
            panel = pygame.Rect(118, 112, 404, 132)
            self._panel(overlay, panel, (8, 12, 24), (255, 190, 82))
            dots = "." * (1 + int(frame.elapsed_seconds * 4.0) % 3)
            self._text(overlay, self.font_big, f"LOADING COUCH'S BLOCK{dots}", (255, 226, 136), (320, 139), center=True)
            self._text(overlay, self.font, "PREPARING AWAKEN CHURCH SHOWDOWN", (142, 225, 255), (320, 181), center=True)
            overlay.set_alpha(max(0, min(255, int(round(255 * frame.overlay_alpha)))))
            surface.blit(overlay, (0, 0))
            return
        # A short comic-book confrontation replaces the silent pre-boss freeze.
        scene_time = frame.elapsed_seconds - relocate_at
        # The single BMX is already painted at its manifest world coordinate;
        # only Couch is added here, beside that same persistent prop.
        bmx_screen_x = self._landmark_world_x("daves_bmx") - self._render_camera_x
        couch_screen_x = clamp(bmx_screen_x + 56.0, 54.0, LOGICAL_SIZE[0] - 54.0)
        pixel_art.draw_boss(
            surface,
            couch_screen_x,
            278,
            facing=-1,
            state="laugh" if scene_time > 4.0 else "idle",
            frame=self.frame,
        )
        panel_index = 0 if scene_time < 2.0 else 1 if scene_time < 4.0 else 2
        speakers = (
            ("COUCH", "WHAT DO YOU WANT, DAVID?", (255, 142, 201), pygame.Rect(42, 28, 300, 68)),
            ("DAVE", "YOU KNOW THAT'S MY BIKE, COUCH.", (105, 225, 255), pygame.Rect(42, 28, 330, 68)),
            ("COUCH", "OH REALLY? I PAID FOR IT SO HA HA.", (255, 142, 201), pygame.Rect(30, 20, 368, 86)),
        )
        speaker, line, accent, rect = speakers[panel_index]
        self._panel(surface, rect, (10, 14, 28), accent)
        self._text(surface, self.font_tiny, speaker, accent, (rect.x + 12, rect.y + 9))
        self._text(surface, self.font, line, (255, 243, 216), (rect.x + 12, rect.y + 26))
        if panel_index == 2:
            self._text(surface, self.font, "WHAT YOU GONNA DO?  HA HA!", (255, 243, 216), (rect.x + 12, rect.y + 49))
        self._text(surface, self.font_tiny, "AWAKEN CHURCH PARKING LOT  •  FINAL SHOWDOWN", (255, 219, 118), (320, 337), center=True)

    def _draw_pause_menu(self, surface: pygame.Surface) -> None:
        shade = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        shade.fill((2, 4, 13, 218))
        for offset in range(-360, 720, 42):
            pygame.draw.line(shade, (43, 113, 147, 18), (offset, 0), (offset - 180, 360), 2)
        surface.blit(shade, (0, 0))

        if self.pause_page == "controls":
            self._draw_pause_controls(surface)
        elif self.pause_page.startswith("confirm_"):
            self._draw_pause_confirmation(surface)
        else:
            self._draw_pause_root(surface)

    def _draw_pause_root(self, surface: pygame.Surface) -> None:
        panel = pygame.Rect(137, 28, 366, 304)
        pulse = 205 + int(35 * (0.5 + 0.5 * math.sin(self.elapsed * 4.5)))
        self._panel(surface, panel, (8, 12, 25), (69, 202, pulse))
        pygame.draw.rect(surface, (255, 211, 83), (panel.x + 2, panel.y + 2, panel.width - 4, 4))
        self._text(surface, self.font_big, "GAME PAUSED", (255, 225, 119), (320, 48), center=True)
        self._text(surface, self.font_tiny, "SECOND STREET  •  FATE IS WAITING", (148, 221, 245), (320, 72), center=True)

        for index, (_, label) in enumerate(PAUSE_MENU_ITEMS):
            rect = pygame.Rect(183, 88 + index * 47, 274, 38)
            selected = index == self.pause_selection
            fill = (39, 38, 48) if selected else (13, 18, 32)
            border = (255, 215, 86) if selected else (54, 88, 111)
            self._panel(surface, rect, fill, border)
            if selected:
                pygame.draw.rect(surface, (255, 215, 86), (rect.x, rect.y, 6, rect.height))
                self._text(surface, self.font, ">", (255, 232, 139), (rect.x + 21, rect.centery), center=True)
            color = (255, 244, 207) if selected else (168, 190, 207)
            self._text(surface, self.font, label, color, rect.center, center=True)

        self._text(surface, self.font_tiny, "ARROWS / WASD / STICK / D-PAD  •  ENTER / A SELECT", (177, 225, 241), (320, 291), center=True)
        self._text(surface, self.font_tiny, "ESC / B / START  RESUME", (255, 213, 106), (320, 311), center=True)

    def _draw_pause_controls(self, surface: pygame.Surface) -> None:
        panel = pygame.Rect(37, 17, 566, 326)
        self._panel(surface, panel, (8, 12, 25), (76, 211, 240))
        pygame.draw.rect(surface, (255, 211, 83), (panel.x + 2, panel.y + 2, panel.width - 4, 4))
        self._text(surface, self.font_big, "CONTROLS", (255, 225, 119), (320, 36), center=True)
        self._text(surface, self.font_tiny, "EVERY PLAYER CAN PAUSE AND NAVIGATE", (148, 221, 245), (320, 60), center=True)

        left_panel = pygame.Rect(53, 72, 257, 226)
        right_panel = pygame.Rect(330, 72, 257, 226)
        self._panel(surface, left_panel, (12, 18, 32), (75, 143, 176))
        self._panel(surface, right_panel, (12, 18, 32), (75, 143, 176))
        self._text(surface, self.font, "KEYBOARD", (117, 226, 255), (left_panel.centerx, 80), center=True)
        self._text(surface, self.font, "CONTROLLER", (255, 187, 225), (right_panel.centerx, 80), center=True)

        for index, (label, value) in enumerate(KEYBOARD_CONTROLS):
            y = 104 + index * 20
            self._text(surface, self.font_tiny, label, (166, 195, 214), (left_panel.x + 11, y))
            self._text(surface, self.font_tiny, value, (255, 239, 184), (left_panel.right - 10, y), right=True)
        for index, (label, value) in enumerate(CONTROLLER_CONTROLS):
            y = 104 + index * 20
            self._text(surface, self.font_tiny, label, (199, 179, 205), (right_panel.x + 11, y))
            self._text(surface, self.font_tiny, value, (255, 239, 184), (right_panel.right - 10, y), right=True)

        self._text(surface, self.font_small, "ESC / B / START  BACK", (255, 220, 108), (320, 313), center=True)
        self._text(surface, self.font_tiny, "ENTER / SPACE / A ALSO RETURNS", (154, 205, 226), (320, 329), center=True)

    def _draw_pause_confirmation(self, surface: pygame.Surface) -> None:
        exiting_game = self.pause_page == "confirm_exit_game"
        panel = pygame.Rect(112, 69, 416, 224)
        accent = (255, 103, 126) if exiting_game else (255, 187, 79)
        self._panel(surface, panel, (18, 12, 24), accent)
        pygame.draw.rect(surface, accent, (panel.x + 2, panel.y + 2, panel.width - 4, 5))
        title = "EXIT THE GAME?" if exiting_game else "RETURN TO MAIN MENU?"
        self._text(surface, self.font_big, title, (255, 226, 159), (320, 92), center=True)
        self._text(surface, self.font, "CURRENT SECOND STREET PROGRESS WILL BE LOST.", (222, 202, 211), (320, 130), center=True)
        self._text(surface, self.font_small, "Are you sure you want to leave this run?", (165, 190, 208), (320, 154), center=True)

        labels = ("CANCEL", "EXIT GAME" if exiting_game else "MAIN MENU")
        for index, label in enumerate(labels):
            rect = pygame.Rect(154 + index * 178, 190, 154, 43)
            selected = index == self.pause_confirm_selection
            fill = (43, 40, 48) if selected else (12, 17, 29)
            border = (113, 230, 255) if selected and index == 0 else (accent if selected else (65, 78, 96))
            self._panel(surface, rect, fill, border)
            self._text(surface, self.font, label, (255, 242, 207) if selected else (157, 177, 194), rect.center, center=True)
        self._text(surface, self.font_tiny, "ARROWS / WASD / STICK  CHOOSE  •  ENTER / A CONFIRM", (172, 217, 235), (320, 257), center=True)
        self._text(surface, self.font_tiny, "ESC / B / START  CANCEL", (255, 214, 113), (320, 274), center=True)

    def _draw_effects(self, surface: pygame.Surface) -> None:
        # The logical gameplay canvas is normally an RGB surface.  Keep the
        # new fading particles on one RGBA overlay so alpha ramps remain real
        # compositing instead of being silently discarded by pygame.draw.
        particle_overlay = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        for effect in self.effects:
            if effect.projected:
                point = self.projection.project(
                    WorldPoint(effect.x, effect.y, effect.elevation),
                    camera_x=self._render_camera_x,
                    camera_depth=self._projection_depth_origin,
                    screen_shake=(0.0, self._camera_shake_y),
                )
                x, y = point.xy
            elif effect.world_space:
                x = effect.x - self._render_camera_x
                y = effect.y + self._camera_shake_y
            else:
                x = effect.x
                y = effect.y
            progress = effect.progress
            if effect.kind == "shock":
                radius = max(2, int(effect.radius * progress))
                pygame.draw.ellipse(surface, effect.color, (int(x - radius), int(y - radius * 0.35), radius * 2, int(radius * 0.7)), max(1, 4 - int(progress * 3)))
            elif effect.kind == "fist":
                radius = max(4, int(effect.radius * (0.55 + progress * 0.95)))
                core = max(2, radius // 4)
                # A compact, readable cyan/white punch aura keeps Dave's fists
                # legible without adding a separate non-pixel particle system.
                pygame.draw.circle(surface, (13, 29, 45), (int(x), int(y)), radius + 2)
                pygame.draw.circle(surface, effect.color, (int(x), int(y)), radius, max(1, 3 - int(progress * 2)))
                pygame.draw.circle(surface, (248, 255, 255), (int(x), int(y)), core)
                for angle in (0.0, math.tau * 0.25, math.tau * 0.5, math.tau * 0.75):
                    inner = radius * 0.52
                    outer = radius * (0.84 + progress * 0.28)
                    start = (int(x + math.cos(angle) * inner), int(y + math.sin(angle) * inner))
                    end = (int(x + math.cos(angle) * outer), int(y + math.sin(angle) * outer))
                    pygame.draw.line(surface, effect.color, start, end, 2)
            elif effect.kind == "bass_drop":
                radius = max(8, int(effect.radius * (0.14 + progress * 0.86)))
                # Screen-space pulses make the full-map wipe feel immediate
                # even when its farthest enemies are outside the current camera.
                for multiplier, width in ((1.0, 4), (0.67, 3), (0.35, 2)):
                    pulse = max(6, int(radius * multiplier))
                    pygame.draw.ellipse(
                        surface,
                        effect.color,
                        (int(x - pulse), int(y - pulse * 0.42), pulse * 2, max(4, int(pulse * 0.84))),
                        width,
                    )
                flash_alpha = max(0, int((1.0 - progress) * 74))
                flash = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
                flash.fill((*effect.color, flash_alpha))
                surface.blit(flash, (0, 0))
            elif effect.kind == "chief_frenzy":
                radius = max(10, int(effect.radius * (0.34 + progress * 0.86)))
                # Concentric gold/red rings plus four quick slash rays read as
                # Chief's sudden all-in charge without relying on a new asset.
                for multiplier, width in ((1.0, 4), (0.66, 3), (0.34, 2)):
                    pulse = max(6, int(radius * multiplier))
                    pygame.draw.ellipse(
                        surface,
                        effect.color,
                        (int(x - pulse), int(y - pulse * 0.45), pulse * 2, max(4, int(pulse * 0.9))),
                        width,
                    )
                ray_length = max(8, int(radius * (0.52 + progress * 0.35)))
                for angle in (0.15, 1.72, 3.29, 4.86):
                    start = (int(x + math.cos(angle) * radius * 0.18), int(y + math.sin(angle) * radius * 0.12))
                    end = (int(x + math.cos(angle) * ray_length), int(y + math.sin(angle) * ray_length * 0.48))
                    pygame.draw.line(surface, (255, 246, 184), start, end, 2)
            elif effect.kind == "hit":
                pixel_art.draw_effect(
                    surface,
                    x,
                    y,
                    kind="hit",
                    frame=int(progress * 4.0),
                    color=effect.color,
                    radius=max(12, int(effect.radius)),
                )
            elif effect.kind in {"spark", "streak", "dust", "ring"}:
                scale = effect.visual_scale
                alpha = effect.visual_alpha
                tint = (*effect.color, alpha)
                if effect.kind == "ring":
                    radius = max(2, int(effect.radius * scale))
                    pygame.draw.ellipse(particle_overlay, tint, (int(x-radius), int(y-radius*0.42), radius*2, max(2, int(radius*0.84))), 2)
                elif effect.kind == "dust":
                    radius = max(2, int(effect.radius * scale))
                    pygame.draw.ellipse(particle_overlay, tint, (int(x-radius), int(y-radius*0.35), radius*2, max(2, int(radius*0.7))))
                else:
                    length = max(3, int(effect.radius * (1.0 + abs(effect.vx + effect.vy) / 90.0) * scale))
                    direction = -1.0 if effect.direction < 0.0 else 1.0
                    pygame.draw.line(
                        particle_overlay,
                        tint,
                        (int(x - direction * length), int(y + length * 0.35)),
                        (int(x + direction * length), int(y - length * 0.35)),
                        2,
                    )
            elif effect.kind.startswith("flame_trail_"):
                pixel_art.draw_effect(
                    surface,
                    x,
                    y,
                    kind=effect.kind,
                    frame=int(progress * 7.0),
                    color=effect.color,
                    radius=max(16, int(effect.radius)),
                )
            elif effect.kind == "flame_burst":
                pixel_art.draw_effect(
                    surface,
                    x,
                    y,
                    kind="flame_burst",
                    frame=int(progress * 6.0),
                    color=effect.color,
                    radius=max(18, int(effect.radius)),
                )
            elif effect.kind == "scorch":
                pixel_art.draw_effect(
                    surface,
                    x,
                    y,
                    kind="scorch",
                    frame=int(progress * 6.0),
                    color=effect.color,
                    radius=max(12, int(effect.radius)),
                )
            elif effect.kind == "ember":
                pixel_art.draw_effect(
                    surface,
                    x,
                    y,
                    kind="ember",
                    frame=int(progress * 6.0),
                    color=effect.color,
                    radius=max(6, int(effect.radius)),
                )
            elif effect.kind == "flame":
                pixel_art.draw_effect(
                    surface,
                    x,
                    y,
                    kind="flame",
                    frame=int(progress * 6.0),
                    color=effect.color,
                    radius=max(10, int(effect.radius)),
                )
            elif effect.kind == "impact":
                radius = max(5, int(effect.radius * (0.45 + progress * 0.85)))
                flat_height = max(4, radius // 2)
                pygame.draw.ellipse(
                    surface,
                    (72, 35, 43),
                    (int(x - radius), int(y - flat_height), radius * 2, flat_height * 2),
                    4,
                )
                pygame.draw.ellipse(
                    surface,
                    effect.color,
                    (int(x - radius), int(y - flat_height), radius * 2, flat_height * 2),
                    2,
                )
                core = max(2, int((1.0 - progress) * 8))
                pygame.draw.line(surface, (255, 255, 235), (int(x - core), int(y)), (int(x + core), int(y)), 2)
                pygame.draw.line(surface, (255, 255, 235), (int(x), int(y - core)), (int(x), int(y + core)), 2)
            elif effect.kind == "spawn":
                radius = int(effect.radius * (1.0 - progress))
                pygame.draw.ellipse(surface, effect.color, (int(x - radius), int(y - radius * 0.5), radius * 2, max(2, radius)), 2)
            elif effect.kind == "text":
                self._text(surface, self.font_small, effect.text, effect.color, (int(x), int(y)), center=True)
        surface.blit(particle_overlay, (0, 0))

    @staticmethod
    def _compact_hud_rects(player_count: int, scale: float = 1.0) -> tuple[pygame.Rect, ...]:
        """Return safe-corner HUD slots for every supported local roster."""

        count = max(0, min(4, int(player_count)))
        if count == 0:
            return ()
        factor = clamp(float(scale), 0.80, 1.50)
        panel_w = int(round(174 * factor))
        panel_h = int(round(43 * factor))
        margin = 6
        positions = (
            (margin, margin),
            (LOGICAL_SIZE[0] - margin - panel_w, margin),
            (margin, margin + panel_h + 7),
            (LOGICAL_SIZE[0] - margin - panel_w, margin + panel_h + 7),
        )
        return tuple(pygame.Rect(x, y, panel_w, panel_h) for x, y in positions[:count])

    def _draw_route_card(self, surface: pygame.Surface) -> None:
        """Draw a short route objective without covering the combat lane."""

        if self.route_card_timer <= 0.0:
            return
        alpha = min(1.0, self.route_card_timer * 1.8)
        card = pygame.Surface((232, 43), pygame.SRCALPHA)
        card.fill((5, 10, 20, int(214 * alpha)))
        pygame.draw.rect(card, (87, 216, 248, int(230 * alpha)), card.get_rect(), 1)
        surface.blit(card, (7, 104))
        heading = f"LEVEL {self.level_number} • {self.level_title}".upper()
        objective = self.route_card_objective[:34]
        self._text(surface, self.font_small, heading, (255, 224, 112), (14, 110))
        self._text(surface, self.font_tiny, objective, (201, 234, 245), (14, 130))
        self._text(surface, self.font_tiny, "STREET ROUTE", (123, 205, 231), (14, 143))

    def _draw_content_prompt(self, surface: pygame.Surface) -> None:
        """Offer optional authored content from a safe, compact screen edge."""

        if not self._content_optional_prompt or self.encounter_active:
            return
        text = self._content_optional_prompt
        width = min(292, max(154, self.font_tiny.size(text)[0] + 22))
        rect = pygame.Rect((LOGICAL_SIZE[0] - width) // 2, 332, width, 20)
        prompt = pygame.Surface(rect.size, pygame.SRCALPHA)
        prompt.fill((8, 13, 22, 214))
        pygame.draw.rect(prompt, (255, 211, 98, 228), prompt.get_rect(), 1)
        surface.blit(prompt, rect)
        self._text(surface, self.font_tiny, text, (255, 234, 166), rect.center, center=True)

    def _draw_hud(self, surface: pygame.Surface) -> None:
        """Render concise corner cards that preserve the combat sightline."""

        factor = clamp(float(self.options.hud_scale), 0.80, 1.50)
        layer = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        cards = self._compact_hud_rects(len(self.players), factor)
        detail_font = self.font_small if factor >= 1.25 else self.font_tiny
        chief_max = float(self.data.get("chief", {}).get("command_meter_max", 100.0))
        inset = max(4, int(round(5 * factor)))
        for index, (player, rect) in enumerate(zip(self.players, cards)):
            color = PLAYER_COLORS[index % len(PLAYER_COLORS)]
            self._panel(layer, rect, (9, 13, 23), color)
            name = str(self.data["players"][player.character]["display_name"]).upper()
            owner_label = "CPU" if player.is_cpu else f"P{player.slot + 1}"
            lives_label = "DEV ∞" if player.unlimited_lives else f"♥{player.lives}"
            self._text(layer, detail_font, f"{owner_label} {name}", color, (rect.x + inset, rect.y + inset - 1))
            self._text(layer, self.font_tiny, f"{player.score:06d} {lives_label}", (238, 239, 226), (rect.right - inset, rect.y + inset), right=True)

            bar_x = rect.x + inset
            bar_w = rect.width - inset * 2
            health_y = rect.y + max(15, int(round(16 * factor)))
            self._bar(layer, pygame.Rect(bar_x, health_y, bar_w, max(5, int(round(6 * factor)))), player.health / max(1, player.max_health), (84, 222, 119), (56, 25, 30))
            super_y = health_y + max(8, int(round(9 * factor)))
            self._bar(layer, pygame.Rect(bar_x, super_y, bar_w, max(3, int(round(4 * factor)))), player.super_meter / 100.0, (69, 190, 255), (22, 41, 65))
            chief_y = super_y + max(6, int(round(6 * factor)))
            self._bar(layer, pygame.Rect(bar_x, chief_y, bar_w, max(3, int(round(3 * factor)))), player.chief_meter / max(1.0, chief_max), (255, 201, 61), (66, 45, 19))

            resource_y = chief_y + max(5, int(round(5 * factor)))
            if player.character == "black_dave":
                bb_max = max(1, int(self.data.get("bb_gun", {}).get("max_ammo", 6)))
                label = f"BB {player.bb_ammo}/{bb_max}"
                self._text(layer, self.font_tiny, label, (142, 225, 255), (bar_x, resource_y - 1))
                segment_x = bar_x + min(max(31, self.font_tiny.size(label)[0] + 4), max(31, bar_w // 3))
                segment_w = max(2, (rect.right - inset - segment_x - (bb_max - 1)) // bb_max)
                for segment in range(bb_max):
                    ammo = pygame.Rect(segment_x + segment * (segment_w + 1), resource_y, segment_w, max(4, int(round(5 * factor))))
                    pygame.draw.rect(layer, (26, 47, 61), ammo)
                    pygame.draw.rect(layer, (77, 119, 137), ammo, 1)
                    if segment < player.bb_ammo:
                        pygame.draw.rect(layer, (115, 224, 255), ammo.inflate(-2, -2))
            elif player.character == "shelly":
                propane_cfg = self.data.get("shelly_propane", {})
                propane_max = max(1.0, float(propane_cfg.get("meter_max", 100.0)))
                butane_label = "BUTANE"
                self._text(layer, self.font_tiny, butane_label, (255, 193, 100), (bar_x, resource_y - 1))
                resource_x = bar_x + self.font_tiny.size(butane_label)[0] + 4
                resource = pygame.Rect(resource_x, resource_y, max(8, rect.right - inset - resource_x), max(4, int(round(5 * factor))))
                self._bar(layer, resource, player.super_butane_meter / propane_max, (255, 132, 47), (79, 35, 19))
            status = "FIRE" if player.flaming_fists else ""
            if player.state == "downed":
                status = f"REVIVE {player.down_timer:0.1f}"
            if status:
                self._text(layer, self.font_tiny, status, (255, 231, 94), (rect.right - inset, resource_y - 1), right=True)

        boss = next((enemy for enemy in self.enemies if enemy.kind == "couch" and enemy.alive), None)
        if boss:
            top_card_width = cards[0].width if cards else 0
            center_space = LOGICAL_SIZE[0] - top_card_width * (2 if len(cards) >= 2 else 1) - 18
            boss_w = 214 if center_space >= 214 else min(214, LOGICAL_SIZE[0] - 20)
            if center_space >= 214:
                boss_rect = pygame.Rect((LOGICAL_SIZE[0] - boss_w) // 2, 6, boss_w, 18)
            else:
                lowest = max((rect.bottom for rect in cards), default=0)
                boss_rect = pygame.Rect((LOGICAL_SIZE[0] - boss_w) // 2, lowest + 7, boss_w, 18)
            self._panel(layer, boss_rect, (27, 11, 27), (255, 102, 206))
            boss_label = (
                f"COUCH • CREW {boss.couch_retreats_started}/2"
                if boss.state in COUCH_RETREAT_STATES
                else "COUCH"
            )
            self._text(layer, self.font_tiny, boss_label, (255, 205, 236), (boss_rect.centerx, boss_rect.y + 3), center=True)
            self._bar(layer, pygame.Rect(boss_rect.x + 5, boss_rect.bottom - 6, boss_rect.width - 10, 3), boss.health / boss.max_health, (239, 78, 174), (69, 20, 57))
        layer.set_alpha(int(round(255 * self.options.hud_opacity)))
        surface.blit(layer, (0, 0))

    def _draw_debug(self, surface: pygame.Surface) -> None:
        rect = pygame.Rect(6, 88, 354, 260)
        self._panel(surface, rect, (4, 7, 12), (74, 236, 160))
        player = self.players[0] if self.players else None
        phase = "none"
        if player is not None and player.state in {"light", "heavy", "air_attack"}:
            move = (
                player._light_move()
                if player.state == "light"
                else player.moves["heavy"]
                if player.state == "heavy"
                else player.moves["air"]
            )
            active_start = float(move["startup"])
            active_end = active_start + float(move["active"])
            phase = (
                "startup"
                if player.state_clock < active_start
                else "active"
                if player.state_clock < active_end
                else "recovery"
            )
        evaluation = (
            next(
                (
                    candidate
                    for candidate in self._debug_last_evaluations
                    if not candidate.accepted
                ),
                None,
            )
            or (self._debug_last_evaluations[0] if self._debug_last_evaluations else None)
        )
        attack_age = (
            self.frame - self._debug_last_query_frame
            if self._debug_last_query_frame >= 0
            else None
        )
        visible_attack = (
            self._debug_last_attack
            if attack_age is not None and 0 <= attack_age <= 45
            else None
        )

        def actor_for(entity_id: Any) -> Any | None:
            if not isinstance(entity_id, tuple) or len(entity_id) != 2:
                return None
            group, number = entity_id
            actors = self.players if group == "player" else self.enemies if group == "enemy" else ()
            return next(
                (
                    actor
                    for actor in actors
                    if int(getattr(actor, "slot", getattr(actor, "enemy_id", -1))) == int(number)
                ),
                None,
            )

        evaluated_actor = actor_for(evaluation.target_id) if evaluation is not None else None
        if self._debug_last_attack is not None and evaluated_actor is not None:
            _, origin_depth = self._debug_last_attack.front_origin
            depth_delta = abs(float(evaluated_actor.y) - origin_depth)
            elevation_delta = abs(
                float(getattr(evaluated_actor, "z", 0.0))
                - self._debug_last_attack.elevation
            )
            delta_line = f"DELTA D={depth_delta:.2f} Z={elevation_delta:.2f}"
        else:
            delta_line = "DELTA D=-- Z=--"
        if self._debug_last_contacts:
            contact = self._debug_last_contacts[0]
            contact_line = f"CONTACT X={contact.contact_x:.1f} D={contact.contact_depth:.1f}"
        else:
            contact_line = "CONTACT X=-- D=--"
        try:
            stage_debug = pixel_art.stage_world_debug_snapshot(
                self.location_route["theme"],
                self._render_camera_x,
                LOGICAL_SIZE[0],
            )
            active_chunks = ",".join(stage_debug["active_chunk_ids"]) or "NONE"
            chunk_line = (
                f"CHUNKS {stage_debug['active_chunk_count']}/{stage_debug['total_chunk_count']} "
                f"ACTIVE={active_chunks}"
            )
            layer_line = "LAYERS " + " ".join(
                f"{name}={offset}"
                for name, offset in stage_debug["layer_offsets"].items()
            )
        except (KeyError, RuntimeError, ValueError) as exc:
            chunk_line = f"CHUNKS ERROR {type(exc).__name__}"
            layer_line = "LAYERS unavailable"
        lines = [
            f"DEBUG  FRAME {self.frame}  ENGINE {self.VERSION}",
            f"CAM {self.camera_x:.1f} GATE {self.active_gate} LOCK {self.camera.encounter_locked}",
            f"ZONE {(self._last_camera_view.zone_name if self._last_camera_view else None)} HITSTOP {self.hitstop_remaining:.3f}",
            f"ROUTE {self.location_route['theme']} W={int(self.location_route['world_width'])}",
            chunk_line,
            layer_line,
            f"ENEMIES {len(self.enemies)} QUEUED {len(self.spawn_queue)} TOKENS {self.attack_tokens_used}",
            (
                f"P{player.slot + 1} {player.state}:{phase} CF={int(player.state_clock * 60):02d} "
                f"FACE={player.facing:+d} ID={player.attack_instance_id}"
                if player is not None
                else "NO PLAYERS"
            ),
            (
                f"BUFFER L={player.light_buffer_remaining:.3f} "
                f"H={player.heavy_buffer_remaining:.3f} COMBO={player.combo_step + 1}"
                if player is not None
                else ""
            ),
            f"RESULT {self._debug_last_result}  REJECT {self._debug_last_rejection}",
            (
                f"GAP X={evaluation.horizontal_gap:.2f} D={evaluation.depth_gap:.2f} "
                f"Z={evaluation.elevation_gap:.2f}"
                if evaluation is not None
                else "GAP X=-- D=-- Z=--"
            ),
            delta_line,
            contact_line,
            (
                f"ATTACK {repr(self._debug_last_attack.attack_id)[:35]} AGE={attack_age}"
                if self._debug_last_attack is not None
                else "ATTACK NONE"
            ),
            "BLUE body  YELLOW push  GREEN hurt  WHITE invuln",
            "RED down  SKY air  ORANGE current  PINK previous",
            "MAGENTA swept  PURPLE grab  CYAN contact",
        ]
        lines.extend(
            (
                f"P{candidate.slot + 1} {candidate.state} z={candidate.z:.1f} "
                f"ID={candidate.attack_instance_id} S={candidate.super_meter:.0f}"
            )
            for candidate in self.players[1:4]
        )
        lines.extend(
            (
                f"E{enemy.enemy_id} {enemy.kind}:{enemy.state} hp={enemy.health:.0f} "
                f"ID={enemy.attack_instance_id}"
            )
            for enemy in self.enemies[:3]
        )
        for index, line in enumerate(lines):
            self._text(surface, self.font_tiny, line, (174, 255, 214), (11, 94 + index * 13))

        def project_floor(x: float, depth: float) -> tuple[int, int]:
            return self.projection.project(
                WorldPoint(x, depth),
                camera_x=self._render_camera_x,
                camera_depth=self._projection_depth_origin,
                screen_shake=(0.0, self._camera_shake_y),
            ).pixel_xy

        def draw_bounds(bounds: AABB2, color: tuple[int, int, int], width: int = 1) -> None:
            points = [
                project_floor(bounds.min_x, bounds.min_depth),
                project_floor(bounds.max_x, bounds.min_depth),
                project_floor(bounds.max_x, bounds.max_depth),
                project_floor(bounds.min_x, bounds.max_depth),
            ]
            pygame.draw.lines(surface, color, True, points, width)

        confidence_colors = {
            "high": (82, 241, 152),
            "medium": (255, 211, 86),
            "low": (255, 105, 105),
        }
        for landmark in self.location_route.get("landmarks", ()):
            if not isinstance(landmark, Mapping):
                continue
            world_x = float(landmark["world_x"])
            screen_x = int(round(world_x - self._render_camera_x))
            if not -2 <= screen_x <= LOGICAL_SIZE[0] + 2:
                continue
            confidence = str(landmark.get("confidence", "low")).lower()
            color = confidence_colors.get(confidence, confidence_colors["low"])
            pygame.draw.line(surface, color, (screen_x, 42), (screen_x, 338), 1)
            self._text(
                surface,
                self.font_tiny,
                f"{landmark['id']} X={int(world_x)} {confidence.upper()}",
                color,
                (screen_x + 3, 44),
            )

        for zone in self.data["stage_geometry"].get("camera_zones", ()):
            if not isinstance(zone, Mapping):
                continue
            for edge_name, world_x in (
                ("IN", float(zone["start_x"])),
                ("OUT", float(zone["end_x"])),
            ):
                screen_x = int(round(world_x - self._render_camera_x))
                if not -2 <= screen_x <= LOGICAL_SIZE[0] + 2:
                    continue
                pygame.draw.line(
                    surface,
                    (190, 103, 255),
                    (screen_x, 68),
                    (screen_x, 350),
                    1,
                )
                self._text(
                    surface,
                    self.font_tiny,
                    f"{zone['name']} {edge_name}",
                    (224, 177, 255),
                    (screen_x + 3, 69),
                )

        for segment in self.data["stage_geometry"]["rails"]:
            start_x, end_x = float(segment["start_x"]), float(segment["end_x"])
            if end_x < self.camera_x or start_x > self.camera_x + LOGICAL_SIZE[0]:
                continue
            rail = [
                project_floor(start_x, float(segment["far_depth"])),
                project_floor(end_x, float(segment["far_depth"])),
                project_floor(end_x, float(segment["near_depth"])),
                project_floor(start_x, float(segment["near_depth"])),
            ]
            pygame.draw.lines(surface, (72, 235, 198), True, rail, 1)
            self._text(
                surface,
                self.font_tiny,
                f"RAIL {start_x:g}-{end_x:g}",
                (72, 235, 198),
                (rail[0][0] + 3, rail[0][1] + 2),
            )
        for obstacle in self.data["stage_geometry"].get("obstacles", ()):
            x, depth = float(obstacle["x"]), float(obstacle["depth"])
            half_x, half_depth = float(obstacle["half_width"]), float(obstacle["half_depth"])
            footprint = [
                project_floor(x - half_x, depth - half_depth),
                project_floor(x + half_x, depth - half_depth),
                project_floor(x + half_x, depth + half_depth),
                project_floor(x - half_x, depth + half_depth),
            ]
            pygame.draw.lines(surface, (255, 207, 70), True, footprint, 1)
            anchor = project_floor(x, depth)
            self._text(
                surface,
                self.font_tiny,
                str(obstacle.get("id", "OBSTACLE")),
                (255, 224, 113),
                (anchor[0] + 3, anchor[1] - 10),
            )
        # Navigation bodies and actor push boxes use different geometry even
        # when they share a centre: a circular stage body versus a rectangular
        # mass-separation footprint.
        for _entity_id, actor in [
            *((("player", candidate.slot), candidate) for candidate in self.players),
            *((("enemy", candidate.enemy_id), candidate) for candidate in self.enemies),
        ]:
            half_width, half_depth, _, _ = self._actor_extents(actor)
            body_points = [
                project_floor(
                    actor.x + math.cos(index * math.tau / 12.0) * half_depth,
                    actor.y + math.sin(index * math.tau / 12.0) * half_depth,
                )
                for index in range(12)
            ]
            pygame.draw.lines(surface, (72, 158, 255), True, body_points, 2)
            draw_bounds(
                AABB2(
                    actor.x - half_width,
                    actor.x + half_width,
                    actor.y - half_depth,
                    actor.y + half_depth,
                ),
                (255, 207, 70),
            )
            facing = int(getattr(actor, "facing", 1))
            pygame.draw.line(
                surface,
                (72, 158, 255),
                project_floor(actor.x, actor.y),
                project_floor(actor.x + facing * (half_width + 8.0), actor.y),
                1,
            )

        for hurtbox in (*self._player_hurtboxes(), *self._enemy_hurtboxes()):
            if not hurtbox.vulnerable:
                color = (244, 249, 255)
            elif "downed" in hurtbox.tags:
                color = (255, 90, 90)
            elif not hurtbox.is_grounded:
                color = (112, 194, 255)
            else:
                color = (78, 245, 139)
            draw_bounds(hurtbox.bounds_2d, color, 2)

        attack = visible_attack
        if attack is not None:
            attack_color = (
                (194, 88, 255)
                if isinstance(attack.attack_id, tuple)
                and attack.attack_id
                and attack.attack_id[0] == "player_throw"
                else (255, 159, 54)
            )
            start_x, start_depth = attack.sweep_start
            previous_bounds = AABB2(
                start_x - attack.half_width,
                start_x + attack.half_width,
                start_depth - attack.half_depth - attack.depth_tolerance,
                start_depth + attack.half_depth + attack.depth_tolerance,
            )
            draw_bounds(attack.swept_bounds_2d, (255, 65, 218), 1)
            draw_bounds(previous_bounds, (255, 118, 188), 1)
            draw_bounds(attack.bounds_2d, attack_color, 2)
        for contact in self._debug_last_contacts if visible_attack is not None else ():
            pygame.draw.circle(
                surface,
                (91, 242, 255),
                project_floor(contact.contact_x, contact.contact_depth),
                4,
                1,
            )

    def _draw_end(self, surface: pygame.Surface) -> None:
        if self.state == "complete":
            self._draw_level_complete(surface)
            return
        surface.blit(self.key_art, (0, 0))
        shade = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        shade.fill((5, 5, 15, 190))
        surface.blit(shade, (0, 0))
        self._text(surface, self.font_huge, "THE FADES GOT FADED", (255, 108, 128), (320, 90), center=True)
        y = 150
        for player in self.players:
            self._text(surface, self.font, f"P{player.slot + 1} {self.data['players'][player.character]['display_name']}   SCORE {player.score:06d}   KOs {player.ko_count}", PLAYER_COLORS[player.slot], (320, y), center=True)
            y += 29
        self._panel(surface, pygame.Rect(175, 290, 290, 36), (8, 9, 20), (82, 220, 255))
        self._text(surface, self.font, "PRESS ENTER / A TO RETURN", (208, 244, 255), (320, 308), center=True)

    def _draw_level_complete(self, surface: pygame.Surface) -> None:
        atmosphere = self.atmosphere.snapshot()
        pixel_art.draw_stage_background(
            surface,
            float(self.data["encounters"][-1].get("camera_x", 2960.0)),
            float(self.meta["stage_width"]),
            0.0,
            theme=self.level_theme,
            atmosphere=atmosphere,
        )
        shade = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        shade.fill((4, 5, 15, 156 if self.victory_frame.show_results else 118))
        surface.blit(shade, (0, 0))
        heading = "CHAPTER 1 COMPLETE!" if self.level_is_chapter_finale else f"LEVEL {self.level_number} COMPLETE!"
        self._text(surface, self.font_big, heading, (255, 226, 98), (320, 20), center=True)

        phase_label = f"{self.level_title.upper()} CLEAR"
        if self.level_is_chapter_finale:
            if self.victory_frame.phase == "hug":
                phase_label = "DAVE + SHELLY"
            elif self.victory_frame.phase == "treat_toss":
                phase_label = "TREATS FOR CHIEF!"
            else:
                phase_label = f"COUCH DEFEATED AT {self.level_title.upper()}"
            art_index = self._victory_art_index()
            victory_art = sprite_atlas.victory_frame(art_index)
            if victory_art is not None:
                victory_art = pixel_art.shade_authored_sprite(victory_art, "celebration")
                surface.blit(victory_art, victory_art.get_rect(midtop=(320, 42)))

        if self.level_is_chapter_finale and not self.victory_frame.show_results:
            self._panel(surface, pygame.Rect(154, 286, 332, 42), (8, 12, 24), (255, 181, 91))
            self._text(surface, self.font, phase_label, (255, 239, 183), (320, 300), center=True)
            self._text(surface, self.font_tiny, "VICTORY CELEBRATION", (151, 222, 246), (320, 319), center=True)
            return

        stats = self.completion_stats or self.level_stats.preview(self.players)
        panel = pygame.Rect(62, 174, 516, 160)
        self._panel(surface, panel, (8, 12, 24), (94, 220, 255))
        pygame.draw.rect(surface, (255, 205, 78), (panel.x + 2, panel.y + 2, panel.width - 4, 4))
        self._text(surface, self.font_small, phase_label, (159, 225, 247), (320, 183), center=True)
        left_x, right_x = 85, 310
        rows = (
            ("TIME", stats.formatted_time, "SCORE", f"{stats.combined_score:06d}"),
            ("KOs", str(stats.kos), "HITS", str(stats.hits_landed)),
            ("DAMAGE TAKEN", str(int(round(stats.damage_taken))), "RATING", str(stats.rating_points)),
        )
        for row, (left_label, left_value, right_label, right_value) in enumerate(rows):
            y = 207 + row * 30
            self._text(surface, self.font_tiny, left_label, (166, 192, 211), (left_x, y))
            self._text(surface, self.font, left_value, (255, 242, 194), (left_x + 104, y - 4), right=True)
            self._text(surface, self.font_tiny, right_label, (166, 192, 211), (right_x, y))
            self._text(surface, self.font, right_value, (255, 242, 194), (panel.right - 18, y - 4), right=True)
        self._text(surface, self.font_small, "RANK", (255, 195, 112), (271, 292), right=True)
        self._text(surface, self.font_huge, stats.rank, (255, 110, 194), (322, 304), center=True)
        continue_label = (
            "PRESS ANY BUTTON FOR THE RIDE HOME"
            if self.level_is_chapter_finale
            else "PRESS ANY BUTTON FOR LEVEL OPTIONS"
        )
        self._text(surface, self.font_tiny, continue_label, (207, 239, 250), (320, 343), center=True)

    def _draw_interlevel(self, surface: pygame.Surface) -> None:
        """Render the canonical route card or moving travel bridge."""

        atmosphere = self.atmosphere.snapshot()
        next_level = next(
            (level for level in campaign_levels(self.data) if str(level.get("id")) == self.pending_level_id),
            None,
        )
        travel = self.interlevel_travel_panel
        if travel is None and self.interlevel_source_id and self.pending_level_id:
            travel = location_lock.travel_panel_between(
                self.interlevel_source_id,
                self.pending_level_id,
                self.location_manifest,
            )
        if travel is None:
            raise location_lock.LocationLockError("interlevel state has no travel panel")
        progress = 1.0 - self.interlevel_timer / max(0.01, self.interlevel_duration)
        moving = str(travel["presentation"]) == "moving_panel"
        if moving:
            pixel_art.draw_location_travel_panel(
                surface,
                travel,
                progress,
                atmosphere=atmosphere,
            )
        else:
            pixel_art.draw_stage_background(
                surface,
                max(0.0, float(self.meta["stage_width"]) - LOGICAL_SIZE[0]),
                float(self.meta["stage_width"]),
                0.0,
                theme=self.level_theme,
                atmosphere=atmosphere,
            )
        shade = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        shade.fill((4, 7, 18, 42 if moving else 194))
        surface.blit(shade, (0, 0))
        panel = pygame.Rect(44, 16, 552, 62) if moving else pygame.Rect(62, 82, 516, 196)
        self._panel(surface, panel, (8, 15, 29), (99, 221, 255))
        heading = str(travel["heading"]).upper()
        waypoints = tuple(
            str(waypoint["display_name"]).upper()
            for waypoint in travel["waypoints"]
            if isinstance(waypoint, Mapping)
        )
        detail = "  →  ".join(waypoints)
        self._text(
            surface,
            self.font_big if not moving else self.font,
            "MOVING NORTH" if moving else "NEXT STOP",
            (255, 224, 112),
            (320, 29 if moving else 103),
            center=True,
        )
        self._text(
            surface,
            self.font_small,
            heading,
            (129, 231, 255),
            (320, 53 if moving else 137),
            center=True,
        )
        if next_level is not None:
            route = f"LEVEL {int(next_level['number'])}: {str(next_level['title']).upper()}"
            self._text(
                surface,
                self.font,
                route,
                (255, 242, 204),
                (320, 291 if moving else 164),
                center=True,
            )
            start = str(next_level.get("start", {}).get("display_name", "NEXT BLOCK")).upper()
            self._text(
                surface,
                self.font_tiny,
                f"ARRIVING AT {start}",
                (191, 224, 233),
                (320, 313 if moving else 188),
                center=True,
            )
        self._text(
            surface,
            self.font_tiny,
            detail,
            (235, 232, 206) if moving else (193, 208, 225),
            (320, 270 if moving else 213),
            center=True,
        )
        self._bar(
            surface,
            pygame.Rect(144, 329 if moving else 239, 352, 9 if moving else 12),
            progress,
            (83, 218, 181),
            (16, 26, 42),
        )
        self._text(
            surface,
            self.font_tiny,
            "ACTION SKIPS  •  ESC / B BACK" if moving else "PRESS ANY ACTION TO DEPART  •  ESC / B BACK",
            (255, 225, 127),
            (320, 344 if moving else 301),
            center=True,
        )

    def _draw_epilogue(self, surface: pygame.Surface) -> None:
        """Show ordinary route results or the finale-only BMX sunset."""

        atmosphere = self.atmosphere.snapshot()
        if self.level_is_chapter_finale:
            pixel_art.draw_sunset_epilogue(surface, self.epilogue_timer)
        else:
            pixel_art.draw_stage_background(
                surface,
                max(0.0, float(self.meta["stage_width"]) - LOGICAL_SIZE[0]),
                float(self.meta["stage_width"]),
                theme=self.level_theme,
                atmosphere=atmosphere,
            )
        shade = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        shade.fill((12, 10, 30, 52 if self.level_is_chapter_finale else 116))
        surface.blit(shade, (0, 0))
        heading = "SECOND STREET: SUNSET" if self.level_is_chapter_finale else f"CHAPTER 1  •  LEVEL {self.level_number} CLEAR"
        subtitle = (
            "DAVE RIDES HOME • SHELLY AND CHIEF WALK BESIDE HIM"
            if self.level_is_chapter_finale
            else self.level_title.upper()
        )
        self._text(surface, self.font_big, heading, (255, 228, 135), (320, 24), center=True)
        self._text(surface, self.font_small, subtitle, (229, 235, 244), (320, 48), center=True)
        if not self.level_is_chapter_finale:
            route_panel = pygame.Rect(38, 112, 320, 160)
            self._panel(surface, route_panel, (10, 18, 24), (95, 225, 168))
            start = str(self.level_data.get("start", {}).get("display_name", "START"))
            end = str(self.level_data.get("end", {}).get("display_name", "FINISH"))
            self._text(surface, self.font_small, "ROUTE CLEARED", (255, 222, 111), (198, 128), center=True)
            self._text(surface, self.font, start.upper(), (202, 246, 224), (198, 161), center=True)
            self._text(surface, self.font_big, "↓", (255, 210, 104), (198, 188), center=True)
            self._text(surface, self.font, end.upper(), (202, 246, 224), (198, 225), center=True)
        if self.epilogue_page == "options":
            panel = pygame.Rect(72, 115, 496, 130)
            self._panel(surface, panel, (12, 17, 31), (104, 222, 255))
            self._text(surface, self.font_big, "OPTIONS", (255, 225, 117), (320, 137), center=True)
            self._text(surface, self.font_small, "MUSIC / SFX SETTINGS ARE DATA-DRIVEN IN THIS DEMO", (225, 234, 241), (320, 172), center=True)
            self._text(surface, self.font_small, "PAUSE MENU CONTROLS REMAIN AVAILABLE IN GAME", (173, 219, 240), (320, 199), center=True)
            self._text(surface, self.font_tiny, "ENTER / A / ESC / B  BACK", (255, 220, 117), (320, 228), center=True)
            return
        next_level = self._next_campaign_level()
        next_label = (
            f"START LEVEL {int(next_level['number'])}"
            if next_level is not None and str(next_level.get("status", "")).lower() == "playable"
            else "CHAPTER 1 COMPLETE"
        )
        menu = (
            next_label,
            f"REPLAY LEVEL {self.level_number}",
            "RETURN TO MAIN MENU",
            "OPTIONS",
        )
        for index, label in enumerate(menu):
            rect = pygame.Rect(382, 128 + index * 35, 214, 28)
            selected = index == self.epilogue_selection
            self._panel(surface, rect, (35, 35, 55) if selected else (12, 16, 30), (255, 215, 95) if selected else (107, 181, 210))
            self._text(surface, self.font_tiny, label, (255, 244, 213) if selected else (196, 220, 230), rect.center, center=True)
        if self.epilogue_notice:
            self._panel(surface, pygame.Rect(171, 301, 298, 26), (20, 17, 33), (255, 191, 86))
            self._text(surface, self.font_small, self.epilogue_notice, (255, 229, 156), (320, 314), center=True)
        self._text(surface, self.font_tiny, "ARROWS / STICK + ENTER / A  •  ESC / B RETURNS TO MENU", (248, 232, 182), (320, 343), center=True)

    def _victory_art_index(self) -> int:
        """Bind every one of the sixteen celebration poses to its milestone.

        The doubled strip spends its first eight cels on the approach/hug,
        then reserves four pre-release and four post-release cels for the
        treat toss.  This keeps the audible treat-release event and the visual
        hand-off in the same fixed 60 Hz simulation interval.
        """

        if self.victory_frame.phase == "hug":
            return min(7, int(self.victory_frame.phase_progress * 8.0))
        if self.victory_frame.phase == "treat_toss":
            release_progress = self.victory_timeline.treat_release_seconds / self.victory_timeline.treat_toss_seconds
            if self.victory_frame.phase_progress < release_progress:
                pre_release_progress = self.victory_frame.phase_progress / max(0.001, release_progress)
                return 8 + min(3, int(pre_release_progress * 4.0))
            post_release_progress = (self.victory_frame.phase_progress - release_progress) / max(0.001, 1.0 - release_progress)
            return 12 + min(3, int(post_release_progress * 4.0))
        return 15

    @staticmethod
    def _panel(surface: pygame.Surface, rect: pygame.Rect, fill: tuple[int, int, int], border: tuple[int, int, int]) -> None:
        pygame.draw.rect(surface, (2, 3, 8), rect.inflate(4, 4))
        pygame.draw.rect(surface, fill, rect)
        pygame.draw.rect(surface, border, rect, 2)

    @staticmethod
    def _bar(surface: pygame.Surface, rect: pygame.Rect, fraction: float, fill: tuple[int, int, int], back: tuple[int, int, int]) -> None:
        pygame.draw.rect(surface, back, rect)
        inner = rect.inflate(-2, -2)
        inner.width = max(0, round(inner.width * clamp(fraction, 0.0, 1.0)))
        pygame.draw.rect(surface, fill, inner)
        pygame.draw.rect(surface, (4, 7, 12), rect, 1)

    @staticmethod
    def _text(
        surface: pygame.Surface,
        font: pygame.font.Font,
        text: str,
        color: tuple[int, int, int],
        position: tuple[int, int],
        *,
        center: bool = False,
        right: bool = False,
    ) -> None:
        shadow = font.render(text, False, (3, 3, 7))
        image = font.render(text, False, color)
        rect = image.get_rect()
        if center:
            rect.center = position
        elif right:
            rect.topright = position
        else:
            rect.topleft = position
        surface.blit(shadow, rect.move(1, 1))
        surface.blit(image, rect)
