<p align="center">

![taxue-imagegen: four types, four workflows — turn a sentence into a stable cover, group illustration, packaging mockup, or storyboard](./assets/readme/hero.png)

</p>

<p align="center">
  <a href="./README.md">中文</a> ·
  <a href="#specimens">Specimens</a> ·
  <a href="#four-types">Types</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#how-to-use">Get started</a>
</p>

# Taxue Imagegen

Four types, four workflows — turn a sentence into a stable cover, group illustration, packaging mockup, or storyboard.

[![Version](https://img.shields.io/badge/VERSION-1.19.0-2ea44f?style=flat-square&labelColor=333)](./CHANGELOG.md)

Runs only inside [WorkBuddy](https://www.workbuddy.cn/docs/workbuddy/Overview). Generation goes through its ImageGen; slot fill and verification are scripts. The other three skills in the family ship prompts you can copy anywhere; this one ships a pipeline that lives in WorkBuddy.

Hard lines and thresholds were measured on hunyuan-image. One image is about 5–10 credits; a revision is another full render.

## Image-generation family

Same family — pick the right skill:

| Skill | One-liner | Repo |
|---|---|---|
| **taxue-creative-style** (image-style engine) | 14 families, 77 variants: by-style generation, prompt rewriting, from-scratch, remember preferences | [taxue-creative-style](https://github.com/taxueseek/taxue-creative-style) |
| **taxue-halftone** (print-feel engine) | 12 styles + 2 variants: a phrase, a theme, or a photo into a print-feel cover | [taxue-halftone](https://github.com/taxueseek/taxue-halftone) |
| **taxue-solar-polaroid** (solar-term engine) | Solar terms, festivals, phenology lines → posters, paper archives, polaroids | [taxue-solar-polaroid](https://github.com/taxueseek/taxue-solar-polaroid) |
| **taxue-imagegen** (meta-prompt library) | Four types + four workflows + mechanical slot fill + one-shot verify | **You are here** · WorkBuddy-exclusive · [taxue-imagegen](https://github.com/taxueseek/taxue-imagegen) |

## Specimens

Three Type A posters, two Type B groups, four Type C mockups — all real outputs. Click a title for the original.

![Nine specimens: ink poster, intercut poster, char-matrix, dog lineup, travelers, coffee pouch, serum bottle, beverage can, rigid box](./assets/readme/types-grid.jpg)

<p align="center">
<a href="./examples/example-A-crane-ink.png">Ink crane</a> ·
<a href="./examples/example-A-sheer-silk.png">SHEER</a> ·
<a href="./examples/example-A-char-matrix.png">Char-matrix</a> ·
<a href="./examples/example-B-dog-lineup.png">Dog lineup</a> ·
<a href="./examples/example-B-travelers.png">Travelers</a> ·
<a href="./examples/example-C-01-coffee-pouch.png">SLOW/ROAST</a> ·
<a href="./examples/example-C-02-glass-serum.png">PURE/ACTIVE</a> ·
<a href="./examples/example-C-03-beverage-can.png">BITTER/CITRUS</a> ·
<a href="./examples/example-C-04-lidded-box.png">SILENT/HOURS</a> ·
<a href="./examples/README.md">All originals</a>
</p>

Platform watermarks stripped. See [ASSET-LICENSE.md](./ASSET-LICENSE.md).

## Four types

| Type | Use it for | Entry point |
|---|---|---|
| **A · Vertical concept poster** | Concept poster, exhibition KV, album cover, book cover | `scripts/fill_meta.py A` |
| **B · Hand-drawn group illustration** | Multi-character illustration, animal bestiary, travel group | `scripts/fill_meta.py B --theme <theme>` |
| **C · Photoreal packaging mockup** | Studio-lit mockup (coffee bag / serum bottle / can / rigid box) | `scripts/fill_meta.py C` |
| **D · Narrative storyboard** | Comic slices, picture-book sequences, same character across 6–9 frames | `scripts/build_storyboard.py --case cyber\|ink` |

**Not sure?** Is the subject **one** thing or **many**? One → A, many → B. Product mockup → C. Continuous narrative → D.

## Four workflows

| Workflow | When | Discipline |
|---|---|---|
| **Production** (default) | Type + template mature, target is a final | Fill → preflight → **generate 1 image only** → three-tier review → done or one targeted fix |
| **Exploration** | New theme / new style / template iteration | `scripts/explore.py` batched prompts + `settle` rename + verify + write back conclusions; single-style 2–5, multi-style 5–9; see [`references/explore-mode.md`](./references/explore-mode.md) |
| **Watermark removal** | Output has bottom-right "AI 生成 / WORKBUDDY" | Default [`scripts/dewm_v10.py`](./scripts/dewm_v10.py) (v9 + flat-area adaptive fusion, 31 ms); tricky images use [`scripts/pick_wm.py`](./scripts/pick_wm.py) four-way picker; all outputs go to `_clean/`, **never overwrite source** |
| **Verification** | Close the loop after generation | [`scripts/postcheck.py`](./scripts/postcheck.py) metrics + 2× text-band crop + dewm + runs.csv logging, <0.5 s |

**Production quota: 1 image by default.** No draft-then-final. No "compare" second image. Only blockers permit one targeted regeneration, changing exactly one thing. **Exploration quota**: single-style 2–5, multi-style 5–9; batches ≤ 3 per round, immediately `ls` and `explore.py settle` to rename-lock (prevents same-second timestamp collisions).

## How it works

<p align="center">
  <img src="./assets/readme/workflow.svg" width="100%" alt="From slot fill to a passing image: pick a type, fill slots, generate and verify, ship only if it passes">
</p>

The hard problem is not writing one pretty sentence. It is making the model produce the expected image every time, and locating the break when it doesn't. Three pieces: four types, each owning one figure-text relationship; scripts fill slots and never rewrite the template; one verification call after generation.

## How to use

Prerequisite: [WorkBuddy](https://www.workbuddy.cn/docs/workbuddy/Overview) installed — this is a WorkBuddy-exclusive image-generation Skill.

Install:

```bash
npx skills add taxueseek/taxue-imagegen
```

Script dependencies (only needed if you use the CLIs standalone — already present inside a WorkBuddy session):

```bash
pip install numpy pillow opencv-python-headless
```

Then just say it **inside WorkBuddy**, e.g.:

- "Type A, a 2:3 concept poster — ukiyo-e style, theme: impermanence, English headline WAITING"
- "Type B, full-bleed dog lineup, 14 dogs, modify with `fill_meta.py B --theme bird`"
- "Type C, a matte serum bottle in a paper box, deep indigo ink, metaphor is a single falling water drop"
- "Run explore_sample.csv in exploration mode, pick one as the main line"

Or trigger with `/taxue-imagegen`. Production mode defaults to 1 image per request — if you want batch exploration, say "exploration mode, N images" explicitly.

**A refinement is a render**: saying "one more version" = one more image = one more charge. State all your edits up front instead of five micro-tweaks.

## Credit cost

Billed per image:

| Scenario | Estimate |
|---|---|
| Production mode, 1 image | 5–10 credits |
| Exploration mode, 6 images | 30–60 credits |
| One refinement round (look → tweak prompt → re-render 1) | +5–10 credits |

Spend less: lock the aspect ratio first, run `preflight.py`, batch edits into one round. Batch runs (≥5 images) ask first.

## What it's for

- **Posters**: events, exhibitions, city walks, concept posters, KVs, album covers
- **Platform covers**: Xiaohongshu, WeChat OA, podcast, Bilibili, avatars, ultra-wide headers
- **Brand material**: postcards, invitations, tickets, menus, packaging stickers (Type C for the actual mockup)
- **Books**: covers, frontispiece, chapter pages, zine inner pages
- **Group illustrations & bestiaries**: character bestiary, animal bestiary, travel group portraits, journal multi-character spreads
- **Text**: literary excerpts, poetry, personal manifestos (Type A's three-tier copy hierarchy)

## Rules

1. **Paper / background rejects hue words** — `warm / aged / faded / unbleached / vintage` are strong hue commands that turn output yellow. For texture use `fibre grain / laid lines / halftone / tooth / deckle`.
2. **Numerics only on crash-prevention items** — background color, three-tier copy ratio, overlap area, accent-color ratio, top padding: lockable. Subject size, scale contrast, position/density: must stay vague.
3. **Area / density percentages are mostly noise to the model** — replace "1/3 padding", "low density" with countable constraints (subject count lower bound, max subject ≤ 1/4 frame, small subject ≥ 1/12) + positive descriptions.
4. **Resolve paths with `find` first** — the archiver normalizes consecutive underscores into one.
5. **Separate meta info from content physically** — weight hints (`= 100`), ratio explanations next to copy are roughly 50% likely to be painted as text.

Full rules plus 22 verified pitfall fixes across tracks: [`references/pitfalls.md`](./references/pitfalls.md).

## Randomness & creativity

The magic of image generation is the artistic side — randomness and creativity are baked in. This is an **engineering-first skill**: every prohibition, hard line, and template is there to make output stable — but it deliberately avoids rigid constraints and doesn't aim to reproduce a fixed look. The same prompt handed to GPT Image 2, Grok Imagine 2, Nano Banana 2, Seedream 5.0 Pro can produce noticeably different results. That creative headroom is intentional — run the same line a few times, pick the one that fits.

**The baseline model is hunyuan-image**: every hard line and threshold here was measured on it — use it and you get the results shown in this README.

Other models work in principle (the prompts are plain English descriptions), but style bias and text accuracy drift. If you switch, render one and re-check with `postcheck.py` first:

- **Known to work**: GPT Image 2, Grok Imagine 2, Nano Banana 2, Seedream 5.0 Pro
- **Re-verify first after switching**: verbatim text accuracy, padding / top space, halftone grain and spot-color rendering

> Switching models costs another round of threshold tuning — and a few more images' worth of credits. With no specific need, staying on hunyuan-image is the cheapest path.

## Engineering checks

The spec doesn't just live in docs: `SKILL.md` slots, templates, hard lines, and verification thresholds all have machine-readable checks. Patch any of them, run the check, see what broke — GitHub Actions runs the same on push and PR.

```bash
bash scripts/run_tests.sh                       # run all checks
python3 scripts/preflight.py "your prompt"     # preflight a single prompt (A/B/C)
python3 scripts/postcheck.py a.png --track A   # verify a single output
```

CI: [`.github/workflows/validate.yml`](./.github/workflows/validate.yml).

## Changelog

- **v1.12.0** (2026-09-12): New type E "multi-grid layout" (sprite sheets / series posters / stamp sets / character-bible sheets), where every cell is an independent finished piece bound by one shared spec; `fill_meta.py E` (11 slots + cell-count vs cell-list check); preflight no longer mistakes a cell size for the output canvas size. See [CHANGELOG.md](./CHANGELOG.md).
- **v1.11.1** (2026-09-09): Fix `measure.py` crash on `%`, fake-green verification tests, missing hue words in preflight. See [CHANGELOG.md](./CHANGELOG.md).
- **v1.11.0** (2026-09-09): Optional cloud post-processing (propose first); dual-route watermark removal.
- **v1.10.0** (2026-09-08): Add Type D "Narrative Storyboard" — a dual LOCK anchor keeps one character consistent across 9 frames (`references/storyboard.md` + `build_storyboard.py --case cyber|ink`); `fill_meta.py C` turns packaging mockups from hand-copying a 17-slot template into mechanical slot fill; fixes four classes of low-level bugs that actively misled generation (preflight word boundaries falsely blocking 9/9 prompts, `【】` slots undetected, postcheck logging unverified text as pass, overwrite guard bypassed by case/hard links); adds 42 assertion-based regression tests. Default watermark removal stays v10 — v11/v12 measured worse overall and are demoted to optional for dark-region cases.
- **v1.9.1** (2026-09-08): Fix CI failing on every push since publication — three benchmark scripts hard-coded a machine-local path, so `import dewm` failed on the runner (locally they silently picked up same-named modules from `~/.workbuddy/skills/`, which is why the suite passed on the author's machine); all three now resolve their own directory, test images come from `TAXUE_BENCH_IMGS`, and `run_tests.sh` gains a privacy scan while CI runs that same suite.
- **v1.9.0** (2026-09-08): Add Type C "Photoreal Packaging Mockup" — studio-lit physical base + editorial monochrome ink layout + single-metaphor AM halftone graphic + giant stacked brand wordmark, Chinese meta-template with slots (`references/packaging-editorial.md`, three rounds, r3 4/4 text verbatim-correct).
- **v1.8.0** (2026-09-07): Add `dewm_v10` — v9 + flat-area adaptive fusion, fixes "visually visible watermark ghosts on flat backgrounds" (amp says CLEAN but the eye sees residue); flat-background RMS 5.98 → 1.43, textured images byte-identical (zero regression); default watermark removal switches to `dewm_v10.py`.
- **v1.7.0** (2026-09-07): Exploration mode (`explore.py` + CSV-driven); default watermark removal switches to `pick_wm` (v6/v7/v8 each have a specialty; 18-sample test showed v6 missed/left noise on 5 of 18, 28%); add `audit_wm` residual audit (works without source images to flag DIRTY).
- **v1.6.0** (2026-09-07): Single-call `postcheck.py` after generation — metrics + text-band visual crop + dewm reverse-alpha + runs.csv logging; verification round-trips drop from 3–4 to 1; data feedback loop for template tuning.
- **v1.5.0** (2026-09-07): Borrowed `taxue-halftone` pipeline — `fill_meta.py` mechanical slot fill (LLM never rewrites the template, word counts auto-derived); tiered prompt library loading; three-tier review card + 1-image production quota.
- **v1.4.0** (2026-09-06): Size test — `size` accepts arbitrary pixel counts (not just the three schema examples); 1024/1152/1536 long-edge variants all output exactly.
- **v1.0.0** (2026-09-01): Initial release. Two types, five themes, mechanical slot fill, single-source templates. See [CHANGELOG.md](./CHANGELOG.md).

## License

Code, SKILL instructions, scripts, references — [MIT License](./LICENSE).
Images in `examples/` and `assets/readme/` — [ASSET-LICENSE.md](./ASSET-LICENSE.md), not distributed under MIT.