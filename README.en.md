<p align="center">

![taxue-imagegen: three tracks, four workflows — turn a sentence, a theme, or a photo into a stable cover, group illustration, or photoreal packaging mockup](./assets/readme/hero.png)

</p>

<div align="center">

[中文](./README.md) · **English**

# taxue-imagegen · Meta-Prompt Library

**Three tracks, four workflows — turn a sentence, a theme, or a photo into a stable cover, group illustration, or photoreal packaging mockup.**

[![Version](https://img.shields.io/badge/VERSION-1.9.0-2ea44f?style=flat-square&labelColor=333)](./CHANGELOG.md)
[![Skills](https://img.shields.io/badge/SKILLS-1-2ea44f?style=flat-square&labelColor=333)](./SKILL.md)
[![Tracks](https://img.shields.io/badge/TRACKS-A·B·C-214f9b?style=flat-square&labelColor=333)](./SKILL.md)
[![Stars](https://img.shields.io/github/stars/taxueseek/taxue-imagegen?style=flat-square&label=STARS&color=e37f2c&labelColor=333)](https://github.com/taxueseek/taxue-imagegen/stargazers)
[![Validate](https://github.com/taxueseek/taxue-imagegen/actions/workflows/validate.yml/badge.svg)](https://github.com/taxueseek/taxue-imagegen/actions/workflows/validate.yml)
[![SKILL.md](https://img.shields.io/badge/Agent-SKILL.md-214f9b?style=flat-square&labelColor=333)](./SKILL.md)

</div>

<p align="center">
  <a href="#examples">Examples</a> ·
  <a href="#three-tracks">Three tracks</a> ·
  <a href="#four-workflows">Workflows</a> ·
  <a href="#how-to-use">How to use</a> ·
  <a href="#what-its-for">What it's for</a> ·
  <a href="#rules">Rules</a> ·
  <a href="#engineering-checks">Engineering</a> ·
  <a href="#changelog">Changelog</a>
</p>

## What this is

taxue-imagegen is not a style library and not a prompt collection — it is a **meta-prompt library + image-generation workflow** designed for the WorkBuddy / Agent loop. The hard problem is not "writing one pretty sentence" — it is "making the model reliably produce the expected image every time, and fixing it fast when it doesn't."

It does that with three things:

- **Three tracks** — vertical concept poster (A), hand-drawn group illustration (B), photoreal packaging mockup (C), each managing a different figure-text relationship;
- **Mechanical slot filling** — a single source-of-truth prompt template (e.g. `references/poster-v5.md` §1), the LLM never rewrites it, slots are declared verbatim, word counts auto-derived, punctuation pre-validated;
- **One-shot verification** — `scripts/postcheck.py` measures metrics + crops the text band for visual inspection + strips watermarks + appends to `runs.csv`. Verifying one image drops from 3–4 round-trips to 1.

Since v1.6 there's a **data feedback loop for template tuning**: every output is logged to `scripts/logs/runs.csv` (top padding, yellowing R-B, text-band verdict, …). When the next blocker appears, read the table first, then patch the template — never stack a second ad-hoc prohibition.

## Examples

> Images in `examples/` are real outputs from this skill (AI compliance watermark stripped, see [ASSET-LICENSE.md](./ASSET-LICENSE.md)). Track A: three covers, three different styles. Track B: two density tiers. Track C: four packagings matching the four rows of `references/packaging-editorial.md` §2 (coffee pouch / serum bottle + box / beverage can / rigid box), text verbatim-correct (v1.9 r3 4/4 verified).

| Ink Crane (Track A · ink) | SHEER (Track A · intercut) | Char-Matrix (Track A · experimental) |
|:---:|:---:|:---:|
| <img src="./examples/example-A-crane-ink.png" alt="Track A ink crane poster WORKBUDDY" width="280"> | <img src="./examples/example-A-sheer-silk.png" alt="Track A intercut SHEER poster" width="280"> | <img src="./examples/example-A-char-matrix.png" alt="Track A char-matrix art poster" width="280"> |

| Dog Lineup (Track B · dense) | Travelers (Track B · dense + mixed forms) |
|:---:|:---:|
| <img src="./examples/example-B-dog-lineup.png" alt="Track B fourteen-breed canine lineup" width="280"> | <img src="./examples/example-B-travelers.png" alt="Track B travelers, robot, and monster mixed group" width="280"> |

| SLOW/ROAST (Track C · coffee pouch) | PURE/ACTIVE (Track C · serum bottle + box) |
|:---:|:---:|
| <img src="./examples/example-C-01-coffee-pouch.png" alt="Track C deep-roast brown SLOW/ROAST coffee pouch" width="280"> | <img src="./examples/example-C-02-glass-serum.png" alt="Track C deep-indigo PURE/ACTIVE frosted serum bottle + bone-white paper box" width="280"> |

| BITTER/CITRUS (Track C · beverage can) | SILENT/HOURS (Track C · rigid box) |
|:---:|:---:|
| <img src="./examples/example-C-03-beverage-can.png" alt="Track C ink-black + lemon-yellow BITTER/CITRUS beverage can" width="280"> | <img src="./examples/example-C-04-lidded-box.png" alt="Track C charcoal-linen debossed SILENT/HOURS rigid box" width="280"> |

> All nine samples are free of the "AI 生成 / WORKBUDDY" platform watermark — original outputs were pixel-repaired by `scripts/dewm_v10.py` or `scripts/rmwm.py`. For sharing/redistribution please respect [ASSET-LICENSE.md](./ASSET-LICENSE.md).

## Three tracks

| Track | Use it for | Template source-of-truth | Entry point |
|---|---|---|---|
| **A · Vertical concept poster** | Concept poster / exhibition KV / album cover / book cover / film mood poster / magazine feature | [`references/poster-v5.md` §1](./references/poster-v5.md) | `scripts/fill_meta.py A` |
| **B · Hand-drawn group illustration** | Multi-character illustration / animal bestiary / character lineup / travel group / journal group | [`references/crowd-illustration.md`](./references/crowd-illustration.md) + [`crowd-themes.md`](./references/crowd-themes.md) | `scripts/fill_meta.py B --theme <theme>` |
| **C · Photoreal packaging mockup** | Studio-lit product mockup (coffee bag / serum bottle / beverage can / rigid box) | [`references/packaging-editorial.md`](./references/packaging-editorial.md) | Template directly (see [SKILL.md Track C](./SKILL.md)) |

**Not sure which?** Is the subject **one** thing or **many** things? One → A, many → B. Want a product mockup → C.

A and C use the size table in `references/size-and-params.md` (default `1024x1536` / 3:4 uses `1152x1536`); B's sizing is in `references/crowd-illustration.md`.

## Four workflows

| Workflow | When | Discipline |
|---|---|---|
| **Production** (default) | Track + template mature, target is a final | Fill → preflight → **generate 1 image only** → three-tier review → done or one targeted fix |
| **Exploration** | New theme / new style / template iteration | `scripts/explore.py` batched prompts + `settle` rename + verify + write back conclusions; single-style 2–5, multi-style 5–9; see [`references/explore-mode.md`](./references/explore-mode.md) |
| **Watermark removal** | Output has bottom-right "AI 生成 / WORKBUDDY" | Default [`scripts/dewm_v10.py`](./scripts/dewm_v10.py) (v9 + flat-area adaptive fusion, 31 ms); tricky images use [`scripts/pick_wm.py`](./scripts/pick_wm.py) four-way picker; all outputs go to `_clean/`, **never overwrite source** |
| **Verification** | Close the loop after generation | [`scripts/postcheck.py`](./scripts/postcheck.py) metrics + 2× text-band crop + dewm + runs.csv logging, <0.5 s |

**Production quota: 1 image by default.** No draft-then-final. No "compare" second image. Only blockers permit one targeted regeneration, changing exactly one thing. **Exploration quota**: single-style 2–5, multi-style 5–9; batches ≤ 3 per round, immediately `ls` and `explore.py settle` to rename-lock (prevents same-second timestamp collisions).

## How to use

Install:

```bash
npx skills add taxueseek/taxue-imagegen
```

Then just say, e.g.:

- "Track A, a 2:3 concept poster — ukiyo-e style, theme: impermanence, English headline WAITING"
- "Track B, full-bleed dog lineup, 14 dogs, modify with `fill_meta.py B --theme bird`"
- "Track C, a matte serum bottle in a paper box, deep indigo ink, metaphor is a single falling water drop"
- "Run explore_sample.csv in exploration mode, pick one as the main line"

Or trigger with `/taxue-imagegen`. Production mode defaults to 1 image per request — if you want batch exploration, say "exploration mode, N images" explicitly.

## What it's for

- **Posters**: events, exhibitions, city walks, concept posters, KVs, album covers
- **Platform covers**: Xiaohongshu, WeChat OA, podcast, Bilibili, avatars, ultra-wide headers
- **Brand material**: postcards, invitations, tickets, menus, packaging stickers (Track C for the actual mockup)
- **Books**: covers, frontispiece, chapter pages, zine inner pages
- **Group illustrations & bestiaries**: character bestiary, animal bestiary, travel group portraits, journal multi-character spreads
- **Text**: literary excerpts, poetry, personal manifestos (Track A's three-tier copy hierarchy)

## Rules

1. **Paper / background rejects hue words** — `warm / aged / faded / unbleached / vintage` are strong hue commands that turn output yellow. For texture use `fibre grain / laid lines / halftone / tooth / deckle`.
2. **Numerics only on crash-prevention items** — background color, three-tier copy ratio, overlap area, accent-color ratio, top padding: lockable. Subject size, scale contrast, position/density: must stay vague.
3. **Area / density percentages are mostly noise to the model** — replace "1/3 padding", "low density" with countable constraints (subject count lower bound, max subject ≤ 1/4 frame, small subject ≥ 1/12) + positive descriptions.
4. **Resolve paths with `find` first** — the archiver normalizes consecutive underscores into one.
5. **Separate meta info from content physically** — weight hints (`= 100`), ratio explanations next to copy are roughly 50% likely to be painted as text.

Full rules plus 22 verified pitfall fixes across tracks: [`references/pitfalls.md`](./references/pitfalls.md).

## Randomness & creativity

The magic of image generation is the artistic side — randomness and creativity are baked in. This is an **engineering-first skill**: every prohibition, hard line, and template is there to make output stable — but it deliberately avoids rigid constraints and doesn't aim to reproduce a fixed look. The same prompt handed to GPT Image 2, Grok Imagine 2, Nano Banana 2, Seedream 5.0 Pro can produce noticeably different results. That creative headroom is intentional — run the same line a few times, pick the one that fits.

Model suggestions (personal):

- **Primary**: GPT Image 2, Grok Imagine 2
- **Backup**: Nano Banana 2, Seedream 5.0 Pro

## Engineering checks

The spec doesn't just live in docs: `SKILL.md` slots, templates, hard lines, and verification thresholds all have machine-readable checks. Patch any of them, run the check, see what broke — GitHub Actions runs the same on push and PR.

```bash
bash scripts/run_tests.sh                       # run all checks
python3 scripts/preflight.py "your prompt"     # preflight a single prompt (A/B/C)
python3 scripts/postcheck.py a.png --track A   # verify a single output
```

CI: [`.github/workflows/validate.yml`](./.github/workflows/validate.yml).

## Sibling skills

Same family of WorkBuddy image-generation skills — pick the right one for the job:

| Skill | One-liner | Repo |
|---|---|---|
| **taxue-creative-style** (image-style engine) | 14 families, 77 variants: by-style generation, prompt rewriting, from-scratch, remember preferences | [taxue-creative-style](https://github.com/taxueseek/taxue-creative-style) |
| **taxue-imagegen** (meta-prompt library + workflow) | 3 tracks + 4 workflows + mechanical slot fill + one-shot verify | **You are here** · [taxue-imagegen](https://github.com/taxueseek/taxue-imagegen) |
| **taxue-halftone** (print-feel engine) | 11 styles + 1 variant: turn a sentence, theme, or photo into a print-feel cover | [taxue-halftone](https://github.com/taxueseek/taxue-halftone) |
| **taxue-solar-polaroid** (solar-term engine) | Solar terms, festivals, phenology short lines → memorable posters, paper archives and polaroids | [taxue-solar-polaroid](https://github.com/taxueseek/taxue-solar-polaroid) |

## Changelog

- **v1.9.0** (2026-09-08): Add Track C "Photoreal Packaging Mockup" — studio-lit physical base + editorial monochrome ink layout + single-metaphor AM halftone graphic + giant stacked brand wordmark, Chinese meta-template with slots (`references/packaging-editorial.md`, three rounds, r3 4/4 text verbatim-correct).
- **v1.8.0** (2026-09-07): Add `dewm_v10` — v9 + flat-area adaptive fusion, fixes "visually visible watermark ghosts on flat backgrounds" (amp says CLEAN but the eye sees residue); flat-background RMS 5.98 → 1.43, textured images byte-identical (zero regression); default watermark removal switches to `dewm_v10.py`.
- **v1.7.0** (2026-09-07): Exploration mode (`explore.py` + CSV-driven); default watermark removal switches to `pick_wm` (v6/v7/v8 each have a specialty; 18-sample test showed v6 missed/left noise on 5 of 18, 28%); add `audit_wm` residual audit (works without source images to flag DIRTY).
- **v1.6.0** (2026-09-07): Single-call `postcheck.py` after generation — metrics + text-band visual crop + dewm reverse-alpha + runs.csv logging; verification round-trips drop from 3–4 to 1; data feedback loop for template tuning.
- **v1.5.0** (2026-09-07): Borrowed `taxue-halftone` pipeline — `fill_meta.py` mechanical slot fill (LLM never rewrites the template, word counts auto-derived); tiered prompt library loading; three-tier review card + 1-image production quota.
- **v1.4.0** (2026-09-06): Size test — `size` accepts arbitrary pixel counts (not just the three schema examples); 1024/1152/1536 long-edge variants all output exactly.
- **v1.0.0** (2026-09-01): Initial release. Two tracks, five themes, mechanical slot fill, single-source templates. See [CHANGELOG.md](./CHANGELOG.md).

## License

Code, SKILL instructions, scripts, references — [MIT License](./LICENSE).
Images in `examples/` and the header `assets/readme/hero.png` — [ASSET-LICENSE.md](./ASSET-LICENSE.md), not distributed under MIT.