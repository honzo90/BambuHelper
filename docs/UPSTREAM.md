# Upstream sync – Keralots/BambuHelper

This fork follows [Keralots/BambuHelper](https://github.com/Keralots/BambuHelper) (`main`).
The 4.3B port started from upstream **v3.9.0** (`23347fb`). This file records which
upstream commits were taken into the fork and which were skipped, so a review only
has to look at commits newer than the last entry.

## How to sync

1. Fetch upstream and list what the fork does not have:
   ```sh
   git fetch origin main
   git log --no-merges --format='%h %cs %s' $(git merge-base origin/main honzo90/waveshare-43b)..origin/main
   ```
   Skip commits already listed below.
2. For each relevant commit: `git cherry-pick -x <sha>` on the beta branch (`-x` keeps
   a reference to the upstream commit), then adapt it to the native 4.3B UI and the
   PL/EN/DE catalogs if needed.
3. Run the host tests and the release-profile build (see `WAVESHARE.md`), ship it as a
   beta, and add the commits to the table below.

Rules of thumb:
- Keep 4.3B-specific code in `ws43b_*` files, behind `BOARD_IS_WS43B`, or in build-time
  patches (`localize_web.py`) rather than editing shared files.
- Fixes that help every board (e.g. shared Wi-Fi, MQTT, settings code) are candidates
  for a pull request upstream, which keeps the fork from drifting.

## Branch policy

- **`waveshare-43b` (default branch) always matches the latest stable release.** It
  only receives changes through one pull request per Stable release (v4.1.0, v4.2.0, …).
- **Betas are built only from `ws43b/layout-settings`.** Day-to-day work and upstream
  ports land there first.
- **Urgent fixes:** a serious bug in a stable release (e.g. restarts, failing updates)
  gets a stable patch release (v4.1.1, …) built from the work branch and merged to the
  default branch right away, without waiting for the next feature release.
- The README on the default branch describes the stable release and points to the
  Beta channel / work branch for test builds.
- Exception in effect until v4.1.0: the default branch already carries beta.18 code
  (merged before this policy); it is aligned again by the v4.1.0 pull request.

## Last reviewed

- **2026-11-05**, upstream `main` at `35ea068` (2026-11-01).

## Taken

| Upstream | Date | Subject | Fork | Notes |
|---|---|---|---|---|
| `d610cb4` | 2026-10 | feat(wifi): send the configured hostname over DHCP (#192) | already in the 4.3B baseline | – |
| `20cefc9` | 2026-10-17 | feat(wifi): explain why the stored network failed in AP mode | `496cfab` (v4.1.0-beta.19) | 4.3B setup screen shows the reason; portal texts rewritten as whole sentences with placeholders for PL/DE |
| `636f10d` | 2026-11-01 | fix(wifi): give the AP-fallback scan time to finish | `ed35874` (v4.1.0-beta.19) | – |

## Skipped

| Upstream | Date | Subject | Why |
|---|---|---|---|
| `cba4725` | 2026-10-17 | feat(cards): temperature grid with bigger values on 320x240 landscape | Cards style is not used by the native 4.3B UI |
| `661d69f` | 2026-10-27 | Cards idle: keep the headline and job name clear of the big clock | Cards style |
| `5e26772` | 2026-10-27 | Cards print screen: drop the beta label | Cards style |
| `2068815` | 2026-11-01 | build: pin library versions exactly | PlatformIO only; 4.3B builds with pinned sources via `build.py` |
| `5bbf2e4` | 2026-11-01 | ci: build every env on push and pull requests | upstream CI for PlatformIO envs |
| `7fdd46f` | 2026-11-01 | release: v3.9.1 | version bump and binaries of other boards |
| `5adc0ad`, `99abc5b`, `8aa1a27`, `c2ad808`, `a2a64ec` | 2026-10-20/21 | docs(readme): community forks table | upstream README only |

## Possible upstream contributions

Fork changes to shared code that could help every board:
- night window with minutes (`dpSettings.nightStartMinute/EndMinute`, `isNightHour`);
- `getLocalTime(&t, 0)` can fail spuriously on a synced clock (use a few ms);
- AP-diagnosis texts as whole sentences with placeholders (translatable);
- the upstream README lists this fork as "experimental, Polish or English UI" (now stable v4.0.0, PL/EN/DE).
