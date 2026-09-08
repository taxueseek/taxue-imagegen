# Changelog

All notable changes to taxue-imagegen are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.9.1] — 2026-09-08

### Fixed
- **CI red on every push since the initial release** — `bench_dewm.py`,
  `bench_dewm_align.py` and `probe_k_bias.py` hard-coded a machine-local
  `SCRIPTS = "/Users/<user>/.workbuddy/..."` path, so `import dewm` raised
  `ModuleNotFoundError` on the runner and the *Smoke import all scripts* step
  failed after two files. On the author's machine the same scripts silently
  imported the sibling modules from `~/.workbuddy/skills/`, which is why
  `run_tests.sh` passed locally while CI failed. All three now resolve their
  own directory via `os.path.dirname(os.path.abspath(__file__))`.
- **Machine-local paths removed from the public repo** — the three benchmark
  scripts no longer embed absolute sample-image paths; test images come from
  the `TAXUE_BENCH_IMGS` environment variable (`os.pathsep`-separated) and the
  scripts exit with a clear message when it is unset. `SKILL.md`,
  `references/size-and-params.md` and `scripts/measure.py` no longer leak a
  user-specific interpreter path — they use `PY=${PY:-python3}` / `pip install
  pillow` instead.

### Added
- `scripts/run_tests.sh` grows a sixth check that fails on any machine-local
  absolute path (`/Users/<name>/`, `/home/<name>/`) in tracked files, so this
  class of leak cannot come back unnoticed.

### Changed
- **CI now runs `bash scripts/run_tests.sh`** instead of duplicating the
  import / front-matter / preflight / critical-file checks inline. Local and CI
  share one source of truth, which is what allowed the two to drift.
- Workflow actions bumped to `actions/checkout@v5` and
  `actions/setup-python@v6` (both Node 24), clearing the Node 20 deprecation
  warning.

## [1.9.0] — 2026-09-08

### Added
- **WorkBuddy-exclusive positioning** — README.md / README.en.md now lead with
  a "WorkBuddy 专属 Skill" badge and callout, plus a new *Why WorkBuddy-
  exclusive* section (generation via WorkBuddy ImageGen, skill loading via
  `SKILL.md` + `/taxue-imagegen`, and the Agent loop chaining
  `fill_meta.py → generate → postcheck.py → dewm_v10.py`). README also spells
  out that the CLIs (`preflight` / `postcheck` / `dewm_v10` / `explore`) still
  run standalone anywhere.
- **Binding scope clarified** — only taxue-imagegen is WorkBuddy-exclusive.
  taxue-creative-style / taxue-halftone / taxue-solar-polaroid ship prompts
  with no platform, model, or Agent lock-in. The sibling-skills table now has
  a "Binding" column saying so.
- **Baseline model: hunyuan-image** — new section stating that every hard line
  (background hex, copy ratio, top padding, overlap area, countable
  constraints, `postcheck.py` thresholds) was measured on hunyuan-image; other
  models work in principle but require re-verifying thresholds after a switch.
- **Credit cost** — new section with a per-scenario estimate table (1 image
  5–10 credits; each refinement round is a fresh full-price render; 3 rounds
  × 2 images ≈ 30–60) and three saving rules (lock aspect ratio, preflight,
  batch edits). Badge + nav link + a note in "How to use".
- **SKILL.md** — §0 grows from two pre-flight items to three (add "preflight
  first", which is free) and states that refinement rounds bill again.
- **Track C · Photoreal Packaging Mockup** — studio-lit physical base +
  editorial monochrome ink layout + single-metaphor AM halftone graphic +
  giant stacked brand wordmark; Chinese meta-template with slots
  (`references/packaging-editorial.md`, three rounds, r3 4/4 text
  verbatim-correct).
- `references/packaging-editorial.md` §1 template, §2 slot table with four
  real packagings (coffee bag / serum bottle + box / beverage can / rigid
  box), §3 hard rules (eight verified rules), §4 padding/density hints.

### Notes
- Track C uses `1152x1536` (3:4) — width 1152 differs from Track A's default
  1024 (2:3). The width is intentional for a true 3:4 ratio.
- Gallery samples for Track C: four packagings (coffee pouch /
  serum bottle + box / beverage can / rigid box) from the v1.9 r3 round
  where 4/4 images passed the verbatim-text check.
- `SKILL.md` corrected from "two tracks" to "three tracks" in the front-matter
  description and the §0 header — Track C shipped in v1.9 but both lines were
  never updated.

## [1.8.0] — 2026-09-07

### Added
- `scripts/dewm_v10.py` — v9 + flat-area adaptive fusion. Fuses the
  reverse-alpha result with the inpainted background via an alpha ramp when
  the area just outside the watermark box is detected as flat
  (`std < 12`). Fixes "amp says CLEAN but the eye sees residue" — the
  shape mismatch was being treated as texture.
- `scripts/metric_flat.py` — flat-area residual RMS meter for the
  watermark box.

### Changed
- Default watermark removal switches from `dewm_v9.py` to `dewm_v10.py`.
  Behavior unchanged on textured images (byte-identical); flat-background
  images see RMS 5.98 → 1.43.
- `scripts/postcheck.py` `--dewm` now invokes `dewm_v10.py`. Output line
  gains `flat=Y/N(std=)` so flat-area fusion is visible at a glance.

## [1.7.0] — 2026-09-07

### Added
- **Exploration mode** — `scripts/explore.py` + CSV-driven prompt batch;
  `references/explore-mode.md` documents single-style 2–5 and multi-style
  5–9 quotas, batch ≤ 3 per round, `settle` rename to prevent same-second
  timestamp collisions (pitfall 17).
- `scripts/pick_wm.py` — four-way picker (v6 / v7 / v8 / v9) auto-selects
  the cleanest version; output goes to `_clean/`, never overwrites source.
- `scripts/audit_wm.py` — residual audit; works without source images,
  fits current image's actual opacity `k̂` + R² + amp, `|amp| ≥ 2.5`
  flags DIRTY.
- `scripts/dewm_io.py` — shared IO layer for the dewm scripts: overwrite
  guard (default writes to `_clean/`, `--inplace` required to overwrite
  source) + Unicode-safe Chinese path read/write.

### Changed
- Default watermark removal now goes through `pick_wm.py` for non-trivial
  inputs; v1.8+ this is `dewm_v10.py` instead.
- 18-image test: the previous default (`dewm_v6.py`) left noise or missed
  the watermark on 5 of 18 (28%). Picker eliminates most of these.

## [1.6.0] — 2026-09-07

### Added
- `scripts/postcheck.py` — single-call verification after generation:
  metrics (reuse `measure.py`) + bottom text-band 2× crop + dewm
  reverse-alpha watermark removal + append to `scripts/logs/runs.csv`.
  Total < 0.5 s. Establishes the data feedback loop for template tuning.
- Three-tier review card: **blocker** (yellowing R-B ≥ 3 / top_noise ≥ 6 /
  top invaded / missing or wrong text / duplicated headline) permits one
  targeted regeneration changing one thing only; **fixable** does not
  permit regen; **pass** = metrics in threshold + text verbatim correct.

### Changed
- Verification round-trips drop from 3–4 (measure / dewm / manual crop /
  manual log) to 1 (`postcheck.py`).

## [1.5.0] — 2026-09-07

### Added
- `scripts/fill_meta.py` — mechanical slot fill for Track A. Reads
  `references/poster-v5.md` §1 as single source of truth, performs
  verbatim replacement, derives `{N}` and the character list automatically,
  pre-validates punctuation, runs preflight before emitting. `--list`
  enumerates slots; `--manpu` switches to the full-bleed variant.
- Three-tier review card (see v1.6.0 entry).
- Production quota: 1 image by default.

### Notes
- Borrowed the pipeline pattern from `taxue-halftone` — the principle is
  the same: the template is verified asset, the LLM must not rewrite it.

## [1.4.0] — 2026-09-06

### Added
- `references/size-and-params.md` — ImageGen parameter table + size
  measurement. `size` accepts arbitrary pixel counts (not just the three
  schema examples); 1024 / 1152 / 1536 long-edge variants all output
  exactly.

## [1.0.0] — 2026-09-01

### Added
- Initial release. Two tracks (Track A vertical concept poster, Track B
  hand-drawn group illustration), five themes, mechanical slot fill,
  single-source templates, Explore mode in-script, watermark removal
  (rmwm + dewm v1).
- `references/pitfalls.md` — initial 12 verified pitfalls.
- `references/poster-v5.md` §1 — v5.0 baseline template.

[1.9.0]: https://github.com/taxueseek/taxue-imagegen/releases/tag/v1.9.0
[1.8.0]: https://github.com/taxueseek/taxue-imagegen/releases/tag/v1.8.0
[1.7.0]: https://github.com/taxueseek/taxue-imagegen/releases/tag/v1.7.0
[1.6.0]: https://github.com/taxueseek/taxue-imagegen/releases/tag/v1.6.0
[1.5.0]: https://github.com/taxueseek/taxue-imagegen/releases/tag/v1.5.0
[1.4.0]: https://github.com/taxueseek/taxue-imagegen/releases/tag/v1.4.0
[1.0.0]: https://github.com/taxueseek/taxue-imagegen/releases/tag/v1.0.0