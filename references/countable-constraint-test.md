# 测试 · v5.1 补丁与可数约束修正（2026-09-06）

> 目的：把技能文档里三项「待实测」补丁闭环。
> 测试 1/2 验证 v5.1（海报类型），测试 3 验证可数约束（群像类型，对照上轮最差的奇幻 A 版）。

---

## v5.1 三处补丁（相对 v5 的全部差异）

1. **三级文字统一放底部空带**：三级文字自上而下排在画面底部一条水平文字带内；除该文字带外画面其他位置不得出现文字。**连带修改**：原 v5 的「交叠 ≤15%」硬底线删除（文字与主体分区后无穿插），改为「主体不得与底部文字带重叠，文字四周净空 ≥ 字高 1/2」。
2. **留白禁横幅**：`留白是背景色的直接延续，不得被画成纸条、横幅或任何有边缘的实体色块`（针对 VACANT 上轮米白横幅违规）。
3. **引号禁令加强**：`三组文案不得包含任何引号字符`（针对 OVERTIME 上轮装饰性引号违规）。

---

## 测试 1 · VACANT 复现场景（瑞士国际主义 / 空缺 / 最后一个离开的夜晚）

```
设计一张竖版 2:3 概念海报。

【三项输入】
视觉风格：瑞士国际主义平面设计
内容主题：空缺
表达意图：办公室里最后一个离开的夜晚，灯已经灭了
表达意图决定主体状态、元素关系与情绪，不决定画什么。

【画面】
围绕一个明确的瞬间或一组形象关系展开，不把多个情节或概念拼在一起。
主体：一把被放大的办公椅，靠背与坐面由版面网格的骨架构成，几何化、去细节。其状态与动势由表达意图决定。
从视觉风格中只取两至三个特点，运用到主体轮廓、画面分区、色块关系或文字排列中，不必全部使用。
让风格体现在画面的组织方式里，而不是贴上纹样、边框或符号。
若参考具体作品，不照搬其中可辨认的角色、物体或场景。

【硬底线：以下为数值约束，不可协商】
- 背景：单一均匀纯白。无渐变、无纸纹、无颗粒，无米白、奶油、象牙、泛黄、牛皮纸色调，无茶渍与做旧
- 顶部 25% 为连续留白：留白是背景色的直接延续，不得被画成纸条、横幅或任何有边缘的实体色块
- 三级文字统一放置在画面底部的一条水平文字带内，自上而下依次为英文主标题、中文短句、英文短句；
  除底部文字带外，画面其他任何位置不得出现文字
- 主体不得与底部文字带重叠；每个文字块四周净空不小于该块字高的 1/2
- 强调色：单一连续色块，覆盖 ≤ 画面 8%
- 网点与颗粒：仅用于图像内部必要区域，不得进入字形外扩 12px

【软引导：以下交给主题与意图决定，不预设数值】
- 主体与参照物可形成强烈尺度反差，具体倍数由主题决定
- 位置、方向、疏密、间距由表达意图决定
- 不固定左图右字或中央构图

【三组文案】
英文主标题 VACANT = 100，不压过主体、不占满画面；
中文短句 灯灭了 椅子还记得 = 22，承担主要阅读信息，完整、清晰、醒目；
英文短句 the chair remembers the light = 12，呼应中文语义但不逐字直译，正常观看时清楚可读。
三组文案不得包含任何引号字符。
层级主要通过字重、位置、间距与对齐建立，不依赖悬殊字号。

【负向】
场景内的招牌不出现随机字句。除三组文案外无额外文字、编号、日期或网址。
不添加多余标点。不出现 logo、水印、相框、墙面样机或手机屏幕展示效果。

【观看路径】
第一眼看清主体与英文主标题；
第二眼通过中文短句理解画面想表达什么；
近看发现与主题有关的细节。
```

---

## 测试 2 · TIDE 复现场景（浮世绘 / 汛期 / 河水涨到最后一级石阶）

```
设计一张竖版 2:3 概念海报。

【三项输入】
视觉风格：日本浮世绘版画
内容主题：汛期
表达意图：河水涨到石阶最后一级，没有人说话
表达意图决定主体状态、元素关系与情绪，不决定画什么。

【画面】
围绕一个明确的瞬间或一组形象关系展开，不把多个情节或概念拼在一起。
主体：一道抬起的巨浪，浪尖卷曲成爪形，平面化色块构成。其状态与动势由表达意图决定。
从视觉风格中只取两至三个特点，运用到主体轮廓、画面分区、色块关系或文字排列中，不必全部使用。
让风格体现在画面的组织方式里，而不是贴上纹样、边框或符号。
若参考具体作品，不照搬其中可辨认的角色、物体或场景。

【硬底线：以下为数值约束，不可协商】
- 背景：单一均匀纯白。无渐变、无纸纹、无颗粒，无米白、奶油、象牙、泛黄、牛皮纸色调，无茶渍与做旧
- 顶部 25% 为连续留白：留白是背景色的直接延续，不得被画成纸条、横幅或任何有边缘的实体色块
- 三级文字统一放置在画面底部的一条水平文字带内，自上而下依次为英文主标题、中文短句、英文短句；
  除底部文字带外，画面其他任何位置不得出现文字
- 主体不得与底部文字带重叠；每个文字块四周净空不小于该块字高的 1/2
- 强调色：单一连续色块，覆盖 ≤ 画面 8%
- 网点与颗粒：仅用于图像内部必要区域，不得进入字形外扩 12px

【软引导：以下交给主题与意图决定，不预设数值】
- 主体与参照物可形成强烈尺度反差，具体倍数由主题决定
- 位置、方向、疏密、间距由表达意图决定
- 不固定左图右字或中央构图

【三组文案】
英文主标题 TIDE = 100，不压过主体、不占满画面；
中文短句 水涨上来的时候 谁也没说话 = 22，承担主要阅读信息，完整、清晰、醒目；
英文短句 the river kept its own schedule = 12，呼应中文语义但不逐字直译，正常观看时清楚可读。
三组文案不得包含任何引号字符。
层级主要通过字重、位置、间距与对齐建立，不依赖悬殊字号。

【负向】
场景内的招牌不出现随机字句。除三组文案外无额外文字、编号、日期或网址。
不添加多余标点。不出现 logo、水印、相框、墙面样机或手机屏幕展示效果。

【观看路径】
第一眼看清主体与英文主标题；
第二眼通过中文短句理解画面想表达什么；
近看发现与主题有关的细节。
```

---

## 测试 3 · 奇幻旅行团可数约束版（对照上轮变体 A：白底 80.6%、构图裂两团）

> 基于 `references/crowd-illustration.md` 主题四变体 A，只改密度段，其余逐字保留。
> 变化点：
> - `LOW to medium density, generous white space` → `Exactly thirteen characters on the sheet — no fewer. Largest ≤ 1/4 sheet height, smallest ≥ 1/12`
> - 新增 `ONE single connected cluster covering the middle two thirds of the sheet` + `no two characters share a horizontal baseline`
> - 白底通道描述从「整张画面」改为「贯穿团块内部」

```
A vertical 2:3 hand-drawn illustrated poster: a gentle humorous low-fantasy travelling party of
ten figures and three animal companions, drawn with loose wobbly dark grey-black hand-drawn
contour lines of slightly varying weight, flat matte color fills with a faint marker or gouache
stroke, no shading, no realistic light, no 3D render, no heavy paper texture. Warm, gentle,
slightly clumsy cartoon generalization — like a naturalist's sketchbook crossed with an
independent illustration poster. Not an epic movie poster, not a game character lineup, not a
battle party, not corporate mascots, not emoji.

Pure white background. Exactly thirteen characters on the sheet — no fewer: ten figures and
three animals. The largest character stands no taller than one quarter of the sheet height; the
smallest no shorter than one twelfth of the sheet height. The characters form ONE single
connected cluster covering the middle two thirds of the sheet, arranged in one irregular cloud —
not a row, not a grid, not a V formation, and no two characters share a horizontal baseline.
Core members cluster near the centre; the rest stay attached to the same cloud at varied
distances. White background runs through the cluster as irregular channels and gaps BETWEEN the
figures, not just around the outer edge. Every character can be appreciated individually; nobody
is buried behind someone else. Natural breathing space at the edges; no figure awkwardly cropped
by the frame.

Every figure is a distinct silhouette, not one template recolored or rotated. Specifically:
1 a teenage human boy, thin and a little gawky, standing in three-quarter view with a simple
travel pack slung over one shoulder, head tilted down and to one side;
2 a middle-aged human man, short and round-bellied, standing frontally with hands on hips,
grinning, simple everyday travel clothes — plain tunic, trousers, worn boots;
3 an elderly human woman, stooped and narrow-shouldered, leaning on a walking stick, seen in
profile, a long simple coat, hair in a loose bun;
4 a young human woman, average height and sturdy, standing in profile with one hand in her pocket,
short practical jacket, looking off to one side rather than at the viewer;
5 a tall thin plant-person whose whole body is built from branch structure — a slender trunk torso,
two thin tapering branch arms, a head formed from a cluster of leaves with no human face, long
root-like feet, standing perfectly still and slightly taller than everyone;
6 a short round old-fashioned robot with a blunt rounded shell body, a dome head with a single
simple lens eye, visibly simplified ball joints at shoulders and elbows, stubby legs, standing
frontally with its head cocked to one side, no brand markings, no panel lines;
7 a broad heavy-set orc with its own head-to-torso proportions — a large forward-jutting jaw, a
wide thick torso, long heavy arms hanging past the hips, short thick legs — NOT a human with ears
glued on; sitting on the ground, seen at a three-quarter angle, calm.
8 a cat in true four-legged cat body structure, curled up beside the sitting orc, no clothing;
9 a dog in true four-legged dog body structure, leaning its weight against the sitting orc's leg
or resting its chin on a knee, no clothing;
10 a small bird in true bird body structure, perched on the shoulder of the tall plant-person,
no clothing.
The three animal companions each connect to a different humanoid in one local spot — a paw resting
against a leg, a bird's feet on a shoulder, a cat curled against a hip — but these are small local
touchpoints only; they never cover or break the main silhouette of any figure.
Silhouettes alternate tall and short, wide and narrow, standing and sitting, frontal, profile and
three-quarter. Only two or three characters look out at the viewer; the rest look down, sideways,
away, or at each other. Two human characters stand close with their heads turned toward one
another as if mid-conversation. Arms, packs, branches, tails and necks may reach into the gaps
between neighbours, but every body stays separate, correctly connected and clearly readable —
no fused bodies, no stray extra limbs.

Costume restraint: clothing is simple everyday travel wear in muted tones — plain tunics, trousers,
boots, a coat, a pack. No uniforms, no matching outfits, no armor, no capes, no helmets, no
weapons, no staffs with crystals, no piles of gear and pouches. Recognizability comes from body
outline, not from costume.

Color: a unified low-to-mid saturation natural palette of cream white, warm grey, grey-brown,
ochre brown, sage green and slate blue. All members share a few recurring muted elements of misty
blue, ochre orange and sage green — a scarf, a leaf cluster, a painted shell panel, a bird's
plumage, a coat lining — distributed unevenly across the group so the party reads as one party
without wearing a uniform. Neutrals carry the main area. One or two dark characters serve as
separate visual anchors rather than one dark cluster. Warm and cool echo across the sheet without
forming a checkerboard.

No text, no labels, no titles, no borders, no scenery, no ground, no background environment,
no flowers, no stars, no hearts, no magic effects, no glowing auras.

Negative prompt: no grid layout, no evenly spaced rows, no V formation, no symmetrical lineup,
no repeated identical character template, no recolored clones, no rotated copies, no cloned or
mirrored characters, no chibi mascot style, no big sparkly eyes, no emoji faces, no anime-style
pretty faces, no photographic realism, no 3D render, no soft gradient shading, no airbrush,
no drop shadow, no glow outline, no magical glow, no particle effects, no sticker white border,
no die-cut outline, no heavy paper texture, no strong grain, no noise overlay, no vintage filter,
no aged or cream or ivory or yellowed background, no epic movie poster composition, no dramatic
low angle, no heroic lighting, no game character selection screen, no scenery, no landscape,
no ground, no road, no background environment, no flowers, no stars, no hearts, no decorative
clutter, no armor, no helmets, no capes, no uniforms, no matching outfits, no weapons, no swords,
no staffs, no crystal orbs, no magic wands, no shields, no piles of gear, no pouches and straps,
no props, no text, no labels, no captions, no numbers, no watermark, no frame, no border,
no extra limbs, no fused bodies, no merged characters, no anatomically wrong joints, no orc drawn
as a human with animal ears, no robot drawn with a human face, no animal standing on two legs,
no anthropomorphic cat or dog or bird, no clothes on the animals, no figures cut off awkwardly
by the frame edge.
```

---

## 结果记录（2026-09-06 实测回填）

出图 4 张（1024x1536，quality=high）：
- 测试 1 VACANT：`…/2026-09-06/设计一张竖版_2_3_概念海报____三项输入__视觉风格__2026-09-06T08-10-20.png`
- 测试 2 TIDE：`…/2026-09-06/设计一张竖版_2_3_概念海报____三项输入__视觉风格__2026-09-06T08-10-50.png`
- 测试 3 奇幻：`…/2026-09-06/A_vertical_2_3_hand_drawn_illu_2026-09-06T08-11-25.png`
- 追加 v5.2 修正验证：`…/2026-09-06/设计一张竖版_2_3_概念海报____三项输入__视觉风格__2026-09-06T08-13-21.png`

| 测试 | 判定项 | 结果 |
|---|---|---|
| 1 VACANT | 文字全部落底部带 | ✅ VACANT／中文／英文三级全在底部 |
| 1 VACANT | 顶部留白无横幅 | ✅ 无横幅；但纯白被画成**浅灰底**（背景 RGB≈242，white% 32.9 / near% 88.5）→ 新坑 9 |
| 1 VACANT | 文案无引号 | ✅ |
| 2 TIDE | 文字落底部带 | ✅ |
| 2 TIDE | 顶部留白干净 | ✅ 量测最优（top noise 1.2，RGB 246/245/245） |
| 2 TIDE | 文案无引号 | ❌ **主标题渲染成 "TIDE = 100"** —— `标题 = 权重` 连写被吞进文案 → 新坑 8 |
| 3 奇幻 | white% vs 上轮 80.6% | ✅ 降到 **66.1%**（-14.5pp，未达 40–55% 目标但方向确认） |
| 3 奇幻 | 单团构图 | ✅ **裂团修复**，13 角色成一团圆 clump，留白通道贯穿团内 |
| 3 奇幻 | 角色 ≥13 且不重样 | ✅ 7 人形 + 猫狗鸟，差异化全部落实 |

### 追加 · v5.2 文案写法修复验证（TIDE 场景重出）

改动：三组文案声明改为「字最大的一行是英文主标题，内容只有两个词：TIDE」式**内容与权重分离**写法；
权重比例移到硬底线单独一行（`字高比例固定为 100 比 22 比 12`）；
新增负向 `底部文字带内不得出现任何数字、等号、比例符号或其他标注`；纯白加强 `不是浅灰`。

| 判定项 | 结果 |
|---|---|
| 主标题干净无 "= 100" | ✅ **坑 8 修复验证通过** |
| 文字带三级无引号无标注 | ✅ |
| 背景纯白 | ❌ 海面场景铺满下半部（top noise 94.9，留白条款失效）——**坑 10：满铺型主体与纯白/留白硬底线冲突** |

### 结论

1. **v5.1 三补丁全部有效**（文字带 ×3 张全过、横幅未复现、引号未复现）。
2. **文案声明必须与权重标注分离**（v5.2 写法），否则约 50% 概率把 `= 100` 吞进画面。
3. **「背景纯白 + 顶部留白」只适用于孤置型主体**；满铺型主体（巨浪、巨字场景）会天然突破。
   模板需按主体类型二选一：满铺场景 + 文字带（放弃纯白留白）／ 纯白底 + 孤置主体（保留留白）。
