# Asset coverage and variation report

Generated from `data/content-generation/style_profiles.json` with:

```powershell
python tools/environment_authoring.py analyze-assets --style-profile fades_environment_v1 --output data/content-generation/generated/approved_asset_analysis.json
```

Current result: 21 approved PNG files analyzed, 0 missing. The existing chunk library contains 824px/848px by 360px RGBA scenery layers, 800px by 360px haze tiles, and the three approved route-art reference plates are 1672px by 941px. The report records SHA-256, native dimensions, PNG color type/alpha, and pixel filtering contract. It flags the mixed source-size inventory as a likely scale inconsistency for human review; no rescaling is performed by the generator.

Covered module families:

- far skyline, secondary architecture, ground/curb, and foreground framing from the location-locked Chapter 1 chunks;
- civic/plaza and neighborhood-market/sunset tags;
- foliage/planter, breakable cart, and breakable bollard through the existing authored `draw_stage_prop` path;
- three-band animated ambience through `AtmosphereSnapshot`.

Missing coverage is intentional and fail-closed: standalone trees, bushes, vehicles, signs, and light fixtures. The generated proof manifests list these under `coverage.missing_module_families` rather than fabricating replacement art.

Seed proof results:

- `civic_hall_dusk`: seeds 1729, 1730, and 1731 each produced a distinct manifest and passed validation.
- `neighborhood_market_sunset`: seeds 2718, 2719, and 2720 each produced a distinct manifest and passed validation.
- Repeating a seed produces byte-identical JSON and the same `manifest_sha256`.

The proof scenes use only approved current assets and existing native prop/atmosphere systems. They are composition manifests, not replacements for the four hand-authored playable Chapter 1 routes.
