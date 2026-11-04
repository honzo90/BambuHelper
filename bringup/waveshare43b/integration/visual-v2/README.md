# Native Wydruk assets

The assets in this directory are compiled into the Waveshare 4.3B firmware.
`assets.json` declares each source viewport and its fixed destination canvas.
`manifest.json` records source, raster, pipeline and generated-header hashes.
The host previews are design checks, not physical LCD scanout evidence.

## Dashboard icon revision — 2026-10-25

Nozzle, Bed and Chamber now use simpler SVG silhouettes with consistent edge
weights and cool neutral surfaces. The spool is an editable SVG with a clear
filament band and neutral flanges, replacing the small photographic atlas crop.
The other 17 assets and their rasters are unchanged, including the hero scene.
The original artwork is traceable to `source_reference` in the manifest.

The thermal canvases remain 42×46, with a centred 48-unit SVG viewBox. Spool
remains 64×69. Asset enum order, layout coordinates, alpha composition and the
native decoder are unchanged. The revisions therefore reach all existing uses
of these four assets, including dashboard cards, detail views and animations.

The material mask selects green source pixels only in assets that opt into
`green_material`. Spool flanges are neutral and stay visible for black or white
filament; the band and inner sectors use the actual requested filament colour.
Unknown and empty telemetry continue to use the existing state-specific icons.

## Rebuild the four dashboard icons

With locally installed `sharp` (no network or browser required), from the repo:

```sh
NODE_PATH=/path/to/node_modules node bringup/waveshare43b/integration/visual-v2/rasterize_icons.cjs
python3 -B bringup/waveshare43b/integration/visual-v2/generate.py
python3 -B -m unittest discover -s bringup/waveshare43b/integration/tests -p 'test_visual_assets.py' -v
```

The selective rasterizer updates only Nozzle, Bed, Chamber and Spool. It records
sharp/librsvg versions per asset in `rasterizer.json`; unchanged records retain
their original Chromium provenance. SVG `xMidYMid meet` renders directly into
the declared canvas. No asset is rescaled or recoloured by the RGB565 encoder.

`rasterize.cjs` remains the original full-atlas Chromium rasterizer. It can
rebuild every source via local Chromium/Playwright when a full raster refresh
is intended; rerun `generate.py` afterwards to regenerate provenance.
The Model, Plate and Head atlas remains 1448×1086 with its declared viewports.

## Embedded format and budgets

Rows contain little-endian 16-bit skip, 15-bit count plus material bit, then
RGB565+alpha8 pixels. Transparent pixels are omitted. Row offsets delimit each
row. The portable decoder validates bounds, preserves straight alpha and uses
a 64-pixel/128-byte stack buffer without heap allocation. It supports images
up to 256×1024 and emits native RGB565 values for LovyanGFX.

The first eight sprites retain a 65 KiB allowance, scene components 100 KiB,
and additional controls 32 KiB; the combined ceiling remains 165 KiB. Current
encoded sizes are recorded in `manifest.json`. Tests cover provenance, row
coding, mask separation, alpha, clipping, tint colours and malformed input.
