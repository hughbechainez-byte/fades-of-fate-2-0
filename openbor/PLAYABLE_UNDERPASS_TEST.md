# Playable tech demo — I-8 Sunset Underpass

OpenBOR 4.0 Build 7949 loads four unique indexed 640×360 panels with sunset parallax, drifting haze, and three-pose rooted curb foliage behind Dave. Pixel posters, glyphs, cracks, aggregate, wrappers, and crushed cans are baked into the world plane and walkable asphalt. The free-walk floor spans X `0–2559` and Z `252–326`; no enemies, holes, platforms, or physical props are active.

## Build and install

```powershell
powershell -ExecutionPolicy Bypass -File tools\Build-Underpass-FreeWalk.ps1
```

The installed demo is written to `C:\Users\blowb\Desktop\Fades of Fate 2.0 - Sunset Underpass Tech Demo`. Launch it with `Launch_Black_Dave_Underpass_Demo.cmd`.

Controls: arrows move, Ctrl attacks, Alt jumps, Enter starts. Press F12 for an OpenBOR screenshot.

The runtime acceptance gate is the packaged Build 7949 traversal evidence recorded in `data/levels/i8_underpass/underpass_manifest.json`; lookdev stills and layer previews do not replace gameplay.
