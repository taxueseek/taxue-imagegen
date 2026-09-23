<p align="center">

![踏雪生图元提示词库：五种类型、四种工作流——把一句话做成稳定的封面、群像、包装样机、多格组图或分镜](./assets/readme/hero.png)

</p>

<p align="center">
  <a href="./README.en.md">English</a> ·
  <a href="#成图标本">成图</a> ·
  <a href="#五种类型">类型</a> ·
  <a href="#怎么工作">怎么工作</a> ·
  <a href="#开始使用">开始使用</a>
</p>

# 踏雪生图

五种类型、四种工作流——把一句话做成稳定的封面、群像、包装样机、多格组图或分镜。

[![Version](https://img.shields.io/badge/VERSION-1.21.0-2ea44f?style=flat-square&labelColor=333)](./CHANGELOG.md)

只在 [WorkBuddy](https://www.workbuddy.cn/docs/workbuddy/Overview) 里跑通。出图走它的 ImageGen，填槽和验收由脚本完成。同系列另外三个技能交的是提示词本身，复制到哪都能用；本技能交的是一条跑在 WorkBuddy 里的流水线。

硬底线和验收阈值都在 hunyuan-image 上实测。单张大约 5–10 积分，改一版等于再出一张。

## 生图技能家族

同属踏雪生图系列，先认门，再用对技能：

| 技能 | 一句话 | 仓库 |
|---|---|---|
| **踏雪创意风格**（影像风格引擎） | 14 个家族、77 个变体：按风格出图、改提示词、从零写、记住偏好 | [taxue-creative-style](https://github.com/taxueseek/taxue-creative-style) |
| **半调海报**（印刷质感引擎） | 12 种风格 + 2 个变体：一句话、一个主题或一张照片，做成印刷感封面 | [taxue-halftone](https://github.com/taxueseek/taxue-halftone) |
| **节气拍立得**（节气创作引擎） | 节气、节日、物候短句，推出有记忆点的海报、纸本档案与拍立得 | [taxue-solar-polaroid](https://github.com/taxueseek/taxue-solar-polaroid) |
| **踏雪生图**（元提示词库） | 五种类型 + 四种工作流 + 机械填槽 + 一次验收 | **你在这里** · WorkBuddy 专属 · [taxue-imagegen](https://github.com/taxueseek/taxue-imagegen) |

## 成图标本

类型 A 三张、类型 B 两张、类型 C 四张，都是本技能实际出图。点题名看原图。

![九张成图：水墨海报、穿插海报、字符点阵、犬种图鉴、旅行团、咖啡袋、精华瓶、饮料罐、天地盖硬盒](./assets/readme/types-grid.jpg)

<p align="center">
<a href="./examples/example-A-crane-ink.png">踏雪</a> ·
<a href="./examples/example-A-sheer-silk.png">SHEER</a> ·
<a href="./examples/example-A-char-matrix.png">字符点阵</a> ·
<a href="./examples/example-B-dog-lineup.png">犬种图鉴</a> ·
<a href="./examples/example-B-travelers.png">旅行团</a> ·
<a href="./examples/example-C-01-coffee-pouch.png">SLOW/ROAST</a> ·
<a href="./examples/example-C-02-glass-serum.png">PURE/ACTIVE</a> ·
<a href="./examples/example-C-03-beverage-can.png">BITTER/CITRUS</a> ·
<a href="./examples/example-C-04-lidded-box.png">SILENT/HOURS</a> ·
<a href="./examples/README.md">全部原图</a>
</p>

样张已去掉平台水印。版权见 [ASSET-LICENSE.md](./ASSET-LICENSE.md)。

## 五种类型

| 类型 | 你要什么 | 入口 |
|---|---|---|
| **A · 竖版概念海报** | 概念海报、展览 KV、专辑封面、书籍封面 | `scripts/fill_meta.py A` |
| **B · 手绘群像** | 多角色插画、动物图鉴、旅行团 | `scripts/fill_meta.py B --theme <主题>` |
| **C · 写实包装 Mockup** | 棚拍包装样机（咖啡袋 / 精华瓶 / 饮料罐 / 天地盖硬盒） | `scripts/fill_meta.py C` |
| **D · 叙事分镜** | 漫剧切片、绘本连环画、同角色多场景（6–9 帧） | `scripts/build_storyboard.py --case cyber\|ink` |
| **E · 多格排版** | 精灵图、系列海报、邮票组、表情包、角色设定表（每格都是独立成品，靠统一规格串成一组） | `scripts/fill_meta.py E --list` |

拿不准：画面主体是**一个**还是**一群**？一个 → A，一群 → B；要产品包装 → C；要连续叙事 → D；要**一组各自成立的成品**（精灵图 / 系列海报 / 邮票组）→ E。

## 四种工作流

| 工作流 | 什么时候用 | 关键纪律 |
|---|---|---|
| **生产模式**（默认） | 类型和模板已成熟，目标出成品 | 填槽 → 预检 → **只出 1 张** → 三档评审 |
| **探索模式** | 新主题、新风格、模板迭代 | `scripts/explore.py` 批量出稿；单风格 2–5 张、多风格 5–9 张 |
| **去水印** | 出图后右下角带「AI 生成 / WORKBUDDY」 | 默认 `scripts/dewm_v10.py`；输出落 `_clean/`，不覆盖原图。**平台署名**（横版渠道后贴的固定图案）不是平铺水印，`dewm` 全族对它必报 `k̂≈0`——改走 `scripts/dewm_imprint.py`，须同系列多张一起跑 |
| **验收** | 出图后闭环 | `scripts/postcheck.py` 量测 + 文字带裁片 + 去水印，一次调用 |

生产配额默认 1 张。禁止先出草稿再出成品。只有 blocker 才允许改一项重生。

## 怎么工作

<p align="center">
  <img src="./assets/readme/workflow.svg" width="100%" alt="从填槽到过关成图：选定类型、机械填槽、出图验收、过关才交">
</p>

核心不是写一句漂亮的话，是让模型每次都稳定出符合预期的图，翻车时能快速定位。做法是三件套：五种类型各管一种图文关系；脚本机械填槽，不重抄模板；出图后一次验收。

## 开始使用

前提：已安装 [WorkBuddy](https://www.workbuddy.cn/docs/workbuddy/Overview)。

```bash
npx skills add taxueseek/taxue-imagegen
```

只用 CLI 时再装依赖（WorkBuddy 会话内已就绪）：

```bash
pip install numpy pillow opencv-python-headless
```

装好后在 WorkBuddy 里直接说，例如：

- 「用类型 A 做一张 2:3 概念海报，视觉风格浮世绘、主题无常、英文标题 WAITING」
- 「类型 B 来一张满铺犬种图鉴」
- 「类型 C 来一张磨砂精华瓶的纸盒包装，色用深靛蓝」
- 「把 explore_sample.csv 跑一遍探索模式」

也可以输入 `/taxue-imagegen` 触发。默认只出 1 张。想批量探索，明说「探索模式 N 张」。

说「再改一版」= 再出一张 = 再扣一次积分。修改点一次说清，比分五次微调省得多。

## 积分消耗

出图按张计费：

| 场景 | 估算 |
|---|---|
| 生产模式出 1 张 | 5–10 积分 |
| 探索模式跑 6 张 | 30–60 积分 |
| 一轮改进（看图 → 改提示词 → 重出 1 张） | 再 5–10 积分 |

省积分的三步：先定画幅；先跑 `preflight.py`；把几处问题攒成一轮改完。批量出图（≥5 张）会先跟你确认。

## 适合做什么

- **海报**：活动、展览、概念海报、KV、专辑封面
- **平台封面**：小红书、公众号、播客、B 站、头像、超宽头图
- **品牌物料**：明信片、邀请函、包装贴纸（用类型 C 出实物样机）
- **书刊**：封面、扉页、章节页、zine 内页
- **群像与图鉴**：人物图鉴、动物图鉴、旅行团合影
- **文字**：文学摘句、诗歌、个人宣言（用类型 A 三组文字层级）

## 基本规矩

1. **纸底不接受色相词**——`warm / aged / faded / vintage` 会泛黄；想要质感用纹理词（`fibre grain / laid lines / halftone`）
2. **数值只用在防翻车项**——背景色、文字比例、交叠面积可以锁；主体大小、位置疏密必须留模糊
3. **面积百分比对模型基本无效**——换成可数约束（最大角色 ≤ 画幅 1/4、小角色 ≥ 1/12）
4. **元信息与内容分开写**——权重标注不要和文案连写，否则大约一半概率被画进画面

完整规则见 [`references/pitfalls.md`](./references/pitfalls.md)。

## 随机性与创造力

这是个工程优先的技能，禁令和硬底线是为了稳定——但它没有做僵化约束，也不追求复刻一个固定效果。同一段提示词交给 GPT Image 2、Grok Imagine 2、Nano Banana 2、Seedream 5.0 Pro，风格有时差得很大。这是有意留的创作空间。

基准模型是 hunyuan-image。换模型先跑一张 + `postcheck.py` 校阈值。没有明确诉求时，留在 hunyuan-image 上最省。

## 工程校验

```bash
bash scripts/run_tests.sh                       # 一次跑完所有检查
python3 scripts/preflight.py "你的 prompt"     # 单条 prompt 预检
python3 scripts/postcheck.py a.png --track A   # 单张图验收
```

CI 详见 [`.github/workflows/validate.yml`](./.github/workflows/validate.yml)。

## 更新记录

- **v1.21.0**（2026-09-23）：**平台署名水印可原地去除**——新增 `scripts/dewm_imprint.py`（跨图共识掩膜 + αM 反解 + 混合路由；署名是生成后另贴的固定图案、不是平铺水印，所以 `dewm` 全族对它必然报 `k̂≈0`），须同系列多张一起跑。修 preflight 第三处假阳性：段落标题豁免由硬编码白名单改为**行位置**判据（手写模板不再被误报「残留槽位」，回归 192 项）。写回平台实测口径：实际模型 `hunyuan-image-alpha`、单张 5.71 积分、`quality` 未必上链。详见 [CHANGELOG.md](./CHANGELOG.md)。
- **v1.20.1**（2026-09-18）：修 `runs.csv` 表头错列——旧版升上来的机器此后每行都错位，正好废掉 reason 归因码要解决的问题；`align_log()` 写前校验表头并按各自列序归位，真实日志 12 条历史备注零丢失。
- **v1.20.0**（2026-09-18）：审查轮——修验收口径漂移（子技能仍挂着已撤的 blocker，会让 Agent 照旧误判重生、白扣积分）；新增 SKILL 与验收子技能的一致性门禁；常驻面二期再瘦身（SKILL.md 34,228 → 29,652 B，−13%）；回归测试按域拆成五个模块。
- **v1.19.0**（2026-09-18）：**针对 WorkBuddy 的常驻面瘦身**——技能描述里塞的变更史搬到 CHANGELOG，描述 9,717 → 1,797 B（**−82%**；本机 82 个技能的描述总长 51 KB，这一个曾占 18.7%、是中位数的 28 倍）；SKILL.md 拆出两个独立参考文件，全文 52,317 → 34 KB（−35%）；新增体积预算门禁。**验收判据按 202 张已归档成品重标**：旧 blocker 在成品上的触发率 46.5% / 64.9% / 82.2%，改后降到 4.3% / 3.0%（每去掉一条噪音误判，就少一次白花 5–10 积分的重生）。另新增 `scripts/_env.py`（缺依赖说人话）、`scripts/sync_release.sh`（真源→发布仓单向同步）。
- **v1.18.0**（2026-09-18）：新增 `scripts/paper_white.py`——白底海报的纸白偏暖改由确定性后处理解决（实测纸白 R-B=+5.5，写进硬底线仍纹丝不动：纸白被模型当**材质色**渲染，不吃语义禁令）；同一张图 R-B 5.45→0.00、亮度 236→250，墨/字/彩色区逐位不变。
- **v1.17.0**（2026-09-13）：推翻上一轮对去水印版本 v13 的判断——那条证据来自**评测盲区**（合成基准的水印是模板自己注入的，生成不出低 conf 样本，而真实库有 30% 是低 conf）；按 conf 分组重测，v13 三组全优。
- **v1.16.0**（2026-09-13）：挖出**度量本身的缺陷**——残留判据随背景变化（白纸底比纯黑底被压约 26 倍，等于在主力图种上测不出残留）；改报背景无关量，并新增不需要参照图的「白蚀单向性」损伤审计。
- **v1.15.0**（2026-09-12）：修正去水印选版的族定义（结构参照只在同口径的版本之间选）；修 `run_tests.sh` 用裸 `python3` 造成的假失败。
- **v1.14.0**（2026-09-12）：出图验收独立成子技能 `sub-skills/verify/`（三档评审口径 + 缺陷修复路由 + 各类型验收重点）；水印改**自动识别、命中才动手**（干净图不再被无条件动刀）；类型 E 补上验收判定。
- **v1.13.0**（2026-09-12）：去水印选版改「残留 + 结构损伤」双判据——旧判据会把整区 inpaint 的版本判成最优（画面被抹平却因残留为 0 得高分）。
- **v1.12.0**（2026-09-12）：新增类型 E「多格排版」（精灵图 / 系列海报 / 邮票组 / 角色设定表），每格独立成品靠统一规格串组；fill_meta 加 E（11 槽 + 格数与清单条数一致性校验）；preflight 修「单格尺寸被当成输出画布尺寸」误报。详见 [CHANGELOG.md](./CHANGELOG.md)。
- **v1.11.1**（2026-09-09）：修 `measure.py` 因百分号崩溃、验收测试假绿、预检色相词缺口。详见 [CHANGELOG.md](./CHANGELOG.md)。
- **v1.11.0**（2026-09-09）：可选云端后处理（先建议后启用）；去水印按图源分流。
- **v1.10.0**（2026-09-08）：新增类型 D 叙事分镜；类型 C 改机械填槽；42 条回归测试。
- **v1.9.1**（2026-09-08）：修 CI 因本机路径全红。
- **v1.9.0**（2026-09-08）：新增类型 C 写实包装 Mockup。
- **v1.8.0**（2026-09-07）：默认去水印改走 `dewm_v10`。
- **v1.7.0**（2026-09-07）：探索模式；去水印多版本选优。
- **v1.6.0**（2026-09-07）：出图后一次调用 `postcheck.py` 验收。
- **v1.5.0**（2026-09-07）：机械填槽、提示词库分层加载、出图配额 1 张。
- **v1.4.0**（2026-09-06）：尺寸实测，按请求像素精确输出。
- **v1.0.0**（2026-09-01）：首次发布。详见 [CHANGELOG.md](./CHANGELOG.md)。

## License

代码、SKILL 指令、scripts、references 等软件部分走 [MIT License](./LICENSE)；`examples/` 里的示例图与 `assets/readme/` 头图、成图墙走 [ASSET-LICENSE.md](./ASSET-LICENSE.md)，不随 MIT 分发。
