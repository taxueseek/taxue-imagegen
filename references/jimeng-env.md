# 豆包/即梦环境适配

> 本文是 `SKILL.md` §9 的完整版（2026-09-18 从 SKILL.md 拆出，逐字搬运）。
> SKILL.md §9 只留判据；**在豆包/即梦环境里跑本技能时以本文为准**。

# 豆包/即梦环境适配（jimeng.py）

> **唯一职责：只换算出图尺寸，不改动 prompt 一个字。**
>
> 模板与 fill_meta/preflight 是在 hunyuan 上验证过的资产，**"换了运行环境/模型"本身不构成改动模板内容的理由**。
> 因此适配层不重排/补删提示词、不过滤 preflight、不内建任何变体或换色改写；它只把比例映射成对应平台的像素尺寸。
>
> **正确迭代路径**：学好原版模板 → 忠实填槽出稿（保持原版效果）→ 实际出图发现问题再针对性调整 → 验证有效后才回头更新模板。
> 不在适配层做"预防性改写"——v1.x 曾内建穿插型替换、背景色正则改写、preflight 规则过滤，结果在深背景下凭空改出顶部白块，已全部移除。

### 9.1 哪些适配、哪些坚决不做

| 事项 | 适配层是否处理 | 正确路径 |
|---|---|---|
| **出图尺寸**（1K ↔ 2K） | ✅ **唯一处理**：按比例映射即梦像素，见 §2·乙 | `jimeng.py` 末尾 stderr 自动给出 width/height |
| 换背景色 | ❌ 不改写 | fill_meta **正规槽位** `--set 背景色=…`（默认明亮纯白） |
| 满铺型（删纯白+顶部留白） | ❌ 不改写 | fill_meta **原生开关** `--manpu`（poster-v5.md §五 硬底线二选一） |
| 穿插型等模板变体 | ❌ 不改写 | 按 `references/poster-v5.md §一·乙` 在**模板层面**定做 |
| preflight 坑11/坑16/槽位告警 | ❌ **不过滤、不吞掉**，原样透传 | Agent 看到报告后按即梦实测判断；确证不成立再走模板/preflight 迭代，而非适配层静默跳过 |
| 提示词文本 | ❌ 逐字节等同 fill_meta 输出 | 回归测试 `test_prompt_byte_identical` 锁死这一点 |

除 `--sizes / --debug-platform / --platform` 三个自有参数外，其余参数**全部原样透传**给 fill_meta（用 `parse_known_args`），fill_meta 以后加参数这里无需改动。

### 9.2 自动检测平台（分层信号链，只为决定用哪套尺寸）

一台机器可能**同时安装**豆包和 WorkBuddy（`~/.workbuddy` 与 `DoubaoWork` 都在），
"安装目录是否存在"只能说明装过、不能说明当前在哪个宿主里运行。检测用**运行时信号分层裁决**：

| 层级 | 信号 | 强度与说明 |
|---|---|---|
| **S0** 显式覆盖 | `--platform`；环境变量 `TAXUE_IMAGEGEN_PLATFORM` | 最高，CI/调试/强制切换 |
| **S1** 运行时环境变量 | 豆包注入整组 `DOUBAO_OFFICE_*`；WorkBuddy 注入 `WORKBUDDY_*`/`CODEBUDDY_*` | 最强，宿主主动注入，同层多数决 |
| **S2** 解释器路径 | `sys.executable`/`sys.prefix` 含 `DoubaoWork` 或 `.workbuddy` | 强 |
| **S3** 工作目录 | cwd 落在哪个宿主工作区 | 中（仓库可能放在对方目录下，单独不足定性） |
| **S4** PATH 片段 | 会话 PATH 含哪个宿主运行时路径 | 中 |
| **S5** 安装目录兜底 | 跨平台固定数据目录（macOS/Windows/Linux） | 最弱 |
| **S6** 默认 | 全无信号默认 **jimeng** | 本层主要服务豆包/即梦 |

从 S1→S5 逐层下沉，高层单一命中即定；同层多数决、平票下沉。指纹大小写不敏感、兼容命名变体。

- 证据链：`python3 scripts/jimeng.py --debug-platform`
- 强制：`--platform jimeng|workbuddy` 或 `TAXUE_IMAGEGEN_PLATFORM=...`
- WorkBuddy 下 `jimeng.py` 等价于直接跑 fill_meta（stdio 与退出码全透传，零适配）

### 9.3 用法

```bash
# 查即梦推荐尺寸
python3 scripts/jimeng.py --sizes

# 查类型 A 槽位（原样透传 fill_meta）
python3 scripts/jimeng.py A --list

# 标准出稿：prompt 与 fill_meta 逐字节一致，仅末尾追加即梦尺寸
python3 scripts/jimeng.py A \
  --set '视觉风格=浮世绘版画' \
  --set '内容主题=无常' \
  --set '表达意图=潮水退去后露出的木桩' \
  --set '主体形象=巨大木桩与远处鸟居' \
  --set '英文主标题=MUJO' \
  --set '中文短句=潮水退了' \
  --set '英文短句=the tide recedes' \
  --out /tmp/poster.txt
# → stderr 末尾给出 ratio=2:3  width=1664 height=2496（seedream_5.0_pro）

# 想要深/彩色背景：走 fill_meta 正规槽位，不是适配层改写
python3 scripts/jimeng.py A --set '背景色=深墨黑（dark ink black），不是浅灰' …
# 不想要顶部留白（满铺场景）：用 fill_meta 原生 --manpu
python3 scripts/jimeng.py A --manpu --set …

# 强制 WorkBuddy（等价直接跑 fill_meta，1K 尺寸 + 完整 preflight）
python3 scripts/jimeng.py A --set … --platform workbuddy
```

stdout 是 fill_meta 原样 prompt；stderr 是 fill_meta 原样 preflight 报告 + 适配层追加的即梦尺寸。退出码沿用 fill_meta（preflight 阻断时同样非 0，不掩盖）。

### 9.4 流程对比

| 步骤 | WorkBuddy | 豆包/即梦（jimeng.py） |
|---|---|---|
| 填槽出稿 | `fill_meta.py A --set …` | 同一命令，经 jimeng 透传，**prompt 逐字节不变** |
| 预检 | fill_meta 内嵌 preflight | **同一份报告原样呈现**，Agent 自行判断即梦适用性 |
| 尺寸 | §2 的 1K 表 | 唯一差异：映射到 §2·乙 的 2K 表 |
| 出图 | hunyuan-image | 即梦 `image_gen`（seedream_5.0_pro） |

### 9.5 已知边界（不属于适配层，按模板迭代流程处理）

1. **postcheck 阈值**：`measure.py`/`postcheck.py` 的泛黄 R-B、留白占比、饱和度阈值在 hunyuan 上实测，即梦需出 5–10 张重新标定；这是模板/验收层的事，不在适配层做。
2. **去水印脚本不适用**：`dewm_v10.py` 等针对 WorkBuddy 水印格式，即梦无此水印，不需要跑。
3. **计费口径**：WorkBuddy 与即梦 5.0 Pro 的积分/计费不同，以各自平台为准，本层不假设。
4. **测试**：`scripts/test_jimeng.py`（43 项，含"prompt 逐字节一致""已无任何改写函数"两条核心保证），不依赖 numpy/PIL，已并入 `run_tests.sh` 第 4 步。
