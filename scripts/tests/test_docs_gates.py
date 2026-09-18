#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文档与门禁域：front-matter（坑 31）、文档一致性、版本三方一致、
常驻面分层契约、坑→检测层映射、隐私扫描，以及 SKILL.md ↔ verify 子技能一致性。"""
import glob
import os
import re

from _harness import HERE, ROOT, SURFACE_BUDGETS, check


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


TESTS = [test_skill_frontmatter_window_free, test_doc_consistency,
         test_version_consistency, test_surface_layering, test_pitfall_coverage,
         test_no_machine_paths, test_skill_verify_consistency,
         test_skill_dir_not_hardcoded]
