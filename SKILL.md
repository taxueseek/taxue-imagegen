---
name: taxue-imagegen
version: 1.9.0
updated: 2026-09-08
agent_created: true
description: >-
  WorkBuddy 专属生图 Skill（仅在 WorkBuddy 内运行：出图走 WorkBuddy ImageGen，填槽与验收由 Agent
  调用 scripts/*.py 完成；同系列另三个技能为通用技能，不绑平台/模型/Agent）。
  基准模型 hunyuan-image——全部硬底线与验收阈值在它上面实测；其它模型原则上可用，换模型须重校阈值。
  积分：单张约 5-10，每轮改进=一次全新出图=再扣一次，多轮打磨消耗大须先告知。
  元提示词库 + 出图工作流，三条赛道——赛道 A 竖版概念海报（v5.4，
  管图文关系与尺度反差）、赛道 B 手绘群像插画（管多角色差异化，可数约束已并入主模板）、
  赛道 C 写实包装 Mockup（棚拍实物做底 + 编辑风单色专色版面，v1.9 新增）。
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
  v1.9 新增赛道 C「写实包装 Mockup」：棚拍实物做底 + 编辑风单色专色版面 +
  单一隐喻图形 AM 网点 + 巨型堆叠品牌字，中文元模板槽位化
  （references/packaging-editorial.md，三轮实测 r3 4/4 文字逐字全对）。
  触发：生图、出图、生成图片、画一张、海报、概念海报、封面、KV、专辑封面、插画、群像、图鉴、角色设定、
  元提示词、ImageGen、画幅比例怎么选、去水印、水印、rmwm、fill_meta、postcheck、
  产品包装、包装图、mockup、包装样机。
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

三条赛道。**先选赛道，再填空**，别混用。
赛道 A 管的是「一个主体 + 三组文字」的图文关系，赛道 B 管的是「N 个角色各自成立」的差异化，
赛道 C 管的是「棚拍实物 + 编辑风专色版面」的包装样机。

---

## 0. 出图前三件事（不可跳）

1. **先报积分**：ImageGen 单张约 5–10 积分。出图前必须在回复里说清这次预计消耗（N 张 × 5–10），批量出图（≥5 张）先确认。**改进同样计费**——「看图 → 调提示词 → 重出」每一轮都是一次全新出图；用户要求多轮打磨时，先说清累计消耗（如 3 轮 × 2 张 ≈ 30–60 积分），并建议把修改点攒成一轮。
2. **先定画幅**：尺寸定错 = 重出 = 双倍积分。按第 2 节选，别凭感觉。
3. **先预检**：`scripts/preflight.py` 能在出图前拦下色相词、面积百分比、元信息混入文案等已知翻车项——预检不花积分。

---

## 1. 赛道路由

| 你要什么 | 走哪条 | 打开 |
|---|---|---|
| 概念海报 / 展览 KV / 专辑封面 / 书籍封面 / 电影氛围海报 / 杂志专题 | **A · 竖版概念海报** | 出稿 `scripts/fill_meta.py A`（默认）；理解规则才读 `references/poster-v5.md` |
| 写实产品包装 mockup（棚拍实物 + 编辑风单色油墨版面 + 半调隐喻图形，品牌字堆叠） | **C · 包装 Mockup** | 出稿读 `references/packaging-editorial.md` §一 模板填槽；理解规则读 §二/§三 |
| 多角色插画 / 动物图鉴 / 角色群像 / 旅行团 / 手账式群像 | **B · 手绘群像** | 出稿 `scripts/fill_meta.py B --theme`（默认）；理解规则才读 `references/crowd-illustration.md` |
| 拿不准 | 问一句：画面主体是**一个**还是**一群**？一个→A，一群→B | — |
| **探索模式**（多风格扫描 / 单风格打磨，N=2–9） | **Explore** | `scripts/explore.py build <csv> _prompts/` 出稿 + manifest → 分批出图 ≤3/批 → `explore.py settle` 改名校对；规则详见 `references/explore-mode.md` |
| 出图后要验收 | `scripts/measure.py` / `scripts/postcheck.py` | 见第 4 节 |
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
| **2:3 竖** | `1024x1536` | ✅ 主力，历史 46 张 | 概念海报、专辑/唱片封面、书籍封面 —— 两条赛道的默认输出 |
| **3:4 竖** | `1152x1536` | ✅ 本轮实测 | 稍宽的竖版、社媒长图 |
| **4:5 竖** | `1024x1280` | ✅ 本轮实测 | 小红书、社媒九宫格（顶部留白要从 25% 提到 35%） |
| **1:1 方** | `1024x1024` | ✅ 本轮实测 | 头像、方形封面、社媒卡片 |
| **3:2 横** | `1536x1024` | ✅ 本轮实测 | 横版 banner、PPT 背景（尺度反差在横幅里会失效） |

> ⚠️ **没有精确 16:9**。横版取 `1536x1024`（3:2）再后期裁；别指望靠 `size` 拿到 1920x1080。

---

## 3. 通用工作流

**两种模式，先分清再动手**（返工的最大来源是把生产当探索跑）：

- **生产模式（默认）**：赛道与模板已成熟 + 目标是产出成品 → fill_meta 填槽 → preflight 通过 → **只出 1 张** → 三档评审 → 成品或一次定向修复。
- **探索模式（仅新主题/新风格/模板迭代；详见 `references/explore-mode.md`）**：N 张同主题/多主题的横向采样；用 `scripts/explore.py` 批量化出稿 + settle 改名 + 验收 + 结论回写。探索结论合并进模板后，同类需求永久转为生产模式。

**生产配额：默认 1 张。** 禁止先出草稿再出成品；禁止为「对比」再出一张；仅 blocker 允许一次定向重生，只改一项。
**探索配额：单风格 2–5 / 多风格扫描 5–9。** 出图分批 ≤ 3/批，每批立即 `ls` 核对 + `explore.py settle` 改名锁定（防同秒时间戳撞名，坑 17）。

| 步 | 做什么 | 要点 |
|---|---|---|
| 1 | 定赛道 + 定尺寸 | 一次定死，中途别改 |
| 2 | **机械出稿（默认）** | 赛道 A：`fill_meta.py A --set 视觉风格=… --set 内容主题=… --set 表达意图=… --set 主体形象=… --set 英文主标题=… --set '中文短句=…' --set '英文短句=…' [--manpu]`——脚本从 v5.4 模板精确组装，逐字声明与词数自动推导，标点前置校验，组装完自动过 preflight。赛道 B：`fill_meta.py B --theme 鸟|猫|狗|合影|休息|前行|百相`。**脚本已含全部验证过的禁令，LLM 不重抄模板**；模板没覆盖的新需求才手写（语种：B 必须英文，A 中文场景用中文，见坑 12），手写完单独跑 preflight |
| 3 | 报积分 → 出图 | 生产模式出 1 张；确需多张的**并行发起**，不要串行等；同主题多张时，三组文案/主体描述只写一次共享，各张只改构图与画幅 |
| 4 | **postcheck 一次调用验收** | `postcheck.py 图.png --track A --top --dewm --text ok --note '版本/场景'`——量测 + 底部文字带 2x 裁片（替代手动裁剪放大）+ 去水印（v1.8 起 `--dewm` 走 `dewm_v10.py`：wm=α·255+(1-α)·orig 解析反解 + 平底自适应融合，只减不猜，31ms；输出行带 `flat=Y/N(std=)` 一眼看出走没走融合）+ runs.csv 记账，全程 <0.5s。三档评审卡：**blocker**（泛黄 R-B≥3 / top_noise≥6 / 顶部被侵入 / 缺字错字 / 主标题重复）才允许一次定向重生只改一项；**可修**（细节软、小构图偏差）不重生；**通过** = 指标在阈值内 + 文字逐字无误。修复纪律：只改所属那一段指令，禁止堆第二波禁令（坑 12）；精确文字两轮仍错 → 后期排版补字，不假装正确、不同词重试。v10 后仍有残留（亮字水印/压复杂图形）→ `pick_wm.py` 四版自动选最佳，输出到 `_clean/`（**不覆盖原图**，A/B 对比可回溯）。**注意 amp 判 CLEAN 不代表目视干净**：平色底上的字形残影 amp 抓不到（R²≈0 被当纹理放过），目视有痕时用 `metric_flat.py` 量平底残影 RMS（坑 22） |
| 5 | 内联展示 | 用 `show_widget` 让用户在对话里直接看到，别只给路径 |
| 6 | 归档 | `cd ~/Pictures/WorkBuddy && python3 _tools/sync_images.py --apply`；**只归档成品**，中途产物留会话目录或子目录隔离（坑 13 教训④） |
| 7 | 记录 | 翻车/新结论写回 `references/pitfalls.md`；运行数据由 postcheck 自动写入 `scripts/logs/runs.csv`（模板调优的数据反馈闭环）；**验证过的修复当场回写主模板**（poster-v5.md §一 或 fill_meta 对应解析逻辑） |

---

## 3½. 加载协议（省 Token，按需读，一次并行读完）

本技能参考文件按「出图不需要、排查才需要」分层。**下表命中多个文件时一次并行读完，禁止逐个串行等，禁止整读大文件**：

| 场景 | 必读 | 不读 |
|---|---|---|
| 赛道 A 快速出图 | 本文件 + fill_meta 输出 + postcheck 输出 | poster-v5.md、pitfalls.md、历史文件 |
| 赛道 A 满铺/穿插变体、改硬底线 | `poster-v5.md` §一/§一·乙/§五 | 版本历史（在 history 文件） |
| 赛道 B 快速出图 | 本文件 + fill_meta 输出 + postcheck 输出 | crowd-illustration.md、crowd-themes.md、pitfalls.md |
| 赛道 B 自定义主题 | `crowd-illustration.md` §一 元提示词 | 主题库整读 |
| 赛道 C 快速出图 | 本文件 + `packaging-editorial.md` §一 模板 + §二 槽位表 | §三 只在翻车/新形态时读 |
| 查某个坑的修复写法 | `pitfalls.md` 对应小节 | 其余坑节 |
| 选画幅/参数细节 | 本文件 §2 不够时读 `size-and-params.md` | — |
| 追溯模板为什么长这样 / 复盘 runs.csv 调模板 | `poster-v5-history.md` / `countable-constraint-test.md` / `scripts/logs/runs.csv` | — |

---

## 4. 出图后验收（measure.py）

```bash
PY=/Users/taxuexunxian/.workbuddy/binaries/python/envs/default/bin/python
$PY ~/.workbuddy/skills/taxue-imagegen/scripts/measure.py a.png b.png c.png
$PY .../measure.py --top poster.png            # 加测顶部 25% 留白（赛道 A 必用）
$PY .../measure.py --grid /tmp/grid.png *.png  # 同时拼一张对比图
```

判定阈值：

| 指标 | 赛道 A 海报 | 赛道 B 群像 | 说明 |
|---|---|---|---|
| `white%`（min(RGB)>240） | 顶部 25% 区域应 >90% | 全图 30–65% | 群像低于 30% = 挤成一团 |
| `R-B`（白/留白区 R 减 B） | **< 3** | **< 3** | ≥3 就是泛黄前兆，≥6 已明显发黄 |
| `noise`（顶部区域 stddev） | < 6 | — | 高了说明留白被画成纹理/横幅 |
| `sat`（平均饱和度） | 依风格 | 20–60 | 群像超过 70 = 配色炸了 |

---

## 5. 跨赛道硬规则（五条）

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

## 6. 参考文件与脚本索引

**文件分层**：出图只碰 scripts；references 按第 3½ 节场景表按需读。

| 文件 | 内容 |
|---|---|
| `references/poster-v5.md` | 赛道 A 操作层：v5.4 模板全文（含全部已验证补丁）、穿插型变体（§一·乙）、填空规则、满铺/孤置二选一（§五）、九个已验证填空、场景适配 |
| `references/poster-v5-history.md` | 赛道 A 历史层：版本演进 v1→v5.4、v5 稳定性/九风格实测、v5.1/v5.2 验证详情（出图不读） |
| `references/crowd-illustration.md` | 赛道 B 方法层：元提示词（可数约束已并入）、实测结论、与赛道 A 对比（11KB） |
| `references/crowd-themes.md` | 赛道 B 主题库：主题一~五完整正负向提示词（36KB，**禁止整读**，fill_meta 按主题提取） |
| `references/packaging-editorial.md` | 赛道 C 方法层：写实包装 mockup 中文元模板 + 槽位表 + 硬规则（2026-09-08 三轮实测，r3 4/4 逐字全对） |
| `references/size-and-params.md` | ImageGen 全部参数、尺寸实测原始数据、画幅选择指南、积分与 quality |
| `references/pitfalls.md` | 已踩的坑（按症状速查，只读命中节）+ 待解决项 |
| `scripts/fill_meta.py` | **机械填槽出稿（默认入口）**：A 从 poster-v5.md §一 单一真源组装，{N}/逐字声明自动推导，标点前置校验，内嵌 preflight；B 按主题提取；`--manpu` 切满铺型；`--list` 查槽位/主题 |
| `scripts/postcheck.py` | **出图后一次调用（默认入口）**：量测（复用 measure）+ 底部文字带 2x 裁片 + dewm 反解去水印 + runs.csv 记账，<0.5s；三档评审卡的 verdict 自动判定 |
| `scripts/measure.py` | 白底占比 / 泛黄 / 饱和度 / 顶部留白（含 top_white%、纸底相对口径 top_zone%）检测 + 拼图（被 postcheck 复用，也可单独跑） |
| `scripts/preflight.py` | 出图前静态检查：15+ 坑可文本拦截项 + 残留槽位（fill_meta 已内嵌，手写提示词时单独跑） |
| `scripts/dewm.py` | 逆向 alpha 反解去水印 v6（白底图最优，0.2s/张；非白底会留红蓝噪点/残影） |
| `scripts/dewm_v7.py` | α 模板做 mask + cv2.inpaint 兜底（深色/金底/满铺图更稳，但纹理被抹平） |
| `scripts/dewm_v8.py` | 自适应反解 + k 拟合 + 物理边界守卫（低对比水印更干净，但在已平滑区会过拟合出鬼影） |
| `scripts/dewm_v9.py` | **v8 + 锚点对齐（当前最优单版，v9.1）**：三重评分（灰度 NCC+梯度 NCC+方差比）±28px×8 档尺度对齐，k̂ 下限 0（无水印自动 no-op）；conf 仅作对齐开关不作门控。合成基准 6 用例平均 PSNR 69.81 vs v8 44.49（坑 21） |
| `scripts/dewm2.py` | Qwen 版无模板去水印：逐像素向量投影 + RMS 校验门 + 彩度/亮度守卫（来源 .qwenworkcn）。适合未知版式水印；纹理区残留是短板（byzantine 18dB）。已在坑 21 实测归档 |
| `scripts/bench_dewm_align.py` | 去水印位置/尺度维合成基准（v6/v8/v9 三方 PSNR 对比 + 对齐精度验证），改去水印代码必跑 |
| `scripts/dewm_v10.py` | **当前最优单版（v1.8 起默认）**：v9 管线 + 平底自适应融合。检测水印框外紧邻带 std，<12 判平底 → 反解结果与 inpaint 背景按 α 斜坡融合（`--no-fuse` 关，=v9 行为；`--flat-thr` 调判据）。平底图 RMS 5.98→1.43，纹理图逐位不动（坑 22） |
| `scripts/pick_wm.py` | 疑难图入口——对每张图跑 v6/v7/v8/v9 四版，按残留签名分自动选最佳，输出到 `_clean/`（**绝不覆盖原图**）。注意：amp 签名分偏袒 v7 的过度平滑（坑 21 教训 4），选后必做视觉抽检；单版能解决时优先 `dewm_v10.py`，更快且可解释 |
| `scripts/audit_wm.py` | 残留审计（无原图也能用）：拟合当前图实际不透明度 k̂ + R² + amp，|amp|≥2.5 判 DIRTY；输出表格 + 三联目检图 |
| `scripts/dewm_io.py` | 去水印脚本共享 IO 层：覆盖守卫（默认落 `_clean/`，`--inplace` 显式才覆盖原图）+ 中文路径安全读写 |
| `scripts/rmwm_light.py` | 亮字水印修复（中值背景 + 双偏差掩膜 + Telea，亮暗通吃）；dewm 反解后残留时逐张补，输出永不覆盖原图 |
| `scripts/rmwm.py` | 暗字水印 inpaint（top-hat 掩膜）；水印压复杂图形时比反解更优，仅留作补充对照 |
| `references/countable-constraint-test.md` | 可数约束修正的完整实测记录与提示词全文（赛道 B 低密度修复） |
| `references/crowd-100-faces-prompt-v1.md` / `-v2.md` | 主题五高密度百相图 v1/v2 完整提示词（脸复制/年龄配额修复实验） |
