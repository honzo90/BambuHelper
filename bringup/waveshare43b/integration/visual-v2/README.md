# Native Wydruk assets

The original seven SVGs in `raw/icons/` and `raw/scene-atlas.png` are byte-for-byte copies from the approved
`design-previews/2026-10-14-wydruk-native-v2/assets/` reference. `scene-components.png`
is the separate generated model/plate/head atlas supplied for this implementation
(original image filename `exec-126e2f2d-f514-4b72-b86f-74d138ff6acf.png`). The component
generation prompt is maintained alongside this pipeline by the integration owner.

`assets.json` describes each source viewport and target size. Chromium renders
SVG `xMidYMid meet` directly into the exact destination canvas. Thermal icons use
42×46 canvases, containing a centred 42×42 SVG image; navigation icons use 33×33.
The spool uses the approved SVG viewport `(735,60,460,540)` in a 64×69 canvas.
Its original PNG is 1254×1254, but the reference HTML explicitly presents that
image as 1280×1280. This scaling is retained. The new component atlas is 1448×1086.

The shared controls added on 2026-10-16 (`Clock`, `Weather`, `Network`, `Check`,
`Pause`, `Alert`, `EmptySlot`, `UnknownData`, `Printer`, `Fan`) extend the same SVG
system with cool metallic gradients, a small extruded edge and transparent
backgrounds. Each uses a 48×48 drawing viewport rasterized directly to 33×33.
They do not replace or modify the original icons or scene components.

No raw art is recoloured or altered by the pipeline. The encoded material mask
selects green source pixels in Print, Spool, Model, Check, Pause and Alert only. The native decoder
optionally multiplies the requested tint by source brightness for those pixels;
all other pixels, including gray/metal flanges, retain their original RGB565.
Disabling tint reproduces the approved source colours without hue conversion.

From the BambuHelper root, with an installed local Chromium/Playwright:

```sh
NODE_PATH=/path/to/node_modules node bringup/waveshare43b/integration/visual-v2/rasterize.cjs --browser=/path/to/chromium
python3 -B bringup/waveshare43b/integration/visual-v2/generate.py
python3 -B -m unittest discover -s bringup/waveshare43b/integration/tests -p 'test_visual_assets.py' -v
```

The rasterizer blocks HTTP(S) requests and uses only supplied local bytes. The
generator requires only Python's standard library. It emits
`include/ws43b_visual_assets_data.h` and `manifest.json` with source, raster,
pipeline and output hashes. Record the complete directory as build provenance;
the firmware only compiles the two generated/public include headers.

The row format is little-endian 16-bit skip, 15-bit count plus material bit,
followed by count RGB565+alpha8 pixels. Transparent pixels are omitted. Offsets
delimit each row. The portable decoder validates all bounds before emitting any
pixels, preserves straight alpha and uses a 64-pixel/128-byte stack buffer.
It supports images up to 256×1024 and never allocates. The sink receives native,
unswapped RGB565 values, suitable for LovyanGFX's typed `rgb565_t` image overload.

The eight reference assets occupy 28,225 encoded bytes including row offsets;
the three scene components occupy 92,629. These measurements exclude small
descriptors and compiled decoder code. Host tests cover encoding fidelity,
provenance, malformed rows, alpha, all primary/neutral tint colours and chunk
limits under ASan/UBSan. They do not certify physical LCD scanout.
The original eight-asset allowance remains 65 KiB; scene components retain
100 KiB, additional shared controls have 32 KiB, and the combined encoded budget
remains 165 KiB. Actual sizes and source/raster hashes are in `manifest.json`.
