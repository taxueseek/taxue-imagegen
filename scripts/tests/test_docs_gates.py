#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文档与门禁域：front-matter（坑 31）、文档一致性、版本三方一致、
常驻面分层契约、坑→检测层映射、隐私扫描、SKILL.md ↔ verify 子技能一致性，
以及脚本 CLI 契约（每个用 argparse 的脚本，--help 必须能打印）。"""
import glob
import os
import re
import subprocess

from _harness import HERE, ROOT, SURFACE_BUDGETS, check, load


def test_referenced_files_exist():
    """活文档里提到的 `.md` 必须真的存在（悬空引用 = 搬出去没人读）。

    2026-09-23 实测：把 `poster-h-series.md` 改名为 `poster-horizontal-series.md`
    （文件里后来装了两支横版母版），**一步就制造了 4 处悬空引用**——
    `poster-v5.md` 2 处、`h-series-prompts.md` 2 处，而另一条门禁只证明
    「每个存在的文件都被引用」，**证不了「被引用的文件都存在」**，方向是反的，
    所以那次改名全绿通过。这条补反方向。

    判据按**存在性**，不写死名单：
      · `references/*.md` 的 basename —— 存在即可；
      · `SKILL.md` / `CHANGELOG.md` —— 根目录那两个；
      · `sub-skills/**/<name>.md` —— 子技能里的（如 verify 的 evidence.md）。
    三条之外还出现的 `.md` 就是悬空的。

    两种写法都查：带前缀的 `references/xxx.md` 与**裸文件名** `xxx.md`。
    起因是第一次写这条门禁时只匹配了带前缀的形式，而文档里大量引用是裸文件名
    （实测 18 种标记里只有 1 种带前缀），反向验证时漏判，等于没牙。

    范围只扫活文档（`SKILL.md` + `references/*.md`）：`CHANGELOG.md` 里出现旧文件名
    是**历史记录**，不该要求它存在（本次改名这件事正是靠它记下来的）。

    2026-09-23 修（同行评审）：本函数此前**排在文件头之前**——shebang、coding cookie、
    模块 docstring 与全部 import 都在它下面第 48 行起。定义在前不影响运行（函数体到调用时
    才求值），但 `__doc__` 成了 None、coding 声明被忽略、shebang 失效。已按
    「文件头 → import → 用例」的约定归位。
    """
    import glob as _glob
    import re as _re
    refs = {os.path.basename(p) for p in _glob.glob(os.path.join(ROOT, "references", "*.md"))}
    subs = {os.path.basename(p) for p in
            _glob.glob(os.path.join(ROOT, "sub-skills", "**", "*.md"), recursive=True)}
    known = refs | subs | {"SKILL.md", "CHANGELOG.md"}
    docs = [os.path.join(ROOT, "SKILL.md")] + sorted(
        _glob.glob(os.path.join(ROOT, "references", "*.md")))
    # 两种写法都要收，缺一种就是半个门禁（实测踩过两次）：
    #   · 带前缀 `references/xxx.md` —— §8 索引那种写法；
    #   · 裸文件名 `xxx.md` —— §4 场景表与正文里的多数写法。
    # 一条正则吞不下两者：裸名那条的 lookbehind 会排除 `/`，
    # 于是 `references/xxx.md` 整个匹配不上（前缀里的 `/` 把它挡住了）。
    prefixed = _re.compile(r"references/([A-Za-z0-9._-]+\.md)")
    bare = _re.compile(r"(?<![\w/.-])([A-Za-z0-9][A-Za-z0-9._-]*\.md)")
    dangling = []
    for p in docs:
        text = open(p, encoding="utf-8").read()
        names = set(prefixed.findall(text)) | set(bare.findall(text))
        for name in sorted(names - known):
            dangling.append(f"{os.path.basename(p)}→{name}")
    check("活文档引用的 md 文件都存在（无悬空引用）", not dangling,
          "悬空：" + "、".join(sorted(set(dangling))[:5]))


def test_repo_root_whitelist():
    """仓库根只跟踪约定文件：运行产物不许混进根目录。

    实测来源（2026-09-23 资产盘点）：仓库根躺着一份 2 行的 `runs.csv`，内容是
    `a.png` 的一次冒烟记录（该图早已不存在），却被 git 跟踪（v1.22.1 那笔的
    `git add -A` 顺手带进去的），而真台账在 `scripts/logs/runs.csv`（70 行、
    被 .gitignore 忽略）。后果不是「多一个文件」这么轻：文档里一律简称
    「runs.csv」，根目录再放一份同名的，读的人会把冒烟数据当成生产记账——
    **归因错了比没有归因更坏**，而技能里所有「先看台账再决定改什么」的动作
    都建在这份数据上。

    判据：`git ls-files` 里位于根目录（无 `/`）的条目 ∈ 白名单。白名单同时
    覆盖真源与发布仓（发布仓独有 README / LICENSE / ASSET-LICENSE.md）。
    本环境无 git 时显式打印「未校验」，不假装通过——覆盖缺口要说出来。
    """
    allow = {".gitignore", "SKILL.md", "CHANGELOG.md", "README.md", "README.en.md",
             "LICENSE", "ASSET-LICENSE.md"}
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                             text=True, timeout=30)
        if out.returncode != 0:
            raise RuntimeError(out.stderr.strip()[:80] or "git ls-files 失败")
        root_items = [l for l in out.stdout.splitlines() if l and "/" not in l]
    except Exception as e:
        print(f"  note 本环境读不到 git 跟踪列表（{e}）→ 根目录白名单**未校验**")
        check("仓库根白名单（本环境无 git，未校验）", True, "")
        return
    bad = sorted(set(root_items) - allow)
    check("仓库根只跟踪约定文件（运行产物不混进根目录）", not bad,
          "根目录多出：" + "、".join(bad))


def test_skill_frontmatter_window_free():
    """坑 31：run_tests.sh 用固定字符窗口读 front-matter，撑爆后报「missing front-matter」。

    同一个坑复发过两次（2048 → 4096）：报错信息把人引向「YAML 格式坏了」，
    真实原因是 description 里的版本变更记录越写越长，超出了读取窗口。
    闭合符位置与长度无关，按行定位即可。本测试既验行为、也**防止改回固定窗口**。
    """
    import subprocess
    import sys

    skill = os.path.join(ROOT, "SKILL.md")
    lines = open(skill, encoding="utf-8").read().splitlines()
    check("坑31 SKILL.md 首行是 ---", lines and lines[0].strip() == "---",
          f"首行是 {lines[0]!r}")
    end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "---"), None)
    check("坑31 front-matter 闭合符可定位", end is not None, "全文找不到闭合 ---")
    if end is None:
        return
    fm = "\n".join(lines[1:end])
    check("坑31 front-matter 同时含 name/description",
          "name:" in fm and "description:" in fm, f"{len(fm)} 字符")
    # 旧守卫的前提是「本文件真的超过常用读取窗口」——2026-09-18 把变更史搬进
    # CHANGELOG.md 后 front-matter 只剩 ~1.9 KB，前提不再成立。规则本身仍然必要，
    # 所以按「保留意图、换掉方向」处理：不再断言本文件有多长，而是构造一个
    # >4096 字符的 front-matter，验证同一套按行定位逻辑照样能找到闭合符
    # （用固定窗口读就会失败）。这样拆短了不会假红，写长了也不会漏掉。
    long_src = "---\n" + "description: >-\n" + ("  " + "x" * 120 + "\n") * 40 + "---\nbody"
    ll = long_src.splitlines()
    end_long = next((i for i, l in enumerate(ll[1:], 1) if l.strip() == "---"), None)
    check("坑31 长度无关：>4096 字符的 front-matter 仍能按行定位闭合符",
          end_long == len(ll) - 2 and len("\n".join(ll[1:end_long])) > 4096,
          f"end={end_long} / 共 {len(ll)} 行")

    rs = open(os.path.join(HERE, "run_tests.sh"), encoding="utf-8").read()
    seg = rs.split("[2/8] SKILL.md front-matter", 1)
    check("坑31 run_tests.sh 含 front-matter 检查段", len(seg) == 2, "找不到该步骤")
    if len(seg) != 2:
        return
    step = seg[1].split("PY\n", 1)[0]
    # 剔除注释行：注释里会**提到**历史上的 f.read(2048) 作为反例，不该被判为违规
    code = "\n".join(l for l in step.splitlines()
                     if not l.lstrip().startswith("#"))
    offenders = re.findall(r"\.read\(\s*\d+\s*\)", code)
    check("坑31 front-matter 检查不得使用固定字符窗口",
          not offenders,
          f"发现固定窗口读取 {offenders} —— 版本说明再长一行就会再次误报「missing front-matter」")


# ── 类型编号与文档数字一致性 ─────────────────────────────────────
def test_doc_consistency():
    sb = os.path.join(ROOT, "references", "storyboard.md")
    if os.path.exists(sb):
        head = open(sb, encoding="utf-8").readline()
        check("storyboard.md 自称类型 D", "类型 D" in head, f"标题={head.strip()}")
        body = open(sb, encoding="utf-8").read()
        check("storyboard.md 不再声称 9:16", "| 9:16 |" not in body,
              "1024x1792 实为 4:7")

    skill = open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8").read()
    check("SKILL.md 声明五种类型", "五种类型" in skill, "类型数漂移")
    check("SKILL.md 索引含 storyboard.md", "references/storyboard.md" in skill,
          "类型 D 规则文件未进索引")
    check("SKILL.md 索引含 multigrid-layout.md", "references/multigrid-layout.md" in skill,
          "类型 E 规则文件未进索引")

    # 坑数一致性
    pitfalls = open(os.path.join(ROOT, "references", "pitfalls.md"), encoding="utf-8").read()
    n = len(re.findall(r"^## 坑 ?\d+", pitfalls, re.M))
    check(f"pitfalls 坑数({n})与 SKILL.md 声明一致",
          f"{n} 个坑" in skill, f"SKILL.md 未同步为 {n} 个坑")


# ── 版本号三方一致（SKILL front-matter / CHANGELOG / README 徽章） ──
def test_version_consistency():
    """2026-09-09 新增：仓库实际以 v1.11.0 发布，但 CHANGELOG 没有 1.11 条目、
    两个 README 徽章还停在 1.10.0 —— 声明与实现三方打架，且违反仓库自己声明的
    Keep a Changelog。这里把三者钉在一起。"""
    skill = open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8").read()
    m = re.search(r"^version:\s*([0-9.]+)", skill, re.M)
    check("SKILL.md front-matter 有 version", bool(m), "缺 version 字段")
    if not m:
        return
    ver = m.group(1)
    major_minor = ".".join(ver.split(".")[:2])

    cl_path = os.path.join(ROOT, "CHANGELOG.md")
    if not os.path.exists(cl_path):
        # 本地 skill 目录（仅 SKILL.md + references + scripts）没有发布资产，
        # 与 run_tests.sh 的 IS_REPO 判定保持一致：跳过而非失败。
        check("CHANGELOG 版本一致（本地 skill 目录无 CHANGELOG，跳过）", True, "")
        return
    cl = open(cl_path, encoding="utf-8").read()
    heads = re.findall(r"^## \[([0-9.]+)\]", cl, re.M)
    check(f"CHANGELOG 含当前版本 [{ver}] 或 [{major_minor}]",
          ver in heads or major_minor in heads,
          f"SKILL={ver}，CHANGELOG 最新={heads[:3]}")

    for name in ("README.md", "README.en.md"):
        p = os.path.join(ROOT, name)
        if not os.path.exists(p):
            continue
        txt = open(p, encoding="utf-8").read()
        bm = re.search(r"badge/VERSION-([0-9.]+)-", txt)
        check(f"{name} 版本徽章与 SKILL 一致",
              bm is not None and bm.group(1) in (ver, major_minor),
              f"徽章={bm.group(1) if bm else '缺失'}，SKILL={ver}")


# ── 隐私：无本机绝对路径 ─────────────────────────────────────────
def test_no_machine_paths():
    pat = re.compile(r"/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/")
    allow = re.compile(r"/(Users|home)/(runner|example|user|yourname)/")
    hits = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
        for fn in filenames:
            if not fn.endswith((".py", ".sh", ".md", ".yml", ".yaml")):
                continue
            p = os.path.join(dirpath, fn)
            try:
                for i, line in enumerate(open(p, encoding="utf-8"), 1):
                    if pat.search(line) and not allow.search(line):
                        hits.append(f"{os.path.relpath(p, ROOT)}:{i}")
            except (OSError, UnicodeDecodeError):
                continue
    check("无本机绝对路径", not hits, f"{hits[:3]}")


# ── 示例命令不得写死技能目录（换宿主的普适性）─────────────────────
def test_skill_dir_not_hardcoded():
    """2026-09-18：SKILL.md §5 与 references/size-and-params.md 共 4 处把
    「技能目录 + /scripts/xxx.py」拼成绝对路径写死。两个问题：

      ① 本技能 §7 硬规则 4 自己写的是「路径名先 `find` 再引用」，示例却违反；
      ② 本技能不只装在 WorkBuddy 下——本机 ~/.qwenworkcn/skills/ 就有一份，
         别的宿主会装进自己的 skills 目录。照抄写死的命令在这些宿主上直接 404。

    改为在每个示例开头定义一次 `SKILL=<技能目录>`，其余一律 `$SKILL/scripts/…`，
    这样「换宿主先确认」只剩一个改动点，而不是散落四处。

    范围只限**指导性文档**（SKILL.md / references / sub-skills）：CHANGELOG.md 是
    历史记录，引用旧写法是它的职责，不该被这条门禁逼着改写事实。
    """
    pat = re.compile(r"skills/taxue-imagegen/scripts")
    docs = [os.path.join(ROOT, "SKILL.md")]
    for sub in ("references", "sub-skills"):
        for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, sub)):
            dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
            docs += [os.path.join(dirpath, fn) for fn in filenames
                     if fn.endswith(".md")]
    hits = []
    for p in docs:
        for i, line in enumerate(open(p, encoding="utf-8"), 1):
            if pat.search(line):
                hits.append(f"{os.path.relpath(p, ROOT)}:{i}")
    check(f"指导性文档不写死「技能目录+scripts」路径（查了 {len(docs)} 个 .md，"
          f"应改用 $SKILL/scripts/…）", not hits, f"{hits[:3]}")


# ── 常驻面 / 条件面的分层契约（2026-09-18 优化轮）───────────────────
def test_surface_layering():
    """2026-09-18：把「每轮都要付的常驻面」与「命中才读的条件面」拆开。

    实测背景：description 曾把 v1.5→v1.18 的变更史当正文带着（9,717 B，占本机
    82 个 skill 描述总长的 18.7%、中位数的 28 倍），SKILL.md 又把只在特定环境/
    诉求下才需要的云端后处理与豆包适配各带一份（合计占主体 25%）。拆开后要有
    门禁锁住三件事，否则下一次「顺手补一段」就会长回去：

      1. front-matter 必须是**合法 YAML**。老版本触发词段有两行顶格，折叠块
         提前结束，yaml.safe_load 直接 ScannerError —— 而宿主正是用 yaml.parse
         读 front-matter 的；旧检查只找 "description:" 字符串，全绿放行。
      2. 体积预算：description ≤ 2,000 B、SKILL.md ≤ 36,000 B。
      3. 条件面文件必须真的被接线：文件存在、SKILL.md 提到、且进了 §4 加载
         协议表——否则就是「搬出去没人读」。**覆盖全部 references/，
         不是只点名两个**（2026-09-18 泛化：原来写死两个文件名，
         explore-mode.md 与百相图两份提示词因此长期漏接线而门禁全绿）。
    """
    skill = open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8").read()
    lines = skill.splitlines()
    end = next(i for i, l in enumerate(lines[1:], 1) if l.strip() == "---")
    fm_lines = lines[1:end]
    dstart = next(i for i, l in enumerate(fm_lines) if l.startswith("description:"))

    # ── 1. YAML 合法性 ───────────────────────────────────────────
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        bad = [i for i in range(dstart + 1, len(fm_lines))
               if fm_lines[i] and not fm_lines[i][0].isspace()]
        check("折叠块内无顶格行（列 0 会提前终止块标量；未装 PyYAML，结构检查）",
              not bad, f"顶格行号（相对 front-matter）: {bad[:3]}")
    else:
        try:
            doc = yaml.safe_load("\n".join(fm_lines))
            check("front-matter 是合法 YAML 且 description 是字符串",
                  isinstance(doc, dict) and isinstance(doc.get("description"), str),
                  f"解析结果类型={type(doc).__name__}")
        except Exception as e:  # noqa: BLE001
            check("front-matter 是合法 YAML", False, f"{type(e).__name__}: {str(e)[:120]}")

    # ── 2. 体积预算 ──────────────────────────────────────────────
    desc_b = len("\n".join(fm_lines[dstart:]).encode())
    check(f"description ≤ {SURFACE_BUDGETS['description']} B（现 {desc_b} B，每轮常驻面）",
          desc_b <= SURFACE_BUDGETS["description"],
          "变更史写 CHANGELOG.md，不要放回 description")
    check(f"SKILL.md ≤ {SURFACE_BUDGETS['skill_md']} B（现 {len(skill.encode()):,} B，触发面）",
          len(skill.encode()) <= SURFACE_BUDGETS["skill_md"],
          "特定环境/诉求才需要的内容应下沉到 references/")

    # ── 3. 条件面接线 ────────────────────────────────────────────
    wired = {"references/jimeng-env.md": "豆包/即梦适配",
             "references/cloud-postprocess.md": "云端后处理"}
    proto = skill.split("## 4. 加载协议")[1].split("\n## 5.")[0] if "## 4. 加载协议" in skill else ""
    for rel, topic in wired.items():
        check(f"{rel} 存在", os.path.exists(os.path.join(ROOT, rel)), f"{topic}完整版缺失")
        check(f"SKILL.md 提到 {rel}", rel in skill, "搬出去了但没接线")
        check(f"§4 加载协议表含 {rel}", rel in proto, "命中该场景时读不到")

    # 条件面接线：原实现把 jimeng-env.md / cloud-postprocess.md 两个文件名写死在
    # 循环里，其余 13 个 references 只查「在 SKILL.md 提到过」——于是
    # explore-mode.md、crowd-100-faces-prompt-v1/v2.md 长期没进 §4 而门禁全绿。
    # 泛化成「每个 references/*.md 都必须在 §4 出现」：§4 就是那张场景表，
    # 不进表 = 命中该场景时读不到 = 搬出去等于删掉。
    refs = sorted(os.path.basename(p)
                  for p in glob.glob(os.path.join(ROOT, "references", "*.md")))
    unmentioned = [f for f in refs if f not in skill]
    check(f"references/ 无孤儿文件（{len(refs)} 个文件都在 SKILL.md 里被引用）",
          not unmentioned, f"未被引用: {unmentioned}")
    unwired = [f for f in refs if f not in proto]
    check(f"§4 加载协议表覆盖全部 references（{len(refs)} 个）", not unwired,
          f"未接线: {unwired}——搬出去了但没进 §4 场景表，命中该场景时读不到")


# ── 坑 → 检测层映射（配置到可验证单元的显式映射）────────────────────
def test_pitfall_coverage():
    """2026-09-18：给每个坑登记「在哪一层能拦住」，并反查实现，防止表变成空话。

    背景：`references/pitfalls.md` 有 33 个坑，其中 11 个能文本拦截、其余散在
    量测/去水印链/门禁/目检里。此前这份归属只存在于人的脑子里——新增一个坑，
    没人知道它到底有没有被拦；preflight 加一条规则，也没人知道该改哪一行。

    这里锁四件事：
      ① 每个坑都必须出现在映射表里（新增坑不登记就红）；
      ② 检测层只能是六个固定取值之一（防止随手写新层名）；
      ③ 写 `preflight` 的，`preflight.py` 里必须真有同名规则——**表不能比代码激进**；
      ④ 反过来，`preflight.py` 里出现的每个坑号也必须登记为 `preflight` 层——
         代码不能比表激进（新增规则不登记就红）。
    """
    pf_path = os.path.join(ROOT, "references", "pitfalls.md")
    text = open(pf_path, encoding="utf-8").read()
    pitfalls = set(int(m) for m in re.findall(r"^## 坑 ?(\d+)", text, re.M))

    sec = text.split("## 坑 → 检测层映射")[1] if "## 坑 → 检测层映射" in text else ""
    sec = sec.split("> 维护规则")[0]
    rows = {}
    for line in sec.splitlines():
        m = re.match(r"^\|\s*(\d+)\s*\|\s*`([^`]+)`\s*\|\s*(.+?)\s*\|", line)
        if m:
            rows[int(m.group(1))] = (m.group(2), m.group(3).strip().strip("`"))
    allowed = {"preflight", "postcheck", "去水印链", "门禁", "运行时", "目检"}

    check("映射表覆盖全部坑（每个坑都有检测层）", pitfalls and set(rows) == pitfalls,
          f"坑集合 {sorted(pitfalls)}，表里 {sorted(rows)}")
    bad_layer = {n: l for n, (l, _) in rows.items() if l not in allowed}
    check("检测层取值合法（六个固定层）", not bad_layer, f"非法层: {bad_layer}")

    # ①·乙 症状速查表：文件开篇承诺「按症状速查」，但 2026-09-18 前只列到坑 18，
    # 坑 22–35（去水印算法族 / 阈值重标 / 纸白 / 分材质填充）全缺——恰好是排障
    # 最费时间、单节最长的那批。检测层表有覆盖门禁、症状表却一直没有，这就是
    # 「门禁不对称导致静默漂移」。只认表格数据行（第二列是「坑 N」），
    # 不把正文里提到的坑号算进来，否则散文一句话就能把覆盖度刷满。
    sym = text.split("## 坑 → 检测层映射")[0]
    sym_pits = set(int(m) for m in
                   re.findall(r"^\|\s*[^|]+\|\s*坑 ?(\d+)\s*\|\s*$", sym, re.M))
    check(f"症状速查表覆盖全部坑（{len(pitfalls)} 个）", sym_pits == pitfalls,
          f"缺: {sorted(pitfalls - sym_pits)}——按症状查不到，只能整读 104 KB")

    # 反查实现：preflight 行必须对得上 preflight.py 里的规则
    pf = open(os.path.join(HERE, "preflight.py"), encoding="utf-8").read()
    pf_claimed = {n for n, (l, tok) in rows.items() if l == "preflight"}
    # 坑号在代码里有「坑1」「坑 24」两种写法，比对时统一去掉空白
    pf_flat = re.sub(r"\s+", "", pf)
    pf_real = set(int(m) for m in re.findall(r"坑(\d+)", pf_flat))
    missing = {n for n in pf_claimed if f"坑{n}" not in pf_flat}
    check("登记为 preflight 的坑在 preflight.py 里真有规则", not missing,
          f"表里写了但代码没有: {sorted(missing)}")
    # 「拦截点」列是给人按图索骥用的，写错等于指错路——同样反查
    for n, (layer, tok) in sorted(rows.items()):
        if layer == "preflight":
            check(f"坑{n} 的 preflight 拦截点「{tok}」在 preflight.py 里存在",
                  tok in pf_flat, "表里写了一个 preflight.py 里没有的规则名")
    unreg = pf_real - pf_claimed
    check("preflight.py 里出现的坑都在表里登记为 preflight", not unreg,
          f"代码里有规则但表里没登记: {sorted(unreg)}")

    # 反查实现：postcheck 行的 token 必须是真实存在的 reason 码或指标名
    pc = open(os.path.join(HERE, "postcheck.py"), encoding="utf-8").read()
    ms = open(os.path.join(HERE, "measure.py"), encoding="utf-8").read()
    # 只认真正挂在 findings 上的码，别把 argparse/局部元组也算进来
    codes = set(re.findall(
        r'(?:blockers|pendings|hints)\.append\(\(\s*"([a-z_]+)"', pc))
    metrics = set(re.findall(r'"(top_[a-z_%]+|near%|paper%|white%|R-B|sat|base)"', ms))
    for n, (layer, tok) in sorted(rows.items()):
        if layer == "postcheck":
            check(f"坑{n} 的 postcheck 拦截点「{tok}」真实存在",
                  tok in codes or tok in metrics,
                  f"既不是 reason 码（{sorted(codes)[:6]}…）也不是指标名")


# ── 父 SKILL.md ↔ verify 子技能的一致性（2026-09-18 审查轮新增）────
def test_skill_verify_consistency():
    """数值真源（父 SKILL.md §5）与判定口径（verify 子技能）必须**同进退**。

    实测漏洞：v1.19.0 校准把类型 B 的 white% blocker 撤了（202 张成品触发 82.2%），
    但 verify/SKILL.md §5 还挂着旧口径——两处数字打架没人拦，按子技能执行的
    Agent 会照旧误判重生（每张白扣 5–10 积分）。坑映射表有双向门禁，这对
    「父/子技能」却一直没有。这里把两边必须同时命中的关键词钉死：任何一侧
    删改、另一侧没跟上，门禁就红。同时锁住已撤口径不得回流 verify。
    """
    skill = open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8").read()
    verify = open(os.path.join(ROOT, "sub-skills", "verify", "SKILL.md"),
                  encoding="utf-8").read()
    sk, vf = re.sub(r"\s+", "", skill), re.sub(r"\s+", "", verify)

    shared = [
        ("near%<40", "类型 B 留白口径（旧 white% 窗口已撤）"),
        ("paper_white", "泛黄的处置入口（坑 33：重生改不了纸白偏色）"),
        ("1024x1792", "类型 D 法定尺寸（声明值，不符即 blocker）"),
        ("expect-cells", "类型 E 格数校验入口"),
        ("top_noise", "只作诊断的假 blocker（坑 27）"),
        ("R²", "水印自动门的双条件之一（高 amp 低 R² 不动手）"),
    ]
    for tok, why in shared:
        check(f"SKILL.md ↔ verify 一致：{tok}（{why}）",
              tok in sk and tok in vf,
              f"SKILL.md {'有' if tok in sk else '无'} / verify {'有' if tok in vf else '无'}"
              f"——两边必须同进退")

    check("verify 不再携带已撤口径 white%∈[30,65]",
          "30–65" not in verify and "white%∉[30,65]" not in vf,
          "旧 blocker 在 verify 复活（202 张成品实测触发 82.2%）")


def _entry_scripts():
    """本目录下「真有 __main__ 块」的入口脚本。

    判据必须是**顶格**的 `if __name__ == "__main__":`：_log.py 的模块 docstring
    里就有这句（当用法示例写着），用子串匹配会把它当成入口，于是「谁从没被调用过」
    里永远挂着一条假记录。`^` + re.M 刚好把缩进的那句排除掉。
    """
    scripts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = []
    for path in sorted(glob.glob(os.path.join(scripts_dir, "*.py"))):
        try:
            src = open(path, encoding="utf-8").read()
        except OSError:
            continue
        if re.search(r'^if __name__ == "__main__":', src, re.M):
            out.append((path, src))
    return out


def test_shell_var_braced_before_multibyte():
    """一类 bug：shell 里 `$var` 紧跟多字节字符时，必须写成 `${var}`。

    2026-09-23 实测（本轮唯一一次「在干净检出里跑」暴露出来的）：
      bash -c 'set -euo pipefail; kwfile=x; echo "缺失（$kwfile）"; echo AFTER'
      → 退出码 1，AFTER 不打印（静默死）；把 `$kwfile` 写成 `${kwfile}` 后正常。
    机制：部分 bash（本机 5.3.15）把紧跟 `$var` 的多字节字节当成变量名的一部分，
    变量名变成 `kwfile）` → `set -u` 判未绑定 → 整脚本退出 1。

    这个坑阴在**它只出现在未被走到的分支**里：那一行在 `else` 分支，
    只有「检出里没有 `_research/`」时才执行，而开发机上有 `_research/`，
    所以本地永远绿；干净检出（CI、或任何人 clone 下来）才踩。CI 目前没红，
    是因为 Ubuntu 那份 bash 不吃多字节——**这是运气，不是设计**：
    runner 的 bash 一升级，红的就是一个只在干净检出里跑的守卫步骤。

    判据：所有被 bash 执行的文件（`*.sh`、`.github/workflows/*.yml`）里，
    不得出现「未加花括号的 `$var` 紧跟非 ASCII 字节」。纯静态、可证伪、零误报
    （写 `${var}` 就过），全仓当前只有 1 处，已修。
    """
    import glob
    import re
    # HERE = scripts/，ROOT = 仓库根（两个都从 _harness 来，别自己再推一遍层级）
    pat = re.compile(rb"\$[A-Za-z_][A-Za-z0-9_]*[\x80-\xff]")
    offenders = []
    targets = sorted(glob.glob(os.path.join(HERE, "*.sh"))) + \
        sorted(glob.glob(os.path.join(ROOT, ".github", "workflows", "*.yml")))
    for path in targets:
        data = open(path, "rb").read()
        for m in pat.finditer(data):
            ln = data[:m.start()].count(b"\n") + 1
            offenders.append(f"{os.path.basename(path)}:{ln}")
    check("门禁确实扫到了 shell 文件（判据前提成立）", len(targets) >= 2,
          f"只扫到 {len(targets)} 个文件")
    check("shell 里 `$var` 紧跟多字节字符时都加了花括号", not offenders,
          "漏花括号：" + "、".join(offenders[:5]))


def test_test_modules_are_wired_exactly_once():
    """一类 bug：回归用例**重复定义**或**定义了却没接线**。

    两者都是静默的，而且恰好是这家仓库踩过的形状：
      · v1.20.1 之前 `test_preflight_quote_declaration` 定义了但没进 TESTS，
        于是它**从未跑过**——门禁不报错，只是不生效。
      · 2026-09-23 我在同一个文件里反复插入用例，把尾部整块复制了一遍：
        同名函数出现两次，Python 取**后定义**的那个，于是「刚写好的新用例」被旧版本
        静默顶掉（实测：新写的格数门禁跑的是被覆盖前的旧断言，还报了两个 FAIL）。
    两次都不是逻辑错，是接线错，而接线错只能靠静态判据兜。

    判据三条，逐文件施加：
      ① 不得有同名 `def test_*`（重复定义 = 后者静默覆盖前者）
      ② 每个 `def test_*` 都必须出现在该文件的 TESTS 里（不许有孤儿）
      ③ TESTS 里不得出现非测试函数（例如把 `_make_grid` 这种夹具写进了列表，
         运行时会以 TypeError 崩，或更糟——把夹具的返回值当成一个"通过"）
    """
    import ast
    tests_dir = os.path.dirname(os.path.abspath(__file__))
    dupes, orphans, strays = [], [], []
    files = [f for f in sorted(os.listdir(tests_dir))
             if f.startswith("test_") and f.endswith(".py")]
    for fn in files:
        path = os.path.join(tests_dir, fn)
        tree = ast.parse(open(path, encoding="utf-8").read())
        defs = [n.name for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
        seen, dup = set(), []
        for d in defs:
            if d in seen:
                dup.append(d)
            seen.add(d)
        if dup:
            dupes.append(f"{fn}: {sorted(set(dup))}")

        registered = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    getattr(t, "id", None) == "TESTS" for t in node.targets):
                registered = [e.id for e in node.value.elts if isinstance(e, ast.Name)]
        if registered is None:
            continue
        orphans += [f"{fn}: {d}" for d in defs if d not in registered]
        strays += [f"{fn}: {n}" for n in registered if n not in defs]

    check("测试用例没有重复定义（后者会静默覆盖前者）", not dupes, "；".join(dupes))
    check("每个 test_ 函数都接进了 TESTS（不许有从未跑过的用例）", not orphans,
          "孤儿：" + "、".join(orphans[:4]))
    check("TESTS 里只有测试函数（夹具混进去会改变运行语义）", not strays,
          "混入：" + "、".join(strays[:4]))


def test_description_covers_every_route():
    """description 是**唯一**决定「用户这么说会不会被路由到本技能」的东西。

    2026-09-23 实测覆盖账（22 条真实口吻的请求，含不熟悉的说法）发现三处零覆盖：
    `探索模式`（多风格扫描是独立工作流，用户说「先出五个风格看看」漏触发）、
    豆包/即梦环境（整条适配层没进 description）、平台署名水印（v1.21.0 的新能力）。
    已补齐；这里把它钉成**路由面下限**——将来再删 description 时不许把整条路由删掉。

    诚实边界：这是**覆盖判据，不是行为判据**，只保证「每条路由都有对应的触发词族」。
    行为侧的数字见 CHANGELOG 的「触发面的真实数据基线」与「路由行为也测了」两节：
      · 覆盖：本机 13,371 条用户消息里筛出 299 条真生图意图，258 条（86.3%）被现盘触发词命中；
      · 行为：44 条 + 13 条难例（不含触发词）+ 8 条「只含被剪词」探针，2–3 个 arm × 3 个模型，
        共 16 次独立运行；标签明确项上 precision 1.00 / recall 0.92–1.00；同单元格三次重复
        量出**噪声底 = 1/44 ≈ 2.3%**，A/B 差异落在噪声内；另测出**触发词表不是承重结构**
        （剪到 13 项仍在 49 条与 8 条剪词探针上全中），但按不对称风险不剪。详见 CHANGELOG 三轮。
    零覆盖必然漏触发，所以这条下限有牙；上限由上面那两个数字界住。
    """
    skill = open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8").read()
    fm = skill.split("---", 2)[1]
    desc = fm[fm.index("description:"):]

    # 路由面 → 至少一个必须出现在 description 里的关键词族
    routes = {
        "类型 A 海报": ("海报",),
        "类型 B 群像": ("插画", "群像"),
        "类型 C 包装": ("包装", "mockup"),
        "类型 D 分镜": ("分镜",),
        "类型 E 多格": ("多格", "九宫格"),
        "验收": ("验收",),
        "去水印": ("水印",),
        "探索模式": ("探索模式",),
        "豆包/即梦环境": ("豆包", "即梦"),
        "云端后处理": ("后处理",),
    }
    missing = [name for name, kws in routes.items()
               if not any(k in desc for k in kws)]
    check("description 覆盖每一条路由面（触发面下限）", not missing,
          "零覆盖：" + "、".join(missing))
    check("路由面清单本身没被写空（判据自检）", len(routes) >= 8,
          f"只剩 {len(routes)} 条，判据可能已失效")


def test_missing_dep_guard():
    """一类 bug：脚本碰了 cv2/numpy/PIL，却没接 _env 的「缺依赖说人话」。

    2026-09-23 实测：dewm_imprint.py（v1.21.0 新增）顶层直接 import cv2/numpy，
    彼时同族另外 23 个脚本都接了 _env，只有它漏了。后果是缺依赖时甩一屏 traceback，
    而 _env 存在的全部意义就是消掉这一屏——新脚本漏接属于**结构性问题**，
    靠人眼复查必然复发，故立门禁。

    判据（可证伪、不靠词表）：
      · 入口脚本（有 __main__ 块）、非 test_*.py、源码里出现 cv2/numpy/from PIL
      · ⇒ 必须出现 _env
    test_*.py 豁免：它们在**字符串**里提到这些包名（模拟缺依赖），并不真的 import。
    """
    offenders = []
    checked = 0
    for path, src in _entry_scripts():
        base = os.path.basename(path)
        if base.startswith("test_"):
            continue
        if not re.search(r"\b(?:cv2|numpy)\b|from PIL", src):
            continue
        checked += 1
        if "_env" not in src:
            offenders.append(base)
    check("依赖自检门禁确实覆盖到脚本", checked >= 15,
          f"只扫到 {checked} 个，判据可能已失效")
    check("碰重型依赖的入口脚本都接了 _env（缺依赖说人话）", not offenders,
          "漏接：" + "、".join(offenders[:3]))


def test_log_instrumentation():
    """一类 bug：新入口脚本忘了接本地使用日志（scripts/_log.py）。

    日志靠「每个入口脚本一行 _log.run(...)」采集。漏一个不会报错，只会让
    log_report.py 的「谁在用 / 谁从没被调用过」悄悄失真——**静默的数据缺口比
    报错更坏**（同 v1.20.1 的 runs.csv 错列：错得没有声音，正好废掉归因本身）。
    故按 _env 的同一模式立门禁。

    log_report.py 豁免：它是日志的**读者**，让它每次分析都往被分析的日志里写一行，
    等于自己改自己要看的数据。这条豁免写在这里，不藏在别处。
    """
    missing = [os.path.basename(p) for p, src in _entry_scripts()
               if os.path.basename(p) != "log_report.py" and "_log.run(" not in src]
    total = len([1 for p, _ in _entry_scripts() if os.path.basename(p) != "log_report.py"])
    check("日志接入门禁确实覆盖到入口脚本", total >= 25,
          f"只扫到 {total} 个，判据可能已失效")
    check("所有入口脚本都接了 _log.run（本地使用日志）", not missing,
          "漏接：" + "、".join(missing[:5]))

    # 名字必须与文件名一致（2026-09-23 加）。`_log.run("名字", main)` 的名字是**手写**的，
    # 而日志里的 script 字段就是它 —— 写错了不会报错，只会让 log_report 的统计**张冠李戴**，
    # 而它是后续所有「该改什么」判断的数据源。复制粘贴改脚本时最容易留下这种错。
    mismatched = []
    for path, src in _entry_scripts():
        stem = os.path.basename(path)[:-3]
        for m in re.finditer(r'_log\.run\(\s*"([^"]+)"', src):
            if m.group(1) != stem:
                mismatched.append(f"{os.path.basename(path)} 写的是 {m.group(1)!r}")
    check("_log.run 的脚本名与文件名一致（日志不许张冠李戴）", not mismatched,
          "；".join(mismatched[:3]))


def test_argparse_help_survives():
    """CLI 契约：任何用 argparse 的脚本，`--help` 都必须能打印出来。

    2026-09-23 实测（H2 批次出图时踩到）：dewm_imprint.py 的 `--roi` help 写了
    「默认右下角 15% x 12%」，而 argparse 会拿 help 文本做 %-格式化 →
    `TypeError: %x format: an integer is required, not dict`，`--help` 直接崩栈、
    退出码 1。help 里要显示百分号必须写成 `%%`。

    崩的是**帮助文本**而不是主流程，所以主流程实测全绿也照样带着这个缺陷
    ——同类只有 `--help` 这条路径能覆盖，故单独立一个门禁。

    判据只认「在 argparse 内部崩」（stderr 有 argparse.py 且退出码非 0）：
    某个脚本压根没定义 --help 不算这一类缺陷，不判失败。
    """
    import subprocess
    import sys
    from concurrent.futures import ThreadPoolExecutor

    scripts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    targets = []
    for path in sorted(glob.glob(os.path.join(scripts_dir, "*.py"))):
        try:
            src = open(path, encoding="utf-8").read()
        except OSError:
            continue
        if "argparse.ArgumentParser" in src:
            targets.append(path)

    def probe(path):
        # --help 要先 import 完才会崩在 argparse 上，而本目录脚本普遍 import
        # numpy/cv2，单个约 1–2 s；串行跑二十来个会把门禁拖到半分钟以上，
        # 故并发探测。超时给足（首次 import 冷启动）。
        r = subprocess.run([sys.executable, path, "--help"],
                           capture_output=True, text=True, timeout=120)
        blob = (r.stdout or "") + (r.stderr or "")
        if r.returncode != 0 and "argparse.py" in blob:
            last = [l for l in blob.strip().splitlines() if l.strip()][-1]
            return f"{os.path.basename(path)}: {last}"
        return None

    with ThreadPoolExecutor(max_workers=8) as ex:
        broken = [b for b in ex.map(probe, targets) if b]

    check("CLI help 门禁确实覆盖到 argparse 脚本", len(targets) >= 5,
          f"只扫到 {len(targets)} 个，判据可能已失效")
    check("所有 argparse 脚本 --help 不在 argparse 内部崩溃", not broken,
          "；".join(broken[:3]))

    # 一类 bug：**没有 argparse 的入口脚本会默默忽略 --help 并直接把活干了**。
    # 2026-09-23 实测两例：`build_storyboard_ink.py --help` 真写出 9 个 prompt 文件、
    # `test_jimeng.py --help` 跑完整套 43 项测试。一个「问怎么用」的动作把活干了，
    # 比报错更糟——调用方以为只是在看帮助。
    # 判据：入口脚本要么用 argparse（--help 由它接管），要么源码里显式认 -h/--help。
    silent = []
    for path, src in _entry_scripts():
        base = os.path.basename(path)
        if "argparse.ArgumentParser" in src:
            continue
        if '"-h"' in src or "'-h'" in src or '"--help"' in src or "'--help'" in src:
            continue
        silent.append(base)
    check("无 argparse 的入口脚本也认 --help（不默默干活）", not silent,
          "忽略 --help：" + "、".join(silent[:4]))


def test_log_report_dual_count():
    """码频次必须同时给「按行」与「按图」，且批次按 note 聚合。

    2026-09-23 自我修正：我先前把 `text_unverified` 那 12 行读成「一次批量扫描被记成
    十几次失败」，理由是 9 行落在同一分钟。**结论是错的**——12 行落在 **12 个不同的
    文件**上，那就是 12 张图各自失败，计数没错；错的是把它当 9 次独立事件去排优先级。
    真正存在重复计入的是 `grid_diag`（按行 7 / 按图 3 = 2.3x，来自同图重复量测与
    当时还没修的「同行两个同名码」）。

    于是这里钉住三件事：① 两个口径都给，比值 >1 才是重复的信号；
    ② 批次用 note 聚合，行列数与图数分开给（一个批次 = 一个待解决问题）；
    ③ note 空值率算出来——空 note 的行没法归因到风格，风格库就回流不了。
    """
    lr = load("log_report")
    runs = [
        {"file": "a.png", "verdict": "pending", "track": "A", "reason": "grid_diag", "note": "批1"},
        {"file": "a.png", "verdict": "pending", "track": "A", "reason": "grid_diag", "note": "批1"},
        {"file": "b.png", "verdict": "pass", "track": "A", "hint": "grid_diag", "note": "批1"},
        {"file": "c.png", "verdict": "blocker", "track": "A", "reason": "txt", "note": ""},
    ]
    S = lr.summarize([], runs)
    # 夹具：a.png 被量了两次（各出一条 grid_diag）+ b.png 一条 hint 也是 grid_diag
    #        → 按行 3；a 与 b 共 2 张图 → 按图 2（a 的那两次被折成 1）
    check("按行如实计入重复量测（3 行）", S["codes"]["grid_diag"] == 3,
          f"实际 {S['codes']['grid_diag']}")
    check("按图把同一张图的重复折成 1（3 行 / 2 图，比值 1.5x 才看得见重复）",
          S["code_files"]["grid_diag"] == 2, f"实际 {S['code_files']['grid_diag']}")
    check("批次按 note 聚合，行列数与图数分开",
          S["batches"]["批1"]["rows"] == 3 and S["batches"]["批1"]["files"] == 2,
          f"实际 {S['batches']['批1']}")
    check("note 空值率算出来（空 note 没法归因到风格）",
          abs(S["note_empty_rate"] - 0.25) < 1e-9, f"实际 {S['note_empty_rate']}")



def test_horizontal_skeleton_passes_preflight():
    """入库的横版骨架必须**自己填得出来、且过得了本技能自己的 preflight**。

    2026-09-23 实测抓到的真事故：我第一版入库的 H 系骨架取自 `meta_prompt_h9.md` 的
    **文档版**，而 11 张实测 pass 的图用的是 `build_h9.py` 的 `TEMPLATE`（生产版）——
    两版槽位名相同，但文档版少三处硬化。**从文档版骨架 + §三 的表机械组装出来的提示词，
    跑 preflight 得 1 阻断**（坑 14A「主标题穿插场景缺『只出现一次』」），
    换生产版后阻断清零。也就是说：**照我入库的东西填，过不了自己的预检**。

    这条门禁把那条验收路径固化下来：按文件里写的骨架与表填一个代表性样本
    （取 §三 的 02 青花），跑真 `preflight.py`，**要求 0 阻断**（提醒可以有：
    坑 16 长度是已知提醒，历史完整模板亦有通过案例）。
    判据是 preflight 的退出码——它是真工具的真判定，不是我自己造的夹具。
    """
    import re as _re
    import subprocess as _sp
    import sys as _sys
    import tempfile
    ref = os.path.join(ROOT, "references", "poster-horizontal-series.md")
    text = open(ref, encoding="utf-8").read()
    m = _re.search(r"## 一、骨架[^\n]*\n+.*?```\n(.*?)\n```", text, _re.S)
    check("能定位到横版骨架（判据前提成立）", bool(m), "§一 骨架块没找到")
    if not m:
        return
    skel = m.group(1)

    def row(sec, num):
        body = text.split(sec, 1)[1].split("\n##", 1)[0]
        for line in body.splitlines():
            if line.startswith(f"| {num} |"):
                return [c.strip().strip("*") for c in line.strip("|").split("|")]
        return None

    a, b = row("### 3.1 主槽位", "02"), row("### 3.2 场景槽位", "02")
    check("能取到 02 青花的槽位行", bool(a and b), f"表A={a} 表B={b}")
    if not (a and b):
        return
    filled = (skel.replace("{视觉风格}", "明代青花瓷釉下彩 × 当代博物馆出版物")
                   .replace("{内容主题}", b[1]).replace("{表达意图}", b[2])
                   .replace("{主体形象}", b[3]).replace("{背景元素}", b[4])
                   .replace("{主色}", a[2]).replace("{强调色}", a[3]).replace("{纸底色}", a[4])
                   .replace("{英文主标题}", a[5]).replace("{主标题逐字母}", "、".join(a[5]))
                   .replace("{中文短句}", a[6]).replace("{中文逐字}", "、".join(a[6]))
                   .replace("{英文短句}", a[7]))
    check("骨架槽位名与表能对上（无残留未替换的槽位）",
          "{" not in filled, "还有没被替换的槽位，说明表与骨架的槽位名不一致")
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "h02.txt")
        open(f, "w", encoding="utf-8").write(filled)
        r = _sp.run([_sys.executable, os.path.join(HERE, "preflight.py"), f],
                    capture_output=True, text=True)
        blockers = [l for l in r.stdout.splitlines() if l.startswith("❌")]
        check("填出来的横版提示词过得了本技能自己的 preflight（0 阻断）",
              not blockers, "；".join(l[:70] for l in blockers[:3]))

    # ── 复古宣传画那支的陷阱：槽位与结构标签**都用【】** ──────────────
    # 「把所有【】替换掉」会砸掉骨架的结构标签（画幅/配色/质感…）。
    # 这里按 §6.2 的表只替换那 5 个槽位，并断言 8 个结构标签**原样还在**。
    r6 = _re.search(r"## 六、复古宣传画[^\n]*\n+.*?```\n(.*?)\n```", text, _re.S)
    check("能定位到复古宣传画骨架（判据前提成立）", bool(r6), "§六 骨架块没找到")
    if not r6:
        return
    skel6 = r6.group(1)
    body6 = text.split("### 6.2 槽位说明", 1)[1].split("\n###", 1)[0]
    table_slots = _re.findall(r"^\| (【[^】]+】) \|", body6, _re.M)
    in_skel = set(_re.findall(r"【[^】]+】", skel6))
    # **非空前置**（被反向验证逼出来的）：第一版把这些断言写成「表里的槽位 ⊆ 骨架里的【】」，
    # 而当时 §6.2 的表**只有表头、没有数据行**——空集对任何集合都是子集，
    # 于是后面几条**全部空转通过**，**文档缺陷与门禁空转互相掩盖**。
    # 所以先断言「真的取到了槽位行」，空表必须红。
    check("§6.2 的表真的取到了槽位行（否则下面的子集断言会空转通过）",
          len(table_slots) >= 4, f"只取到 {len(table_slots)} 个：{table_slots}")
    labels = sorted(in_skel - set(table_slots))
    check("§6.2 声明的槽位都真的在骨架里（表与骨架不脱节）",
          set(table_slots) <= in_skel, f"表里有但骨架没有：{sorted(set(table_slots) - in_skel)}")
    check("骨架里【】确实混着结构标签（所以「全替换」是陷阱，文档必须写明）",
          len(labels) >= 5, f"标签只有 {labels}——若不再混用，文档里那条警告该删")
    filled6 = skel6
    for k in table_slots:
        filled6 = filled6.replace(k, "示例值")
    check("只替换那 5 个槽位后，结构标签一个不少",
          all(k in filled6 for k in labels) and not (set(table_slots) & set(_re.findall(r"【[^】]+】", filled6))),
          "要么标签被误删，要么槽位没换干净")



def test_local_artifacts_excluded_from_release():
    """只留本机的归档/运行产物，不得被 `sync_release.sh` 同步进发布仓。

    2026-09-23：`EXCLUDES` 里写着 `--exclude='_prompts'`，而 rsync 的模式**不是前缀匹配**，
    匹配不到 `scripts/_prompts_archive/`；`scripts/_calib_cache/` 更是压根没列；
    `scripts/wm_alpha_1024.npz.bak-*`（模板的本地备份）同样没列。
    三者都在 `.gitignore` 里（= 明确「只留本机」），却会被 rsync 带进发布检出——
    `_prompts_archive` 装的正是「已验证风格的提示词原文」，泄漏面是资产本身。

    判据取 **`.gitignore` 里锚定在同步树上的模式**（以 `scripts/` / `references/` /
    `sub-skills/` 开头），逐个要求 `EXCLUDES` 里有能匹配它的模式。
    **不用「实际存在的被忽略文件」做输入**：干净检出（CI、新克隆）里那些目录本就
    还不存在，按存在性判定会空转或假红——门禁必须在「这台机器还没产生任何本地
    产物」时也成立，否则它只在开发机上有效。
    """
    import fnmatch
    sh = open(os.path.join(ROOT, "scripts", "sync_release.sh"), encoding="utf-8").read()
    m = re.search(r"EXCLUDES=\((.*?)\)", sh, re.S)
    pats = re.findall(r"--exclude='([^']+)'", m.group(1)) if m else []
    check("能解析出 sync_release.sh 的 EXCLUDES", bool(pats),
          "正则失配——门禁本身失效了，不是内容没问题")

    gi_path = os.path.join(ROOT, ".gitignore")
    check("仓库根有 .gitignore", os.path.exists(gi_path), "无从判定哪些是本地产物")
    if not os.path.exists(gi_path):
        return
    anchored = []
    for line in open(gi_path, encoding="utf-8"):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith(("scripts/", "references/", "sub-skills/")):
            anchored.append(s.rstrip("/"))
    check("判据前提：.gitignore 里有锚定到同步树的模式", bool(anchored),
          "一条都没有时本条会空转通过 —— 覆盖缺口要说出来")

    def covered(entry):
        # 与 rsync 的语义对齐：EXCLUDES 写的是「任意层级的这个名字」
        last = entry.split("/")[-1]
        return any(fnmatch.fnmatch(last, p) or fnmatch.fnmatch(entry, p) for p in pats)

    leaked = [e for e in anchored if not covered(e)]
    check("锚定在同步树上的本地产物都被排除在发布同步之外", not leaked,
          "会被 rsync 带进发布仓：" + "、".join(leaked[:5]) + "（在 sync_release.sh 的 EXCLUDES 里补上）")


def test_modules_have_file_header():
    """每个 `.py` 的首条语句必须是模块 docstring —— 不许把函数写到文件头前面。

    2026-09-23：`tests/test_docs_gates.py` 的 `test_referenced_files_exist` 曾被写在
    **第 1 行**，shebang、coding cookie、模块 docstring 与全部 import 都在它下面第 48 行起。
    定义在前不影响运行（函数体到调用时才求值），所以没有任何一条测试会红——但
    `__doc__` 成了 None、PEP-263 coding 声明被忽略、shebang 失效。是「合并不小心、
    头被顶到后面」这类事故，靠人眼扫不出来。

    判据用 `ast`（首条语句是不是字符串字面量），不看字符串排版，稳且零误报。
    """
    import ast
    files = sorted(glob.glob(os.path.join(HERE, "*.py"))) + \
        sorted(glob.glob(os.path.join(HERE, "tests", "*.py")))
    check("判据前提：扫到了脚本文件", len(files) >= 20, f"只扫到 {len(files)} 个")
    bad = []
    for p in files:
        src = open(p, encoding="utf-8").read()
        try:
            tree = ast.parse(src)
        except SyntaxError as e:
            bad.append(f"{os.path.basename(p)}（语法错误：{e}）")
            continue
        if ast.get_docstring(tree) is None:
            bad.append(os.path.basename(p))
    check("每个脚本的首条语句都是模块 docstring（文件头没被顶到后面）", not bad,
          "缺少文件头：" + "、".join(bad[:5]))


TESTS = [test_referenced_files_exist, test_horizontal_skeleton_passes_preflight, test_skill_frontmatter_window_free, test_log_report_dual_count, test_doc_consistency,
         test_version_consistency, test_surface_layering, test_pitfall_coverage,
         test_no_machine_paths, test_skill_verify_consistency,
         test_skill_dir_not_hardcoded, test_shell_var_braced_before_multibyte,
         test_repo_root_whitelist,
         test_test_modules_are_wired_exactly_once,
         test_description_covers_every_route,
         test_missing_dep_guard,
         test_log_instrumentation, test_argparse_help_survives,
         test_local_artifacts_excluded_from_release,
         test_modules_have_file_header]
