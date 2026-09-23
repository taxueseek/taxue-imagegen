# Changelog

All notable changes to taxue-imagegen are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **版本史单一真源**：1.13.0 起的中文条目于 2026-09-18 从 `SKILL.md` 描述的变更史
> 归位到此（逐字搬运、未改写）。更早的英文发布条目在 1.12.0 及以下各节。

## [1.21.2] — 2026-09-23

### 新增

**坑 37 · 双色高对比 + 大面积平白海报：`wm_auto` 报 `SUSPECT` 是假警报**（2026-09-23 实测）。

- 症状：RISO 双色概念海报（纯白底 `white%`=64.3、荧光粉/深蓝网点圆 + 底部文字带）
  跑 `postcheck.py --wm auto` 得 `|amp|=1.37 落在 SUSPECT 区`，verdict 卡在 **pending**；
  同一行其余量测全正常（R-B=0.0、sat=46.0、top noise=0.0）。
- 三条实测证据：① `wm_auto`：`k̂=1.051 / R²=0.848 / amp=1.37`（1.37/255 ≈ 0.5%，肉眼不可分辨）；
  ② `dewm_v10.py` 自己的可见度门控先拒了——「水印不可解（可见度 1.44 < 阈值 2.00）」→ skip、原图不动，
  **两处独立结论一致**；③ 目检：平白区 std=0.0、右下角 2 倍裁片无署名、网点内部无字形。
- 判定口径：`SUSPECT` 只在**有可见字形 / 署名**时才需动作。平白区 std ≈ 0 且放大裁片无字形 → 直接结项，
  **不要**为了消掉 pending 去跑 `pick_wm`——四版选优会对一张干净图各自反解出一份噪声，再让你从噪声里挑更少的那个。
- 附一条反例边界：**别用合成网点图复现它**。纯白 + 规则网点阵列（pitch 4 / 6 px）走的是另一条分支
  （`amp=8.06~13.88 高、R²=0.02~0.09 < 0.5` 的纹理误报）。本坑的 `SUSPECT` 分支（**低 amp + 高 R²**）
  是「大面积平坦白底 + 高对比双色图文」的组合信号，拿合成网点当同款证据会得出相反结论（同坑 32 的教训）。

### 变更

- **`sub-skills/verify/SKILL.md`：`SUSPECT` 由单条判据拆成两步**。原判据只有
  「`R² ≥ 0.50` → 记 pending → 走 `pick_wm` / 云端 `erase`」，会把干净图推进无谓返工。
  现改为：`R² ≥ 0.50` 先看**形状够不够看得见**——`|amp| < 2.0`（≈0.8% 灰度）时再跑一次
  `dewm_v10.py` 可见度门控，报「不可解」且平白区 std≈0、放大裁片无字形即判**无可见水印、直接结项**；
  `|amp| ≥ 2.0` 且目检见字形/署名才记 pending（平台署名走 `dewm_imprint.py`，坑 36）。
- 登记补齐：`pitfalls.md` 检测层映射表新增坑 37 行（层 `去水印链`，拦截点 `wm_auto.py`），
  坑数声明同步为 37（`SKILL.md` 索引两处 + `pitfalls.md` 速查表抬头）。

## [1.21.1] — 2026-09-23

### 修复

**v1.21.0 推上 GitHub 后 CI 报红，本地却全绿**。根因不在 v1.21.0，而在 v1.20.0 引入的
`_env` 普适性改动——它从没在 CI 上跑过（上一次成功推送还停在 v1.11.1）。

- **`_env._living_interpreters()` 只判「文件存在」，不判「真能跑」**。2026-09-20 那轮把
  「无条件推荐 WorkBuddy 内置路径」修成了「只报本机真实存在的解释器」，方向对，但少了一步：
  CI runner 上 `/usr/bin/python3` **存在却没有 cv2**，于是「① 换解释器重跑」这条修复路径
  指向一个同样跑不起来的解释器——**建议本身是空头支票**，而这正是 `_env` 存在的意义。
  新增 `_probe()`：候选必须 **实测能导入缺的那些模块**（`subprocess` 探针，30s 超时，
  探什么由调用方给的 `modules` 决定，拿不到就退回异常里的包名）；探针判不了时不排除候选
  （保守）。一个候选都过不了时，提示改为**明说「本机没找到」**，不再报一个假的可用路径，
  也不再复述 WorkBuddy 内置路径（它要么可用、要么不该被提）。
- **对应用例去掉了本机专有断言**：原断言要求输出里出现 `workbuddy/binaries/python`——
  那是**本机专有串**，任何非 WorkBuddy 机器上必然没有，属「本地绿、CI 红」的结构性缺陷。
  改为断言**行为**：① 必须给出「换解释器重跑」；② 若点名了解释器，那些解释器必须真实存在；
  ③ 一个都点不出来时必须明说「没找到」。另给判据本身单独加两条牙（不上 shim、用真实环境）：
  **报出来的必须真能导入依赖**、**本机有能导入的候选时不得一个都不报**——前者正是否掉本次
  bug 的那一条（若有候选无 cv2 却被报出，立刻红）。
- 教训写进本节即可，不另开坑号：这不是「生图翻车」，而是**门禁自身只能在作者机器上证真**。
  同批已把这条与 v1.20.0 的「门禁只跑干净夹具」并列为同类风险：**判据里凡是拿本机事实当
  常量（路径、解释器、已装的包），都要在目标环境上真跑一次再算数。**

回归：本地 194/194；修改前 CI 192/194，改动落点即那两条。

## [1.21.0] — 2026-09-23

### 变更

两条线：**平台署名水印可原地去除**（横版渠道新增的交付阻塞）＋**修掉 preflight 第三处假阳性**
（手写模板必踩）。另把平台侧实测口径写回文档。**不改任何提示词模板与判定阈值**。

**新增能力：平台署名水印（`dewm_imprint.py`）**

- 实测发现右下角「AI生成 / WORKBUDDY」署名**只出现在横版图**（同期 1024x1536 竖版无）。
  已有工具全族失效，且失效是**数学上的必然**，不是工具坏了：
  `postcheck.py --wm auto` 判 `[wm_texture] 纹理误报，不拦交付`（既不拦、也不去）；
  `dewm` 全族报 `k̂≈0 / conf≈0.09`；`rmwm_light.py` 掩膜退化为覆盖率 **100%**。
  根因：dewm 全族的模型是「与图像同分布混合的半透明**平铺**水印」，靠 k̂ 与 R² 反解；
  而署名是**生成后另贴的固定图案**（位置/形状/透明度恒定、非平铺），k̂≈0 属必然。
- 新脚本走 **跨图共识掩膜 + αM 反解 + 混合路由**，**须 N 张同系列一起跑**：
  ① 共识掩膜——署名在 N 张里位置形状一致、图像内容各异，逐像素
  `min_i(gray_i − median_blur(gray_i))` 即可把它从图形边缘里分离出来（单图阈值做不到：
  放宽到能盖住笔画就必然误纳图形边缘，inpaint 后把飘带/网点抹平一块，**比水印本身更显眼**）；
  ② αM 反解——`I_out = I_bg·(1−αM) + 255·αM`，`A = median_i(α_i)`，
  `I_bg = (I_out − 255A)/(1−A)`，保住笔画下的纸纹网点；
  ③ 混合路由（默认，实测最优）——逐图判底层类型：亮且低饱和 → 纸底 → inpaint；
  底层亮度 < `--dark`（默认 110）→ 深色场 → **也走 inpaint**；其余中间调彩色图形 → 反解。
  实测待修覆盖率 19.8% → **2.46%**（0.43% 像素）。
- 两条实测教训（都踩过，已写入坑 36）：① **深色场绝不能走反解**——港式霓虹那张是全黑场，
  αM 被另外 8 张纸底图主导（median），署名**整块残留**，打开 `--dark 110` 后立刻干净；
  ② **不能用「跨图离散度 σ」判底层类型**——σ 大只说明 N 张在此处内容不同，不代表某张在此
  是图形：民国那张署名正压在全纸底上，而它的 σ 同样很大。必须用**逐图**的中值背景判。

**修 preflight 第三处假阳性（手写模板必踩）**

- 「残留未填槽位」的【】豁免原是**硬编码白名单**，只认模板自带的那几个段落标题。而
  SKILL.md §3 步 2 规定「模板没覆盖的新需求才手写」→ 手写模板必然出现自定义段落标题
  （本次 H 系横版的 `【版式骨架 · 四层】`/`【工艺】`）→ **手写必踩**，真 BLOCK 被假 BLOCK 淹没。
- 判据改为**行位置**：独占整行的【】= 段落标题，行内嵌的【】= 待填空槽（`LINE_ONLY_CN`）。
  中途试过的「关键词表」被否——`【三比四】` 这类比例槽位与标题在关键词上无法区分，
  回归用例 `test_preflight` 的坑 24 正是它。
- 新增**双向验证**（行内【】仍 BLOCK、独占行【】豁免）；回归 172 → **192 项全过**，
  脚本修复节同步改写为「三处假阳性」。

**平台实测口径（写回文档，不改代码）**

- `references/size-and-params.md`：文生图实际下发 **`hunyuan-image-alpha`**（`branch=hunyuan`），
  端点 `copilot.tencent.com/v2/images/generations`，基础请求体仅 `[model, prompt, size, n]` 四键、
  全程日志**无 `quality` 字样**，1024x1536 单张扣 **5.71 积分**。结论：`quality` 未必真的上链，
  不要把画质差异全归因给它；要确认就做单变量小样对比。另记：本地 `product.json` 的兜底值
  （`hunyuan-image-v3.0` / `-v2.0-general-edit`）会被云产品配置覆盖成 alpha——
  查「到底用了哪个模型」要看日志里的 `[ImageService]` 行，不要只看本地配置。
- `references/pitfalls.md`：新增**坑 36**（平台署名水印：症状 / 根因 / 处置 / 验收口径），
  坑 7 补「不必裁剪、可原地去除」指引；**坑 1 补中文场景的「温暖象牙白纸张」绕法**——
  正向改写成「连续一整片未涂布纸白底色，肉眼近乎中性，比纯白柔和一档」+ 纹理词，把「象牙」
  移进负向子句；实测出图纸张 R-B≈+12、亮度 244（温暖但明亮、不显旧），属材质色**不判 blocker**，
  要更中性跑 `paper_white.py` 免费归正到 R-B≈0.15、亮度 250（纸纹 std 6.28→3.67，纹理仍在）。
  即「象牙白 vs 不发黄」这对矛盾需求可免费出两版让用户选，不必重生。
- 待解决表新增：**顶部 25% 留白 × 居中立像第 3 次复现**（构成主义编辑海报 2 张，2/2 侵入，
  全身立像顶到画面高度 **7.5%**）。新证据：把「所有墨迹最高点位于画面高度百分之三十以下」
  写进【负向】段**本轮实测无效**——负向位置约束对造像一样不生效，与「边饰/文字才吃得动」
  的旧结论一致。下一步只剩「换成正向几何锚」或「先出图 + 后期拼版」两条路。

**其他**

- SKILL.md §5 水印段补「平台署名水印不在 `--wm` 三分支内」的处置入口；§8 索引登记
  `scripts/dewm_imprint.py`；坑数 35 → 36（速查表与检测层映射表同步登记，门禁反查通过）。

## [1.20.1] — 2026-09-18

### 变更

方案 A＋C 轮：修三处真缺陷、补三条门禁、打通条件面可达性。**不改任何提示词模板与阈值
数字，出图能力零变化**——全部改动都是「让已有能力真的生效」与「让该查的查得到」。

**修真 bug（记账错列，一处变两处）**

- `runs.csv` 表头与实际写入错列。v1.19 给 `CSV_COLS` 加了 `reason` / `hint` 两列，
  但表头只在「文件不存在」时写——任何从旧版升上来的机器都保留着旧的 14 列表头，
  此后每行都错位（实测本机 27 行里 15 行，表头最后一列 `note` 里装的其实是 reason 码），
  正好废掉 reason 码自己要解决的归因问题。新增 `align_log()`：写前校验表头，
  过旧则**逐行按各自的列序**归位、认不出表头则留备份后重开；两种情况都先落
  `.bak-<时间戳>`，可回退。表头已对齐时直接返回，不重写、不多留备份。
- 上面那个「逐行按各自的列序」不是多余的小心：真实日志是**混排**的——旧表头下同时
  挂着 14 字段的旧格式行和 16 字段的新格式行。若一律按表头名映射，16 字段行的
  末两列会被读成 `hint` / `note`，**12 条历史备注（如「复刻版去水印」）当场丢失**。
  判别依据是字段数：等于当前列数即当前列序。用真实日志副本复核迁移结果：
  27 行、`note` 与关键列按位置比对 **0 处偏差**。
- 它能长期存活的原因是**门禁只跑干净夹具**：`test_reason_codes_recorded` 每次用全新
  临时文件，**永远拿到新表头**。新增 `test_log_header_migrated`，用「旧表头 ＋ 旧格式行
  ＋ 新格式混排行」夹具补上这条路径；另加一段「认不出的表头」夹具，锁住
  「不猜列义、留备份后重开」——猜的代价是把别的工具的列当成本表列，记账变成编造。

**补门禁（三条，均过变异测试）**

- **症状速查表覆盖门禁**：`references/pitfalls.md` 开篇承诺「按症状速查」，实测只列到
  坑 18，**坑 22–35 全缺**——恰好是去水印算法族、阈值重标、纸白归正、分材质填充这批
  排障最费时间、单节最长的。检测层表一直有覆盖门禁、症状表却一直没有，这是
  「门禁不对称导致的静默漂移」。表已补齐全部 35 个坑并按坑号重排；门禁只认表格
  数据行——正文散文里提一句刷不满覆盖度（反向变异验证）。
- **§4 接线门禁泛化**：原实现把 `jimeng-env.md` / `cloud-postprocess.md` 两个文件名
  **写死**在循环里，其余 13 个 references 只查「在 SKILL.md 提到过」。改为
  「每个 `references/*.md` 都必须在 §4 出现」——泛化当场抓出 `explore-mode.md`
  与百相图两份提示词长期漏接线，均已补进 §4 场景表。
- **示例命令路径门禁**：SKILL.md §5 与 `references/size-and-params.md` 共 4 处把
  「技能目录 ＋ /scripts/xxx.py」拼成绝对路径写死。本技能 §7 硬规则 4 自己写的
  却是「路径名先 `find` 再引用」，而本机 `~/.qwenworkcn/skills/` 下就另有一份安装
  ——照抄写死的命令在这些宿主上直接 404。改为每个示例开头定义一次 `SKILL=`，
  其余一律 `$SKILL/scripts/…`，换宿主只剩一个改动点。门禁范围限指导性文档
  （SKILL.md / references / sub-skills）：CHANGELOG 是历史记录，引用旧写法是它的职责。

**条件面可达性**

- §4 新增**坑节定位入口**：先按症状表定位坑号，再 `grep -n "^## 坑 "` 取行号只读那一节；
  `references/pitfalls.md` 开篇同步写明用法。该文件 104 KB ≈ 2.9 万 token，
  此前只能整读或凭猜。
- §4 新增 `CHANGELOG.md` 一行并明确「**出图不读**」，只在追溯版本史时按版本节读
  （全文 34 KB，此前被 description 指路、容易被整读）。

**验证**

- 回归测试 179 → 192 项，`run_tests.sh` 7 pass / 0 fail / 1 skip。
- **九条变异测试**逐条确认新门禁会失败，每条都断言三件事：锚点唯一、写入后字节确实
  变化、还原后与原件逐字节全等。含两条**反向/边界变异**：
  · 往症状表**散文**里补一句「本表也覆盖坑 35」不能把覆盖度刷满；
  · 去掉 `align_log` 的「表头已对齐则直接返回」，内容看不出差别——靠
    「备份里仍是迁移前那份旧日志」抓住它（判据不能用备份个数：备份名是秒级时间戳，
    同秒两次迁移会撞名，这正是坑 17 的老问题）。
- 过程中另有一次**自我证伪**：一度给 `align_log` 加了「表头对但个别行偏短也归一化」，
  变异测试显示该分支既不可达、又会在真遇到时把旧 `note` 错读成 `reason`
  （猜比不猜更坏），已按奥卡姆移除，理由写在代码注释里。

## [1.20.0] — 2026-09-18

### 变更

代码审查轮（三案并做）：修验收口径漂移、补一致性门禁、常驻面再瘦身、回归测试按域拆分。全部改动不改变任何判定能力与阈值数字。

**修真 bug（验收口径漂移）**

- `sub-skills/verify/SKILL.md` §5 类型 B 仍挂着 v1.19.0 已撤的 `white%∈[30,65]` blocker（202 张成品实测触发 82.2%）——按子技能执行的 Agent 会照旧误判重生、每张白扣 5–10 积分。已改为新口径（`near%<40` 只提示 + `sat>70` 唯一配色 blocker），类型 A 行补 `paper_white.py` 处置入口（坑 33）。
- 新增一致性门禁 `test_skill_verify_consistency`：SKILL.md §5 ↔ verify 子技能六组关键词（near%<40 / paper_white / 1024x1792 / expect-cells / top_noise / R²）必须同进退，已撤口径回流 verify 即红；变异测试验证有牙。
- SKILL.md §3 步 4 里同源的旧口径列举（「泛黄 R-B≥3 / 顶部被侵入」当 blocker）随瘦身一并移除——数值以 §5 为唯一真源。
- `test_preflight_quote_declaration`（坑 5）此前定义了但 main() 漏接线，是一个**从未跑过**的回归测试——拆分时接上。

**普适性**

- `_env.die()` 的「换解释器」提示改为**本机真实存在**的解释器候选（原来无条件推荐 `~/.workbuddy/...`，在非 WorkBuddy 机器上指向不存在的路径），`best_interpreter()` 真正用上。
- `measure.py`（SKILL.md 点名的独立入口）接上 `_env` 人话报错——22 个脚本都有，唯独漏了它。
- 新增 `scripts/requirements.txt`（numpy / pillow / opencv-python-headless）：缺依赖时 `_env` 的修复路径 ② 直接指向它，一条命令装齐。

**常驻面二期**

- SKILL.md 34,228 → 29,652 B（−13%）：§3 步 4 的 1,963 B 巨型单元格收缩为「命令 + 指向 verify 子技能」（判定流程的真源本来就在那里，两处维护正是上面漂移的根因）；§8 索引改为每行只答「何时用哪个」，判据细节归 docstring 与对应文档。体积预算门禁不变（≤36,000 B）。

**工程整理**

- `test_regressions.py` 1,304 行按被测域拆成 `scripts/tests/` 五个模块（preflight / fill_meta / postcheck / dewm / 文档门禁），入口与退出码契约不变；纯搬运，断言逐字未改。
- 真源 `.gitignore` 与发布仓对齐：运行产物（runs.csv、生成的出稿批次）不入库。
- CHANGELOG 修序：1.19.0 排到 1.18.1 之前（两节同日，Keep a Changelog 新版在上）。

## [1.19.0] — 2026-09-18

### 变更

常驻面瘦身、验收判据按实测重标、缺依赖说人话、打通发布通道。全部改动都按「不影响能力」约束做：只搬运、只降级误判、只补人话，没有删掉任何一条判据能力。

**常驻面 / 条件面分离（触及每轮上下文的成本）**

- `description` 里的变更史（v1.5→v1.18，7,942 B，占该字段 81%）搬到本文件：`description` 9,717 → 1,797 B（**−82%**）。本机 82 个 skill 的描述总长 51,017 B，本技能一个曾占 18.7%、是中位数的 28 倍。
- `SKILL.md` §6 云端后处理、§9 豆包/即梦适配拆到 `references/cloud-postprocess.md` 与 `references/jimeng-env.md`，SKILL.md 各留判据 + 第 4 节加载协议接线：全文 52,317 → 约 34 KB（**−35%**）。
- §8 索引里最长的算法演进史下沉到脚本 docstring（四行合计 4,368 → 1,531 B）。
- 新增体积预算门禁（description ≤ 2,000 B、SKILL.md ≤ 36,000 B），超了必须连同理由改预算。

**验收判据按 202 张已归档成品重标（省积分）**

- 新增 `scripts/calibrate_thresholds.py`：用「你留下来过的成品」当正样本，逐条算判据触发率——把 `evidence.md` 里那句纪律（「答不出样本量的阈值，只能当诊断值」）变成可执行的东西。
- 实测四条现役 blocker 在成品上的触发率：`R-B≥3` **46.5%**、`top_R-B≥3` 50.0%、`top_dev≥12` **64.9%**、类型 B 的 `white%∉[30,65]` **82.2%**。按底色分组后 `R-B≥3` 在纯白底子集只占 3.6%、纸底子集 63%——它测的是「有没有用纸底风格」。
- 改后：`R-B` 只在 `base≥240`（本该是白）时判，且**判 pending + 指向 `paper_white.py`**（重生改不了纸白偏色，坑 33），触发率 4.3%；`top_dev`/`top_zone%` 降为诊断（属风格张力）；类型 B 的留白占比改 `near%` 且只提示——旧口径撤除，`sat>70` 保留为唯一配色 blocker（触发 3.0%）。
- 顺带发现一个**结构性死判据**：候选口径 `paper%<30` 永远不会触发（`base` 取中位数，`paper%` 按定义恒 ≥50%）——「触发率 0%」不等于判据干净。

**结论可归因**

- `postcheck.py` 每行 findings 带 **reason 码**（`paper_warm` / `crowded_hint` / `size_mismatch` / `cell_count` / `text_bad` …），写进 `runs.csv` 新增的 `reason` / `hint` 两列；`--log-path` 可覆盖记账位置。以前只有 blocker/pending/pass 三值，「为什么重出」只能翻日志猜。
- 新增 `references/pitfalls.md` 的**坑 → 检测层映射表**（33 个坑各自登记「在哪一层能拦住」），并有门禁反查 `preflight.py` 的真实规则名——表比代码激进、代码比表激进，都会红。
- 修复 front-matter **不是合法 YAML** 的老问题：触发词段有两行顶格，折叠块提前终止，`yaml.safe_load` 直接 ScannerError；新增 YAML 合法性门禁。

**普适性**

- 新增 `scripts/_env.py`：22 个脚本的重型 import 包一层，缺 numpy/PIL/cv2 时给出两条可执行修复路径（换解释器 / 装包）并以退出码 2 结束，不再甩 traceback。
- 新增 `scripts/sync_release.sh`：真源 → 发布仓单向同步，范围限定技能载荷、同步后校验逐字节一致，并断言发布仓独有资产（README / LICENSE / CI）完好——顺带清掉真源 v1.17 与发布仓 v1.12 之间 5 个版本的漂移。
- 归档步骤不再硬编码个人目录，改回技能自己的硬规则「路径名先 find 再引用」。

**工程整理**

- 删除与 `dewm.py` 逐字节重复的 `dewm_v6_legacy.py`（v6 由 `dewm.py` 承担，`pick_wm` 加载的就是它）。
- 回归测试 129 → 172 项；每条新门禁都跑过变异测试确认「会失败」。

## [1.18.1] — 2026-09-18

### 变更

v1.18.1 修 preflight 两处假阳性——类型 A 出稿 **100%** 误报「坑11 竖排多词英文」（模板条件句 「主标题若竖排且多于一个词」被当成竖排指令）与「残留未填槽位 7 个」（模板的【】段落标题被当成 C 类槽位）；并给类型 A 模板【三组文案】段加入「全图只有底部一条文字带」排他声明 （实测修掉三组文案在中部与底部**重复渲染两次**的偏离）。另记坑 34：`rmwm_light` 是亮暗通吃， 在含文字的图上会啃掉笔画，含文字图去水印首选 `dewm_v10`（门控判不可解时 `--no-guard` 仍优于它）。

## [1.18.0] — 2026-09-18

### 变更

v1.18 新增 `scripts/paper_white.py`：白底海报的**纸白稳定偏暖**改由确定性后处理解决（坑 33）。 实测同一提示词两版，纸白均值都是 R237.6/G235.5/B232.0（R-B=+5.5），第二版已把 「三通道数值几乎相等」写进硬底线仍**纹丝不动**——纸底母题里，纸白被模型当**材质色**渲染， 不服从「背景为纯白」这类语义禁令，提示词这条路已证伪。脚本走「纸白掩膜 → 归一化卷积 拍平纸纹 → 白点归正」，墨/字/彩色区逐位不变：同一张图 R-B +5.45→0.00、亮度 236.2→250.0、 white% 1.7%→65.8%、base 232→249，两条泛黄告警清零。**新判据：白底图出图后 R-B≥3 先跑 paper_white，再考虑重生**（重生不改这个偏色，只是再花 5-10 积分）。同时把「顶部 25% 留白 × 居中半身造像」的结构张力记入待解决（苏绣海报 2/2 侵入：边饰已压到 25%，发髻仍顶到 6.3%）。

## [1.17.0] — 2026-09-13

### 变更

v1.17 **推翻 v1.16 对 v13 的判断**（坑 32）：v1.16 据「合成基准 v8 更优」判 v13 的 σ 估计 是缺陷、必须先修。本轮发现那**整条证据来自评测盲区**——合成基准的水印是用标定模板 自己注入的，conf 必然极高，**生成不出「低 conf」样本**，而真实库里有 30%（26/87）是 低 conf 图（真实水印与模板不匹配）。按 conf 分三组重测：**v13 在全部三组都优于 v8**， 低 conf 组优势最大（残留 0.0% vs 30.8%，且改动量更低）。v13 唯一的代价「过度去除」 实测**视觉不可见**（17 张相关图底色中位 249、实际压暗中位 1.1 灰阶、>5 灰阶者 0 张）。 试过 6 类改进（误差传播 σ_A / 动态 c / 常数 c / 稳健 k / NS inpaint / 局部结构调节 c） **全部实测否决**。结论：v13 现状已是实测最优工作点，σ「不对题但好用」；若要启用， 应做 **conf 门控路由**而非改 σ。新增坑 32（基准盲区）并更新待解决表。回归测试 119 → 126 项。

## [1.16.0] — 2026-09-13

### 变更

v1.16 复检时挖出**度量本身的缺陷**（坑 30）并补上两条参照无关工具： ① `amp = k̂·mean(a·(255−bg))` **随背景变化**——白纸底 (255−bg≈9) 比纯黑底 (≈238) 被压约 **26 倍**，而本技能的竖版海报绝大多数是白底，等于判据在主力图种上测不出残留 （03_labor 上 v7 肉眼有明显灰糊斑，amp 仅 0.21 判 CLEAN）。背景无关的量是 **α̂ = k̂**， 已在 `estimate_residual` 里以 `alpha`/`bg_scale` 暴露；换成 α̂ 后 v12 的问题才显形 （86 张真水印图：α̂<0.02 仅 53%、α̂>0.10 高达 26%）。 ② 新增 `audit_wm.brightening_violation()`——由 `orig = (I−αC)/(1−α) ≤ I` 推出的 **白蚀单向性**：去白水印只能变暗，`out > I` 的像素必然是损伤。**不需要参照图、不需要 同口径、跨算法代有效**，绕开了坑 28/29 反复翻车的「挑参照」环节（实测 v7 违反 5674 px、 v12 71 px、v13 0 px）。 ③ 新增 `scripts/dewm_v13.py`——用**最小方差（Wiener）融合** `w=t²/(t²+(σ/σ_b)²)` 取代 v10 的线性斜坡 + 平底二值路由。真实库 86 张 α̂ 最优（85% 不可见）、暗底组最优、 违反 0；但**合成基准（有真值）显示 v8 全面更优**（exact 模式 55.3 vs 44.8）， 根因是 σ 用 Laplacian-MAD 把纹理当噪声 → 过信 inpaint → 良态欠减。 故 v13 **标为实验候选、未并入 `pick_wm` 选版池**。回归测试 110 → 119 项。

## [1.15.2] — 2026-09-12

### 变更

v1.15.2 二次复检（92 张）后把「分歧告警」升级为**拒绝写入**：命中的 2 张图，其 `_clean/` 现任产物恰好都是更优的那版（Design43-10 现任 v7 水印抹净、判据想改选 v8 残影可见；03_labor 现任 v8 字口锐利、判据想改选 v7 白底留灰糊斑）——只告警的话重跑 一次就会把好产物覆盖成差的。并收紧坑 29 根因：参照族 `MODEL_FAMILY(v8/v9)` 在该图 **自身没有干净成员**（5.72 / 6.12），真正去干净的 v7 不在族内，反成唯一「偏离者」。 同时补判据边界：模板按 1024×1536 标定，**非标准尺寸图不能拿 r2/k̂ 下结论**， 改用对齐分（5 张判「无需处理」的图 0.083–0.207 vs 真水印对照 0.774）+ 对比拉伸目检复核。 回归测试 104 → 110 项。

## [1.15.1] — 2026-09-12

### 变更

v1.15.1 全库复检（84 张有原图的图）后补两处保护：① **分歧告警**——胜出版本残留比 某被罚下候选高 5.0 以上时，明确列出两者并声明「取舍只能目检」（水印压在平坦区时 inpaint 的干净结果会被「偏离参照」误判为损伤；实测 amp / R² / dev 三列全交叠， 无法自动裁决，见坑 29）；② **最小干预**——v9 判定无需处理且原图残留已在 CLEAN 内时 直接取 v9（原图已够干净，任何改动都是净损失）。同批修掉两个存量产物： 01_mistgate 的 v8 过减（画面被压暗 13.87 灰度级，实为无水印图上的强推反解）与 03_labor 的 v7 涂抹（笔画糊成一团）。

## [1.15.0] — 2026-09-12

### 变更

v1.15 修正 v1.13 判据的族定义（坑 28 第三次迭代）：结构参照只在**同 k̂ 口径**的 v8/v9 之间选——v6 固定 k≡1、与自适应拟合 k̂ 不同口径，混作一族会让深色图上正确的 v8/v9 被判成「偏离 13.6 / 损伤 10.6」，反而选出发浑的版本；v6/v7 仍是候选，只是不作参照。 同批修正 run_tests.sh 用裸 python3 造成的假失败（managed 环境无 cv2，3 项检查误报）。

## [1.14.0] — 2026-09-12

### 变更

v1.14 出图验收独立成子技能（sub-skills/verify/）：把「出图之后的一切判定」收拢成 一层，含三档评审口径、缺陷修复路由（印在画面里→重生／缺失可替换→编辑）、 各类型验收重点与阈值出处。同时补上两处此前没有的能力—— ① 水印改**自动识别、命中才动手**（scripts/wm_auto.py：amp 与 R² 双条件闸门 + 去后复检， 干净图不再被无条件动刀，存疑交人不拦交付）； ② 类型 E 此前零判定（v1.12 加类型时漏了验收接线），现补格数/每格等比例/格间净空量测， 类型 D 补尺寸声明值校验。触发词增「验收、检查这张图、能不能交付、复检」。

## [1.13.0] — 2026-09-12

### 变更

v1.13 修复坑 28：pick_wm 选版改「残留 + 结构损伤」双判据（旧判据会把整区 inpaint 的版次判成最优——画面被抹平却因残留为 0 得高分）；audit_wm 增 --ref 损伤审计与 key 唯一化。

---

### 简版开发史 1.5.0–1.12.0（详细条目见下方英文各节）

- **1.12.0** buddy-image-processing（enhance/erase/restore/matting，编排不复制脚本），须先向用户建议 （修什么/代价/计费未实测）并获同意才调用，绝不静默启用；新增去水印双路由 （自家 ImageGen 图走 dewm 本地反解；外来图/水印压复杂图形/疑难图走官方 erase 云端重绘）， 并吸纳官方六条调用纪律：错误真实上报、提交状态未知不重提、用户修改指令原样进槽、 后处理重新过 postcheck、计费口径实测前从严报消耗、可选项不默认启用。
- **1.11.0** v1.11 新增云端后处理层（第 6 节，**可选不默认**）：postcheck 判「指标在阈值内、 但细节软/小构图偏差」的图可建议走官方内置
- **1.10.0** v1.10 新增类型 D「叙事分镜」+ 工具链打通：preflight/postcheck 支持 C/D， preflight 修词边界误报（managed/damaged 命中 aged 等）与【】槽位漏检， postcheck 增 pending 档（文字未核对不再计 pass），dewm_io 守卫堵大小写/硬链接绕过。
- **1.9.0** v1.9 新增类型 C「写实包装 Mockup」：棚拍实物做底 + 编辑风单色专色版面 + 单一隐喻图形 AM 网点 + 巨型堆叠品牌字，中文元模板槽位化 （references/packaging-editorial.md，三轮实测 r3 4/4 文字逐字全对）。
- **1.8.0** v1.8 新增 dewm_v10（v9 + 平底自适应融合）：修「平色底上肉眼可见的水印残影」—— amp 判 CLEAN 但人眼仍有痕（形状失配，R² 掉 0 被当纹理放过），平底图上 v9 RMS 5.98 → v10 1.43，纹理图逐位不动零回归。标准水印默认改 dewm_v10.py。
- **1.7.0** v1.7 探索模式（explore.py + CSV 驱动）；去水印默认改 pick_wm 三版选最优（v6/v7/v8 各有擅长， 实测 18 张原 v6 漏清/留噪点 5 张占 28%），所有 dewm 脚本接入 dewm_io 覆盖守卫（不覆盖原图）； 新增 audit_wm 残留审计（无原图也能定位 DIRTY 张）。
- **1.6.0** v1.6 出图后一次调用 postcheck.py：量测 + 文字带目检裁片 + dewm 反解去水印 + runs.csv 记账， 验收路径从 3-4 次工具往返压到 1 次，并建立模板调优的数据反馈闭环。
- **1.5.0** v1.5 借鉴 taxue-halftone 流水线：fill_meta.py 机械填槽（LLM 不重抄模板、逐字声明自动推导）、 提示词库分层加载、三档评审卡 + 出图配额 1 张。

---

## [1.12.0] — 2026-09-12

### Added
- **New type E — multi-grid layout (多格排版)**: sprites sheets, series-poster
  sets, stamp sets, emoji packs, character-bible sheets. Every cell is an
  independent finished piece held together by one shared spec — distinct from
  type D, whose frames are continuous slices of one story.
  - `references/multigrid-layout.md`: the slot-based meta-template, three
    verified fillings (pixel sprite sheet / series posters / stamp set), and
    the hard rules read off the source corpus.
  - `scripts/fill_meta.py E`: 11 slots, plus a cell-count vs cell-list-length
    check (the most common low-level error for this type).
  - `scripts/preflight.py` / `postcheck.py`: type E wired in; the size check
    no longer flags a *cell* size (e.g. a sprite cell at `128x128`) as an
    output canvas size.

### Fixed
- **`preflight.py` cell-size false positive**: any `WxH` found inside a clause
  mentioning 单格/每格/单帧/frame/cell is a cell dimension, not the output
  canvas, and is now skipped instead of raising a 尺寸 warning.

### Notes
- Type E was distilled from the 256-prompt third-party GPT Image 2.5 corpus
  (the "multi-panel / sheet" cluster). Source analysis:
  `gpt-image-2-5-第三方提示词研究/`.
- The three hard rules are evidence-backed, not intuited: the consistency
  anchor must be stated positively; the per-cell list must be all-or-nothing
  (the two full-list prompts are the longest in the whole corpus); and the
  anti-mockup closing sentence is mandatory.

## [1.11.1] — 2026-09-09

### Fixed
- **`measure.py` crashed on every invocation** — its `--help` text contained a
  bare `%` (`"顶部 25% 留白"`), which argparse's `%`-formatting turned into
  `ValueError: unsupported format character`. Because the crash happens inside
  `main()`'s `add_argument`, *normal* runs failed too, on every Python version
  (3.11/3.12/3.14 verified). The smoke test only imported the module, so CI
  stayed green. `run_tests.sh` and `test_regressions.py` now run `--help` on
  every user-facing CLI entry point.
- **A regression test that could not fail** — `test_postcheck_verdict` asserted
  `"C" in stdout` and `'"pending"' in source`, i.e. that the *strings* existed.
  Removing `C`/`D` from `postcheck.py`'s `choices` still passed. Rewritten to
  build real images and assert process exit codes (0 pass / 1 blocker /
  3 pending), covering all three verdicts plus a genuinely yellow image.
- **`preflight.py` hue-word list had a semantic gap** — the 2026-09-09 poster
  run failed with `warm bone-white` (blocked), then passed with
  `neutral near-white`; but `bone-white` alone was *not* in the list, so the
  same failure could silently recur. Added the background-tinting equivalents
  (`bone-white`/`off-white`/`eggshell`/`parchment`/`oatmeal`, `dusty`/`muddy`/
  `dingy`/`grimy`/`murky`, 骨白/泛黄). Deliberately **not** added: `amber` /
  `honey` / `golden` / `rose` — the measured record states these are concrete
  colour names used for light and accents, and blocking them would break the
  verified storyboard workflow.
- **Stale/incorrect counts and claims** — `preflight.py` docstring said
  "11 of 26 text-detectable (50%)" while listing 11 and leaving 15 (42%);
  `postcheck.py` docstring still promised "re-measure the dewm result" and a
  two-value verdict, contradicting the code since v1.10; SKILL.md called the
  six call-discipline rules "four", cited "两个构建脚本" after they were merged
  into one, and described a script verdict named 「可修」 that never existed.

### Changed
- **CHANGELOG.md and README badges catch up with the code** — the repo had
  shipped v1.11.0 with no `[1.11.0]` entry, so Keep a Changelog was violated and
  both READMEs advertised 1.10.0.

## [1.11.0] — 2026-09-09

### Added
- **Cloud post-processing layer (optional, never on by default)** — SKILL.md §6
  routes to the official built-in `buddy-image-processing` skill (enhance /
  erase / restore / matting / beauty). The skill orchestrates, it does not copy
  the official scripts. The Agent must propose first (what will change, the
  cost, and that billing is unmeasured) and only call after the user agrees.
- **Dual-routing for watermark removal** — images produced by this skill's
  ImageGen go to the local `dewm` family (free, pixel-preserving); foreign
  images, watermarks over complex artwork, and hard cases go to the official
  cloud `erase` (which repaints around the target region — must be disclosed).
- **Six call-discipline rules** absorbed from the official skill: report errors
  truthfully, never resubmit when submission state is unknown, pass user
  revisions through verbatim, re-run postcheck after any post-processing, treat
  billing as charged until measured, and never enable optional cloud work
  silently.
- `references/pitfalls.md` "待解决" table gains three rows: cloud billing,
  `erase` repaint scope, and post-processing's effect on postcheck metrics.

## [1.10.0] — 2026-09-08

### Added
- **Type D · Narrative Storyboard** — 9-frame sequential storytelling with a
  dual consistency anchor (`STYLE LOCK` + `CHARACTER LOCK` reused verbatim in
  every frame, since ImageGen has no reference-image channel). Ships
  `references/storyboard.md` (positioning, mechanism, 9-frame shot design,
  measured parameters) and `scripts/build_storyboard.py`, which builds both
  cases (`--case cyber|ink`) from one shared `build()` — the previous two
  scripts had byte-identical `main()` functions.
- **`fill_meta.py C`** — Type C packaging mockups now assemble mechanically
  instead of the LLM hand-copying a 17-slot template. `--list` shows the slots;
  `--set` fills them; empty optional slots (e.g. the second spot colour) have
  their leftover brackets stripped automatically.
- **`scripts/test_regressions.py`** — 42 assertion-based tests, one per fixed
  defect, wired into `run_tests.sh`. They assert behaviour (regex hits, exit
  codes, path resolution), not "it ran without crashing".

### Fixed
- **`preflight.py` word-boundary bugs (both directions at once)** — hue words
  were bare substrings, so `managed`/`staged`/`damaged` matched `aged`,
  `screaming` matched `cream`, and `warmth` matched `warm`: all 9 Type D
  prompts were falsely blocked. Meanwhile `NEGATION`'s bare `ban`/`no` matched
  `banner`/`urban`, so genuine hue violations were silently waved through.
  English terms now use `\b`; Chinese terms stay substring-based.
- **`preflight.py` missed Chinese slot markers** — the leftover-slot rule only
  understood `{}`, so Type C's 17 `【】` slots passed with `findings=[]`.
  Both bracket styles are now detected.
- **`postcheck.py` recorded unverified text as `pass`** — a run with no
  `--text` logged `verdict=pass`, contradicting SKILL.md's "pass = metrics in
  range **and** text verbatim-correct". Now a distinct `pending` verdict with
  exit code 3.
- **`postcheck.py` / `preflight.py` rejected tracks C and D** — `choices=["A","B"]`
  meant the two newest tracks could not be verified at all. Both now accept
  A/B/C/D. Metric warnings are defined for A and B only: R-B is inapplicable to
  Type C's grey studio base, and Type D's narrative warm tones are exempted by
  `storyboard.md` §五. For C/D postcheck therefore runs measurement + text-band
  crop + optional dewm and returns `pending`/`pass` on the text check alone —
  **not** "type-appropriate thresholds".
- **`dewm_io.safe_target` could still overwrite the source** — the guard
  compared path strings, so a case-variant `--out A.PNG` (same file as `a.png`
  on case-insensitive APFS) and a hard link both bypassed it. Now uses
  `os.path.samefile()` when both paths exist, falling back to `normcase`.
- **`build_storyboard.py` wrote to `/tmp`** — output now lands in the script's
  own directory, matching `build_storyboard_ink.py`.
- **`1024x1792` mislabelled as 9:16** — it is 4:7 (0.5714 vs 0.5625, 0.9% off).
  Corrected in both docs; exact 9:16 at width 1024 would be `1024x1820`. The
  size was also missing from `preflight.py`'s tested-size table.
- **`references/storyboard.md` claimed to be "Type C"** while SKILL.md assigns
  C to packaging and D to storyboards; corrected to D.
- **Stale counts** — `preflight.py` said "15 pits" while `pitfalls.md` had 22;
  the SKILL.md index said "15+". Both now state 26 pits / 11 text-detectable
  (42%), with the list of which.

### Changed
- **`runs.csv` can be skipped** — `postcheck.py --no-log` keeps test runs from
  polluting the production log (this session's own verification had added 13
  junk rows, now cleaned).
- **`run_tests.sh` runs in both layouts** — full checks in the release repo,
  release-asset checks skipped in the local skill dir, so the two can no longer
  drift apart.
- `.gitignore` now excludes generated `scripts/_prompts*/` and `scripts/logs/`.

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
- **Type C · Photoreal Packaging Mockup** — studio-lit physical base +
  editorial monochrome ink layout + single-metaphor AM halftone graphic +
  giant stacked brand wordmark; Chinese meta-template with slots
  (`references/packaging-editorial.md`, three rounds, r3 4/4 text
  verbatim-correct).
- `references/packaging-editorial.md` §1 template, §2 slot table with four
  real packagings (coffee bag / serum bottle + box / beverage can / rigid
  box), §3 hard rules (eight verified rules), §4 padding/density hints.

### Notes
- Type C uses `1152x1536` (3:4) — width 1152 differs from Type A's default
  1024 (2:3). The width is intentional for a true 3:4 ratio.
- Gallery samples for Type C: four packagings (coffee pouch /
  serum bottle + box / beverage can / rigid box) from the v1.9 r3 round
  where 4/4 images passed the verbatim-text check.
- `SKILL.md` corrected from "two tracks" to "three types" in the front-matter
  description and the §0 header — Type C shipped in v1.9 but both lines were
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
- `scripts/fill_meta.py` — mechanical slot fill for Type A. Reads
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
- Initial release. Two types (Type A vertical concept poster, Type B
  hand-drawn group illustration), five themes, mechanical slot fill,
  single-source templates, Explore mode in-script, watermark removal
  (rmwm + dewm v1).
- `references/pitfalls.md` — initial 12 verified pitfalls.
- `references/poster-v5.md` §1 — v5.0 baseline template.

[1.11.1]: https://github.com/taxueseek/taxue-imagegen/releases/tag/v1.11.1
[1.11.0]: https://github.com/taxueseek/taxue-imagegen/releases/tag/v1.11.0
[1.10.0]: https://github.com/taxueseek/taxue-imagegen/releases/tag/v1.10.0
[1.9.1]: https://github.com/taxueseek/taxue-imagegen/releases/tag/v1.9.1
[1.9.0]: https://github.com/taxueseek/taxue-imagegen/releases/tag/v1.9.0
[1.8.0]: https://github.com/taxueseek/taxue-imagegen/releases/tag/v1.8.0
[1.7.0]: https://github.com/taxueseek/taxue-imagegen/releases/tag/v1.7.0
[1.6.0]: https://github.com/taxueseek/taxue-imagegen/releases/tag/v1.6.0
[1.5.0]: https://github.com/taxueseek/taxue-imagegen/releases/tag/v1.5.0
[1.4.0]: https://github.com/taxueseek/taxue-imagegen/releases/tag/v1.4.0
[1.0.0]: https://github.com/taxueseek/taxue-imagegen/releases/tag/v1.0.0