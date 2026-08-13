"""Build deterministic registries and the entity combat tech-demo harness."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "openbor" / "data"
SHOWCASE_MARKER_PALETTE_INDEX = 102
PANEL_ORDER = "abcd"
PANEL_SIZE = (640, 360)
PANEL_WORLD_SIZE = (PANEL_SIZE[0] * len(PANEL_ORDER), PANEL_SIZE[1])
PANEL_SOURCE_COMMIT = "84fd94e4ca1b858cdd9f2f28393944aa7cfcd783"
PORTAL_PIXEL_COUNTS = {"a": 37436, "b": 9295, "c": 6175, "d": 48666}
PORTAL_LAYER_SOURCES = {
    "far": {
        "path": DATA / "levels" / "i8_underpass" / "art" / "far.png",
        "size": (2048, 360),
        "sha256": "c1a406d156fb05faaa2c7aa0f7f76d59573db703a6a2541aeadfe89fbf5e0ce9",
    },
    "mid": {
        "path": DATA / "levels" / "i8_underpass" / "art" / "mid.png",
        "size": (1792, 360),
        "sha256": "8b5ab8416b2d3a6ab6f9d7805f66cd261940267ece786ce28c6d4dc98f60bada",
    },
}

MODELS = """# Fades of Fate 2.0 model registry
# Build 7949-supported native animation capacity.
maxattacks 4
maxfreespecials 7
nodropen
load BlackDave data/chars/black_dave/black_dave.txt
load HomelessMan data/chars/homeless_man/homeless_man.txt
load PoliceOfficer data/chars/police_officer/police_officer.txt
load BlackDaveImpact data/chars/black_dave/black_dave_impact_fx.txt
load BlackDaveFlame data/chars/black_dave/black_dave_flame_fx.txt
load BlackDaveFlameShot data/chars/black_dave/black_dave_flame_shot.txt
"""

LEVELS = """set Entity_Combat_Tech_Demo
skiptoset 0
lives 5
credits 5
cansave 0
z 252 326 252
maxplayers 1
skipselect BlackDave
file data/levels/entity_combat_tech_demo.txt
next
end
"""

GAME = """name Fades of Fate 2.0
video 640x360
maxplayers 1
models data/models.txt
levels data/levels.txt
"""

TECH_DEMO_LEVEL = """# Fades of Fate 2.0 entity combat tech demo — OpenBOR Build 7949.
# Panel-only free-walk profile; creates no stage art.
settime 0
notime 1
noslow 1
direction both

spawn1 200 280 0
updatescript data/scripts/entity_tech_demo.c
updatedscript data/scripts/entity_pose_overlay.c

panel data/levels/i8_underpass/panels/underpass_a.png
panel data/levels/i8_underpass/panels/underpass_b.png
panel data/levels/i8_underpass/panels/underpass_c.png
panel data/levels/i8_underpass/panels/underpass_d.png
order abcd
cameratype 0

spawn HomelessMan
alias QA_HomelessMan
coords 400 280 0
at 0

spawn PoliceOfficer
alias QA_PoliceOfficer
coords 540 292 0
at 0
"""

SAFE_SPAWNS = {
    "HomelessMan": (400, 280, 0),
    "PoliceOfficer": (540, 292, 0),
}

BASELINE_INDEX = 4095
BASELINE_TICKS = 400
POSE_TICKS = 40


def pose_ids() -> list[str]:
    result: list[str] = []
    for entity_id, expected in (("black_dave", 220), ("homeless_man", 120), ("police_officer", 120)):
        manifest = ROOT / "content" / "characters" / entity_id / "sprites" / "pose_manifest.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        manifest_ids = [str(record["id"]) for record in data.get("poses", [])]
        ids = manifest_ids
        if entity_id == "black_dave":
            schedule_path = DATA / "chars" / "black_dave" / "black_dave_pose_qa_schedule.json"
            schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
            requests = sorted(schedule.get("requests", []), key=lambda record: int(record["request"]))
            if [int(record["request"]) for record in requests] != list(range(expected)):
                raise ValueError(f"{schedule_path}: requests must be the exact range 0..{expected - 1}")
            ids = [str(record["pose_id"]) for record in requests]
            if set(ids) != set(manifest_ids):
                raise ValueError(f"{schedule_path}: pose IDs must equal the Black Dave art manifest")
        if len(ids) != expected or len(set(ids)) != expected:
            raise ValueError(f"{manifest}: expected {expected} unique ordered pose IDs")
        result.extend(ids)
    if len(result) != 460 or len(set(result)) != 460:
        raise ValueError("combined showcase schedule must contain 460 globally unique pose IDs")
    return result


def build_harness() -> str:
    return f'''/* Deterministic packaged showcase followed by real combat. */
void oncreate()
{{
    setglobalvar("fof2_showcase_mode", 0);
    setglobalvar("fof2_showcase_phase", 0);
    setglobalvar("fof2_showcase_start", -1);
    setglobalvar("fof2_showcase_index", {BASELINE_INDEX});
    setglobalvar("fof2_qa_dave_enabled", 0);
    setglobalvar("fof2_qa_hm_pose", -1);
    setglobalvar("fof2_qa_po_pose", -1);
    setglobalvar("fof2_qa_hm_request", 0);
    setglobalvar("fof2_qa_po_request", 0);
    setglobalvar("fof2_enemy_attack_token", NULL());
    setglobalvar("fof2_native_join_pulse", 0);
    setglobalvar("fof2_native_join_logged", 0);
    setglobalvar("fof2_combat_evidence_mode", 0);
    setglobalvar("fof2_contact_seq", 0);
    setglobalvar("fof2_dave_block_seq", 0);
    setglobalvar("fof2_po_block_seq", 0);
    setglobalvar("fof2_test_hm_choice", -1);
    setglobalvar("fof2_test_po_choice", -1);
    log("[FOF2_ENTITY_QA] initialized playable combat demo\\n");
}}

void demo_clear_join_input()
{{
    changeplayerproperty(0, "keys", 0);
    changeplayerproperty(0, "playkeys", 0);
    changeplayerproperty(0, "newkeys", 0);
    changeplayerproperty(0, "releasekeys", 0);
}}

void demo_request_native_player()
{{
    int pulse;
    int startkey;
    pulse = getglobalvar("fof2_native_join_pulse");
    if(pulse == 0)
    {{
        startkey = openborconstant("FLAG_START");
        changeplayerproperty(0, "credits", 1);
        changeplayerproperty(0, "keys", startkey);
        changeplayerproperty(0, "playkeys", startkey);
        changeplayerproperty(0, "newkeys", startkey);
        changeplayerproperty(0, "releasekeys", 0);
        setglobalvar("fof2_native_join_pulse", 1);
        log("[FOF2_ENTITY_QA] native_player0_join_requested\\n");
        return;
    }}
    demo_clear_join_input();
    if(pulse == 1)
    {{
        setglobalvar("fof2_native_join_pulse", 2);
        log("[FOF2_ENTITY_QA] native_player0_join_input_cleared\\n");
    }}
}}

void demo_place(void actor, int x, int z)
{{
    if(actor == NULL()) return;
    changeentityproperty(actor, "direction", 1);
    changeentityproperty(actor, "position", x, z, 0);
}}

void demo_finish_showcase(void dave, void homeless, void police)
{{
    setglobalvar("fof2_showcase_mode", 0);
    setglobalvar("fof2_showcase_index", -1);
    setglobalvar("fof2_qa_dave_enabled", 0);
    setglobalvar("fof2_qa_hm_pose", -1);
    setglobalvar("fof2_qa_po_pose", -1);
    setglobalvar("fof2_qa_hm_request", 0);
    setglobalvar("fof2_qa_po_request", 0);
    setglobalvar("fof2_enemy_attack_token", NULL());
    demo_place(dave, 200, 280);
    demo_place(homeless, 400, 280);
    demo_place(police, 540, 292);
    log("[FOF2_ENTITY_QA] showcase_complete combat_live\\n");
}}

void main()
{{
    void dave;
    void homeless;
    void police;
    int now;
    int start;
    int phase;
    int request;
    dave = getplayerproperty(0, "entity");
    now = openborvariant("elapsed_time");
    if(dave == NULL())
    {{
        demo_request_native_player();
        setglobalvar("fof2_showcase_start", now);
        return;
    }}
    if(getglobalvar("fof2_native_join_logged") == 0)
    {{
        demo_clear_join_input();
        setglobalvar("fof2_native_join_logged", 1);
        log("[FOF2_ENTITY_QA] black_dave_player0_native_spawned\\n");
    }}
    homeless = getglobalvar("fof2_qa_hm_entity");
    police = getglobalvar("fof2_qa_po_entity");
    if(getglobalvar("fof2_showcase_mode") != 1)
    {{
        return;
    }}
    phase = getglobalvar("fof2_showcase_phase");
    start = getglobalvar("fof2_showcase_start");
    if(start < 0)
    {{
        start = now;
        setglobalvar("fof2_showcase_start", start);
    }}
    if(playerkeys(0, 1, "attack4") != 0)
    {{
        demo_finish_showcase(dave, homeless, police);
        return;
    }}
    if(phase == 0)
    {{
        demo_place(dave, -500, 300);
        demo_place(homeless, -500, 300);
        demo_place(police, -500, 300);
        setglobalvar("fof2_showcase_index", {BASELINE_INDEX});
        if(now - start >= {BASELINE_TICKS})
        {{
            setglobalvar("fof2_showcase_phase", 1);
            setglobalvar("fof2_qa_dave_enabled", 1);
            setglobalvar("fof2_showcase_start", now);
            log("[FOF2_ENTITY_QA] phase=black_dave\\n");
        }}
        return;
    }}
    if(phase == 1)
    {{
        demo_place(dave, 320, 300);
        demo_place(homeless, -500, 300);
        demo_place(police, -500, 300);
        request = getglobalvar("bd_qa_request");
        if(request >= 0 && request < 220) setglobalvar("fof2_showcase_index", request);
        if(getglobalvar("bd_qa_tick") >= 2640)
        {{
            setglobalvar("fof2_qa_dave_enabled", 0);
            setglobalvar("fof2_showcase_phase", 2);
            setglobalvar("fof2_showcase_start", now);
            setglobalvar("fof2_qa_hm_pose", 0);
            setglobalvar("fof2_showcase_index", 220);
            log("[FOF2_ENTITY_QA] phase=homeless_man\\n");
        }}
        return;
    }}
    if(phase == 2)
    {{
        demo_place(dave, -500, 300);
        demo_place(homeless, 320, 300);
        demo_place(police, -500, 300);
        request = (now - start) / {POSE_TICKS};
        if(request < 120)
        {{
            setglobalvar("fof2_qa_hm_pose", request);
            setglobalvar("fof2_showcase_index", 220 + request);
        }}
        else
        {{
            setglobalvar("fof2_qa_hm_pose", -1);
            setglobalvar("fof2_qa_po_pose", 0);
            setglobalvar("fof2_showcase_phase", 3);
            setglobalvar("fof2_showcase_start", now);
            setglobalvar("fof2_showcase_index", 340);
            log("[FOF2_ENTITY_QA] phase=police_officer\\n");
        }}
        return;
    }}
    if(phase == 3)
    {{
        demo_place(dave, -500, 300);
        demo_place(homeless, -500, 300);
        demo_place(police, 320, 300);
        request = (now - start) / {POSE_TICKS};
        if(request < 120)
        {{
            setglobalvar("fof2_qa_po_pose", request);
            setglobalvar("fof2_showcase_index", 340 + request);
        }}
        else demo_finish_showcase(dave, homeless, police);
    }}
}}
'''


def build_overlay(ids: list[str]) -> str:
    label_lines = [
        f'    if(index == {BASELINE_INDEX}) drawstring(8, 8, 0, "FOF2 BASELINE", z + 1);'
    ]
    for index, pose_id in enumerate(ids):
        label_lines.append(
            f'    if(index == {index}) drawstring(8, 8, 0, "{index:03d} {pose_id}", z + 1);'
        )
    labels = "\n".join(label_lines)
    return f'''/* Post-entity overlay: visible pose identity plus a 12-bit barcode. */
int demo_barcode_bit(int value, int bit)
{{
    int divisor;
    divisor = 1;
    while(bit > 0)
    {{
        divisor = divisor * 2;
        bit = bit - 1;
    }}
    return (value / divisor) % 2;
}}

void main()
{{
    int index;
    int bit;
    int parity;
    int color;
    int z;
    if(getglobalvar("fof2_showcase_mode") != 1) return;
    index = getglobalvar("fof2_showcase_index");
    if(index < 0 || index > {BASELINE_INDEX}) return;
    z = openborvariant("hud_z") + 100;
    drawbox(4, 4, 132, 40, z, 0);
{labels}
    drawbox(8, 28, 6, 8, z + 1, 6461939);
    parity = 0;
    bit = 0;
    while(bit < 12)
    {{
        color = 0;
        if(demo_barcode_bit(index, bit) == 1)
        {{
            color = 6461939;
            parity = 1 - parity;
        }}
        drawbox(16 + bit * 8, 28, 6, 8, z + 1, color);
        bit = bit + 1;
    }}
    color = 0;
    if(parity == 1) color = 6461939;
    drawbox(112, 28, 6, 8, z + 1, color);
    drawbox(120, 28, 6, 8, z + 1, 6461939);
}}
'''


def write(path: Path, payload: str) -> None:
    path.write_text(payload, encoding="utf-8", newline="\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def portal_mask() -> Image.Image:
    """Rebuild the exact sky-portal mask authored in the verified 2.0 stage source."""
    mask = Image.new("L", PANEL_WORLD_SIZE, 0)
    draw = ImageDraw.Draw(mask)

    draw.polygon([(124, 76), (632, 76), (632, 172), (184, 172)], fill=255)
    draw.rectangle((444, 70, 536, 190), fill=0)

    b = 640
    draw.polygon([(b + 208, 118), (b + 376, 118), (b + 376, 172), (b + 208, 172)], fill=255)

    c = 1280
    draw.polygon([(c + 568, 78), (c + 632, 78), (c + 632, 172), (c + 568, 172)], fill=255)

    d = 1920
    draw.polygon(
        [(d + 108, 136), (d + 420, 38), (d + 632, 0), (d + 632, 172), (d + 108, 172)],
        fill=255,
    )
    draw.rectangle((d + 324, 54, d + 416, 192), fill=0)
    return mask


def flatten_panel_portals() -> dict:
    """Bake verified far/mid art behind panel portals for the no-layer Build 7949 profile."""
    panel_root = DATA / "levels" / "i8_underpass" / "panels"
    mask = portal_mask()
    panels: list[dict[str, object]] = []
    palettes: list[bytes] = []

    for index, letter in enumerate(PANEL_ORDER):
        path = panel_root / f"underpass_{letter}.png"
        with Image.open(path) as image:
            if image.mode != "P" or image.size != PANEL_SIZE:
                raise ValueError(f"{path}: expected indexed {PANEL_SIZE[0]}x{PANEL_SIZE[1]} panel")
            palette = image.getpalette()
            if palette is None:
                raise ValueError(f"{path}: indexed panel has no palette")
            pixels = image.tobytes()
        palette_bytes = bytes((palette + [0] * 768)[:768])
        palettes.append(palette_bytes)
        panel_mask = mask.crop((index * 640, 0, (index + 1) * 640, 360)).tobytes()
        portal_count = sum(value != 0 for value in panel_mask)
        if portal_count != PORTAL_PIXEL_COUNTS[letter]:
            raise ValueError(
                f"{path}: authored portal mask has {portal_count} pixels, expected {PORTAL_PIXEL_COUNTS[letter]}"
            )
        unexpected_zeros = sum(pixel == 0 and not portal for pixel, portal in zip(pixels, panel_mask))
        transparent_pixels = pixels.count(0)
        if unexpected_zeros or transparent_pixels not in (0, portal_count):
            raise ValueError(
                f"{path}: panel is neither the verified cutout nor deterministic flattened form "
                f"(transparent={transparent_pixels}, unexpected={unexpected_zeros})"
            )
        if transparent_pixels == portal_count and any(
            pixel != 0 for pixel, portal in zip(pixels, panel_mask) if portal
        ):
            raise ValueError(f"{path}: transparent portal mask does not match the verified 2.0 source")
        panels.append(
            {
                "letter": letter,
                "path": path,
                "pixels": pixels,
                "mask": panel_mask,
                "input_sha256": sha256(path),
                "input_transparent_pixels": transparent_pixels,
            }
        )

    if any(palette != palettes[0] for palette in palettes[1:]):
        raise ValueError("tech-demo panels A-D must share one identical palette")

    layer_images: dict[str, Image.Image] = {}
    layer_report: dict[str, dict[str, object]] = {}
    for name, record in PORTAL_LAYER_SOURCES.items():
        path = record["path"]
        assert isinstance(path, Path)
        actual_hash = sha256(path)
        if actual_hash != record["sha256"]:
            raise ValueError(
                f"{path}: verified 2.0 {name} layer hash drifted; got {actual_hash}, expected {record['sha256']}"
            )
        with Image.open(path) as image:
            if image.mode != "P" or image.size != record["size"]:
                raise ValueError(f"{path}: expected indexed verified source layer size {record['size']}")
            palette = image.getpalette()
            layer = image.copy()
        layer_palette = bytes(((palette or []) + [0] * 768)[:768])
        if layer_palette != palettes[0]:
            raise ValueError(f"{path}: verified source layer palette differs from the panel palette")
        layer_images[name] = layer.resize(PANEL_WORLD_SIZE, Image.Resampling.NEAREST)
        layer_report[name] = {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": actual_hash,
            "size": list(record["size"]),
        }

    far_pixels = layer_images["far"].tobytes()
    if 0 in far_pixels:
        raise ValueError("verified far layer must give every panel-only portal an opaque fallback pixel")

    outputs: list[tuple[Path, bytes, bytes, dict[str, object]]] = []
    for index, panel in enumerate(panels):
        start = index * 640
        far = layer_images["far"].crop((start, 0, start + 640, 360)).tobytes()
        mid = layer_images["mid"].crop((start, 0, start + 640, 360)).tobytes()
        source_pixels = bytes(mid_pixel if mid_pixel else far_pixel for mid_pixel, far_pixel in zip(mid, far))
        pixels = panel["pixels"]
        panel_mask = panel["mask"]
        assert isinstance(pixels, bytes) and isinstance(panel_mask, bytes)
        flattened = bytes(
            source if portal else original
            for original, source, portal in zip(pixels, source_pixels, panel_mask)
        )
        if any(original != output for original, output, portal in zip(pixels, flattened, panel_mask) if not portal):
            raise ValueError(f"{panel['path']}: flattening changed an opaque authored panel pixel")
        if 0 in flattened:
            raise ValueError(f"{panel['path']}: panel-only output still exposes transparent pixels")
        output = Image.frombytes("P", PANEL_SIZE, flattened)
        output.putpalette(list(palettes[0]))
        output.info["transparency"] = 0
        panel["changed_pixels"] = sum(a != b for a, b in zip(pixels, flattened))
        outputs.append((panel["path"], flattened, palettes[0], panel))

    for path, pixels, palette, _ in outputs:
        output = Image.frombytes("P", PANEL_SIZE, pixels)
        output.putpalette(list(palette))
        output.info["transparency"] = 0
        output.save(path, optimize=False)

    panel_report: dict[str, dict[str, object]] = {}
    for _, _, _, panel in outputs:
        path = panel["path"]
        assert isinstance(path, Path)
        letter = str(panel["letter"])
        panel_report[letter] = {
            "path": path.relative_to(ROOT).as_posix(),
            "input_sha256": panel["input_sha256"],
            "output_sha256": sha256(path),
            "portal_pixels": PORTAL_PIXEL_COUNTS[letter],
            "input_transparent_pixels": panel["input_transparent_pixels"],
            "changed_pixels": panel["changed_pixels"],
            "output_transparent_pixels": 0,
        }

    return {
        "status": "pass",
        "source_commit": PANEL_SOURCE_COMMIT,
        "method": "nearest indexed far then nonzero mid behind exact authored portal mask",
        "opaque_panel_pixels_preserved": True,
        "palette_sha256": hashlib.sha256(palettes[0]).hexdigest(),
        "source_layers": layer_report,
        "panels": panel_report,
    }


def panel_palette() -> bytes:
    palettes: list[bytes] = []
    for letter in PANEL_ORDER:
        panel = DATA / "levels" / "i8_underpass" / "panels" / f"underpass_{letter}.png"
        with Image.open(panel) as image:
            if image.mode != "P" or image.size != PANEL_SIZE:
                raise ValueError(f"{panel}: expected indexed {PANEL_SIZE[0]}x{PANEL_SIZE[1]} panel")
            palette = image.getpalette()
        if palette is None:
            raise ValueError(f"{panel}: indexed panel has no palette")
        palettes.append(bytes((palette + [0] * 768)[:768]))
    if any(palette != palettes[0] for palette in palettes[1:]):
        raise ValueError("tech-demo panels A-D must share one identical palette")
    return palettes[0]


def validate_text(flatten_report: dict) -> dict:
    required = [
        DATA / "chars" / "homeless_man" / "homeless_man.txt",
        DATA / "chars" / "police_officer" / "police_officer.txt",
        DATA / "scripts" / "homeless_man_ai.c",
        DATA / "scripts" / "police_officer_ai.c",
        DATA / "scripts" / "police_officer_block.c",
        DATA / "scripts" / "entity_enemy_contact.c",
        DATA / "scripts" / "entity_tech_demo.c",
        DATA / "scripts" / "entity_pose_overlay.c",
        DATA / "levels" / "entity_combat_tech_demo.txt",
    ]
    missing = [path.relative_to(ROOT).as_posix() for path in required if not path.is_file()]
    if missing:
        raise ValueError(f"missing generated/runtime files: {missing}")
    level = (DATA / "levels" / "entity_combat_tech_demo.txt").read_text(encoding="utf-8")
    if re.search(r"^\s*(?:background|bglayer|fglayer|layer)\s+", level, flags=re.MULTILINE) or "wait" in level:
        raise ValueError("tech demo must use the panel-only convention and no empty wait")
    expected_panels = [
        f"data/levels/i8_underpass/panels/underpass_{letter}.png" for letter in "abcd"
    ]
    panels = re.findall(r"^panel\s+(\S+)\s*$", level, flags=re.MULTILINE)
    if panels != expected_panels or "order abcd" not in level:
        raise ValueError("tech demo must reuse the four verified 640x360 panel assets")
    if level.count("updatedscript data/scripts/entity_pose_overlay.c") != 1:
        raise ValueError("tech demo requires exactly one post-entity pose overlay")
    for model, coords in SAFE_SPAWNS.items():
        block = re.search(
            rf"^spawn\s+{re.escape(model)}\s*$.*?^coords\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s*$.*?^at\s+0\s*$",
            level,
            flags=re.MULTILINE | re.DOTALL,
        )
        if block is None or tuple(int(value) for value in block.groups()) != coords:
            raise ValueError(f"tech demo requires reviewed safe spawn for {model}: {coords}")
    if (DATA / "video.txt").read_text(encoding="utf-8") != "video 640x360\n":
        raise ValueError("video.txt must contain exactly 'video 640x360'")
    palette = panel_palette()
    system_palette = (DATA / "pal.act").read_bytes()
    if len(system_palette) != 768 or system_palette[:384] != palette[:384]:
        raise ValueError("panel-only demo pal.act indices 0..127 must match the shared panel palette")
    marker_rgb = system_palette[
        SHOWCASE_MARKER_PALETTE_INDEX * 3 : SHOWCASE_MARKER_PALETTE_INDEX * 3 + 3
    ]
    marker_luma = (299 * marker_rgb[0] + 587 * marker_rgb[1] + 114 * marker_rgb[2]) / 1000
    if marker_luma < 128:
        raise ValueError(f"showcase marker palette index {SHOWCASE_MARKER_PALETTE_INDEX} is not bright")
    return {
        "status": "pass",
        "models": ["BlackDave", "HomelessMan", "PoliceOfficer"],
        "level": "openbor/data/levels/entity_combat_tech_demo.txt",
        "panel_assets": "reused from verified I-8 set",
        "showcase_pose_count": 460,
        "showcase_pose_ticks": POSE_TICKS,
        "baseline_index": BASELINE_INDEX,
        "panel_flattening": flatten_report,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-enemy-build", action="store_true")
    args = parser.parse_args()
    if not args.skip_enemy_build:
        subprocess.run([sys.executable, str(ROOT / "tools" / "Build-OpenBOR-Enemies.py")], check=True)
    flatten_report = flatten_panel_portals()
    write(DATA / "models.txt", MODELS)
    write(DATA / "levels.txt", LEVELS)
    write(DATA / "game.txt", GAME)
    write(DATA / "video.txt", "video 640x360\n")
    (DATA / "pal.act").write_bytes(panel_palette())
    write(DATA / "levels" / "entity_combat_tech_demo.txt", TECH_DEMO_LEVEL)
    ids = pose_ids()
    write(DATA / "scripts" / "entity_tech_demo.c", build_harness())
    write(DATA / "scripts" / "entity_pose_overlay.c", build_overlay(ids))
    print(json.dumps(validate_text(flatten_report), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
