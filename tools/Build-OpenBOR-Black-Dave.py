"""Build Black Dave's production OpenBOR model from the approved 220-pose manifest.

The source sprites are copied byte-for-byte.  This builder owns runtime routing,
collision metadata, separate hard-edged effects, and reachability annotations;
it never redraws, rescales, requantizes, or otherwise mutates approved body art.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content/characters/black_dave"
DESIGN_PATH = CONTENT / "metadata/production_manifest.json"
POSE_MANIFEST_PATH = CONTENT / "sprites/pose_manifest.json"
ROUTES_PATH = CONTENT / "metadata/black_dave_v2_routes.json"
OUT = ROOT / "openbor/data/chars/black_dave"
SPRITES = OUT / "sprites"
EFFECTS = OUT / "effects"
MODEL_PATH = OUT / "black_dave.txt"
IMPLEMENTATION_PATH = OUT / "black_dave_implementation_manifest.json"
OPENBOR_MANIFEST_PATH = OUT / "black_dave_openbor_manifest.json"
COMBAT_ROUTES_OUT = OUT / "black_dave_combat_routes.json"
README_PATH = OUT / "README.md"
QA_SCRIPT_PATH = ROOT / "openbor/data/scripts/black_dave_pose_qa.c"
CONTROLLER_PATH = ROOT / "openbor/data/scripts/update.c"
QA_SCHEDULE_PATH = OUT / "black_dave_pose_qa_schedule.json"
ROOT_OFFSET = (96, 156)
EXPECTED_POSES = 220
ROUTE_NAMES = ("regular", "kick", "power")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_source(design: dict, art: dict) -> None:
    poses = art.get("poses", [])
    if design.get("entity_id") != "black_dave" or art.get("entity_id") != "black_dave":
        raise ValueError("Black Dave source manifest identity mismatch")
    if design.get("maturity") != "production":
        raise ValueError("Black Dave implementation requires production art")
    if int(design.get("exact_unique_pose_target", 0)) != EXPECTED_POSES:
        raise ValueError("Black Dave exact production target must remain 220")
    if len(poses) != EXPECTED_POSES or len({pose.get("id") for pose in poses}) != EXPECTED_POSES:
        raise ValueError("Black Dave requires exactly 220 unique pose records")
    if tuple(design.get("canvas", [])) != (192, 160):
        raise ValueError("unexpected Black Dave canvas")
    if tuple(design.get("root_offset", [])) != ROOT_OFFSET or tuple(art.get("root", [])) != ROOT_OFFSET:
        raise ValueError("Black Dave runtime root must be 96 156")
    for pose in poses:
        if pose.get("approved") is not True:
            raise ValueError(f"unapproved pose: {pose.get('id')}")
        source = ROOT / pose["path"]
        if not source.is_file() or sha256(source) != pose.get("sha256"):
            raise ValueError(f"missing or stale approved pose: {pose.get('id')}")
        image = Image.open(source)
        if image.mode != "P" or image.size != (192, 160) or image.info.get("transparency") != 0:
            raise ValueError(f"invalid indexed source pose: {pose.get('id')}")
    palette_hashes = {hashlib.sha256(bytes(Image.open(ROOT / p["path"]).getpalette())).hexdigest() for p in poses}
    if len(palette_hashes) != 1:
        raise ValueError("Black Dave source poses do not share one ordered palette")
    clip_ids = set(art.get("clips", {}))
    expected = {f"{route}_{step:02d}" for route in ROUTE_NAMES for step in range(1, 8)}
    if not expected.issubset(clip_ids):
        raise ValueError(f"missing combat clips: {sorted(expected - clip_ids)}")


def copy_approved_poses(art: dict) -> dict[str, str]:
    SPRITES.mkdir(parents=True, exist_ok=True)
    approved_names = {f"{pose['id']}.png" for pose in art["poses"]}
    for old in SPRITES.glob("*.png"):
        if old.name not in approved_names:
            old.unlink()
    result: dict[str, str] = {}
    for pose in art["poses"]:
        source = ROOT / pose["path"]
        target = SPRITES / f"{pose['id']}.png"
        shutil.copyfile(source, target)
        if sha256(source) != sha256(target):
            raise ValueError(f"runtime copy changed approved pixels: {pose['id']}")
        result[pose["id"]] = f"data/chars/black_dave/sprites/{target.name}"
    return result


def bbox(pose: dict) -> tuple[int, int, int, int, int]:
    left, top, right, bottom = map(int, pose["body_bounds"])
    return left, top, right - left, bottom - top, 18


def attack_box(pose: dict, route: str, drop: int) -> tuple[int, ...]:
    left, top, right, bottom = map(int, pose["body_bounds"])
    body_h = bottom - top
    if route == "kick":
        y = top + body_h // 2
        height = max(10, body_h // 3)
        damage, z = 14, 18
    elif route == "power":
        y = top + body_h // 4
        height = max(14, body_h // 2)
        damage, z = 24, 24
    else:
        y = top + body_h // 4
        height = max(12, body_h // 3)
        damage, z = 10, 16
    x = max(ROOT_OFFSET[0] - 6, left)
    width = max(12, right - x)
    return x, y, width, min(height, 160 - y), damage, drop, 0, 0, 4, z


def append_frame(
    lines: list[str], pose: dict, runtime_path: str, active_route: str | None = None, active_drop: int = 0
) -> None:
    lines.append("    bbox " + " ".join(map(str, bbox(pose))))
    if active_route:
        lines.append("    attack " + " ".join(map(str, attack_box(pose, active_route, active_drop))))
    else:
        lines.append("    attack 0")
    lines.append(f"    frame {runtime_path}")


def append_anim(
    lines: list[str],
    name: str,
    pose_ids: list[str],
    poses: dict[str, dict],
    runtime_paths: dict[str, str],
    *,
    loop: bool = False,
    active_route: str | None = None,
    active_ids: set[str] | None = None,
    active_drop: int = 0,
) -> None:
    lines.extend((f"anim {name}", "    offset 96 156", "    delay 10000"))
    if loop:
        lines.append("    loop 1")
    for pose_id in pose_ids:
        append_frame(
            lines,
            poses[pose_id],
            runtime_paths[pose_id],
            active_route if active_ids and pose_id in active_ids else None,
            active_drop,
        )
    lines.extend(("    attack 0", ""))


def ticks(seconds: float) -> int:
    return int(float(seconds) * 60.0 + 0.5)


def phase_layout(count: int, startup: int, active: int, recovery: int) -> dict[str, int]:
    """Assign every cel to one phase with at least a two-tick authored hold."""
    active_poses = min(2, max(1, active // 2))
    startup_poses = min(max(1, startup // 2), count - active_poses - 1)
    recovery_poses = count - startup_poses - active_poses
    return {
        "startup_ticks": startup,
        "active_ticks": active,
        "declared_recovery_ticks": recovery,
        "effective_recovery_ticks": max(recovery, recovery_poses * 2),
        "startup_pose_count": startup_poses,
        "active_pose_start": startup_poses,
        "active_pose_count": active_poses,
        "recovery_pose_start": startup_poses + active_poses,
        "recovery_pose_count": recovery_poses,
    }


def route_phase_layout(step: dict, count: int) -> dict[str, int]:
    return phase_layout(count, ticks(step["startup"]), ticks(step["active"]), ticks(step["recovery"]))


def write_model(art: dict, routes: dict, runtime_paths: dict[str, str]) -> dict:
    clips = {name: list(record["pose_ids"]) for name, record in art["clips"].items()}
    poses = {pose["id"]: pose for pose in art["poses"]}
    lines = [
        "name BlackDave",
        "type player",
        "health 180",
        "mp 100",
        "speed 4",
        "jumpspeed 3",
        "jumpheight 4",
        "grabdistance 36",
        "knockdowncount 0",
        "death_config fall_land_air fall_land_ground remove_vanish_air remove_vanish_ground",
        "subject_to_gravity 1",
        "shadow 0",
        "atchain 1 2 3 4",
        "didhitscript data/scripts/black_dave_contact.c",
        "didblockscript data/scripts/black_dave_block.c",
        "",
    ]
    bindings = {
        "spawn": clips["spawn"],
        "respawn": clips["respawn"],
        "idle": clips["idle"],
        "walk": clips["walk_start"] + clips["walk"] + clips["walk_stop"],
        "turn": clips["pivot"],
        "jumpdelay": clips["jump_family"][:4],
        "jump": clips["jump_family"][4:10],
        "jumpland": clips["jump_family"][10:],
        "block": clips["block"][:6],
        "blockpain": clips["block"][6:],
        "dodge": clips["dodge"],
        "attackup": clips["ranged"],
        "special": clips["super"],
        "jumpattack": clips["air_punch"],
        "jumpattack2": clips["air_kick"],
        "pain": clips["light_pain"],
        "fall": clips["heavy_pain_fall"] + clips["down"],
        "rise": clips["rise"],
        "get": clips["item_pickup"],
    }
    native_attack_routes = {
        "special": "power",
        "jumpattack": "regular",
        "jumpattack2": "kick",
    }
    native_timings = {
        "special": (30, 12, 48),
        "jumpattack": (8, 6, 22),
        "jumpattack2": (10, 7, 23),
    }
    native_active_ids = {}
    for name, timing in native_timings.items():
        layout = phase_layout(len(bindings[name]), *timing)
        first = layout["active_pose_start"]
        native_active_ids[name] = set(bindings[name][first : first + layout["active_pose_count"]])
    qa_entries: list[dict] = []
    qa_seen: set[str] = set()

    def register_qa(animation: str, pose_ids: list[str]) -> None:
        for frame_index, pose_id in enumerate(pose_ids):
            if pose_id in qa_seen:
                continue
            qa_seen.add(pose_id)
            qa_entries.append(
                {
                    "request": len(qa_entries),
                    "pose_id": pose_id,
                    "animation": animation,
                    "animation_constant": f"ANI_{animation.upper()}",
                    "frame": frame_index,
                    "start_tick": len(qa_entries) * 12,
                    "hold_ticks": 12,
                }
            )

    for name, pose_ids in bindings.items():
        register_qa(name, pose_ids)
        append_anim(
            lines,
            name,
            pose_ids,
            poses,
            runtime_paths,
            loop=name == "idle",
            active_route=native_attack_routes.get(name),
            active_ids=native_active_ids.get(name),
            active_drop={"special": 4, "jumpattack": 1, "jumpattack2": 2}.get(name, 0),
        )

    # Build 7949 initializes the explicit chain table before scripted routing.
    # These safe one-pose definitions are never animation owners at runtime.
    chain_seed = clips["regular_01"][:4]
    for index, pose_id in enumerate(chain_seed, 1):
        append_anim(lines, f"attack{index}", [pose_id], poses, runtime_paths)

    banks: dict[str, dict] = {}
    for step in range(1, 8):
        bank_name = f"freespecial{step}"
        bank_pose_ids: list[str] = []
        offsets: dict[str, dict] = {}
        active_by_pose: dict[str, str] = {}
        for route in ROUTE_NAMES:
            clip_id = f"{route}_{step:02d}"
            sequence = clips[clip_id]
            layout = route_phase_layout(routes["routes"][route][step - 1], len(sequence))
            offsets[route] = {
                "offset": len(bank_pose_ids), "count": len(sequence), "clip": clip_id, "phase_layout": layout
            }
            first = layout["active_pose_start"]
            for pose_id in sequence[first : first + layout["active_pose_count"]]:
                active_by_pose[pose_id] = route
            bank_pose_ids.extend(sequence)
        register_qa(bank_name, bank_pose_ids)
        lines.extend((f"anim {bank_name}", "    offset 96 156", "    delay 10000"))
        cursor = 0
        for route in ROUTE_NAMES:
            sequence = clips[f"{route}_{step:02d}"]
            layout = offsets[route]["phase_layout"]
            first = layout["active_pose_start"]
            contacts = set(sequence[first : first + layout["active_pose_count"]])
            for pose_id in sequence:
                drop = 0
                if step == 7:
                    drop = {"regular": 1, "kick": 2, "power": 4}[route]
                append_frame(
                    lines,
                    poses[pose_id],
                    runtime_paths[pose_id],
                    route if pose_id in contacts else None,
                    drop,
                )
                cursor += 1
        lines.extend(("    attack 0", ""))
        banks[bank_name] = offsets

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    if len(qa_entries) != EXPECTED_POSES:
        raise ValueError(f"QA schedule must cover all {EXPECTED_POSES} poses, got {len(qa_entries)}")
    return {
        "routing": {"native": {key: {"count": len(value)} for key, value in bindings.items()}, "combat_banks": banks},
        "qa_entries": qa_entries,
    }


def write_qa_path(entries: list[dict]) -> None:
    lines = [
        "/* Generated deterministic Black Dave pose request executor. */",
        "void main()",
        "{",
        "    void player;",
        "    int request;",
        "    int animation;",
        "    int frame;",
        "    player = getglobalvar(\"bd_qa_player\");",
        "    request = getglobalvar(\"bd_qa_request\");",
        "    if(player == NULL()) return;",
        "    animation = -1;",
        "    frame = 0;",
    ]
    for entry in entries:
        lines.extend(
            (
                f"    if(request == {entry['request']})",
                "    {",
                f"        animation = openborconstant(\"{entry['animation_constant']}\");",
                f"        frame = {entry['frame']};",
                f"        log(\"[FOF2_POSE] {entry['pose_id']}\\n\");",
                "    }",
            )
        )
    lines.extend(
        (
            "    if(animation < 0) return;",
            "    if(getentityproperty(player, \"animationid\") != animation)",
            "    {",
            "        changeentityproperty(player, \"animation\", animation);",
            "    }",
            "    updateframe(player, frame);",
            "}",
            "",
        )
    )
    QA_SCRIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    QA_SCRIPT_PATH.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    controller = CONTROLLER_PATH.read_text(encoding="utf-8")
    begin = "/* BEGIN GENERATED BLACK DAVE QA POSE ROUTER */"
    end = "/* END GENERATED BLACK DAVE QA POSE ROUTER */"
    if controller.count(begin) != 1 or controller.count(end) != 1:
        raise ValueError("Black Dave controller QA router markers are missing or duplicated")
    router = [
        begin,
        "void bd_apply_qa_pose(void player, int request)",
        "{",
        "    int animation;",
        "    int frame;",
        "    animation = -1;",
        "    frame = 0;",
    ]
    for entry in entries:
        router.extend(
            (
                f"    if(request == {entry['request']})",
                "    {",
                f"        animation = openborconstant(\"{entry['animation_constant']}\");",
                f"        frame = {entry['frame']};",
                f"        log(\"[FOF2_POSE] {entry['pose_id']}\\n\");",
                "    }",
            )
        )
    router.extend(
        (
            "    if(animation < 0) return;",
            "    if(getentityproperty(player, \"animationid\") != animation)",
            "    {",
            "        changeentityproperty(player, \"animation\", animation);",
            "    }",
            "    updateframe(player, frame);",
            "}",
            end,
        )
    )
    prefix, remainder = controller.split(begin, 1)
    _, suffix = remainder.split(end, 1)
    CONTROLLER_PATH.write_text(prefix + "\n".join(router) + suffix, encoding="utf-8", newline="\n")
    QA_SCHEDULE_PATH.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entity": "black_dave",
                "trigger": "fof2_qa_dave_enabled == 1 or Build 7949 input playback mode",
                "simulation_hz": 60,
                "hold_ticks_per_pose": 12,
                "request_count": len(entries),
                "duration_ticks": len(entries) * 12,
                "log_contract": "one literal one-argument [FOF2_POSE] <pose_id> line per request",
                "requests": entries,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def effect_palette() -> list[int]:
    colors = [(0, 0, 0), (55, 17, 10), (130, 39, 12), (224, 78, 12), (255, 154, 24), (255, 235, 132)]
    palette = [channel for color in colors for channel in color]
    return palette + [0] * (768 - len(palette))


def write_effect_sprite(path: Path, frame: int, kind: str) -> None:
    image = Image.new("P", (48, 48), 0)
    image.putpalette(effect_palette())
    image.info["transparency"] = 0
    draw = ImageDraw.Draw(image)
    radius = (5, 9, 13, 9)[frame]
    if kind == "impact":
        cx = cy = 24
        draw.polygon([(cx, 4), (cx + 4, cy - 6), (44, cy), (cx + 6, cy + 4), (cx, 44), (cx - 4, cy + 6), (4, cy), (cx - 6, cy - 4)], fill=3)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=4)
        draw.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill=5)
    elif kind == "flame":
        cx, cy = 24, 30
        draw.polygon([(cx - radius, cy), (cx - 5, 10 + frame), (cx, 17 - frame), (cx + 5, 7 + frame), (cx + radius, cy), (cx, 42)], fill=3)
        draw.ellipse((cx - 6, cy - 7, cx + 6, cy + 7), fill=4)
        draw.ellipse((cx - 2, cy - 4, cx + 2, cy + 3), fill=5)
    else:
        cx, cy = 24, 24
        draw.ellipse((cx - radius - 3, cy - radius, cx + radius + 3, cy + radius), fill=3)
        draw.ellipse((cx - radius, cy - radius + 2, cx + radius, cy + radius - 2), fill=4)
        draw.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill=5)
    image.save(path, optimize=False)


def write_effects() -> dict:
    EFFECTS.mkdir(parents=True, exist_ok=True)
    result: dict[str, list[str]] = {}
    for kind in ("impact", "flame", "shot"):
        paths = []
        for frame in range(4):
            path = EFFECTS / f"black_dave_{kind}_{frame:02d}.png"
            write_effect_sprite(path, frame, kind)
            paths.append(f"data/chars/black_dave/effects/{path.name}")
        result[kind] = paths
        if kind == "shot":
            model = [
                "name BlackDaveFlameShot",
                "type pshot",
                "health 1",
                "speed 6",
                "lifespan 2",
                "subject_to_gravity 0",
                "candamage enemy",
                "didhitscript data/scripts/black_dave_contact.c",
                "anim idle",
                "    offset 24 24",
                "    delay 3",
                "    loop 1",
            ]
            for runtime_path in paths:
                model.extend(("    bbox 10 10 28 28 12", "    attack 8 8 32 32 18 3 0 0 4 20", f"    frame {runtime_path}"))
            model.extend(("    attack 0", ""))
            target = OUT / "black_dave_flame_shot.txt"
        else:
            model = [
                f"name BlackDave{kind.title()}",
                "type none",
                "health 1",
                "lifespan 0.2",
                "subject_to_gravity 0",
                "candamage none",
                "anim spawn",
                "    offset 24 24",
                "    delay 3",
            ]
            model.extend(f"    frame {runtime_path}" for runtime_path in paths)
            model.append("")
            target = OUT / f"black_dave_{kind}_fx.txt"
        target.write_text("\n".join(model), encoding="utf-8", newline="\n")
    return result


def write_runtime_metadata(
    art: dict, routes: dict, runtime_paths: dict[str, str], route_map: dict, effects: dict, qa_entries: list[dict]
) -> None:
    clip_records = {}
    for clip_id, clip in art["clips"].items():
        clip_records[clip_id] = {
            "pose_ids": clip["pose_ids"],
            "frames": [runtime_paths[pose_id] for pose_id in clip["pose_ids"]],
            "native_animation": clip["native_animation"],
            "trigger": clip["trigger"],
        }
    OPENBOR_MANIFEST_PATH.write_text(
        json.dumps(
            {
                "version": 2,
                "engine": "OpenBOR 4.0 Build 7949",
                "model": "black_dave",
                "model_path": rel(MODEL_PATH),
                "model_sha256": sha256(MODEL_PATH),
                "controller_path": rel(CONTROLLER_PATH),
                "controller_sha256": sha256(CONTROLLER_PATH),
                "contact_callback_sha256": sha256(ROOT / "openbor/data/scripts/black_dave_contact.c"),
                "block_callback_sha256": sha256(ROOT / "openbor/data/scripts/black_dave_block.c"),
                "status": "implementation_static_pass_runtime_evidence_pending",
                "source": rel(POSE_MANIFEST_PATH),
                "canvas": [192, 160],
                "offset": list(ROOT_OFFSET),
                "pose_count": EXPECTED_POSES,
                "unique_runtime_files": len(runtime_paths),
                "clip_count": len(clip_records),
                "clips": clip_records,
                "routing": route_map,
                "effects": effects,
                "deterministic_pose_qa": {
                    "script": "data/scripts/black_dave_pose_qa.c",
                    "schedule": "data/chars/black_dave/black_dave_pose_qa_schedule.json",
                    "trigger": "fof2_qa_dave_enabled == 1 or getrecordingstatus() == 2",
                    "requests": len(qa_entries),
                    "hold_ticks": 12,
                },
                "gameplay_evidence": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    COMBAT_ROUTES_OUT.write_text(
        json.dumps(
            {
                "version": 2,
                "engine": "OpenBOR 4.0 Build 7949",
                "model": "black_dave",
                "source": rel(ROUTES_PATH),
                "routes": [
                    {
                        "id": route_name,
                        "steps": [
                            {
                                **step,
                                "native_animation": f"FREESPECIAL{index}",
                                "bank_offset": route_map["combat_banks"][f"freespecial{index}"][route_name]["offset"],
                            }
                            for index, step in enumerate(routes["routes"][route_name], 1)
                        ],
                    }
                    for route_name in ROUTE_NAMES
                ],
                "animation_owner": "openbor/data/scripts/update.c",
                "contact_owner": "openbor/data/scripts/black_dave_contact.c",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    README_PATH.write_text(
        "# Black Dave OpenBOR model\n\n"
        "Generated byte-for-byte from the approved 220-pose production manifest with "
        "`tools/Build-OpenBOR-Black-Dave.py`.\n\n"
        "Canvas/root: `[192, 160]` / `[96, 156]`\n\n"
        "Runtime: OpenBOR 4.0 Build 7949\n\n"
        "Static implementation audit: 220 approved / referenced / runtime-reachable poses.\n\n"
        "Packaged gameplay evidence remains required before runtime approval.\n",
        encoding="utf-8",
        newline="\n",
    )


def update_source_manifest(
    art: dict, runtime_paths: dict[str, str], route_map: dict, effects: dict, qa_entries: list[dict]
) -> None:
    for pose in art["poses"]:
        pose["generated_path"] = "openbor/" + runtime_paths[pose["id"]]
        pose["runtime_reachable"] = True
        pose.setdefault("gameplay_evidence", [])
    art["runtime"] = {
        "engine": "OpenBOR 4.0 Build 7949",
        "simulation_hz": 60,
        "authored_pose_hz": 30,
        "animation_owner": "data/scripts/update.c",
        "native_control": "scoped BlackDave-only controller clears takeaction while owned, restores noaicontrol on release, and deliberately hands zero-health removal to common_lie after the authored down hold",
        "meter": {"power_step_cost": 10, "ranged_cost": 20, "super_full_gate_and_cost": 100},
        "model": rel(MODEL_PATH),
        "implementation_manifest": rel(IMPLEMENTATION_PATH),
        "root_offset": list(ROOT_OFFSET),
        "combat_banks": route_map["combat_banks"],
        "effects": effects,
        "deterministic_pose_qa": {
            "script": "openbor/data/scripts/black_dave_pose_qa.c",
            "schedule": rel(QA_SCHEDULE_PATH),
            "trigger": "fof2_qa_dave_enabled == 1 or getrecordingstatus() == 2",
            "requests": len(qa_entries),
            "hold_ticks": 12,
        },
        "gameplay_evidence": [],
    }
    POSE_MANIFEST_PATH.write_text(json.dumps(art, indent=2) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    design = load_json(DESIGN_PATH)
    art = load_json(POSE_MANIFEST_PATH)
    routes = load_json(ROUTES_PATH)
    validate_source(design, art)
    runtime_paths = copy_approved_poses(art)
    model_build = write_model(art, routes, runtime_paths)
    route_map = model_build["routing"]
    qa_entries = model_build["qa_entries"]
    write_qa_path(qa_entries)
    effects = write_effects()
    source_art_fingerprint = hashlib.sha256(
        "".join(f"{pose['id']}:{pose['sha256']}\n" for pose in art["poses"]).encode("ascii")
    ).hexdigest()
    implementation = {
        "schema_version": 1,
        "entity": "black_dave",
        "status": "implementation_ready_static_validation",
        "engine": "OpenBOR 4.0 Build 7949",
        "model": rel(MODEL_PATH),
        "model_sha256": sha256(MODEL_PATH),
        "controller": "openbor/data/scripts/update.c",
        "controller_sha256": sha256(CONTROLLER_PATH),
        "contact_callback": "openbor/data/scripts/black_dave_contact.c",
        "contact_callback_sha256": sha256(ROOT / "openbor/data/scripts/black_dave_contact.c"),
        "block_callback": "openbor/data/scripts/black_dave_block.c",
        "block_callback_sha256": sha256(ROOT / "openbor/data/scripts/black_dave_block.c"),
        "source_pose_manifest": rel(POSE_MANIFEST_PATH),
        "source_art_fingerprint_sha256": source_art_fingerprint,
        "pose_count": EXPECTED_POSES,
        "unique_runtime_files": len(runtime_paths),
        "root_offset": list(ROOT_OFFSET),
        "simulation_hz": 60,
        "authored_pose_hz": 30,
        "animation_owner": "fixed-60Hz scripted pose selection; native timer frozen with delay 10000; explicit native death-removal handoff only after authored down hold",
        "route_source": rel(ROUTES_PATH),
        "route_count": sum(len(value) for value in routes["routes"].values()),
        "routing": route_map,
        "collision": "per-pose bbox and contact-pose-only attack boxes",
        "contact": "didhitscript-confirmed latch owns Dave-only contact pose pause and impact VFX; world time is not frozen",
        "input_owner": "data/scripts/update.c scopes player 0 by exact BlackDave name, accumulates engine time at 60Hz, clears takeaction while owned, and restores native control on release",
        "meter": {"power_step_cost": 10, "ranged_cost": 20, "super_full_gate_and_cost": 100},
        "effects": effects,
        "deterministic_pose_qa": {
            "script": rel(QA_SCRIPT_PATH),
            "schedule": rel(QA_SCHEDULE_PATH),
            "trigger": "fof2_qa_dave_enabled == 1 or getrecordingstatus() == 2",
            "requests": len(qa_entries),
            "hold_ticks": 12,
        },
        "gameplay_evidence": [],
    }
    IMPLEMENTATION_PATH.write_text(json.dumps(implementation, indent=2) + "\n", encoding="utf-8", newline="\n")
    write_runtime_metadata(art, routes, runtime_paths, route_map, effects, qa_entries)
    update_source_manifest(art, runtime_paths, route_map, effects, qa_entries)
    print(f"Black Dave production runtime: {len(runtime_paths)} unique poses / 21 combat clips / 7 banks")


if __name__ == "__main__":
    main()
