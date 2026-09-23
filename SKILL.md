---
name: taxue-imagegen
version: 1.22.1
updated: 2026-09-23
agent_created: true
description: >-
  WorkBuddy 专属生图 Skill（仅在 WorkBuddy 内运行：出图走 WorkBuddy ImageGen，填槽与验收由 Agent 调用 scripts/*.py 完成；同系列另三个技能为通用技能，不绑平台/模型/Agent）。 基准模型 hunyuan-image——全部硬底线与验收阈值在它上面实测；其它模型原则上可用，换模型须重校阈值。 积分：单张约 5-10，每轮改进=一次全新出图=再扣一次，多轮打磨消耗大须先告知。
  元提示词库 + 出图工作流，五种类型——类型 A 竖版概念海报（管图文关系与尺度反差）、
  类型 B 手绘群像插画（管多角色差异化）、类型 C 写实包装 Mockup（棚拍实物做底 + 编辑风单色专色版面）、
  类型 D 叙事分镜（漫剧切片，双 LOCK 一致性锚跨帧复现）、
  类型 E 多格排版（精灵图/系列海报/邮票组/设定表，每格独立成品靠统一规格串组）。
  触发：生图、出图、生成图片、画一张、海报、概念海报、封面、KV、专辑封面、插画、群像、图鉴、角色设定、
  元提示词、ImageGen、画幅比例怎么选、去水印、水印、rmwm、fill_meta、postcheck、
  产品包装、包装图、mockup、包装样机、分镜、漫剧、绘本、连环画、storyboard、
  多格、九宫格、精灵图、sprite sheet、图集、系列海报、邮票组、表情包、角色设定表、
  云端修复、后处理、验收、检查这张图、能不能交付、复检、量测、泛黄、留白不够、
  平台署名水印、右下角署名、探索模式、多风格扫描、在豆包或即梦里跑。
  注意：只处理本技能自己出的图；与生图链路无关的独立修图任务（外部照片美颜/老照片修复、
  外来图的去水印）不接，路由到官方 buddy-image-processing（外来图去水印走 §6 的云端 erase）。
---

# WorkBuddy 生图元提示词库

> **WorkBuddy 专属**：出图走它的 ImageGen，填槽与验收由 Agent 调 `scripts/*.py` 完成；同系列另三个技能
> （creative-style / halftone / solar-polaroid）是通用技能——**拿走提示词只拿到三分之一**。
> **基准模型 `hunyuan-image`**：全部硬底线、比例与阈值都在它上面实测；换模型（GPT Image 2 / Grok Imagine 2 /
> Nano Banana 2 / Seedream 5.0 Pro）须重跑一张 + `postcheck.py` 校阈值，重标入口 `scripts/calibrate_thresholds.py`。
> **积分**：单张约 5–10，**每轮改进 = 一次全新出图 = 再扣一次**；先定画幅 + 先 `preflight.py`，把修改点攒成一轮。

五种类型，**先选类型再填空，别混用**（各自管什么见 front-matter description 与 §1 路由表）。

---

## 0. 出图前三件事（不可跳）

1. **先报积分**：ImageGen 单张约 5–10 积分。出图前必须在回复里说清这次预计消耗（N 张 × 5–10），批量出图（≥5 张）先确认。**改进同样计费**——「看图 → 调提示词 → 重出」每一轮都是一次全新出图；用户要求多轮打磨时，先说清累计消耗（如 3 轮 × 2 张 ≈ 30–60 积分），并建议把修改点攒成一轮。云端后处理（第 6 节）计费口径未实测，首次实测前按「可能同样计费」从严报消耗。
2. **先定画幅**：尺寸定错 = 重出 = 双倍积分。按第 2 节选，别凭感觉。
3. **先预检**：`scripts/preflight.py` 能在出图前拦下色相词、面积百分比、元信息混入文案等已知翻车项——预检不花积分。

---

## 1. 类型路由

| 你要什么 | 走哪条 | 打开 |
|---|---|---|
| 概念海报 / 展览 KV / 专辑封面 / 书籍封面 / 电影氛围海报 / 杂志专题 | **A · 竖版概念海报** | 出稿 `scripts/fill_meta.py A`（默认）；理解规则才读 `references/poster-v5.md`。**三个段落级变体**：§一·乙 主标题穿插型 / §一·丙 横版 16:9 + 两级文字 / §一·丁 图形规则系统型（主规则 1+辅助 1~2）——命中即按变体替换对应段落，别另起炉灶 |
| 写实产品包装 mockup（棚拍实物 + 编辑风单色油墨版面 + 半调隐喻图形，品牌字堆叠） | **C · 包装 Mockup** | 出稿 `scripts/fill_meta.py C --list` 查槽位后 `--set` 填齐（默认，17 槽自动组装 + 内嵌 preflight）；理解规则读 `references/packaging-editorial.md` §二/§三 |
| 多角色插画 / 动物图鉴 / 角色群像 / 旅行团 / 手账式群像 | **B · 手绘群像** | 出稿 `scripts/fill_meta.py B --theme`（默认）；理解规则才读 `references/crowd-illustration.md` |
| 多格排版 / 精灵图 / sprite sheet / 系列海报 / 邮票组 / 表情包 / 角色设定表（每格独立成品，N 格同规格） | **E · 多格排版** | 出稿 `scripts/fill_meta.py E`（默认，【】槽位 11 个）；理解规则读 `references/multigrid-layout.md` §三硬规则；**不与 D 混用**（D 是同一故事的连续帧） |
| 叙事分镜 / 漫剧切片 / 绘本连环画 / 同角色多场景（N=6–9 帧连续叙事） | **D · 叙事分镜** | 出稿改 `scripts/build_storyboard.py` 的 SCENES 列表生成 9 条 prompt；**串行**出图逐张落地改名；规则详见 `references/storyboard.md`（双 LOCK 一致性锚） |
| 拿不准 | 问一句：画面主体是**一个**→A，**一群**→B，**多张连续叙事**→D | — |
| **豆包/即梦环境**（自动用即梦 2K 尺寸，prompt 与 fill_meta 逐字节一致、不改写） | **jimeng.py 适配层** | `scripts/jimeng.py A --set …`（其余参数原样透传；换背景色 `--set 背景色=`、满铺 `--manpu`）；`--sizes` 查即梦尺寸；`--platform workbuddy` 切回原行为；完整边界见 `references/jimeng-env.md` |
| **探索模式**（多风格扫描 / 单风格打磨，N=2–9） | **Explore** | `scripts/explore.py build <csv> _prompts/` 出稿 + manifest → 分批出图 ≤3/批 → `explore.py settle` 改名校对；规则详见 `references/explore-mode.md` |
| 出图后要验收 | `scripts/postcheck.py` | **见子技能 `sub-skills/verify/`**（三档口径 / 水印政策 / 修复路由 / 各类重点） |
| 出图后要修图（增强 / 修破损 / 抠图换底 / 云端去疑难水印） | **云端后处理（可选）** | 判据见 §6，完整编排与纪律见 `references/cloud-postprocess.md`；用户点名直接走，Agent 建议须获同意 |
| 出图前查提示词 | `scripts/preflight.py` | fill_meta 已内嵌；手写提示词时单独跑 |
| 要无水印的图 | `scripts/dewm_v10.py`（**默认单版**，v9 + 平底自适应融合）；疑难图 `scripts/pick_wm.py`（v6/v7/v8/v9 四版选优，**残留 + 结构损伤双判据**，参照族取 v8/v9 同 k̂ 口径） | 选版判据见 §3 步 4 与坑 28；`dewm.py` / `dewm_v7.py` / `dewm_v8.py` / `dewm_v9.py` 仍是手动单选；`audit_wm.py` 审计残留（`--ref` 加测结构损伤）；输出全部走 `_clean/` 不覆盖原图 |
| 翻车了（泛黄 / 撞脸 / 挤成一团 / 文字糊） | `references/pitfalls.md` | 按症状查表，只读命中的那节 |

---

## 2. 尺寸速查（2026-09-06 实测）

**实测结论：`size` 不是只有三档。** 官方参数只声明了 `1024x1024 / 1024x1536 / 1536x1024` 三个示例值，
但本轮用同一 prompt 实测的四组尺寸全部**按请求像素精确输出**，无一被裁剪或就近取整。
详见 `references/size-and-params.md`。

| 画幅 | `size` 值 | 状态 | 典型用途 |
|---|---|---|---|
| **2:3 竖** | `1024x1536` | ✅ 主力，历史 46 张 | 概念海报、专辑/唱片封面、书籍封面 —— 类型 A/B 默认输出 |
| **3:4 竖** | `1152x1536` | ✅ 本轮实测 | 稍宽的竖版、社媒长图；**类型 C 包装 Mockup 指定尺寸** |
| **4:5 竖** | `1024x1280` | ✅ 本轮实测 | 小红书、社媒九宫格（顶部留白要从 25% 提到 35%） |
| **1:1 方** | `1024x1024` | ✅ 本轮实测 | 头像、方形封面、社媒卡片 |
| **3:2 横** | `1536x1024` | ✅ 本轮实测 | 横版 banner、PPT 背景（尺度反差在横幅里会失效） |
| **16:9 横** | `1536x864` | ✅ 2026-09-23 实测（3/3 精确输出） | 横版概念海报、PPT、宽屏 banner —— **不需要再后期裁** |
| **4:7 竖** | `1024x1792` | ✅ 2026-09-08 分镜实测 | **类型 D 分镜指定尺寸**（漫剧原生比例，近似 9:16；精确 9:16 应为 1024x1820） |

> ⚠️ **16:9 可直接要 `1536x864`，不必裁**（2026-09-23 更正）。原结论「没有精确 16:9、横版取 3:2 再裁」已被推翻：本机连出 3 张 `1536x864`，`PIL` 量测均为精确 `1536x864`（比例 1.778），无一被就近取整。
> 竖版近似 9:16 用 `1024x1792`（4:7，差 0.9%）；要精确 9:16 可先试 `1024x1820` 再看是否被取整。
> 若在豆包/即梦环境运行，仍以 §2·乙 的 `2560×1440` 为准。

### 2·乙 · 豆包/即梦（Seedream）尺寸

在豆包环境运行时，**不要用上面的 WorkBuddy 尺寸**，用即梦 2K 尺寸（`jimeng.py --sizes` 可查）：

| 画幅 | `width×height` | 总像素 | 典型用途 |
|---|---|---|---|
| **1:1 方** | `2048×2048` | 4.2M | 头像、方形封面、社媒卡片 |
| **4:3 横** | `2304×1728` | 4.0M | 文章配图、横向标准 |
| **3:4 竖** | `1728×2304` | 4.0M | 竖版海报、小红书封面 |
| **16:9 横** | `2560×1440` | 3.7M | PPT、横版 Banner、宽屏 |
| **9:16 竖** | `1440×2560` | 3.7M | 手机全屏、短视频封面 |
| **3:2 横** | `2496×1664` | 4.2M | 横版摄影 |
| **2:3 竖** | `1664×2496` | 4.2M | 竖版摄影、专辑/唱片封面（类型 A/B 默认） |
| **21:9 超宽** | `3024×1296` | 3.9M | 电影感、超宽屏 |
| **4:5 竖** | `1638×2048` | 3.4M | 社媒九宫格（自行换算） |
| **4:7 竖** | `1462×2560` | 3.7M | 分镜/漫剧（自行换算，近似 9:16） |

即梦宽高比范围 1:16 ~ 16:1，总像素上限约 10.3M（5.0 lite）/ 更高（5.0 Pro）。`jimeng.py` 自动按比例映射到上表，无需手动算像素。

---

## 3. 通用工作流

**两种模式，先分清再动手**（返工的最大来源是把生产当探索跑）：

- **生产模式（默认）**：类型与模板已成熟 + 目标是产出成品 → fill_meta 填槽 → preflight 通过 → **只出 1 张** → 三档评审 → 成品或一次定向修复。
- **探索模式（仅新主题/新风格/模板迭代；详见 `references/explore-mode.md`）**：N 张同主题/多主题的横向采样；用 `scripts/explore.py` 批量化出稿 + settle 改名 + 验收 + 结论回写。探索结论合并进模板后，同类需求永久转为生产模式。

**生产配额：默认 1 张。** 禁止先出草稿再出成品；禁止为「对比」再出一张；仅 blocker 允许一次定向重生，只改一项。
**探索配额：单风格 2–5 / 多风格扫描 5–9。** 出图分批 ≤ 3/批，每批立即 `ls` 核对 + `explore.py settle` 改名锁定（防同秒时间戳撞名，坑 17）。

| 步 | 做什么 | 要点 |
|---|---|---|
| 1 | 定类型 + 定尺寸 | 一次定死，中途别改 |
| 2 | **机械出稿** | **A/B/C/E 走脚本（默认）**：`fill_meta.py <类型> --list` 查槽位 → `--set KEY=VALUE` 填齐（A 是 7 槽、C 17 槽、E 11 槽；B 用 `--theme` 选主题），A 可加 `--manpu` 切满铺型；组装完自动过 preflight。**脚本已含全部验证过的禁令与校验（含 E 的「格数=清单条数」），LLM 不重抄模板**。**D 是半机械**：改 `build_storyboard.py --case cyber\|ink` 的 SCENES 生成 9 条，生成后单独跑 `preflight.py --track D`（跳过 A/B 专属规则）。模板没覆盖的新需求才手写（语种：B 必须英文，A 中文场景用中文，见坑 12），手写完单独跑 preflight |
| 3 | 报积分 → 出图 | 生产模式出 1 张；确需多张的**并行发起**，不要串行等；同主题多张时，三组文案/主体描述只写一次共享，各张只改构图与画幅 |
| 4 | **postcheck 一次调用验收** | `postcheck.py 图.png --track A --top --text ok --note 'A/<风格>/<主题>/<主标题>'`——量测 + 底部文字带 2x 裁片 + **水印自动识别**（`--wm auto` 默认：amp 与 R² 双条件先判有无，命中才去并复检，干净图不动刀）+ runs.csv 记账，全程 <0.5s。**怎么判、判错了怎么办、各类型盯什么，真源在子技能 `sub-skills/verify/`**；数值阈值见 §5。生产纪律：**blocker 才允许一次定向重生，只改一项**（修复只改所属那段指令，坑 12）；精确文字两轮仍错 → 后期排版补字，不假装正确 |
| 5 | 内联展示 | 用 `show_widget` 让用户在对话里直接看到，别只给路径 |
| 6 | 归档 | 路径先 `find` 再引用（§7 硬规则 4）：本机成品目录下有 `_tools/sync_images.py`，确认存在再 `--apply`。**只归档成品**，中途产物留会话目录隔离（坑 13 教训④） |
| 7 | 记录 | **数据先落本地，攒够频次再改文档**（见 §8 的 `log_report.py`）：运行数据由 postcheck 自动写入 `scripts/logs/runs.csv`，每次脚本调用由 `_log.py` 记入 `scripts/logs/usage.jsonl`；`log_report.py` 把两份日志读成「哪个坑真在高频发生 / 哪个脚本从没被用 / 哪一步在变慢」。**`--note` 按 `A/<视觉风格>/<主题>/<主标题>` 写**——不记风格就只能靠文件名反推，已验证风格会散落成资产流失（见 poster-v5.md §六·戊）。翻车与新结论先记进日志，**同一件事反复出现才写回 `references/pitfalls.md`，并当场把验证过的修复回写主模板**（poster-v5.md §一 / §六·戊 或 fill_meta 对应解析逻辑） |

---

## 4. 加载协议（省 Token，按需读，一次并行读完）

本技能参考文件按「出图不需要、排查才需要」分层。**下表命中多个文件时一次并行读完，禁止逐个串行等，禁止整读大文件**：

| 场景 | 必读 | 不读 |
|---|---|---|
| 类型 A 快速出图 | 本文件 + fill_meta 输出 + postcheck 输出 | poster-v5.md、pitfalls.md、历史文件 |
| 类型 A 变体（穿插／横版两级文字／图形规则系统）、满铺、改硬底线 | `poster-v5.md` §一/§一·乙/§一·丙/§一·丁/§五；要复用已验证风格查 §六/§六·乙/§六·戊 | 版本历史（在 history 文件） |
| 类型 B 快速出图 | 本文件 + fill_meta 输出 + postcheck 输出 | crowd-illustration.md、crowd-themes.md、pitfalls.md |
| 类型 B 自定义主题 | `crowd-illustration.md` §一 元提示词 | 主题库整读 |
| 类型 B 主题五（高密度百相图） | `crowd-100-faces-prompt-v2.md`（修复版）；`crowd-100-faces-prompt-v1.md` 只在追溯两版差异时读 | 不做百相图时两个都不读 |
| 探索模式（多风格扫描 / 单风格打磨） | `explore-mode.md` | — |
| 类型 C 快速出图 | 本文件 + `packaging-editorial.md` §一 模板 + §二 槽位表 | §三 只在翻车/新形态时读 |
| 类型 D 快速出图 | 本文件 + `storyboard.md` §三 模板 + §四 镜头设计法 | §一/§二 定位与机制只在首次建 LOCK 时读 |
| 类型 E 快速出图 | 本文件 + fill_meta E 输出 + postcheck 输出 | `multigrid-layout.md` 只在翻车/改模板时读 |
| 查某个坑的修复写法 | `pitfalls.md` 对应小节（先按症状表定位，再 `grep -n "^## 坑 "` 取行号只读那一节） | 其余坑节（全文约 114 KB，禁止整读） |
| 选画幅/参数细节 | 本文件 §2 不够时读 `size-and-params.md` | — |
| 在豆包/即梦里跑本技能 | `references/jimeng-env.md` | — |
| 要调用云端后处理（erase/enhance/restore/matting/beauty） | `references/cloud-postprocess.md` | — |
| 追溯模板为什么长这样 / 复盘 runs.csv 调模板 | `poster-v5-history.md` / `countable-constraint-test.md` / `scripts/logs/runs.csv` | — |
| 追溯某个版本改了什么 | `CHANGELOG.md` 对应版本节 | **出图不读**——全文约 49 KB，只在需要版本史时按版本节读 |

---

## 5. 出图后验收

> **完整流程与判定政策见子技能 `sub-skills/verify/SKILL.md`**（触发：验收、检查这张图、
> 能不能交付、复检、量测、泛黄、留白不够）。本节只放**数值真源**，两者的分工：
> 本表给数字，子技能给「怎么判、判错了怎么办、各类图盯什么」。
> 阈值出处与样本量见 `sub-skills/verify/evidence.md`。

一次调用（替代 measure/dewm/裁剪/记账的 3–4 次往返）：

```bash
# 本技能目录：WorkBuddy 下默认如上行所示；**换宿主/换机先确认**（§7 硬规则 4）
# ——别的宿主会把本技能装在自己的 skills 目录下，照抄绝对路径会 404
SKILL=~/.workbuddy/skills/taxue-imagegen
PY=${PY:-python3}   # 换成你的解释器（WorkBuddy 内置解释器带齐 numpy/PIL/cv2）

$PY "$SKILL/scripts/postcheck.py" a.png --track A --top --text ok
$PY "$SKILL/scripts/postcheck.py" a.png --track E --expect-cells 9 --text ok   # 类型 E 校格数
$PY "$SKILL/scripts/measure.py" --grid /tmp/grid.png *.png                     # 单独出对比拼图
```

判定阈值（**全五类**；此前只有 A/B 两列，C/D/E 缺）：

判据分三层：**blocker**（真错，允许一次定向重生）、**pending**（能免费修或待核对，
不得计 pass）、**诊断**（只报数不判）。判完之后每行都带 `[reason]` / `[hint]` 码，
同时写进 `runs.csv` 的 `reason` / `hint` 两列——这样「这张图为什么没通过」可以直接统计。

| 指标 | 类型 A 海报 | 类型 B 群像 | 类型 C 包装 | 类型 D 分镜 | 类型 E 多格 | 说明 |
|---|---|---|---|---|---|---|
| `R-B`（留白区 R 减 B） | 仅当 `base≥240`（本该是白）才判 → 走 **pending + `paper_white.py`**，**不判 blocker** | 同 A | **不适用** | **叙事性暖色豁免** | — | 纸底/纹理底的暖色是材质色。202 张成品实测：纯白底子集触发 3.6%，纸底子集 63% |
| `paper_warm_hint` | `base<240` 且 R-B≥3 时只提示 | 同 A | — | — | — | 可跑 `paper_white.py` 更中性，但不是缺陷 |
| `sat`（平均饱和度） | 依风格 | **> 70 判 blocker** | — | — | — | 成品触发 3.0%，是唯一保留的配色 blocker |
| `top_dev` / `top_zone%` | **仅诊断，不判 blocker** | — | — | — | — | 成品触发 64.9%，属「风格母题 vs 留白禁令」张力（pitfalls 待解决表） |
| `top_noise`（顶部 stddev） | **仅诊断** | — | — | — | — | 纸纹/网点把 std 顶到 30+，13/13 张真实海报越线（坑 27） |
| `white%`（min(RGB)>240） | — | **不再判 blocker** | — | — | — | 纸底图上恒为 0，成品触发 82.2%；留白改用 `near%<40`（且 `base≥200`）只提示 |
| **尺寸** | — | — | — | **必须 1024x1792** | — | D 是声明值（storyboard.md §五），不符即 blocker |
| **格数** | — | — | — | — | **需 `--expect-cells`** | 格数是硬判据；等比例与净空为诊断值（`evidence.md` §2） |

> 阈值不是拍出来的：每条 blocker 的**触发率**都在 202 张已归档成品上实测过，
> 数据与复算命令见 `sub-skills/verify/evidence.md` §4（复算：
> `python3 scripts/calibrate_thresholds.py ~/Pictures/WorkBuddy`）。改判据先跑它。

**水印**：`postcheck.py` 默认 `--wm auto`——先识别，命中才动手，去后复检；
干净图不被无条件动刀。三分支与双条件闸门见子技能 §3。
`--dewm` 等价 `--wm force`（保留旧参数），`--wm off` 关闭。
**但平台署名水印（右下角「AI生成 / WORKBUDDY」）不在这三条分支内**：它会被判成
`[wm_texture] 纹理误报，不拦交付`，因而既不拦、也不去。它的处置是
`scripts/dewm_imprint.py`（须同系列多张一起跑）——判据与两条实测教训见坑 36。
**`dewm` 报 `conf<0.1` / `k̂≈0` 是它在说「这张图我解不了」——不要 `--no-guard` 硬解，
也不要改用手工 inpaint 硬框**：背景是深色实色块 + 高频纹理（或水印跨材质）时，
这两条路都会把整块抹平并啃掉邻接文字；应改用**分材质填充**（坑 35）。

**泛黄/纸白偏暖**（坑 33）：母题是纸/绢/墙面的白底图（类型 A 常见）会被模型当材质色渲染，
`R-B` 稳定偏暖且**提示词压不下来**。postcheck 给 `[paper_warm]` + **pending**，
处置是跑 `scripts/paper_white.py`（免费、只动纸白像素）——**重生改不了这个偏色**，只会再扣 5–10 积分。
**`top_noise` 是诊断值不是 blocker**（坑 27：阈值 6 在 13/13 张真实海报上全触发过，
判它等于每张白扣一次重生）；要看顶部是否真被画脏，用 `top_lf_std`/`top_dark%` + 目检裁片。

---

## 6. 云端后处理（可选项，先建议后启用）

> **完整编排与调用纪律见 `references/cloud-postprocess.md`**（触发：云端修复、后处理、抠图、
> 去疑难水印、修老照片）。本节只留判据——要真正调用时以该文件为准。

- **定位：可选项，不默认启用。** 与重生并列的另一条补救路；默认路径仍是三档评审的原结论
  （可修不重生、blocker 定向重生）。**绝不由 Agent 静默发起。**
- **授权边界**：用户主动要求修图/增强/抠图视为已授权；Agent 评审后建议的，**必须获用户同意**。
  建议话术说清三点：① 修什么（哪个操作、动画面哪一块）；② 代价（重生=再扣 5–10 积分且已验收部分
  作废；云端只动指定区域，但**计费口径未实测**）；③ 无论走哪条，**修完都要重新过 `postcheck.py`**。
- **去水印双路由**：本技能 ImageGen 出的图走本地 `dewm*`（免费、逐位保护画面）；外来图 / 水印压
  复杂图形 / dewm 全族救不回 → 官方 `erase` 云端重绘（**目标区域周边会被重画，调用前必须告知**）。


## 7. 跨类型硬规则（五条）

1. **纸底/背景不接受色相词**：`warm / aged / faded / unbleached / vintage` 在图像模型里是**强色相指令**，
   想要质感只能用纹理词（`fibre grain / laid lines / halftone / tooth / deckle`）。写了 `warm` 必泛黄。
2. **数值只用在防翻车项**：背景色、文字三级比例、交叠面积、强调色占比、顶部留白 → 可以锁。
   主体大小、尺度反差倍数、位置疏密 → **必须留模糊**，锁死就变僵（v3 的教训）。
3. **面积/密度百分比对模型基本无效**：想控制"留白 1/3""低密度"，要换成**可数约束**
   （角色数量下限、最大角色 ≤ 画幅 1/4、小角色 ≥ 1/12）+ 正向描述（"不规则云团分布、禁水平对齐"）。
4. **路径名先 `find` 再引用**：归档脚本会把连续下划线规范化成单个
   （`A_vertical_2_3_poster__Visual__` → `A_vertical_2_3_poster_Visual`），凭记忆拼路径必 404。
5. **元信息与内容物理分离**：权重标注（`= 100`）、比例说明不要和文案连写，
   否则约 50% 概率被原样画进画面（写法已并入 v5.4 模板三组文案段与硬底线，验证细节在 poster-v5-history.md）。

---

## 8. 参考文件与脚本索引

**文件分层**：出图只碰 scripts；references 按第 4 节场景表按需读。
本表只答「何时用哪个」；**判据语义、算法细节与实测依据的真源在各文件 docstring 与对应文档里**，这里不再重复。

| 文件 | 何时用 |
|---|---|
| `references/poster-v5.md` | 类型 A 操作层：v5.4 模板全文、三个段落级变体（§一·乙 主标题穿插 / §一·丙 横版 16:9 两级文字 / §一·丁 图形规则系统型）、填空规则、满铺/孤置（§五）、已验证风格三库（§六/§六·乙/§六·戊） |
| `references/poster-v5-history.md` | 追溯模板为什么长这样（v1→v5.4 演进与验证详情，出图不读） |
| `references/crowd-illustration.md` | 类型 B 方法层：元提示词、可数约束、实测结论 |
| `references/crowd-themes.md` | 类型 B 主题一~五完整正负向提示词（36KB，**禁止整读**，fill_meta 按主题提取） |
| `references/packaging-editorial.md` | 类型 C 方法层：包装 Mockup 中文元模板（【】槽位）+ 槽位表 + 硬规则 |
| `references/storyboard.md` | 类型 D 方法层：双 LOCK 一致性锚 + 9 帧镜头设计法（1024x1792，必须串行出图） |
| `references/multigrid-layout.md` | 类型 E 方法层：多格排版元模板 + 硬规则（一致性锚必填、清单全给或全不给、防样机收口） |
| `references/size-and-params.md` | 全部参数、尺寸实测原始数据、画幅选择指南、积分与 quality |
| `references/pitfalls.md` | 翻车了按症状查表（37 个坑，只读命中节）+ 待解决项 |
| `references/explore-mode.md` | 探索模式规则：单风格 2–5 / 多风格 5–9、分批 ≤3、settle 改名防撞名（坑 17） |
| `references/cloud-postprocess.md` | 云端后处理完整版（§6 的展开）：操作映射、去水印双路由、官方六条纪律 |
| `references/jimeng-env.md` | 豆包/即梦适配完整版（§9 的展开）：适配边界表、S0–S6 平台检测信号链 |
| `references/countable-constraint-test.md` | 可数约束修正的完整实测记录与提示词全文（类型 B 低密度修复） |
| `references/crowd-100-faces-prompt-v1.md` / `references/crowd-100-faces-prompt-v2.md` | 主题五高密度百相图 v1/v2 完整提示词（脸复制/年龄配额修复实验） |
| `scripts/fill_meta.py` | **机械填槽出稿（默认入口）**：A/B/C/E 全走它，组装完自动过 preflight；`--list` 查槽位/主题，`--manpu` 切满铺型 |
| `scripts/jimeng.py` | 豆包/即梦环境出稿：只换算尺寸，prompt 与 fill_meta 逐字节一致；`--sizes` 查尺寸 |
| `scripts/test_jimeng.py` | jimeng.py 回归测试（43 项，不依赖 numpy/PIL），已并入 run_tests.sh |
| `scripts/preflight.py` | 手写提示词时单独跑的出图前静态检查（37 个坑中 11 个可文本拦截 + 残留槽位，认 {} 与【】）；fill_meta 已内嵌 |
| `scripts/postcheck.py` | **出图后一次调用（默认入口）**：量测+文字带 2x 裁片+水印自动识别+runs.csv 记账；`--track A–E`，类型 E 加 `--expect-cells N`；verdict 三值 blocker/pending/pass = 退出码 1/3/0 |
| `scripts/measure.py` | 单独量测 / `--grid` 出对比拼图；`grid_metrics()` 是类型 E 网格结构判定 |
| `scripts/wm_auto.py` | 水印自动识别与条件去除：amp 与 R² 双条件闸门 → skip/remove/manual；默认只探测，`--remove` 才执行；实测依据见 evidence.md §1 |
| `scripts/dewm_v10.py` | **默认单版去水印**：v9 管线 + 平底自适应融合（`--no-fuse` 关）+ 可解性门控（`--no-guard` 关，坑 26） |
| `scripts/dewm_imprint.py` | **平台署名水印**（右下角「AI生成 / WORKBUDDY」）：dewm 全族对它必报「解不了」、rmwm_light 掩膜退化为 100%，故单开本脚本，**须 N 张同系列一起跑**（坑 36） |
| `scripts/dewm.py` / `dewm_v7.py` / `dewm_v8.py` / `dewm_v9.py` | 手动单选旧版（v6 反解 / v7 inpaint / v8 自适应 / v9 锚点对齐）；同时是 pick_wm 的候选池 |
| `scripts/dewm_v11.py` / `dewm_v12.py` | 疑难可选（暗区白残留 / 水印挪位），实测整体劣于 v10，非默认 |
| `scripts/dewm_v13.py` | **实验候选，未并入选版池**：Wiener 融合；若启用走 conf 门控路由，不要改 σ（坑 32） |
| `scripts/dewm2.py` | Qwen 版无模板去水印（未知版式；纹理区残留是短板），坑 21 实测归档 |
| `scripts/pick_wm.py` | 疑难图入口：v6–v9 四版按「残留+结构损伤」选优，输出 `_clean/` 绝不覆盖原图（坑 28/29） |
| `scripts/audit_wm.py` | 去水印质量审计（残留 + `--ref` 结构损伤 + 三联目检图，坑 30） |
| `scripts/dewm_io.py` | 去水印共享 IO 层：覆盖守卫（默认落 `_clean/`）+ 中文路径安全读写 |
| `scripts/rmwm_light.py` | 亮字水印修复（亮暗通吃；**含文字的图会啃笔画，首选 dewm_v10**，坑 34）。带**覆盖率守卫**（掩膜 >40% 或 ROI 越界即拒绝写出，坑 35）；用前先 `--check` 看覆盖率 |
| `scripts/rmwm.py` | 暗字水印 inpaint（水印压复杂图形时比反解优），仅作补充对照 |
| `scripts/metric_flat.py` | 平底残影 RMS（amp 判 CLEAN 但目视有痕时用，坑 22） |
| `scripts/paper_white.py` | **纸白归正 + 背景去斑**（坑 33，确定性免费）：白底图 R-B≥3 先跑它再考虑重生，`--dry-run` 只看报告 |
| `scripts/_env.py` | 依赖自检底座：**缺 numpy/PIL/cv2 时说人话**（打印缺哪个包 + 两条可执行修复路径）并以退出码 2 结束；23 个入口脚本的重型 import 都包它。用户看到「❌ 依赖不可用」时，报错就来自这里 |
| `scripts/_log.py` | 本地使用日志：每次脚本调用记一行 `scripts/logs/usage.jsonl`（谁被调用、退出码、耗时、宿主）；只落本地、不进发布仓、写失败静默跳过 |
| `scripts/log_report.py` | **读使用日志出「下一步该改什么」**：脚本调用频次 / 失败率 / 耗时 p50·p95 / 环境画像 / 从没被调用过的脚本 / runs.csv 高频码。改文档前先看它 |
| `scripts/bench_dewm_align.py` | 改去水印代码必跑的合成基准（`bench_dewm.py` / `probe_k_bias.py` 同）：`TAXUE_BENCH_IMGS="a.png:b.png" python3 …` |
| `scripts/explore.py` | 探索模式：CSV 驱动批量出稿 + settle 改名校对 |
| `scripts/build_storyboard.py` | 类型 D 出稿：改 SCENES 生成 9 条 prompt（`build_storyboard_ink.py` 是旧命令转发壳） |
| `scripts/calibrate_thresholds.py` | 换模型 / 改判据前先跑：用已归档成品重算各判据触发率 |
| `scripts/test_regressions.py` | 断言式回归测试入口（断言本体按域拆在 `scripts/tests/`）：`python3 scripts/test_regressions.py` |
| `scripts/run_tests.sh` | 总测试门禁（导入 / front-matter / preflight 冒烟 / 回归 / 关键文件 / 发布资产 / 隐私 / 发布守卫），本地与 CI 共用 |
| `.github/workflows/validate.yml` | CI：装 numpy+pillow+opencv（见 `scripts/requirements.txt`）后跑 `bash scripts/run_tests.sh` |
| `sub-skills/verify/SKILL.md` | **出图验收子技能**：三档评审口径 / 水印自动政策 / 缺陷修复路由 / 各类型验收重点 |
| `sub-skills/verify/evidence.md` | 验收阈值的**实测依据与样本量**（水印双条件闸门 n=14 两组分布、类型 E 网格合成基准；改阈值先读它） |

---

## 9. 豆包/即梦环境适配（jimeng.py）

> **完整适配边界、尺寸表与平台检测信号链见 `references/jimeng-env.md`**（触发：在豆包/即梦里跑本技能）。

`scripts/jimeng.py` **唯一职责是换算出图尺寸**（即梦 2K，`--sizes` 可查）：prompt 与 `fill_meta.py`
输出**逐字节一致，一个字不改**；参数原样透传，`--platform workbuddy` 切回原行为。换背景色 / 满铺 /
模板变体走 fill_meta 正规槽位与 `--manpu`——**「换了运行环境或模型」本身不构成改动模板的理由**。
preflight 报告**原样透传**（不过滤、不吞），由 Agent 按即梦实测判断。
