from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import pixel_art
from src.animation_manifest import action_segment_tick, enemy_animation_actor
from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager


FPS = 30
LOGICAL_SIZE = (320, 180)
OUTPUT_SIZE = (640, 360)
MODEL_IDS = (
    "encampment_bottle_scarf",
    "encampment_bottle_puffer",
    "encampment_tire_slinger",
    "underpass_tire_runner",
    "cart_tent_bottle_pitcher",
    "mall_security_watch",
    "event_security_heavy",
    "night_security_patrol",
    "city_patrol_nightstick",
    "transit_patrol_nightstick",
    "riot_line_nightstick",
    "bike_patrol_taser",
    "tactical_taser_unit",
)
RANGED_STYLES = {"glass_bottle", "bike_tire", "taser"}
CATEGORY_COLORS = {
    "homeless": (217, 143, 72),
    "security": (255, 207, 83),
    "police": (104, 177, 255),
}
# An exact, deliberately unnatural pixel run used only by opt-in QA media.
# Tests can reject this signature without guessing whether a legitimate costume
# happens to share one of the individual colors.
DEBUG_OVERLAY_SIGNATURE = (
    (255, 0, 255),
    (0, 255, 255),
    (255, 255, 0),
    (255, 0, 255),
    (255, 255, 0),
    (0, 255, 255),
)


def has_debug_overlay_signature(frame: Image.Image) -> bool:
    """Return whether a 2x preview frame carries the opt-in QA marker."""

    rgb = frame.convert("RGB")
    expected = tuple(color for color in DEBUG_OVERLAY_SIGNATURE for _ in range(2))
    if rgb.width < len(expected):
        return False
    return tuple(rgb.getpixel((x, 0)) for x in range(len(expected))) == expected


def _phase(frame_index: int, attack_style: str) -> tuple[str, str, float, float, int]:
    if frame_index < 18:
        return "idle", "IDLE", frame_index / FPS, 0.60, 1
    if frame_index < 48:
        return "chase", "WALK", (frame_index - 18) / FPS, 1.00, 1
    if frame_index < 60:
        return "windup", "WINDUP", (frame_index - 48) / FPS, 0.40, 1
    if frame_index < 84:
        action_label = "THROW" if attack_style in {"glass_bottle", "bike_tire"} else "TASER" if attack_style == "taser" else "STRIKE"
        return "attack", action_label, (frame_index - 60) / FPS, 0.80, 1
    if frame_index < 102:
        return "recovery", "RECOVER", (frame_index - 84) / FPS, 0.60, 1
    if frame_index < 114:
        return "hitstun", "HURT", (frame_index - 102) / FPS, 0.40, -1
    return "down", "DOWN", (frame_index - 114) / FPS, 0.80, -1


def _animation_tick(
    runtime_kind: str,
    variant_id: str,
    state: str,
    elapsed: float,
    duration: float,
) -> int:
    actor = enemy_animation_actor(runtime_kind, variant_id)
    if state == "windup":
        return action_segment_tick(actor, "attack", "startup", elapsed, duration)
    if state == "attack":
        return action_segment_tick(actor, "attack", "active", elapsed, duration)
    if state == "recovery":
        return action_segment_tick(actor, "attack", "recovery", elapsed, duration)
    return int(elapsed * 12.0)


def _crisp_text(font: pygame.font.Font, text: str, color: tuple[int, int, int]) -> pygame.Surface:
    return font.render(text, False, color)


def _draw_debug_overlay(
    surface: pygame.Surface,
    font: pygame.font.Font,
    small_font: pygame.font.Font,
    *,
    display_name: str,
    runtime_kind: str,
    attack_style: str,
    phase_label: str,
) -> None:
    accent = CATEGORY_COLORS[runtime_kind]
    pygame.draw.rect(surface, (10, 13, 22), (0, 0, surface.get_width(), 29))
    pygame.draw.rect(surface, accent, (0, 27, surface.get_width(), 2))
    surface.blit(_crisp_text(font, display_name.upper(), (247, 244, 226)), (7, 3))
    descriptor = f"{runtime_kind.upper()}  /  {attack_style.replace('_', ' ').upper()}"
    surface.blit(_crisp_text(small_font, descriptor, accent), (7, 16))
    badge = _crisp_text(font, phase_label, (255, 255, 255))
    badge_rect = badge.get_rect()
    badge_panel = pygame.Rect(surface.get_width() - badge_rect.width - 13, surface.get_height() - 19, badge_rect.width + 9, 14)
    pygame.draw.rect(surface, (10, 13, 22), badge_panel)
    pygame.draw.rect(surface, accent, badge_panel, 1)
    surface.blit(badge, (badge_panel.x + 5, badge_panel.y + 2))

    # These guides are diagnostic-only. Approval media must never contain
    # them, so this helper is called solely for --debug-overlay output.
    target_x = surface.get_width() - 34
    pygame.draw.ellipse(surface, accent, (target_x - 8, 147, 16, 5), 1)
    pygame.draw.line(surface, accent, (target_x, 140), (target_x, 154), 1)
    pygame.draw.line(surface, accent, (target_x - 4, 144), (target_x + 4, 144), 1)
    # Stamp last so the title panel cannot cover the exact QA signature.
    for offset, color in enumerate(DEBUG_OVERLAY_SIGNATURE):
        surface.set_at((offset, 0), color)


def _background(game: FadesGame) -> pygame.Surface:
    full = pygame.Surface((640, 360))
    pixel_art.draw_stage_background(
        full,
        120.0,
        float(game.meta["stage_width"]),
        theme=game.level_theme,
        atmosphere=game.atmosphere.snapshot(),
    )
    # Review cards use a native 320x180 crop from the real logical canvas.
    # Only the final 2x presentation enlargement is performed, with nearest-neighbor.
    return full.subsurface(pygame.Rect(160, 174, *LOGICAL_SIZE)).copy()


def _save_gif(frames: list[Image.Image], output_path: Path) -> None:
    rgb = [frame.convert("RGB") for frame in frames]
    palette = rgb[0].convert(
        "P",
        palette=Image.Palette.ADAPTIVE,
        colors=255,
        dither=Image.Dither.NONE,
    )
    indexed = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in rgb]
    indexed[0].save(
        output_path,
        save_all=True,
        append_images=indexed[1:],
        # GIF stores timing in 10 ms units. Alternating 30/40/30 ms yields an
        # exact 100 ms per three frames instead of silently turning 33 ms into
        # 30 ms and speeding up the authored 30 FPS review.
        duration=[(30, 40, 30)[index % 3] for index in range(len(indexed))],
        loop=0,
        disposal=2,
        optimize=False,
    )


def _render_model(
    game: FadesGame,
    human: object,
    base: pygame.Surface,
    font: pygame.font.Font,
    small_font: pygame.font.Font,
    variant_id: str,
    *,
    debug_overlay: bool = False,
    frame_count: int = 138,
) -> list[Image.Image]:
    game.enemies.clear()
    game.projectiles.clear()
    game.effects.clear()
    enemy = game._spawn_enemy(variant_id)
    game.effects.clear()
    game.enemies[:] = [enemy]
    runtime_kind = enemy.kind
    attack_style = str(enemy.stats["attack_style"])
    display_name = str(enemy.stats["display_name"])
    ranged = attack_style in RANGED_STYLES
    target_x = 286.0
    attack_x = 112.0 if ranged else 220.0
    walk_start_x = attack_x - 30.0
    human.x = target_x
    human.y = 151.0
    human.health = human.max_health
    human.state = "idle"
    human.state_clock = 0.0
    human.invulnerable = 999.0 if attack_style != "taser" else 0.0
    frames: list[Image.Image] = []
    for frame_index in range(frame_count):
        state, phase_label, elapsed, duration, facing = _phase(frame_index, attack_style)
        if state == "chase":
            enemy.x = walk_start_x + min(30.0, elapsed * 30.0)
        elif state == "idle" and frame_index < 18:
            enemy.x = walk_start_x
        else:
            enemy.x = attack_x
        enemy.y = 151.0
        enemy.facing = facing
        enemy.state = state
        enemy.state_clock = elapsed
        enemy.state_duration = duration
        enemy.locomotion_distance = max(0.0, (frame_index - 18) * 1.8)
        enemy.hit_flash = 0.16 if state == "hitstun" and frame_index % 4 < 2 else 0.0
        enemy.attack_instance_id = 1
        game.frame = frame_index

        if frame_index == 63 and ranged:
            game.spawn_enemy_projectile(enemy, human, attack_style)
        for projectile in list(game.projectiles):
            projectile.update(game, 1.0 / FPS)
        game.projectiles[:] = [projectile for projectile in game.projectiles if not projectile.spent]

        logical = base.copy()
        tick = _animation_tick(runtime_kind, variant_id, state, elapsed, duration)
        pixel_art.draw_enemy(
            logical,
            enemy.x,
            enemy.y,
            facing=enemy.facing,
            state=state,
            kind=f"{runtime_kind}:{variant_id}",
            frame=tick,
            tint=enemy.stats.get("render_tint"),
            hit_flash=enemy.hit_flash,
        )
        for projectile in game.projectiles:
            pixel_art.draw_projectile(
                logical,
                projectile.x,
                projectile.y,
                projectile.z,
                1 if projectile.vx >= 0.0 else -1,
                projectile.kind,
                frame_index // 2,
            )
        if debug_overlay:
            _draw_debug_overlay(
                logical,
                font,
                small_font,
                display_name=display_name,
                runtime_kind=runtime_kind,
                attack_style=attack_style,
                phase_label=phase_label,
            )
        enlarged = pygame.transform.scale(logical, OUTPUT_SIZE)
        frames.append(Image.frombytes("RGB", OUTPUT_SIZE, pygame.image.tobytes(enlarged, "RGB")))
        for effect in game.effects:
            effect.update(1.0 / FPS)
        game.effects[:] = [effect for effect in game.effects if effect.alive]
    return frames


def build(output_dir: Path, *, debug_overlay: bool = False) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    pygame.init()
    pygame.display.set_mode((1, 1))
    manager = InputManager(max_players=4, discover_controllers=False)
    game = FadesGame(manager, mute=True)
    try:
        game.select_slots = [SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)]
        game._start_stage()
        human = next(player for player in game.players if not player.is_cpu)
        for player in game.players:
            if player is not human:
                player.state = "eliminated"
        base = _background(game)
        font = pygame.font.Font(None, 14)
        small_font = pygame.font.Font(None, 11)
        font.set_bold(True)
        small_font.set_bold(True)
        output_paths: list[Path] = []
        contact_frames: list[Image.Image] = []
        debug_dir = output_dir / "qa_debug"
        if debug_overlay:
            debug_dir.mkdir(parents=True, exist_ok=True)
        for index, variant_id in enumerate(MODEL_IDS, start=1):
            frames = _render_model(game, human, base, font, small_font, variant_id)
            output_path = output_dir / f"{index:02d}_{variant_id}.gif"
            _save_gif(frames, output_path)
            output_paths.append(output_path)
            contact_frames.append(frames[68].resize(LOGICAL_SIZE, resample=Image.Resampling.NEAREST))
            if debug_overlay:
                debug_frames = _render_model(
                    game,
                    human,
                    base,
                    font,
                    small_font,
                    variant_id,
                    debug_overlay=True,
                )
                debug_path = debug_dir / f"{index:02d}_{variant_id}_qa.gif"
                _save_gif(debug_frames, debug_path)
                output_paths.append(debug_path)

        contact_sheet = Image.new("RGB", (LOGICAL_SIZE[0] * 3, LOGICAL_SIZE[1] * 5), (8, 10, 17))
        for index, frame in enumerate(contact_frames):
            contact_sheet.paste(frame, ((index % 3) * LOGICAL_SIZE[0], (index // 3) * LOGICAL_SIZE[1]))
        contact_sheet_path = output_dir / "00_enemy_roster_contact_sheet.png"
        contact_sheet.save(contact_sheet_path)
        output_paths.insert(0, contact_sheet_path)
        return output_paths
    finally:
        game.close()
        manager.close()
        pygame.quit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Render deterministic in-engine GIF reviews for the expanded enemy roster.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "build" / "enemy_roster_previews",
        help="Directory for the 13 review GIFs and one contact sheet.",
    )
    parser.add_argument(
        "--debug-overlay",
        action="store_true",
        help="Also emit separate QA GIFs with labels and target guides under qa_debug/.",
    )
    args = parser.parse_args()
    paths = build(args.output_dir.resolve(), debug_overlay=args.debug_overlay)
    for path in paths:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        print(f"{path.name}  {path.stat().st_size} bytes  sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
