#!/usr/bin/env python3
"""CLI for the fail-closed environment authoring pipeline.

Examples are documented in ``docs/content-generation/LOW_COST_ENVIRONMENT_AGENT.md``.
All generated files are outputs of this tool; recipes, style profiles, and
module metadata are the editable sources.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.environment_generation import (  # noqa: E402
    EnvironmentGenerationError,
    EnvironmentGenerator,
    load_library,
    load_recipe,
    write_json,
)


def _path(value: str, root: Path) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else root / candidate


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _generator(args: argparse.Namespace) -> EnvironmentGenerator:
    root = Path(args.project_root).resolve()
    recipe = load_recipe(_path(args.recipe, root))
    return EnvironmentGenerator(load_library(root), recipe, seed=getattr(args, "seed", None))


def _write_preview(root: Path, manifest: dict[str, Any], output: Path) -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError as error:
        raise EnvironmentGenerationError("preview requires Pillow; install the project authoring dependencies") from error
    width = int(manifest["recipe"]["target_length"])
    canvas = Image.new("RGBA", (width, 360), (12, 16, 28, 255))
    draw = ImageDraw.Draw(canvas)
    for placement in manifest.get("placements", ()):
        module_id = str(placement["module_id"])
        source = next((record["source"] for record in manifest.get("source_attribution", ()) if record["module_id"] == module_id), "")
        if source.startswith("assets/"):
            path = root / source
            if path.is_file():
                image = Image.open(path).convert("RGBA")
                x = int(placement["x"])
                crop = image.crop((0, 0, min(image.width, max(0, width - x)), min(image.height, 360)))
                canvas.alpha_composite(crop, (x, 0))
        else:
            x = int(placement["x"])
            draw.rectangle((x, 280, min(width - 1, x + 48), 326), outline=(255, 218, 76, 220), width=2)
            draw.text((x + 2, 282), module_id[:8], fill=(255, 218, 76, 255))
    for marker in manifest.get("spawn_markers", ()):
        x = int(marker["x"])
        draw.line((x, 235, x, 326), fill=(57, 217, 230, 180), width=1)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fades of Fate deterministic environment authoring")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list-modules")
    list_parser.add_argument("--style-profile", default="fades_environment_v1")
    list_parser.add_argument("--category")

    inspect_parser = sub.add_parser("inspect-module")
    inspect_parser.add_argument("module_id")

    validate_library = sub.add_parser("validate-library")
    validate_library.add_argument("--style-profile", default="fades_environment_v1")

    analyze = sub.add_parser("analyze-assets")
    analyze.add_argument("--style-profile", default="fades_environment_v1")
    analyze.add_argument("--output")

    recipe_parser = sub.add_parser("validate-recipe")
    recipe_parser.add_argument("--recipe", required=True)

    generate = sub.add_parser("generate", aliases=["bake"])
    generate.add_argument("--recipe", required=True)
    generate.add_argument("--seed", type=int)
    generate.add_argument("--output", required=True)
    generate.add_argument("--preview")
    generate.add_argument("--zone")

    validate_manifest = sub.add_parser("validate-manifest")
    validate_manifest.add_argument("--recipe", required=True)
    validate_manifest.add_argument("--manifest", required=True)

    compare = sub.add_parser("compare-seeds")
    compare.add_argument("--recipe", required=True)
    compare.add_argument("--seeds", nargs="+", type=int, required=True)
    compare.add_argument("--output", required=True)

    save = sub.add_parser("save-recipe")
    save.add_argument("--template", choices=("civic", "market"), required=True)
    save.add_argument("--output", required=True)

    args = parser.parse_args(argv)
    root = Path(args.project_root).resolve()
    try:
        library = load_library(root)
        if args.command == "list-modules":
            modules = []
            for module in sorted(library.modules.values(), key=lambda item: item.module_id):
                if args.category and module.category != args.category:
                    continue
                modules.append({"module_id": module.module_id, "category": module.category, "tags": module.tags, "layer": module.layer, "source_type": module.source_type, "source": module.source})
            _print({"style_profile": args.style_profile, "modules": modules})
            return 0
        if args.command == "inspect-module":
            module = library.module(args.module_id)
            _print({"module": module.__dict__ if hasattr(module, "__dict__") else {field: getattr(module, field) for field in module.__dataclass_fields__}, "validation": library.validate_module(module).as_dict()})
            return 0
        if args.command == "validate-library":
            report = library.validate_all(args.style_profile)
            _print(report.as_dict())
            return 0 if report.passed else 1
        if args.command == "analyze-assets":
            payload = library.analyze_assets(args.style_profile)
            if args.output:
                write_json(_path(args.output, root), payload)
            _print(payload)
            return 0 if not payload["missing_assets"] else 1
        if args.command == "validate-recipe":
            generator = _generator(args)
            report = generator.validate_recipe()
            _print(report.as_dict())
            return 0 if report.passed else 1
        if args.command in {"generate", "bake"}:
            generator = _generator(args)
            manifest = generator.generate(zone_id=args.zone)
            report = generator.validate_manifest(manifest)
            output = _path(args.output, root)
            write_json(output, manifest)
            write_json(output.with_name(output.stem + "_validation.json"), report.as_dict())
            if args.preview:
                _write_preview(root, manifest, _path(args.preview, root))
            _print({"manifest": str(output), "validation": report.as_dict(), "manifest_sha256": manifest["manifest_sha256"]})
            return 0 if report.passed else 1
        if args.command == "validate-manifest":
            generator = _generator(args)
            manifest = json.loads(_path(args.manifest, root).read_text(encoding="utf-8-sig"))
            report = generator.validate_manifest(manifest)
            _print(report.as_dict())
            return 0 if report.passed else 1
        if args.command == "compare-seeds":
            recipe = load_recipe(_path(args.recipe, root))
            records = []
            for seed in args.seeds:
                manifest = EnvironmentGenerator(library, recipe, seed=seed).generate()
                records.append({"seed": seed, "manifest_sha256": manifest["manifest_sha256"], "placement_signature": [[item["module_id"], item["x"], item["layer"]] for item in manifest["placements"]]})
            payload = {"scene_id": recipe.scene_id, "seeds": records, "all_unique": len({item["manifest_sha256"] for item in records}) == len(records)}
            write_json(_path(args.output, root), payload)
            _print(payload)
            return 0 if payload["all_unique"] else 1
        if args.command == "save-recipe":
            source = root / "data/content-generation/recipes" / ("civic_hall_dusk.json" if args.template == "civic" else "neighborhood_market_sunset.json")
            output = _path(args.output, root)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(source.read_bytes())
            print(str(output))
            return 0
    except (EnvironmentGenerationError, OSError, json.JSONDecodeError) as error:
        print(f"environment-authoring: {error}", file=sys.stderr)
        return 2
    parser.error("unhandled command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
