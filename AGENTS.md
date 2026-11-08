# AGENTS.md — working guide for coding agents

This fork (Waveshare ESP32-S3-Touch-LCD-4.3B port of Keralots/BambuHelper) is
maintained by coding agents. Optimise code, docs and tooling for agents:
explicit, greppable, one fact in one place, every claim checkable by a command.
The owner tests on hardware and decides releases; agents do the rest.

## Repository map

| Path | What it is | Owner |
|---|---|---|
| `src/`, `include/` | Firmware (C++, Arduino). Shared with upstream. | upstream + fork |
| `src/*ws43b*`, `include/ws43b_*` | 4.3B-only code (display, touch, memory, OTA, weather, TLS). | fork |
| `boards/ws_lcd_43b.ini` | 4.3B board profile; **`FW_VERSION` lives here**. | fork |
| `bringup/waveshare43b/integration/` | 4.3B build system, SDK builder, patches, locale, host tests. | fork |
| `bringup/waveshare43b/integration/build.py` | The only supported 4.3B build (Arduino CLI, not PlatformIO). | fork |
| `bringup/waveshare43b/integration/localize_web.py` | Build-time WebUI patches + PL/DE translation. | fork |
| `bringup/waveshare43b/integration/locale/{pl,de}.json` | WebUI translations (source strings are English). | fork |
| `bringup/waveshare43b/integration/tests/` | Host regression tests (`test_*.py`). | fork |
| `bringup/waveshare43b/*.md`, `bringup/waveshare43b/*.json` | Hardware journal — **git-ignored on purpose** (private data). Never commit. | local |
| `docs/` | GitHub Pages: web installer, OTA channel (`docs/WS43B_OTA_CHANNEL.md`), upstream sync log (`docs/UPSTREAM.md`). | fork |
| `tools/companion/` | Upstream desktop companion tool. Do not reformat. | upstream |
| `WAVESHARE.md` | Human-facing build instructions and hardware status. | fork |

## Commands (run from repo root)

```sh
python3 -B scripts/agent_check.py            # all host tests (~2 min); must pass before any commit
python3 -B scripts/agent_check.py -k fixture # only test modules whose name contains "fixture"
python3 -B bringup/waveshare43b/integration/build.py   # firmware build, see WAVESHARE.md for setup
```

Release-profile build environment:
`WS43B_ARDUINO_DATA=<dir with core 3.3.11> WS43B_SDK_PROFILE=cache64_xip WS43B_RGB_PCLK_HZ=12000000`.
Arduino ESP32 core must be exactly **3.3.11**. `build.py` fails if local paths leak
into the binary (`-ffile-prefix-map`); keep it that way.

## Hard constraints

- **Flash is ~97 % full.** No new libraries, no large tables/fonts/images. Prefer
  smaller code; report the app size change of every firmware change.
- **Internal RAM is tight** (min free internal heap ~57 KB under WebUI load).
  Large buffers go to PSRAM; TLS during MQTT connect already uses PSRAM.
- **Display uses an RGB bounce buffer.** No long work in ISRs; avoid long
  PSRAM-heavy bursts while frames are output (causes scanout artifacts).
- **Never** put IPs, MACs, serials, access codes, Wi-Fi data, usernames or home
  paths into code, commits, docs or release notes. In examples and tests use
  generic `10.0.0.x` addresses (the fixture/capture validators accept private LAN
  addresses only; 192.0.2.x is rejected) and `SYNTHETIC…` placeholders.
- Hardware behaviour you cannot verify on the host: say so and propose a
  measurement (`/monitor/status`, `/diagnostics/*` endpoints) instead of guessing.

## Code conventions

- 4.3B changes go into `ws43b_*` files, behind `BOARD_IS_WS43B`, or into
  build-time patches — keep shared upstream files close to upstream so
  `docs/UPSTREAM.md` syncs stay cheap. Do not reformat upstream C++.
- Fork Python: `ruff format bringup/waveshare43b` (config in `bringup/waveshare43b/ruff.toml`,
  `pip install ruff` into `.venv`). Files excluded there are SHA256-pinned by asset
  provenance or patched as text by other tests — editing them means regenerating the
  assets / updating the markers in the same change. Tests use stdlib `unittest` only.
- WebUI text: English in source, add PL and DE to `locale/{pl,de}.json` in the same
  change. German uses informal "du". Exceptions: the monitor page has Polish source
  text (`locale/monitor_{en,de}.json`); inline triples `W(pl,en,de)` in `web/app.js`
  and `ws43bText(pl,en,de)` (`src/ws43b_language.h`) in C++.
- Memory: big buffers via `heap_caps_malloc(..., MALLOC_CAP_SPIRAM)`; no large stack
  arrays; avoid `String` churn in hot paths.
- Every logic change gets a host test in `tests/` (name `test_<area>.py`).
- Comments explain *why* (hardware quirk, memory budget, upstream reason), not what.

## Branches and releases

- `waveshare-43b` (default) = latest **stable** only; changes only via one PR per stable release.
- `ws43b/layout-settings` = work branch; all commits and betas go here.
- Version scheme: stable `vX.Y.Z`; betas `vX.Y.Z-beta.N` (published as GitHub prerelease, online OTA);
  alphas `vX.Y.Z-alpha.N` (manual OTA file only, never published).
- Bump `FW_VERSION` in `boards/ws_lcd_43b.ini` for every built image.
- Upstream sync procedure and log: `docs/UPSTREAM.md` (update "Last reviewed" each time).
- Local-only branches whose names start with `feature/` or `backup/` contain private
  data in history — never push them.

## Keeping this guide working

`tests/test_agent_guide.py` enforces the first three points.

- `CLAUDE.md` stays a one-line `@AGENTS.md` import and must not be git-ignored
  (upstream ignores `CLAUDE.md`; re-check `.gitignore` after every upstream sync).
- Every repo path and command named in this file must exist. When you move or rename
  one, update this file in the same commit.
- Rules live here only — not in editor configs or private notes. Continue (VS Code)
  and Claude Code load this file automatically from the repo root, so the editor
  must open the repository folder itself, not its parent.
- When a fact here changes (flash/RAM budget, versions, branch or release policy,
  new hardware constraint), update this file in the same change. A stale rule is
  worse than none.
- After a big edit here or a model change in the editor, the owner re-runs the local
  model check (questions answered with and without this file; expected 5/5 with it).

## Before committing

1. `python3 -B scripts/agent_check.py` passes.
2. `git diff --cached` contains no private data (see Hard constraints).
3. Commit message: imperative subject, body says what was verified (tests / build / hardware).
