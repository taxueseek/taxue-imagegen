---
name: taxue-imagegen
version: 1.11.1
updated: 2026-09-09
agent_created: true
description: >-
  WorkBuddy 专属生图 Skill（仅在 WorkBuddy 内运行：出图走 WorkBuddy ImageGen，填槽与验收由 Agent
  调用 scripts/*.py 完成；同系列另三个技能为通用技能，不绑平台/模型/Agent）。
  基准模型 hunyuan-image——全部硬底线与验收阈值在它上面实测；其它模型原则上可用，换模型须重校阈值。
  积分：单张约 5-10，每轮改进=一次全新出图=再扣一次，多轮打磨消耗大须先告知。
  元提示词库 + 出图工作流，四种类型——类型 A 竖版概念海报（v5.4，
  管图文关系与尺度反差）、类型 B 手绘群像插画（管多角色差异化，可数约束已并入主模板）、
  类型 C 写实包装 Mockup（棚拍实物做底 + 编辑风单色专色版面，v1.9 新增）、
  类型 D 叙事分镜（漫剧切片，双 LOCK 一致性锚跨帧复现，v1.10 新增）。
  v1.5 借鉴 taxue-halftone 流水线：fill_meta.py 机械填槽（LLM 不重抄模板、逐字声明自动推导）、
  提示词库分层加载、三档评审卡 + 出图配额 1 张。
  v1.6 出图后一次调用 postcheck.py：量测 + 文字带目检裁片 + dewm 反解去水印 + runs.csv 记账，
  验收路径从 3-4 次工具往返压到 1 次，并建立模板调优的数据反馈闭环。
  v1.7 探索模式（explore.py + CSV 驱动）；去水印默认改 pick_wm 三版选最优（v6/v7/v8 各有擅长，
  实测 18 张原 v6 漏清/留噪点 5 张占 28%），所有 dewm 脚本接入 dewm_io 覆盖守卫（不覆盖原图）；
  新增 audit_wm 残留审计（无原图也能定位 DIRTY 张）。
  v1.8 新增 dewm_v10（v9 + 平底自适应融合）：修「平色底上肉眼可见的水印残影」——
  amp 判 CLEAN 但人眼仍有痕（形状失配，R² 掉 0 被当纹理放过），平底图上 v9 RMS 5.98
  → v10 1.43，纹理图逐位不动零回归。标准水印默认改 dewm_v10.py。
  v1.9 新增类型 C「写实包装 Mockup」：棚拍实物做底 + 编辑风单色专色版面 +
  单一隐喻图形 AM 网点 + 巨型堆叠品牌字，中文元模板槽位化
  （references/packaging-editorial.md，三轮实测 r3 4/4 文字逐字全对）。
  v1.10 新增类型 D「叙事分镜」+ 工具链打通：preflight/postcheck 支持 C/D，
  preflight 修词边界误报（managed/damaged 命中 aged 等）与【】槽位漏检，
  postcheck 增 pending 档（文字未核对不再计 pass），dewm_io 守卫堵大小写/硬链接绕过。
  v1.11 新增云端后处理层（第 6 节，**可选不默认**）：postcheck 判「指标在阈值内、
  但细节软/小构图偏差」的图可建议走官方内置
  buddy-image-processing（enhance/erase/restore/matting，编排不复制脚本），须先向用户建议
  （修什么/代价/计费未实测）并获同意才调用，绝不静默启用；新增去水印双路由
  （自家 ImageGen 图走 dewm 本地反解；外来图/水印压复杂图形/疑难图走官方 erase 云端重绘），
  并吸纳官方六条调用纪律：错误真实上报、提交状态未知不重提、用户修改指令原样进槽、
  后处理重新过 postcheck、计费口径实测前从严报消耗、可选项不默认启用。
  触发：生图、出图、生成图片、画一张、海报、概念海报、封面、KV、专辑封面、插画、群像、图鉴、角色设定、
  元提示词、ImageGen、画幅比例怎么选、去水印、水印、rmwm、fill_meta、postcheck、
  产品包装、包装图、mockup、包装样机、分镜、漫剧、绘本、连环画、storyboard、云端修复、后处理。
  注意：与生图链路无关的独立修图任务（外部照片美颜/老照片修复等）不接，路由到官方 buddy-image-processing。
---

# WorkBuddy 生图元提示词库

> **WorkBuddy 专属 Skill**：出图走 WorkBuddy 的 ImageGen，填槽与验收由 Agent 调用 `scripts/*.py` 完成。
> 同系列另三个技能（creative-style / halftone / solar-polaroid）是通用技能，不绑平台、模型或 Agent；
> **只有本技能绑定 WorkBuddy 运行时**——拿走提示词只拿到三分之一。
>
> **基准模型 hunyuan-image**：全部硬底线、比例与验收阈值都在 hunyuan-image 上实测得到，
> 用它效果与实测一致；其它模型（GPT Image 2 / Grok Imagine 2 / Nano Banana 2 / Seedream 5.0 Pro）
> 原则上可用，但换模型后必须重跑一张 + `postcheck.py` 校阈值，不要直接沿用这里的数字。
>
> **积分纪律**：单张约 5–10 积分，**每轮改进 = 一次全新出图 = 再扣一次**。
> 多轮打磨（3 轮 × 2 张 ≈ 30–60 积分）消耗很快，先定画幅 + 先 `preflight.py` 预检，把修改点一次说清。

四种类型。**先选类型，再填空**，别混用。
类型 A 管的是「一个主体 + 三组文字」的图文关系，类型 B 管的是「N 个角色各自成立」的差异化，
类型 C 管的是「棚拍实物 + 编辑风专色版面」的包装样机，类型 D 管的是「同角色跨帧一致 + 镜头叙事」的分镜切片。

---

## 0. 出图前三件事（不可跳）

1. **先报积分**：ImageGen 单张约 5–10 积分。出图前必须在回复里说清这次预计消耗（N 张 × 5–10），批量出图（≥5 张）先确认。**改进同样计费**——「看图 → 调提示词 → 重出」每一轮都是一次全新出图；用户要求多轮打磨时，先说清累计消耗（如 3 轮 × 2 张 ≈ 30–60 积分），并建议把修改点攒成一轮。云端后处理（第 6 节）计费口径未实测，首次实测前按「可能同样计费」从严报消耗。
2. **先定画幅**：尺寸定错 = 重出 = 双倍积分。按第 2 节选，别凭感觉。
3. **先预检**：`scripts/preflight.py` 能在出图前拦下色相词、面积百分比、元信息混入文案等已知翻车项——预检不花积分。

---

## 1. 类型路由

| 你要什么 | 走哪条 | 打开 |
|---|---|---|
| 概念海报 / 展览 KV / 专辑封面 / 书籍封面 / 电影氛围海报 / 杂志专题 | **A · 竖版概念海报** | 出稿 `scripts/fill_meta.py A`（默认）；理解规则才读 `references/poster-v5.md` |
| 写实产品包装 mockup（棚拍实物 + 编辑风单色油墨版面 + 半调隐喻图形，品牌字堆叠） | **C · 包装 Mockup** | 出稿 `scripts/fill_meta.py C --list` 查槽位后 `--set` 填齐（默认，17 槽自动组装 + 内嵌 preflight）；理解规则读 `references/packaging-editorial.md` §二/§三 |
| 多角色插画 / 动物图鉴 / 角色群像 / 旅行团 / 手账式群像 | **B · 手绘群像** | 出稿 `scripts/fill_meta.py B --theme`（默认）；理解规则才读 `references/crowd-illustration.md` |
| 叙事分镜 / 漫剧切片 / 绘本连环画 / 同角色多场景（N=6–9 帧连续叙事） | **D · 叙事分镜** | 出稿改 `scripts/build_storyboard.py` 的 SCENES 列表生成 9 条 prompt；**串行**出图逐张落地改名；规则详见 `references/storyboard.md`（双 LOCK 一致性锚） |
| 拿不准 | 问一句：画面主体是**一个**→A，**一群**→B，**多张连续叙事**→D | — |
| **探索模式**（多风格扫描 / 单风格打磨，N=2–9） | **Explore** | `scripts/explore.py build <csv> _prompts/` 出稿 + manifest → 分批出图 ≤3/批 → `explore.py settle` 改名校对；规则详见 `references/explore-mode.md` |
| 出图后要验收 | `scripts/measure.py` / `scripts/postcheck.py` | 见第 5 节 |
| 出图后要修图（增强 / 修破损 / 抠图换底 / 云端去疑难水印） | **云端后处理（可选）** | 见 第 6 节；用户点名直接走，Agent 评审建议须获同意，编排官方 buddy-image-processing |
| 出图前查提示词 | `scripts/preflight.py` | fill_meta 已内嵌；手写提示词时单独跑 |
| 要无水印的图 | `scripts/dewm_v10.py`（**默认单版**，v9 + 平底自适应融合）；疑难图 `scripts/pick_wm.py`（v6/v7/v8/v9 四版选优） | `dewm.py` / `dewm_v7.py` / `dewm_v8.py` / `dewm_v9.py` 仍是手动单选；`audit_wm.py` 只审计不修改；输出全部走 `_clean/` 不覆盖原图 |
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
| **4:7 竖** | `1024x1792` | ✅ 2026-09-08 分镜实测 | **类型 D 分镜指定尺寸**（漫剧原生比例，近似 9:16；精确 9:16 应为 1024x1820） |

> ⚠️ **没有精确 16:9**。横版取 `1536x1024`（3:2）再后期裁；竖版近似 9:16 用 `1024x1792`（4:7，差 0.9%），别指望靠 `size` 拿到 1920x1080。

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
| 2 | **机械出稿** | **A/B/C 走脚本（默认）**：类型 A `fill_meta.py A --set 视觉风格=… --set 内容主题=… --set 表达意图=… --set 主体形象=… --set 英文主标题=… --set '中文短句=…' --set '英文短句=…' [--manpu]`——从 v5.4 模板精确组装，逐字声明与词数自动推导，标点前置校验；类型 B `fill_meta.py B --theme 鸟\|猫\|狗\|合影\|休息\|前行\|百相`；类型 C `fill_meta.py C --list` 查 17 槽后 `--set` 填齐（【】槽位替换，单专色时 `--set '+色B='` 留空会自动清掉空括号）。三者组装完都自动过 preflight。**脚本已含全部验证过的禁令，LLM 不重抄模板**。**D 是半机械**：改 `build_storyboard.py --case cyber\|ink` 的 SCENES 生成 9 条，生成后单独跑 `preflight.py --track D`（跳过 A/B 专属规则）。模板没覆盖的新需求才手写（语种：B 必须英文，A 中文场景用中文，见坑 12），手写完单独跑 preflight |
| 3 | 报积分 → 出图 | 生产模式出 1 张；确需多张的**并行发起**，不要串行等；同主题多张时，三组文案/主体描述只写一次共享，各张只改构图与画幅 |
| 4 | **postcheck 一次调用验收** | `postcheck.py 图.png --track A --top --dewm --text ok --note '版本/场景'`——量测 + 底部文字带 2x 裁片（替代手动裁剪放大）+ 去水印（v1.8 起 `--dewm` 走 `dewm_v10.py`：wm=α·255+(1-α)·orig 解析反解 + 平底自适应融合，只减不猜，31ms；输出行带 `flat=Y/N(std=)` 一眼看出走没走融合）+ runs.csv 记账，全程 <0.5s。三档评审卡：**blocker**（泛黄 R-B≥3 / top_noise≥6 / 顶部被侵入 / 缺字错字 / 主标题重复）才允许一次定向重生只改一项；**可修**（指标在阈值内、仅细节软或小构图偏差）不重生，可按 第 6 节 向用户建议云端后处理（获同意后执行）；**通过** = 指标在阈值内 + 文字逐字无误。**注意三档是评审卡的判定口径，脚本 verdict 只有 blocker/pending/pass 三值**（pending = 文字未核对，未传 `--text` 时出现）；「可修」= 脚本判 pass 但目检有瑕疵，由 Agent 判定，不写进 runs.csv。修复纪律：只改所属那一段指令，禁止堆第二波禁令（坑 12）；精确文字两轮仍错 → 后期排版补字，不假装正确、不同词重试。v10 后仍有残留（亮字水印/压复杂图形）→ `pick_wm.py` 四版自动选最佳，输出到 `_clean/`（**不覆盖原图**，A/B 对比可回溯）。**注意 amp 判 CLEAN 不代表目视干净**：平色底上的字形残影 amp 抓不到（R²≈0 被当纹理放过），目视有痕时用 `metric_flat.py` 量平底残影 RMS（坑 22） |
| 5 | 内联展示 | 用 `show_widget` 让用户在对话里直接看到，别只给路径 |
| 6 | 归档 | `cd ~/Pictures/WorkBuddy && python3 _tools/sync_images.py --apply`；**只归档成品**，中途产物留会话目录或子目录隔离（坑 13 教训④） |
| 7 | 记录 | 翻车/新结论写回 `references/pitfalls.md`；运行数据由 postcheck 自动写入 `scripts/logs/runs.csv`（模板调优的数据反馈闭环）；**验证过的修复当场回写主模板**（poster-v5.md §一 或 fill_meta 对应解析逻辑） |

---

## 4. 加载协议（省 Token，按需读，一次并行读完）

本技能参考文件按「出图不需要、排查才需要」分层。**下表命中多个文件时一次并行读完，禁止逐个串行等，禁止整读大文件**：

| 场景 | 必读 | 不读 |
|---|---|---|
| 类型 A 快速出图 | 本文件 + fill_meta 输出 + postcheck 输出 | poster-v5.md、pitfalls.md、历史文件 |
| 类型 A 满铺/穿插变体、改硬底线 | `poster-v5.md` §一/§一·乙/§五 | 版本历史（在 history 文件） |
| 类型 B 快速出图 | 本文件 + fill_meta 输出 + postcheck 输出 | crowd-illustration.md、crowd-themes.md、pitfalls.md |
| 类型 B 自定义主题 | `crowd-illustration.md` §一 元提示词 | 主题库整读 |
| 类型 C 快速出图 | 本文件 + `packaging-editorial.md` §一 模板 + §二 槽位表 | §三 只在翻车/新形态时读 |
| 类型 D 快速出图 | 本文件 + `storyboard.md` §三 模板 + §四 镜头设计法 | §一/§二 定位与机制只在首次建 LOCK 时读 |
| 查某个坑的修复写法 | `pitfalls.md` 对应小节 | 其余坑节 |
| 选画幅/参数细节 | 本文件 §2 不够时读 `size-and-params.md` | — |
| 追溯模板为什么长这样 / 复盘 runs.csv 调模板 | `poster-v5-history.md` / `countable-constraint-test.md` / `scripts/logs/runs.csv` | — |

---

## 5. 出图后验收（measure.py）

```bash
PY=${PY:-python3}   # 换成你的解释器（WorkBuddy 内置：~/.workbuddy/binaries/python/envs/default/bin/python）
$PY ~/.workbuddy/skills/taxue-imagegen/scripts/measure.py a.png b.png c.png
$PY .../measure.py --top poster.png            # 加测顶部 25% 留白（类型 A 必用）
$PY .../measure.py --grid /tmp/grid.png *.png  # 同时拼一张对比图
```

判定阈值：

| 指标 | 类型 A 海报 | 类型 B 群像 | 说明 |
|---|---|---|---|
| `white%`（min(RGB)>240） | 顶部 25% 区域应 >90% | 全图 30–65% | 群像低于 30% = 挤成一团 |
| `R-B`（白/留白区 R 减 B） | **< 3** | **< 3** | ≥3 就是泛黄前兆，≥6 已明显发黄 |
| `top_noise`（顶部区域 stddev） | **仅诊断，不判 blocker** | — | 纸纹/网点把 std 顶到 30+，13/13 张真实海报全部越线，无区分力 |
| `top_lf_std` / `top_dark%` | 诊断用 | — | 高斯模糊 σ=9 去织纹后的低频结构；dark%≥40 才是「顶部被实体占满」 |
| `sat`（平均饱和度） | 依风格 | 20–60 | 群像超过 70 = 配色炸了 |

> **top_noise 的坑（2026-09-09 实测）**：阈值 6 曾在 13/13 张真实海报上全部触发
> （含已验收成品 `charming-girl-poster.png` = 50.1），属**假 blocker**——而 blocker
> 会触发一次定向重生，即再扣 5–10 积分。判「顶部是否真被画脏」改看
> `top_lf_std`/`top_dark%` + 目检裁片；`postcheck.py` 已同步把该阈值降级为诊断值。

---

## 6. 云端后处理（可选项，先建议后启用，v1.11）

> 接入 WorkBuddy 官方内置 skill `buddy-image-processing`（云端 API，异步任务，能力=对已有图片做
> erase 去水印/ enhance 增强 / beauty 美颜 / restore 修复 / matting 抠图，操作与模型映射固定）。
> **编排不复制**：本 skill 只写「何时路由过去」，脚本本体留在官方插件缓存目录随 App 升级自动更新，
> 调用规范（connect_cloud_service 取 token → 提交 → 轮询）以官方 SKILL.md 为准，禁止把官方脚本
> 复制进来，也禁止手拼其版本号路径。
> 与生图链路无关的独立修图任务（外部照片美颜/老照片修复等）不归本 skill，直接让官方 skill 接。

**定位：可选项，不默认启用。** 云端后处理与重生是两条并列的补救路，**默认路径仍是三档评审的
原结论**（可修不重生、维持现状；blocker 定向重生）。Agent 不得静默调用云端后处理，正确开启方式
是**先建议、后启用**——建议话术说清三件事，然后等用户同意：

1. 修什么（对应下表哪个操作）、预期动画面哪一块；
2. 代价对比：重生 = 一次全新出图再扣 5–10 积分且已验收部分作废；云端后处理只动指定区域/维度，
   但计费口径未实测（纪律 5），且 enhance/erase 的目标区域可能被重画；
3. 无论走哪条，修完都要重新过 postcheck（纪律 4）。

**授权边界**：用户主动要求修图/增强/抠图（触发词命中）视为已授权，直接走下表；
Agent 评审后主动建议的，必须获用户同意才调用。

| 诉求 | 走哪条 | 说明 |
|---|---|---|
| 细节软 / 分辨率不够 | 官方 `enhance` | 超分、降噪、去模糊、低光增强 |
| 去掉画面里的杂物文字/章戳（非 ImageGen 自带水印） | 官方 `erase` | 云端重绘，**目标区域周边会被重画**；ImageGen 自带水印仍走 dewm（本地反解，不动画面） |
| 老照片质感、破损、缺角、霉斑修复 | 官方 `restore` | |
| 抠主体 / 透明底 / 换背景 | 官方 `matting` + 合成 | **matting 只返回透明底前景**；白底/彩色底/替换背景是单独的合成步骤，绝不声称一步完成 |
| 人像美颜 | 官方 `beauty` | 海报/mockup/分镜场景基本用不上，列出仅为完整性 |

### 去水印双路由（撞词分流）

「去水印」两家都接，按图源分流：

- **本 skill ImageGen 出的图** → `dewm_v10.py` / `pick_wm.py`：本地反解，免费、快、逐位保护画面像素，永远第一优先。
- **外来图片、水印压复杂图形、dewm 全族 + rmwm_light 都救不回** → 官方 `erase`：云端重绘更强，
  但目标区域被重画，**调用前必须告知用户这个代价**。

### 调用纪律（吸纳自官方 skill 的行为约束）

1. **错误真实上报**：云端调用失败时返回实际报错（脱敏后），禁止伪造结果或文件路径。
2. **提交状态未知 ≠ 失败**：提交超时没拿到 task_id 时，明确报「提交状态未知」并停手，禁止自动重提
   （防重复扣费/重复任务）；拿到 task_id 后只查询原任务，认证过期就重新认证，不重新提交。
3. **用户修改指令原样进槽**：多轮打磨时用户的修改点原文传给 `--prompt` / fill_meta `--set`，
   不做美化扩写——与 fill_meta「LLM 不重抄模板」同一纪律，锁的都是 LLM 自由发挥。
4. **后处理不继承验收结论**：任何云端后处理过的图必须重新跑 `postcheck.py` 才算通过；
   enhance/erase 可能改变量测指标（白底占比、泛黄 R-B、顶部留白）。
5. **计费口径未实测**：官方 SKILL.md 未标积分。首次调用先拿一张废图实测扣费并把结果写回本节；
   实测前按「可能同样计费」从严执行第 0 节的报消耗纪律。
6. **可选项不默认启用**：Agent 永远不静默发起云端后处理；建议话术必含修什么/代价/计费未实测
   三点，用户同意后才调用（授权边界见本节开头）。

---

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

| 文件 | 内容 |
|---|---|
| `references/poster-v5.md` | 类型 A 操作层：v5.4 模板全文（含全部已验证补丁）、穿插型变体（§一·乙）、填空规则、满铺/孤置二选一（§五）、九个已验证填空、场景适配 |
| `references/poster-v5-history.md` | 类型 A 历史层：版本演进 v1→v5.4、v5 稳定性/九风格实测、v5.1/v5.2 验证详情（出图不读） |
| `references/crowd-illustration.md` | 类型 B 方法层：元提示词（可数约束已并入）、实测结论、与类型 A 对比（11KB） |
| `references/crowd-themes.md` | 类型 B 主题库：主题一~五完整正负向提示词（36KB，**禁止整读**，fill_meta 按主题提取） |
| `references/packaging-editorial.md` | 类型 C 方法层：写实包装 mockup 中文元模板 + 槽位表 + 硬规则（2026-09-08 三轮实测，r3 4/4 逐字全对）。模板用【】槽位，preflight 已支持拦截 |
| `references/storyboard.md` | 类型 D 方法层：双 LOCK 一致性锚 + 9 帧镜头设计法 + 实测参数（1024x1792；必须串行出图）。构建脚本 `build_storyboard.py --case cyber\|ink`（两案例共用 build()；`build_storyboard_ink.py` 仅为旧命令的转发壳） |
| `references/size-and-params.md` | ImageGen 全部参数、尺寸实测原始数据、画幅选择指南、积分与 quality |
| `references/pitfalls.md` | 已踩的坑（按症状速查，只读命中节）+ 待解决项 |
| `scripts/fill_meta.py` | **机械填槽出稿（默认入口）**：A 从 poster-v5.md §一 组装（{N}/逐字声明自动推导）；B 按主题提取；**C 从 packaging-editorial.md §一 组装（【】槽位，空括号自动清理）**；三者标点前置校验 + 内嵌 preflight。`--manpu` 切满铺型；`--list` 查槽位/主题 |
| `scripts/postcheck.py` | **出图后一次调用（默认入口）**：量测（复用 measure）+ 文字带 2x 裁片（A/C）+ dewm 反解去水印 + runs.csv 记账，<0.5s。`--track A\|B\|C\|D`；verdict 三档 blocker/pending/pass，退出码 1/3/0（pending=文字未核对，不算通过） |
| `scripts/measure.py` | 白底占比 / 泛黄 / 饱和度 / 顶部留白（含 top_white%、纸底相对口径 top_zone%）检测 + 拼图（被 postcheck 复用，也可单独跑） |
| `scripts/preflight.py` | 出图前静态检查：27 个坑中 11 个可文本拦截（坑 1/3/5/8/9/10/11/12/14/16 + 槽位）+ 残留槽位（认 {} 与【】两种）。`--track A\|B\|C\|D`，按类型切换适用规则；fill_meta 已内嵌 |
| `scripts/dewm.py` | 逆向 alpha 反解去水印 v6（白底图最优，0.2s/张；非白底会留红蓝噪点/残影） |
| `scripts/dewm_v7.py` | α 模板做 mask + cv2.inpaint 兜底（深色/金底/满铺图更稳，但纹理被抹平） |
| `scripts/dewm_v8.py` | 自适应反解 + k 拟合 + 物理边界守卫（低对比水印更干净，但在已平滑区会过拟合出鬼影） |
| `scripts/dewm_v9.py` | **v8 + 锚点对齐（当前最优单版，v9.1）**：三重评分（灰度 NCC+梯度 NCC+方差比）±28px×8 档尺度对齐，k̂ 下限 0（无水印自动 no-op）；conf 仅作对齐开关不作门控。合成基准 6 用例平均 PSNR 69.81 vs v8 44.49（坑 21） |
| `scripts/dewm2.py` | Qwen 版无模板去水印：逐像素向量投影 + RMS 校验门 + 彩度/亮度守卫（来源 .qwenworkcn）。适合未知版式水印；纹理区残留是短板（byzantine 18dB）。已在坑 21 实测归档 |
| `scripts/bench_dewm_align.py` | 去水印位置/尺度维合成基准（v6/v8/v9 三方 PSNR 对比 + 对齐精度验证），改去水印代码必跑。用法：`TAXUE_BENCH_IMGS="a.png:b.png" python3 scripts/bench_dewm_align.py`（`bench_dewm.py` / `probe_k_bias.py` 同） |
| `scripts/dewm_v10.py` | **当前默认单版（v1.8 起）**：v9 管线 + 平底自适应融合 + 可解性门控。检测水印框外紧邻带 std，<12 判平底 → 反解与 inpaint 背景按 α 斜坡融合（`--no-fuse` 关，=v9 行为）。**可解性门控（v1.10）**：可见度 `α·(C−背景)` 低于噪声门即判不可解、原图返回不硬解——近白底硬解会把噪声放大 1/(1−α) 倍，实测残差可降 39%（坑 26）；`--no-guard` 关 |
| `scripts/pick_wm.py` | 疑难图入口——对每张图跑 v6/v7/v8/v9 四版，按残留签名分自动选最佳，输出到 `_clean/`（**绝不覆盖原图**）。注意：amp 签名分偏袒 v7 的过度平滑（坑 21 教训 4），选后必做视觉抽检；单版能解决时优先 `dewm_v10.py`，更快且可解释 |
| `scripts/audit_wm.py` | 残留审计（无原图也能用）：拟合当前图实际不透明度 k̂ + R² + amp，|amp|≥2.5 判 DIRTY；输出表格 + 三联目检图 |
| `scripts/dewm_io.py` | 去水印脚本共享 IO 层：覆盖守卫（默认落 `_clean/`，`--inplace` 显式才覆盖原图）+ 中文路径安全读写 |
| `scripts/rmwm_light.py` | 亮字水印修复（中值背景 + 双偏差掩膜 + Telea，亮暗通吃）；dewm 反解后残留时逐张补，输出永不覆盖原图 |
| `scripts/rmwm.py` | 暗字水印 inpaint（top-hat 掩膜）；水印压复杂图形时比反解更优，仅留作补充对照 |
| `scripts/dewm_v11.py` / `dewm_v12.py` | **暗区/对齐疑难图可选**（非默认）：v11 加暗区迭代修「黑字上的白残留」，v12 加对齐空白守卫修「水印被挪到空白处、原处没处理」。实测整体劣于 v10，故默认仍 v10；仅当目视见暗区残留时手动切 v12 |
| `scripts/metric_flat.py` | 平底残影 RMS 计量（amp 判 CLEAN 但目视有痕时用，坑 22） |
| `scripts/dewm_v6_legacy.py` | 初版反解（白底图历史参照，已被 v10 取代；保留用于 A/B 回溯） |
| `scripts/test_regressions.py` | 断言式回归测试（每个断言对应一个已修缺陷，含 CLI `--help` 与真实进程退出码断言）。`python3 scripts/test_regressions.py` |
| `scripts/run_tests.sh` | 总测试门禁（导入检查 / front-matter / preflight 冒烟 / 回归 / 关键文件 / 发布资产 / 隐私扫描 / 发布守卫）。本地与 CI 共用同一套，避免「本地绿、CI 红」 |
| `.github/workflows/validate.yml` | CI：安装 numpy+pillow+opencv 后跑 `bash scripts/run_tests.sh` |
| `references/countable-constraint-test.md` | 可数约束修正的完整实测记录与提示词全文（类型 B 低密度修复） |
| `references/crowd-100-faces-prompt-v1.md` / `-v2.md` | 主题五高密度百相图 v1/v2 完整提示词（脸复制/年龄配额修复实验） |
