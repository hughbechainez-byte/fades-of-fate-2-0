"""Record clean 60 Hz, actual-FadesGame approval evidence for Animation V2."""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
from typing import Any

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PIL import Image
import pygame

from src.entities import Enemy
from src.game import FadesGame, LOGICAL_SIZE, SelectSlot
from src.input_manager import InputManager


SIMULATION_HZ = 60
GIF_HZ = 30
SIM_DT = 1.0 / SIMULATION_HZ


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(command: list[str]) -> str:
    return subprocess.check_output(["git", *command], cwd=PROJECT_ROOT, text=True, encoding="utf-8").strip()


def _new_game(characters: tuple[int, ...] = (0,)) -> tuple[FadesGame, InputManager]:
    manager = InputManager(max_players=4, discover_controllers=False)
    game = FadesGame(manager, mute=True)
    game.select_slots = [
        SelectSlot({"type": "keyboard", "instance_id": -1}, character_index=index, confirmed=True)
        for index in characters
    ]
    game._start_stage()
    # The campaign adds its default CPU companion for a solo start.  Approval
    # evidence is deliberately a one-on-one/one-on-crowd scene so Black Dave's
    # authored cels and effect sockets stay readable; four-character lineup
    # capture retains all explicitly selected players.
    if len(characters) == 1:
        game.players[:] = [player for player in game.players if not player.is_cpu]
    game.encounter_index = len(game.data["encounters"])
    game.encounter_active = False
    game.active_gate = None
    game.spawn_queue.clear()
    game.enemies.clear()
    game.projectiles.clear()
    game.chiefs.clear()
    game.ko_companion = None
    game.effects.clear()
    game._dave_flame_visuals.clear()
    game.route_card_timer = 0.0
    game.stage_banner = ""
    game.stage_banner_timer = 0.0
    # The capture scene starts beyond several authored environment triggers.
    # Exhaust them deliberately so the approval footage contains only actual
    # combat presentation, never a route-card text pulse or spawn ring that
    # could be mistaken for a debug marker or VFX reticle.
    environmental_events = game.runtime_chapter_content.get("environmental_events", ())
    game._content_event_index = len(environmental_events) if isinstance(environmental_events, list) else 0
    game._content_event_seen.clear()
    game._content_event_props.clear()
    game._content_event_ambush_active = False
    game._content_event_ambush_name = ""
    game._content_optional = None
    game._content_optional_active = False
    game._content_optional_prompt = ""
    game.options = replace(game.options, hud_opacity=0.40, shake_intensity=0.0)
    camera_x = min(800.0, float(game.meta["stage_width"]) - LOGICAL_SIZE[0])
    game.camera.pan_to(camera_x, 0.0)
    game.camera_x = camera_x
    game._render_camera_x = camera_x
    for index, player in enumerate(game.players):
        player.x = camera_x + 320.0 + index * 16.0
        player.y = 298.0
        player.set_state("idle")
    return game, manager


def _add_practice_crowd(game: FadesGame, *, count: int = 1, spacing: float = 52.0) -> None:
    dave = next(player for player in game.players if player.character == "black_dave")
    for index in range(count):
        stats = dict(game.data["enemies"]["stick"])
        stats["health"] = 50_000.0
        stats["speed"] = 0.0
        stats["damage"] = 0.0
        enemy = Enemy(8_100 + index, "stick", dave.x + 42.0 + index * spacing, dave.y, stats)
        enemy.state = "idle"
        enemy.cooldown = 99.0
        game.enemies.append(enemy)


def _keep_practice_targets_visible(game: FadesGame) -> None:
    """Keep only recorder-created targets inside the real gameplay camera."""
    left = float(game._render_camera_x) + 24.0
    right = float(game._render_camera_x) + LOGICAL_SIZE[0] - 24.0
    for enemy in game.enemies:
        if enemy.enemy_id >= 8_100:
            enemy.x = min(right, max(left, enemy.x))


def _anchor_route_receiver(game: FadesGame) -> None:
    """Keep one real practice enemy available for every route contact.

    The game still owns hit queries, damage, hitstop and rendering.  This
    recorder-only fixture merely clears a completed receiver's knockback/down
    state between route steps, so a seven-step evidence run cannot turn into a
    four-hit capture because the first knockdown carried its sole target away.
    Power-route side targets remain free for the required crowd displacement.
    """

    dave = next((player for player in game.players if player.character == "black_dave"), None)
    receiver = next((enemy for enemy in game.enemies if enemy.enemy_id == 8_100), None)
    if dave is None or receiver is None or not receiver.alive:
        return
    receiver.x = dave.x + 34.0 * (1 if dave.facing >= 0 else -1)
    receiver.y = dave.y
    receiver.hitbox_sweep_x = receiver.x
    receiver.hitbox_sweep_y = receiver.y
    receiver.knockback_vx = 0.0
    receiver.knockback_vy = 0.0
    receiver.wake_invulnerable = 0.0
    receiver._set_state("idle")


def _draw_frame(game: FadesGame, canvas: pygame.Surface) -> Image.Image:
    _keep_practice_targets_visible(game)
    game.draw(canvas)
    return Image.frombytes("RGB", LOGICAL_SIZE, pygame.image.tobytes(canvas, "RGB"))


def _write_gif(path: Path, frames: list[Image.Image]) -> None:
    if not frames:
        raise RuntimeError(f"no frames captured for {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=round(1000 / GIF_HZ),
        loop=0,
        optimize=False,
        disposal=2,
    )


def _write_contact_sheet(path: Path, frames: list[Image.Image], *, columns: int = 4) -> None:
    """Write a separate clean QA sheet from real captured gameplay frames."""

    if not frames:
        raise RuntimeError(f"no frames available for {path.name}")
    count = min(8, len(frames))
    indices = sorted({round(index * (len(frames) - 1) / max(1, count - 1)) for index in range(count)})
    selected = [frames[index].resize((320, 180), Image.Resampling.NEAREST) for index in indices]
    rows = (len(selected) + columns - 1) // columns
    sheet = Image.new("RGB", (320 * columns, 180 * rows))
    for index, frame in enumerate(selected):
        sheet.paste(frame, ((index % columns) * 320, (index // columns) * 180))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def _press_event(key: int) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, key=key)


def _release_event(key: int) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYUP, key=key)


def _capture_route(action: str, output: Path, *, crowd_count: int = 1) -> dict[str, Any]:
    key = {"regular": pygame.K_z, "kick": pygame.K_x, "power": pygame.K_c}[action]
    game, manager = _new_game()
    canvas = pygame.Surface(LOGICAL_SIZE)
    frames: list[Image.Image] = []
    trace: list[dict[str, Any]] = []
    try:
        dave = next(player for player in game.players if player.character == "black_dave")
        dave.flaming_fists_timer = 12.0
        if crowd_count:
            _add_practice_crowd(
                game,
                count=crowd_count,
                spacing=44.0 if action == "power" else 52.0,
            )
        queued_steps: set[int] = set()
        step_hits = [0] * 7
        last_hit_count = dave.hit_count
        release_key: int | None = None
        started = False
        post_finish_ticks = 0
        prior_clip = ""
        for tick in range(760):
            events: list[pygame.event.Event] = []
            if release_key is not None:
                events.append(_release_event(release_key))
                release_key = None
            if not started and tick == 8:
                events.append(_press_event(key))
                release_key = key
                started = True
            execution = dave.attack_execution
            if execution is not None:
                if execution.clip_id != prior_clip:
                    trace.append({
                        "simulation_tick": tick,
                        "route": execution.route_id,
                        "step": execution.step_index + 1,
                        "step_id": execution.step_id,
                        "clip_id": execution.clip_id,
                    })
                    prior_clip = execution.clip_id
                move = dave.attack_timing_move or {}
                queue_threshold = max(0.035, float(move.get("cancel_start", 0.15)) - 0.055)
                if execution.step_index < 6 and execution.step_index not in queued_steps and dave.state_clock >= queue_threshold:
                    events.append(_press_event(key))
                    release_key = key
                    queued_steps.add(execution.step_index)
            _anchor_route_receiver(game)
            active_step = execution.step_index if execution is not None else None
            manager.process_events(events)
            game.update(SIM_DT)
            manager.consume_pressed()
            gained_hits = max(0, dave.hit_count - last_hit_count)
            if active_step is not None:
                step_hits[active_step] += gained_hits
            last_hit_count = dave.hit_count
            _anchor_route_receiver(game)
            image = _draw_frame(game, canvas)
            if tick % 2 == 0:
                frames.append(image)
            if len(trace) == 7 and dave.attack_execution is None and dave.state == "idle":
                post_finish_ticks += 1
                if post_finish_ticks >= 18:
                    break
        if len(trace) != 7:
            raise RuntimeError(f"{action} capture resolved {len(trace)} V2 route steps, expected seven")
        if any(hits < 1 for hits in step_hits):
            raise RuntimeError(
                f"{action} capture did not confirm one real hit on every route step: {step_hits}"
            )
        _write_gif(output, frames)
        _write_contact_sheet(output.with_name(f"{output.stem}_contact.png"), frames)
        return {
            "trace": trace,
            "frames": len(frames),
            "hits": dave.hit_count,
            "step_hits": step_hits,
            "target_fixture": "anchored_real_practice_receiver",
        }
    finally:
        game.close()
        manager.close()


def _capture_flame_system(output: Path) -> dict[str, Any]:
    """Record a mirrored whiff, then a confirmed flame hit in one real game scene."""
    game, manager = _new_game()
    canvas = pygame.Surface(LOGICAL_SIZE)
    frames: list[Image.Image] = []
    trace: list[dict[str, Any]] = []
    try:
        dave = next(player for player in game.players if player.character == "black_dave")
        dave.flaming_fists_timer = 12.0
        phase = "whiff"
        release_key: int | None = None
        started_whiff = False
        started_contact = False
        contact_at: int | None = None
        post_contact_ticks = 0
        for tick in range(420):
            events: list[pygame.event.Event] = []
            if release_key is not None:
                events.append(_release_event(release_key))
                release_key = None
            if phase == "whiff":
                dave.facing = -1
                if not started_whiff and tick == 8:
                    events.append(_press_event(pygame.K_z))
                    release_key = pygame.K_z
                    started_whiff = True
            elif phase == "contact" and contact_at is not None and tick >= contact_at and not started_contact:
                dave.facing = 1
                events.append(_press_event(pygame.K_z))
                release_key = pygame.K_z
                started_contact = True
            manager.process_events(events)
            game.update(SIM_DT)
            manager.consume_pressed()
            execution = dave.attack_execution
            if execution is not None and (
                not trace
                or trace[-1]["clip_id"] != execution.clip_id
                or trace[-1]["phase"] != phase
            ):
                trace.append({
                    "phase": phase,
                    "simulation_tick": tick,
                    "clip_id": execution.clip_id,
                    "route": execution.route_id,
                    "step": execution.step_index + 1,
                })
            if phase == "whiff" and started_whiff and execution is None and dave.state == "idle":
                _add_practice_crowd(game)
                phase = "contact"
                contact_at = tick + 12
            elif phase == "contact" and started_contact and execution is None and dave.state == "idle":
                post_contact_ticks += 1
                if post_contact_ticks >= 24:
                    break
            image = _draw_frame(game, canvas)
            if tick % 2 == 0:
                frames.append(image)
        if not started_contact or dave.hit_count < 1:
            raise RuntimeError("flame review did not reach a confirmed post-whiff enemy hit")
        _write_gif(output, frames)
        _write_contact_sheet(output.with_name(f"{output.stem}_contact.png"), frames)
        return {"frames": len(frames), "hits": dave.hit_count, "trace": trace}
    finally:
        game.close()
        manager.close()


def _air_kind_for_seed(seed: int) -> str:
    bag = ["punch", "kick"]
    random.Random(1_000_003 + seed).shuffle(bag)
    return bag.pop()


def _capture_air(kind: str, output: Path) -> dict[str, Any]:
    game, manager = _new_game()
    canvas = pygame.Surface(LOGICAL_SIZE)
    frames: list[Image.Image] = []
    try:
        dave = next(player for player in game.players if player.character == "black_dave")
        dave.flaming_fists_timer = 12.0
        _add_practice_crowd(game, count=1)
        seed = next(candidate for candidate in range(1, 50) if _air_kind_for_seed(candidate) == kind)
        dave.air_attack_seed = seed - 1
        release_key: int | None = None
        jump_pressed = False
        attack_pressed = False
        observed_kind = ""
        grounded_after_air_ticks = 0
        for tick in range(360):
            events: list[pygame.event.Event] = []
            if release_key is not None:
                events.append(_release_event(release_key))
                release_key = None
            if not jump_pressed and tick == 8:
                events.append(_press_event(pygame.K_SPACE))
                release_key = pygame.K_SPACE
                jump_pressed = True
            if jump_pressed and not attack_pressed and dave.z > 8.0:
                events.append(_press_event(pygame.K_z if kind == "punch" else pygame.K_x))
                release_key = pygame.K_z if kind == "punch" else pygame.K_x
                attack_pressed = True
            manager.process_events(events)
            game.update(SIM_DT)
            manager.consume_pressed()
            if dave.air_attack_kind:
                observed_kind = dave.air_attack_kind
            image = _draw_frame(game, canvas)
            if tick % 2 == 0:
                frames.append(image)
            if attack_pressed and observed_kind == kind and dave.z <= 0.0 and dave.state in {"jump_land", "idle"}:
                grounded_after_air_ticks += 1
                if grounded_after_air_ticks >= 18:
                    break
        if observed_kind != kind:
            raise RuntimeError(f"air capture selected {observed_kind or 'none'}, expected {kind}")
        _write_gif(output, frames)
        _write_contact_sheet(output.with_name(f"{output.stem}_contact.png"), frames)
        return {"seed": seed, "kind": kind, "frames": len(frames)}
    finally:
        game.close()
        manager.close()


def _capture_lineup(output: Path) -> dict[str, Any]:
    game, manager = _new_game((0, 1, 2, 3))
    canvas = pygame.Surface(LOGICAL_SIZE)
    try:
        camera_x = game._render_camera_x
        positions = (camera_x + 78.0, camera_x + 235.0, camera_x + 400.0, camera_x + 550.0)
        for player, x in zip(game.players, positions):
            player.x = x
            player.y = 302.0
            player.set_state("idle")
        for _ in range(18):
            game.update(SIM_DT)
        image = _draw_frame(game, canvas)
        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output)
        return {"actors": [player.character for player in game.players], "size": list(LOGICAL_SIZE)}
    finally:
        game.close()
        manager.close()


def _capture_idle_audit(output: Path) -> dict[str, Any]:
    """Create a separate, label-free, temporal sheet for lead visual review."""

    game, manager = _new_game((0, 1, 2, 3))
    canvas = pygame.Surface(LOGICAL_SIZE)
    frames: list[Image.Image] = []
    try:
        camera_x = game._render_camera_x
        positions = (camera_x + 78.0, camera_x + 235.0, camera_x + 400.0, camera_x + 550.0)
        for player, x in zip(game.players, positions):
            player.x = x
            player.y = 302.0
            player.set_state("idle")
        for _ in range(5):
            game.update(SIM_DT * 2.0)
            frames.append(_draw_frame(game, canvas))
        strip = Image.new("RGB", (LOGICAL_SIZE[0] * len(frames), LOGICAL_SIZE[1]))
        for index, frame in enumerate(frames):
            strip.paste(frame, (LOGICAL_SIZE[0] * index, 0))
        output.parent.mkdir(parents=True, exist_ok=True)
        strip.save(output)
        return {"frames": len(frames), "size": list(strip.size)}
    finally:
        game.close()
        manager.close()


def capture(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    preview_active = os.environ.get("FADES_BLACK_DAVE_PREVIEW", "").strip().lower() in {"1", "true", "yes", "on"}
    pygame.init()
    pygame.display.set_mode(LOGICAL_SIZE)
    try:
        captures = {
            "main_character_scale_lineup.png": _capture_lineup(output_dir / "main_character_scale_lineup.png"),
            "black_dave_z_regular_7_hit.gif": _capture_route("regular", output_dir / "black_dave_z_regular_7_hit.gif", crowd_count=1),
            "black_dave_x_kicks_7_hit.gif": _capture_route("kick", output_dir / "black_dave_x_kicks_7_hit.gif", crowd_count=1),
            "black_dave_c_power_7_hit_crowd.gif": _capture_route("power", output_dir / "black_dave_c_power_7_hit_crowd.gif", crowd_count=3),
            "black_dave_air_punch.gif": _capture_air("punch", output_dir / "black_dave_air_punch.gif"),
            "black_dave_air_kick.gif": _capture_air("kick", output_dir / "black_dave_air_kick.gif"),
            "black_dave_flame_system.gif": _capture_flame_system(output_dir / "black_dave_flame_system.gif"),
        }
        qa_captures = {
            "main_character_idle_temporal_audit.png": _capture_idle_audit(
                output_dir / "main_character_idle_temporal_audit.png"
            ),
        }
        assets = {
            relative: _sha256(PROJECT_ROOT / relative)
            for relative in (
                "assets/sprites/black_dave_v2_animation_atlas.png",
                "assets/sprites/black_dave_v2_flame_vfx_atlas.png",
                "assets/sprites/black_dave_v2_pose_metadata.json",
                "assets/sprites/shelly_rooted_animation_atlas.png",
                "assets/sprites/jermaine_rooted_animation_atlas.png",
                "assets/sprites/white_dave_rooted_animation_atlas.png",
                "assets/sprites/black_dave_preview_atlas_v1.png",
                "assets/sprites/black_dave_preview_metadata_v1.json",
                "art_source/black_dave/preview/black_dave_preview_pose_board_v1.png",
                "data/black_dave_v2_routes.json",
                "data/playable_character_animation_v2.json",
            )
        }
        return {
            "commit": _git(["rev-parse", "HEAD"]),
            "tree_dirty": bool(_git(["status", "--porcelain"])),
            "simulation_hz": SIMULATION_HZ,
            "gif_hz": GIF_HZ,
            "black_dave_preview": preview_active,
            "preview_contract": (
                {
                    "metadata": "assets/sprites/black_dave_preview_metadata_v1.json",
                    "mode": "flag_gated_review_only",
                    "full_pose_library": "deferred_pending_review",
                }
                if preview_active
                else None
            ),
            "captures": captures,
            "qa_captures": qa_captures,
            "asset_sha256": assets,
            "output_sha256": {
                filename: _sha256(output_dir / filename)
                for filename in captures
            },
        }
    finally:
        pygame.quit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "build" / "animation_v2_review")
    args = parser.parse_args()
    manifest = capture(args.output_dir.resolve())
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
