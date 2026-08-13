"""Build the two audited 120-pose production enemies for OpenBOR Build 7949.

The approved source poses are copied byte-for-byte.  This builder owns runtime
routing, per-pose collision metadata, and the source manifest runtime fields;
it never edits the approved art or its approval/hash records.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANIMATION_CONSTANTS = {
    "spawn": "ANI_SPAWN",
    "idle": "ANI_IDLE",
    "walk": "ANI_WALK",
    "turn": "ANI_TURN",
    "attack1": "ANI_ATTACK1",
    "attack2": "ANI_ATTACK2",
    "attack3": "ANI_ATTACK3",
    "block": "ANI_BLOCK",
    "blockpain": "ANI_BLOCKPAIN",
    "pain": "ANI_PAIN",
    "pain2": "ANI_PAIN2",
    "fall": "ANI_FALL",
    "rise": "ANI_RISE",
    "death": "ANI_DIE",
}
ENTITIES = {
    "homeless_man": {
        "runtime_name": "HomelessMan",
        "health": 82,
        "speed": 1.8,
        "thinkscript": "data/scripts/homeless_man_ai.c",
        "qa_order": [
            "spawn", "idle", "alert_aggro", "walk_start", "walk_loop", "walk_stop",
            "turn_pivot", "unarmed_jab", "two_hand_shove", "heavy_overhand",
            "taunt_hesitate", "light_pain", "heavy_pain", "knockdown_fall",
            "down", "rise", "death",
        ],
        "animations": [
            ("spawn", ["spawn"]),
            ("idle", ["idle", "alert_aggro", "taunt_hesitate"]),
            ("walk", ["walk_start", "walk_loop", "walk_stop"]),
            ("turn", ["turn_pivot"]),
            ("attack1", ["unarmed_jab"]),
            ("attack2", ["two_hand_shove"]),
            ("attack3", ["heavy_overhand"]),
            ("pain", ["light_pain"]),
            ("pain2", ["heavy_pain"]),
            ("fall", ["knockdown_fall", "down"]),
            ("rise", ["rise"]),
            ("death", ["death"]),
        ],
        "attacks": {
            "unarmed_jab": {"damage": 7, "drop": 0, "active": (3, 4), "z": 14},
            "two_hand_shove": {"damage": 9, "drop": 0, "active": (3, 4), "z": 18},
            "heavy_overhand": {"damage": 15, "drop": 1, "active": (5, 6), "z": 16},
        },
    },
    "police_officer": {
        "runtime_name": "PoliceOfficer",
        "health": 96,
        "speed": 2.0,
        "thinkscript": "data/scripts/police_officer_ai.c",
        "qa_order": [
            "spawn", "idle", "alert_command", "walk_start", "walk_loop", "walk_stop",
            "turn_pivot", "baton_jab", "baton_backhand", "baton_overhead", "block",
            "block_impact", "light_pain", "heavy_pain", "knockdown_fall", "down",
            "rise", "death",
        ],
        "animations": [
            ("spawn", ["spawn"]),
            ("idle", ["idle", "alert_command"]),
            ("walk", ["walk_start", "walk_loop", "walk_stop"]),
            ("turn", ["turn_pivot"]),
            ("attack1", ["baton_jab"]),
            ("attack2", ["baton_backhand"]),
            ("attack3", ["baton_overhead"]),
            ("block", ["block"]),
            ("blockpain", ["block_impact"]),
            ("pain", ["light_pain"]),
            ("pain2", ["heavy_pain"]),
            ("fall", ["knockdown_fall", "down"]),
            ("rise", ["rise"]),
            ("death", ["death"]),
        ],
        "attacks": {
            "baton_jab": {"damage": 8, "drop": 0, "active": (3, 4), "z": 14},
            "baton_backhand": {"damage": 11, "drop": 0, "active": (3, 4), "z": 16},
            "baton_overhead": {"damage": 16, "drop": 1, "active": (5, 6), "z": 16},
        },
    },
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def attack_box(pose: dict, damage: int, drop: int, z_reach: int) -> list[int]:
    left, top, right, bottom = pose["body_bounds"]
    width = max(12, min(58, 192 - right + 28))
    height = max(12, min(30, bottom - top))
    x = min(191 - width, max(0, right - 6))
    y = min(159 - height, max(0, top + (bottom - top) // 3))
    return [x, y, width, height, damage, drop, 0, 0, 4, z_reach]


def pose_phase(index: int, count: int, active: tuple[int, int] | None) -> str:
    if active is None:
        return "presentation"
    if index < active[0]:
        return "startup"
    if index <= active[1]:
        return "active"
    return "recovery"


def inject_pose_logger(entity_id: str, config: dict, clips: dict) -> None:
    """Generate literal per-pose runtime markers without dynamic log arguments."""
    controller = ROOT / "openbor" / config["thinkscript"]
    prefix = "hm" if entity_id == "homeless_man" else "po"
    begin = f"// BEGIN GENERATED {prefix.upper()} POSE LOGGER"
    end = f"// END GENERATED {prefix.upper()} POSE LOGGER"
    text = controller.read_text(encoding="utf-8")
    if begin not in text or end not in text:
        raise ValueError(f"{controller}: missing generated pose logger markers")

    bank_offsets: dict[str, int] = {}
    for _animation, clip_ids in config["animations"]:
        offset = 0
        for clip_id in clip_ids:
            bank_offsets[clip_id] = offset
            offset += len(clips[clip_id]["pose_ids"])

    lines = [begin, f"void {prefix}_log_pose(int state, int pose)", "{"]
    first = True
    for state, clip_id in enumerate(config["qa_order"]):
        offset = bank_offsets[clip_id]
        for index, pose_id in enumerate(clips[clip_id]["pose_ids"]):
            keyword = "if" if first else "else if"
            lines.append(
                f'    {keyword}(state == {state} && pose == {offset + index}) '
                f'log("[FOF2_POSE] {pose_id}\\n");'
            )
            first = False
    lines.extend(("}", end))
    generated = "\n".join(lines)
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
    controller.write_text(pattern.sub(lambda _match: generated, text), encoding="utf-8", newline="\n")


def inject_showcase_mapping(entity_id: str, config: dict, clips: dict, poses: list[dict]) -> None:
    """Generate a manifest-order 0..119 mapping to exact native bank frames."""
    controller = ROOT / "openbor" / config["thinkscript"]
    prefix = "hm" if entity_id == "homeless_man" else "po"
    begin = f"// BEGIN GENERATED {prefix.upper()} SHOWCASE MAPPING"
    end = f"// END GENERATED {prefix.upper()} SHOWCASE MAPPING"
    text = controller.read_text(encoding="utf-8")
    if begin not in text or end not in text:
        raise ValueError(f"{controller}: missing generated showcase mapping markers")

    clip_routes: dict[str, tuple[int, str, int]] = {}
    for animation, clip_ids in config["animations"]:
        if animation not in ANIMATION_CONSTANTS:
            raise ValueError(f"{entity_id}: no native constant for {animation}")
        offset = 0
        for clip_id in clip_ids:
            clip_routes[clip_id] = (
                config["qa_order"].index(clip_id),
                ANIMATION_CONSTANTS[animation],
                offset,
            )
            offset += len(clips[clip_id]["pose_ids"])

    pose_routes: dict[str, tuple[int, str, int]] = {}
    for clip_id, clip in clips.items():
        if clip_id not in clip_routes:
            raise ValueError(f"{entity_id}: showcase mapping has no route for clip {clip_id}")
        state, animation_constant, offset = clip_routes[clip_id]
        for index, pose_id in enumerate(clip["pose_ids"]):
            if pose_id in pose_routes:
                raise ValueError(f"{entity_id}: pose {pose_id} appears in multiple showcase routes")
            pose_routes[pose_id] = (state, animation_constant, offset + index)

    pose_ids = [pose["id"] for pose in poses]
    if len(pose_ids) != 120 or len(set(pose_ids)) != 120 or set(pose_ids) != set(pose_routes):
        raise ValueError(f"{entity_id}: direct showcase must biject manifest indices 0..119 to all poses")
    routed_frames = [pose_routes[pose_id] for pose_id in pose_ids]
    if len(set((state, frame) for state, _animation, frame in routed_frames)) != 120:
        raise ValueError(f"{entity_id}: direct showcase state/frame routes are not one-to-one")

    lines = [begin, f"int {prefix}_showcase_map(void self, int request)", "{"]
    for request, pose_id in enumerate(pose_ids):
        state, animation_constant, frame = pose_routes[pose_id]
        keyword = "if" if request == 0 else "else if"
        lines.extend(
            (
                f"    {keyword}(request == {request})",
                "    {",
                f'        changeentityproperty(self, "animation", openborconstant("{animation_constant}"));',
                f'        setentityvar(self, "showcase_state", {state});',
                f'        setentityvar(self, "showcase_frame", {frame});',
                f"        updateframe(self, {frame});",
                f'        setentityvar(self, "logged_state", {state});',
                f'        setentityvar(self, "logged_pose", {frame});',
                f"        {prefix}_log_pose({state}, {frame});",
                "        return 1;",
                "    }",
            )
        )
    lines.extend(("    return 0;", "}", end))
    generated = "\n".join(lines)
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
    controller.write_text(pattern.sub(lambda _match: generated, text), encoding="utf-8", newline="\n")


def validate_script_contract(entity_id: str, config: dict) -> None:
    controller = ROOT / "openbor" / config["thinkscript"]
    contact = ROOT / "openbor" / "data/scripts/entity_enemy_contact.c"
    scripts = [controller, contact]
    if entity_id == "police_officer":
        scripts.append(ROOT / "openbor" / "data/scripts/police_officer_block.c")
    for path in scripts:
        text = path.read_text(encoding="utf-8")
        calls = list(re.finditer(r"log\((.*?)\);", text))
        for call in calls:
            argument = call.group(1).strip()
            if not re.fullmatch(r'"(?:[^"\\]|\\.)*"', argument):
                number = text.count("\n", 0, call.start()) + 1
                raise ValueError(f"{path}:{number}: log must have one string-literal argument")
    controller_text = controller.read_text(encoding="utf-8")
    if 'changeentityproperty(self, "animpos"' in controller_text:
        raise ValueError(f"{controller}: controller frame presentation must use updateframe, not raw animpos writes")
    prefix = "HM" if entity_id == "homeless_man" else "PO"
    showcase_match = re.search(
        rf"// BEGIN GENERATED {prefix} SHOWCASE MAPPING(.*?)// END GENERATED {prefix} SHOWCASE MAPPING",
        controller_text,
        re.DOTALL,
    )
    if showcase_match is None:
        raise ValueError(f"{controller}: missing generated direct-showcase block")
    showcase_text = showcase_match.group(1)
    if 'changeentityproperty(self, "animpos"' in showcase_text:
        raise ValueError(f"{controller}: direct showcase must use updateframe, not raw animpos writes")
    if len(re.findall(r"\bupdateframe\(self, \d+\);", showcase_text)) != 120:
        raise ValueError(f"{controller}: direct showcase must route all 120 poses through updateframe")
    hold_match = re.search(
        rf"int {prefix.lower()}_showcase\(void self, int request\)(.*?)\nvoid {prefix.lower()}_present\(",
        controller_text,
        re.DOTALL,
    )
    if hold_match is None:
        raise ValueError(f"{controller}: missing direct-showcase hold function")
    hold_text = hold_match.group(1)
    if 'changeentityproperty(self, "animpos"' in hold_text:
        raise ValueError(f"{controller}: direct-showcase hold must not write raw animpos")
    if "updateframe(self, frame);" not in hold_text:
        raise ValueError(f"{controller}: direct-showcase hold must refresh through updateframe")
    for token in ('"aiflag", "drop"', '"aiflag", "falling"', "killentity(self)"):
        if token not in controller_text:
            raise ValueError(f"{entity_id}: controller lacks native knockdown/death hook {token!r}")
    for token in ("clock_accumulator", 'openborconstant("THINK_SPEED")', "delta * 60", "while(accumulator >= 200)"):
        if token not in controller_text:
            raise ValueError(f"{entity_id}: controller lacks fixed-60Hz thinkscript clock token {token!r}")
    if controller_text.count('log("[FOF2_POSE] ') != 120:
        raise ValueError(f"{entity_id}: controller must contain 120 literal per-pose markers")
    prefix = "hm" if entity_id == "homeless_man" else "po"
    mapping = re.search(
        re.escape(f"// BEGIN GENERATED {prefix.upper()} SHOWCASE MAPPING")
        + r"(.*?)"
        + re.escape(f"// END GENERATED {prefix.upper()} SHOWCASE MAPPING"),
        controller_text,
        re.DOTALL,
    )
    if mapping is None or len(re.findall(r"(?:if|else if)\(request == (\d+)\)", mapping.group(1))) != 120:
        raise ValueError(f"{entity_id}: controller must contain 120 direct showcase routes")
    route_indices = [
        int(value) for value in re.findall(r"(?:if|else if)\(request == (\d+)\)", mapping.group(1))
    ]
    if route_indices != list(range(120)):
        raise ValueError(f"{entity_id}: direct showcase requests must be the exact range 0..119")
    pose_global = "fof2_qa_hm_pose" if entity_id == "homeless_man" else "fof2_qa_po_pose"
    entity_global = "fof2_qa_hm_entity" if entity_id == "homeless_man" else "fof2_qa_po_entity"
    for token in (f'"{pose_global}"', f'"{entity_global}"', '"showcase_active"', '"showcase_frame"'):
        if token not in controller_text:
            raise ValueError(f"{entity_id}: controller lacks direct showcase token {token!r}")
    for token in ('"qa_mode"', 'request == 0'):
        if token not in controller_text:
            raise ValueError(f"{entity_id}: controller lacks explicit QA ownership token {token!r}")
    contact_text = contact.read_text(encoding="utf-8")
    for token in ('getlocalvar("damagetaker")', 'getlocalvar("blocked")'):
        if token not in contact_text:
            raise ValueError(f"contact callback lacks didhitscript local {token!r}")
    if "attackid" in contact_text or "attack_id" in contact_text:
        raise ValueError("didhitscript does not supply an attack ID")


def build_entity(entity_id: str, config: dict) -> dict:
    manifest_path = ROOT / "content" / "characters" / entity_id / "sprites" / "pose_manifest.json"
    design_path = ROOT / "content" / "characters" / entity_id / "metadata" / "production_manifest.json"
    manifest = load_json(manifest_path)
    design = load_json(design_path)
    poses = manifest["poses"]
    clips = manifest["clips"]
    actions = {action["id"]: action for action in design["actions"]}
    if design["maturity"] != "production" or design["entity_class"] != "basic_enemy":
        raise ValueError(f"{entity_id}: expected production basic_enemy brief")
    if int(design["exact_unique_pose_target"]) != 120 or len(poses) != 120:
        raise ValueError(f"{entity_id}: exact 120-pose art gate is not satisfied")
    if design["root_offset"] != [96, 156] or manifest["root"] != [96, 156]:
        raise ValueError(f"{entity_id}: runtime requires root 96 156")
    if set(config["qa_order"]) != set(clips) or len(config["qa_order"]) != len(clips):
        raise ValueError(f"{entity_id}: deterministic QA order must cover every clip exactly once")
    inject_pose_logger(entity_id, config, clips)
    inject_showcase_mapping(entity_id, config, clips, poses)
    validate_script_contract(entity_id, config)

    by_id = {pose["id"]: pose for pose in poses}
    output = ROOT / "openbor" / "data" / "chars" / entity_id
    sprites = output / "sprites"
    sprites.mkdir(parents=True, exist_ok=True)
    referenced: list[str] = []
    runtime_clips: dict[str, dict] = {}
    model_lines = [
        f"name {config['runtime_name']}",
        "type enemy",
        f"health {config['health']}",
        f"speed {config['speed']}",
        "grabdistance 34",
        "knockdowncount 0",
        "remove None",
        "death_config death_air death_ground remove_vanish_air remove_vanish_ground",
        "subject_to_gravity 1",
        "shadow 0",
        "gfxshadow 1",
        f"onspawnscript {config['thinkscript']}",
        f"thinkscript {config['thinkscript']}",
        "didhitscript data/scripts/entity_enemy_contact.c",
    ]
    if entity_id == "police_officer":
        model_lines.append("didblockscript data/scripts/police_officer_block.c")
    model_lines.append("")

    for animation, clip_ids in config["animations"]:
        model_lines.extend((f"anim {animation}", "    delay 10000"))
        frame_offset = 0
        for clip_id in clip_ids:
            clip = clips[clip_id]
            action = actions.get(clip_id)
            if action is None:
                raise ValueError(f"{entity_id}: production timing sheet lacks {clip_id}")
            if action["trigger"] != clip["trigger"] or action["native_animation"] != clip["native_animation"]:
                raise ValueError(f"{entity_id}: {clip_id} production trigger/native mapping drift")
            ids = clip["pose_ids"]
            active_spec = config["attacks"].get(clip_id)
            active = tuple(active_spec["active"]) if active_spec else None
            runtime_clips[clip_id] = {
                "native_animation": animation,
                "frame_start": frame_offset,
                "frame_end": frame_offset + len(ids) - 1,
                "pose_ids": ids,
                "production_trigger": clip["trigger"],
                "timing_ticks": action["ticks"],
                "qa_request": config["qa_order"].index(clip_id) + 1,
                "frame_owner": "thinkscript",
            }
            for index, pose_id in enumerate(ids):
                pose = by_id[pose_id]
                source = ROOT / pose["path"]
                generated = output / "sprites" / f"{pose_id}.png"
                shutil.copyfile(source, generated)
                if sha256(source) != sha256(generated):
                    raise ValueError(f"{pose_id}: generated sprite differs from approved source")
                generated_rel = generated.relative_to(ROOT).as_posix()
                referenced.append(pose_id)
                pose["generated_path"] = generated_rel
                pose["runtime_reachable"] = True
                pose["gameplay_evidence"] = []
                pose["runtime"] = {
                    "model_animation": animation,
                    "frame_index": frame_offset + index,
                    "phase": pose_phase(index, len(ids), active),
                    "body_box": [
                        pose["body_bounds"][0],
                        pose["body_bounds"][1],
                        pose["body_bounds"][2] - pose["body_bounds"][0],
                        pose["body_bounds"][3] - pose["body_bounds"][1],
                        14,
                    ],
                    "attack_box": None,
                }
                left, top, right, bottom = pose["body_bounds"]
                model_lines.append(f"    offset 96 156")
                model_lines.append(f"    bbox {left} {top} {right-left} {bottom-top} 14")
                model_lines.append("    attack 0")
                if active_spec and active[0] <= index <= active[1]:
                    box = attack_box(pose, active_spec["damage"], active_spec["drop"], active_spec["z"])
                    pose["runtime"]["attack_box"] = box
                    model_lines.append("    attack " + " ".join(str(value) for value in box))
                model_lines.append(f"    frame data/chars/{entity_id}/sprites/{pose_id}.png")
            frame_offset += len(ids)
        if animation in {"idle", "walk", "block"}:
            model_lines.append("    loop 1")
        model_lines.extend(("    attack 0", ""))

    if len(referenced) != 120 or len(set(referenced)) != 120 or set(referenced) != set(by_id):
        raise ValueError(f"{entity_id}: runtime routing must reference every unique pose exactly once")

    model_path = output / f"{entity_id}.txt"
    model_path.write_text("\n".join(model_lines).rstrip() + "\n", encoding="utf-8", newline="\n")
    runtime_manifest = {
        "schema_version": 1,
        "entity_id": entity_id,
        "runtime_name": config["runtime_name"],
        "runtime_build": "OpenBOR 4.0 Build 7949",
        "source_pose_manifest": manifest_path.relative_to(ROOT).as_posix(),
        "model": model_path.relative_to(ROOT).as_posix(),
        "model_sha256": sha256(model_path),
        "controller": config["thinkscript"],
        "controller_sha256": sha256(ROOT / "openbor" / config["thinkscript"]),
        "contact_callback": "data/scripts/entity_enemy_contact.c",
        "contact_callback_sha256": sha256(ROOT / "openbor" / "data/scripts/entity_enemy_contact.c"),
        "root": [96, 156],
        "unique_approved": 120,
        "unique_referenced": 120,
        "unique_runtime_reachable": 120,
        "animation_owner": "thinkscript",
        "damage_route": "native drop/falling signal -> scripted FALL range -> scripted down range -> RISE",
        "death_route": "health zero -> 60-tick DEATH presentation -> killentity removal; QA death holds for capture while health remains positive",
        "death_config": ["death_air", "death_ground", "remove_vanish_air", "remove_vanish_ground"],
        "native_animation_banks": [item[0] for item in config["animations"]],
        "clips": runtime_clips,
        "qa": {
            "request_global": "fof2_qa_hm_request" if entity_id == "homeless_man" else "fof2_qa_po_request",
            "request_range": [1, len(config["qa_order"])],
            "request_zero": "exit QA hold and resume production AI",
            "state_requests": {
                clip_id: index + 1 for index, clip_id in enumerate(config["qa_order"])
            },
            "pose_log_prefix": "[FOF2_POSE] ",
            "direct_pose_request_global": "fof2_qa_hm_pose" if entity_id == "homeless_man" else "fof2_qa_po_pose",
            "direct_pose_entity_global": "fof2_qa_hm_entity" if entity_id == "homeless_man" else "fof2_qa_po_entity",
            "direct_pose_request_range": [0, 119],
            "direct_pose_off": "absent or -1 resumes normal controller state",
            "direct_pose_mapping": "pose-manifest order; exact native animation and frame; held until request changes",
            "qa_death": "nonlethal held presentation; real health-zero death still removes after 60 ticks",
        },
        "gameplay_evidence": [],
    }
    if entity_id == "police_officer":
        runtime_manifest["block_callback"] = "data/scripts/police_officer_block.c"
        runtime_manifest["block_callback_sha256"] = sha256(
            ROOT / "openbor" / "data/scripts/police_officer_block.c"
        )
    runtime_path = output / f"{entity_id}_openbor_manifest.json"
    manifest["runtime"] = {
        "build": "OpenBOR 4.0 Build 7949",
        "model": model_path.relative_to(ROOT).as_posix(),
        "manifest": runtime_path.relative_to(ROOT).as_posix(),
        "model_sha256": runtime_manifest["model_sha256"],
        "controller": config["thinkscript"],
        "controller_sha256": runtime_manifest["controller_sha256"],
        "animation_owner": "thinkscript",
        "unique_referenced_pose_count": 120,
        "unique_runtime_reachable_pose_count": 120,
        "qa_request_global": runtime_manifest["qa"]["request_global"],
        "qa_request_range": runtime_manifest["qa"]["request_range"],
        "pose_log_prefix": runtime_manifest["qa"]["pose_log_prefix"],
        "direct_pose_request_global": runtime_manifest["qa"]["direct_pose_request_global"],
        "direct_pose_entity_global": runtime_manifest["qa"]["direct_pose_entity_global"],
        "direct_pose_request_range": runtime_manifest["qa"]["direct_pose_request_range"],
        "gameplay_evidence": [],
    }
    write_json(manifest_path, manifest)
    runtime_manifest["source_pose_manifest_sha256"] = sha256(manifest_path)
    write_json(runtime_path, runtime_manifest)
    return {"entity": entity_id, "model": str(model_path.relative_to(ROOT)), "poses": 120}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--entity", action="append", choices=sorted(ENTITIES))
    args = parser.parse_args()
    selected = args.entity or list(ENTITIES)
    reports = [build_entity(entity_id, ENTITIES[entity_id]) for entity_id in selected]
    print(json.dumps({"status": "pass", "entities": reports}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
