#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_storyboard.py — 类型 D 分镜 prompt 组装器（数据与逻辑分离）。

设计：
  - STYLE_LOCK / CHARACTER_LOCK 每张逐字相同（一致性锚，坑：改词=换锚）
  - 每张只有 SCENE 段不同（场景/镜头/动作/光线）
  - 无字纯净版：负向排除一切文字

用法：
  python3 build_storyboard.py                    # 默认赛博朋克案 → _prompts/
  python3 build_storyboard.py --case ink         # 水墨武侠案 → _prompts_ink/
  python3 build_storyboard.py --case ink --out DIR

两个案例的差异只有 STYLE_LOCK / CHARACTER_LOCK / NEG / SCENES 四段数据，
组装逻辑共用 build()（此前两份脚本 main() 逐字重复，改一处要改两处）。
"""
import argparse
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# ── 案例一：赛博朋克·雨夜侦探 ─────────────────────────────────
CYBER_STYLE = """STYLE LOCK (identical in every frame): cyberpunk anime illustration, cel-shaded with painterly background, rain-soaked neon night city, dominant palette of deep teal, hot magenta and cyan glow on near-black, wet asphalt mirror reflections, volumetric light in rain haze, cinematic film grain, high contrast chiaroscuro, vertical 9:16 movie storyboard composition, detailed background art, moody atmosphere."""

CYBER_CHAR = """CHARACTER LOCK (identical in every frame): a young female detective in her early twenties, chin-length choppy silver-white hair with a long loose strand framing her face, sharp crimson eyes, calm cold expression, wearing a long black high-collar trench coat with glowing cyan circuit trim on the lapels, left arm is a matte dark prosthetic with faint cyan line lights, a small glowing pink hexagon badge clipped at her left hip, black gloves. Same face, same hair, same outfit in every frame."""

CYBER_NEG = """NEGATIVE: no text, no letters, no numbers, no captions, no speech bubbles, no subtitles, no watermark, no logo, no signature, no border, no panel frame, no split panels, no collage."""

CYBER_SCENES = [
    ("01_rooftop", """FRAME 1 of 9 — Wide establishing shot. The detective stands at the edge of a rooftop, seen from behind in the lower third of the frame, coat and hair stirred by wind and rain. Below and beyond her sprawls the megacity: endless towers, magenta and cyan holograms, rain streaking through neon haze. City lights shimmer on the wet rooftop floor. She gazes down at the city in silence."""),
    ("02_chip", """FRAME 2 of 9 — Medium shot in a narrow back alley. The detective holds up a small glowing data chip between her gloved fingers at eye level, studying it. A flickering pink ramen-shop sign lights one side of her face, the other side in shadow. Rain falls past the single cone of light above her. Tight vertical alley walls frame her in the center."""),
    ("03_alley", """FRAME 3 of 9 — Full body tracking shot. The detective walks toward the camera through a rain-flooded alley, mid-stride, coat swaying. Neon signs in Chinese-style glyphs glow magenta and teal on both walls, their reflections stretching across the wet ground beneath her feet. Steam rises from a street vent. Low angle, slightly tilted, film-noir mood."""),
    ("04_bar", """FRAME 4 of 9 — Interior, dim cyberpunk bar. Two-shot across the counter: the detective sits on one side in shadow, an old bartender with a glowing mechanical eye leans in from the other side. A single hanging lamp throws warm light between them. Bottles of neon liquor line the shelves behind. Tight composition, faces half-lit, secrets in the air."""),
    ("05_datavault", """FRAME 5 of 9 — Interior, data vault. Close medium shot: the detective stands surrounded by floating holographic screens, cyan data streams reflecting across her face and silver hair. Her prosthetic left arm is raised, interfacing with a glowing terminal. Deep blue darkness around, the only light source is the holograms. Concentric arcs of light frame her."""),
    ("06_chase", """FRAME 6 of 9 — Action shot. The detective sprints through traffic on a rain-slick elevated road, coat streaming behind her, one hand pushing off the hood of a hovering car. Strong motion blur on the background vehicles, her figure sharp. Magenta taillights streak the wet asphalt. Dynamic diagonal composition, camera low and close, adrenaline mood."""),
    ("07_confront", """FRAME 7 of 9 — Rooftop confrontation. The detective faces a tall silhouette in a white coat across the rooftop, ten meters apart, shot from a low side angle between them. A single magenta sign glows between their profiles. Rain pours harder now, wind whipping both coats. Tension, stillness before the storm, mirrored stance."""),
    ("08_reveal", """FRAME 8 of 9 — Extreme close-up. The detective's face fills the upper frame, rain on her skin, crimson eyes wide with shock as she looks down at her open gloved hands holding a cracked white mask. The mask's crack glows faint cyan. Background drops into dark bokeh with one distant magenta light. Emotional peak of the sequence."""),
    ("09_dawn", """FRAME 9 of 9 — Wide closing shot. Dawn after the rain. The detective stands on the same rooftop, now from the front, hood down, eyes closed, silver hair damp and wind-stirred. The megacity behind her shifts from night neon to pale orange dawn breaking through thinning clouds, last cyan holograms fading. Wet rooftop reflects the sunrise. Quiet, hopeful, breathing space in the composition."""),
]

# ── 案例二：水墨武侠·孤剑客 ───────────────────────────────────
# 纸底禁色相词（硬规则1）：只用纹理词 laid paper / fibre grain，不写 aged/vintage
INK_STYLE = """STYLE LOCK (identical in every frame): traditional Chinese ink-wash painting (shuimo) rendered as cinematic animation key art, black ink brushwork of varying density over pale rice paper, large areas of deliberate empty space, soft ink gradients and dry-brush texture, laid paper fibre grain, the entire world in monochrome ink greys except a single vermilion red accent (the sword tassel), light and weather painted as ink mist, vertical 9:16 movie storyboard composition, elegant minimal composition, poetic and contemplative atmosphere."""

INK_CHAR = """CHARACTER LOCK (identical in every frame): a lone wandering swordsman in his thirties, long black hair half-tied with a plain white cloth ribbon, the loose ends stirring with the wind, a wide flat straw hat hanging on his back, a loose grey-blue robe with a black sash at the waist, and a long straight sword carried at his left hip with a small vermilion red silk tassel at the hilt — the only red in the frame. Lean weathered face, calm quiet eyes, restrained expression. Same face, same hair, same outfit, same red tassel in every frame."""

INK_NEG = """NEGATIVE: no text, no letters, no numbers, no captions, no speech bubbles, no subtitles, no watermark, no logo, no signature, no border, no panel frame, no split panels, no collage, no color photograph look, no oversaturated colors."""

# 叙事弧：远眺→歇脚→行路→问禅→入林→拔剑→对峙→特写→渡舟
INK_SCENES = [
    ("01_mistgate", """FRAME 1 of 9 — Wide establishing shot. Vast ink-wash mountains fill the frame with layered mist and empty paper sky, tiny and distant. In the lower third, the swordsman is a small figure on a stone mountain path, seen from behind, pausing before a half-visible mountain gate shrouded in ink mist. His red sword tassel is the single point of red in a world of grey. Immense negative space above."""),
    ("02_teastall", """FRAME 2 of 9 — Medium shot at a roadside tea stall under a gnarled pine. The swordsman sits on a wooden bench, holding a plain tea bowl at chest height, thin steam rising. His straw hat rests on the table, sword leaning against the bench, red tassel hanging still. Ink brush strokes define the pine needles; the background dissolves into empty paper and faint distant peaks. Quiet rest before the journey."""),
    ("03_reedpath", """FRAME 3 of 9 — Full body tracking shot. The swordsman walks along a narrow path between tall reeds toward the camera, mid-stride, robe and loose hair stirring in the wind. Dry-brush ink strokes make the reeds bend one way; a wide river and faint sailboats dissolving into mist lie behind. Low ink horizon, huge empty sky. The red tassel sways with his step."""),
    ("04_temple", """FRAME 4 of 9 — Interior two-shot in a small mountain temple at dusk. The swordsman sits cross-legged on one side of a low table, facing an old monk with a shaven head on the other side. One candle flame between them, painted as a soft ink glow. Beams of the wooden temple rendered in a few decisive brush lines, deep ink darkness at the edges. Faces half-lit, a silent conversation."""),
    ("05_bamboo", """FRAME 5 of 9 — Environmental medium shot deep inside a bamboo grove. The swordsman stands still among vertical bamboo stalks painted with fast ink strokes, one hand resting on the sword hilt, head slightly lowered as if listening. A few leaves drift in the air. Bamboo shadows fall across the path in layered ink tones. Dense vertical rhythm, a held breath before violence."""),
    ("06_raincut", """FRAME 6 of 9 — Action shot, strong diagonal composition. Heavy rain painted as long slanting ink strokes. The swordsman mid-draw, the long sword arcing out of its sheath, body twisted in a dynamic diagonal from lower left to upper right. His robe snaps in the wind; a burst of splattered ink marks the sword's wake. The red tassel blurred in motion. Camera low and close, explosive moment frozen in brushwork."""),
    ("07_cliffduel", """FRAME 7 of 9 — Confrontation side shot on a cliff edge above a sea of clouds. The swordsman faces a tall rival silhouette in a flowing dark robe, ten meters apart, both seen in profile from a low angle. Wind pulls at both figures; the rival is a solid black ink silhouette, the swordsman rendered in lighter grey brushwork. Between their profiles, only mist. Mirror stance, absolute stillness before the storm."""),
    ("08_eyes", """FRAME 8 of 9 — Extreme close-up. The swordsman's eyes fill the upper frame, painted with the finest brush detail: calm but unblinking, a raindrop sliding past his temple, loose hair strands crossing his cheek. Above his eyes the white ribbon's knot is visible. Below, out of focus, the sword hilt with its vermilion red tassel glows softly like an ember in the grey world. Emotional peak, everything unsaid."""),
    ("09_ferry", """FRAME 9 of 9 — Wide closing shot at dawn. A river crossing: the swordsman stands at the stern of a small flat ferry boat drifting away from the viewer into pale morning mist, seen from behind, straw hat back on his head. The rising sun is a single pale wash of the faintest gold over the ink mountains — the only warmth the whole sequence allows. Water rendered as long horizontal ink lines. Vast empty space, quiet departure, the red tassel the last point of color."""),
]

CASES = {
    "cyber": {"style": CYBER_STYLE, "char": CYBER_CHAR, "neg": CYBER_NEG,
              "scenes": CYBER_SCENES, "out": "_prompts"},
    "ink": {"style": INK_STYLE, "char": INK_CHAR, "neg": INK_NEG,
            "scenes": INK_SCENES, "out": "_prompts_ink"},
}


def build(out_dir, style, char, neg, scenes):
    """组装并写出 N 条 prompt，返回写出的文件路径列表。"""
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for name, scene in scenes:
        prompt = f"""A single vertical 9:16 movie storyboard frame, one continuous scene, no panel borders.

{style}

{char}

{scene}

{neg}"""
        path = os.path.join(out_dir, f"{name}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(prompt)
        print(f"[ok] {path}  ({len(prompt)} chars)")
        written.append(path)
    return written


def main():
    ap = argparse.ArgumentParser(description="类型 D 分镜 prompt 组装器（taxue-imagegen）")
    ap.add_argument("--case", choices=sorted(CASES), default="cyber",
                    help="案例：cyber=赛博朋克·雨夜侦探（默认），ink=水墨武侠·孤剑客")
    ap.add_argument("--out", help="输出目录（默认 scripts/_prompts[_ink]/）")
    args = ap.parse_args()

    cfg = CASES[args.case]
    out_dir = args.out or os.path.join(HERE, cfg["out"])
    written = build(out_dir, cfg["style"], cfg["char"], cfg["neg"], cfg["scenes"])
    print(f"\n{len(written)} 条 prompt → {out_dir}")
    print("下一步：逐张串行出图（坑 17：并行会撞同秒名覆盖），落地即改名锁定")


if __name__ == "__main__":
    main()
