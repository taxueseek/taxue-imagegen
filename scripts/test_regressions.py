#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_regressions.py — taxue-imagegen 断言式回归测试。

每个断言对应一个已修的真实缺陷（坑 23–26 与 P0 修复），
用「构造输入 → 断言输出」而不是「能跑不报错」，
避免再次出现「本地全绿、CI 全红」或「测试通过但测错了对象」。

用法：
  python3 scripts/test_regressions.py      # 退出码 0=全过，1=有失败
  bash scripts/run_tests.sh                # 集成进总套件

设计原则：
  1. 只测可确定性判定的行为（正则命中、退出码、路径解析），不做图像主观判定。
  2. 每个 case 自带「为什么」，失败信息直接说明违反了什么。
  3. 不依赖网络、不依赖 WorkBuddy、不依赖仓库外的图片。
"""
import glob
import importlib.util
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# ── 常驻面 / 触发面体积预算（唯一真源；2026-09-18 定）────────────────
# 定这两个数的理由：优化轮把 description 从 9,717 B（占本机 82 个 skill 描述总长
# 的 18.7%、中位数的 28 倍）压到 1,786 B；SKILL.md 从 52,317 B 压到 34,039 B。
# 预算不是「刚好等于现状」，而是留约 6% 余量挡住回涨——真要突破，请连同理由
# 一起改这里，不要为了通过而调大。
SURFACE_BUDGETS = {"description": 2000, "skill_md": 36000}

_results = []


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check(label, cond, why=""):
    _results.append((bool(cond), label, why))
    mark = "ok  " if cond else "FAIL"
    print(f"  {mark} {label}" + (f"  <- {why}" if not cond and why else ""))


# ── 坑 23：preflight 词边界（误报与漏报） ──────────────────────────
def test_preflight_word_boundary():
    pf = load("preflight")

    # 误报：这些词含色相词子串，但语义无关，不得报坑1
    for t in ("a managed crowd", "a staged scene", "damaged paper",
              "screaming colors", "a swarm of bees",
              "the only warmth the whole sequence allows"):
        hits = [w for w in pf.HUE_WORDS if re.search(w, t, re.I)]
        check(f"误报-{t[:28]!r} 不报色相", not hits, f"命中 {hits}")

    # 真阳性：必须仍报
    for t in ("warm ink tone", "aged paper texture", "cream background",
              "米白底", "做旧纸面"):
        hits = [w for w in pf.HUE_WORDS if re.search(w, t, re.I)]
        check(f"真阳性-{t[:20]!r} 报色相", bool(hits), "漏报")

    # 漏报：含 ban/no 的无关词不得被当否定语境
    for t in ("banner with aged texture", "urban vintage poster"):
        check(f"否定词边界-{t[:24]!r} 不误放行", not pf.NEGATION.search(t),
              "被当作否定语境，真实违规会漏报")

    # 类型 D 结构标签不得触发坑11
    d_prompt = "vertical 9:16 storyboard\n\nSTYLE LOCK (identical): x\n\nCHARACTER LOCK: y"
    findings = pf.check(d_prompt, "D")
    check("类型 D 结构标签不触发坑11",
          not any(pit == "坑11" for _, pit, _ in findings),
          f"误报 {[p for _, p, _ in findings]}")


# ── 坑 24：槽位检测覆盖 {} 与【】 ─────────────────────────────────
def test_preflight_slot_detection():
    pf = load("preflight")
    for text, label in (("画一张{视觉风格}的海报", "半角 {}"),
                        ("棚拍包装【三比四】竖幅", "全角 【】")):
        findings = pf.check(text, "A")
        check(f"槽位检测-{label}",
              any(pit == "槽位" for _, pit, _ in findings),
              "未拦截未填槽位")
    # 类型 C 真实模板必须被拦
    c_md = os.path.join(ROOT, "references", "packaging-editorial.md")
    if os.path.exists(c_md):
        text = open(c_md, encoding="utf-8").read()
        m = re.search(r"^```\n(.*?)^```$", text, re.S | re.M)
        if m:
            findings = pf.check(m.group(1), "C")
            check("类型 C 模板【】槽位被拦截",
                  any(pit == "槽位" for _, pit, _ in findings),
                  "17 个未填槽位静默放行（坑 24 回归）")


# ── 坑 5：文案引号声明后放行（2026-09-12）──────────────────────────
def test_preflight_quote_declaration():
    """模板用「」声明文案是常规写法。全文声明「不出现引号字符」时放行，
    未声明时照旧拦截——放行不得变成漏检。"""
    pf = load("preflight")
    undeclared = "画面有中文主标题「执念」"
    declared = undeclared + "\n主标题与副标题内容里不出现任何引号字符。"
    hits_bad = [m for m in pf.check(undeclared, "A") if m[1] == "坑5"]
    hits_ok = [m for m in pf.check(declared, "A") if m[1] == "坑5"]
    check("坑5-未声明引号仍拦截", bool(hits_bad), "放行逻辑把漏检也放过了")
    check("坑5-已声明引号放行", not hits_ok,
          f"声明「不出现引号字符」后仍被拦：{hits_ok[:1]}")


# ── preflight track 支持 A/B/C/D/E + 尺寸表 ──────────────────────
def test_preflight_tracks_and_sizes():
    pf = load("preflight")
    check("TRACKS 含 A/B/C/D/E", {"A", "B", "C", "D", "E"} <= set(pf.TRACKS),
          f"实际 {pf.TRACKS}")
    check("TESTED_SIZES 含 1024x1792", "1024x1792" in pf.TESTED_SIZES,
          "类型 D 法定画幅会误报 WARN")
    r = subprocess.run([sys.executable, os.path.join(HERE, "preflight.py"),
                        "-", "--track", "C"], input="x", capture_output=True, text=True)
    check("preflight --track C 可用", r.returncode in (0, 1),
          f"rc={r.returncode}")
    r = subprocess.run([sys.executable, os.path.join(HERE, "preflight.py"),
                        "-", "--track", "E"], input="x", capture_output=True, text=True)
    check("preflight --track E 可用", r.returncode in (0, 1),
          f"rc={r.returncode}")


# ── 坑 25：覆盖守卫（大小写 / 硬链接） ────────────────────────────
def test_overwrite_guard():
    io = load("dewm_io")
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "a.png")
        open(src, "wb").close()

        # 大小写变体
        t = io.safe_target(src, os.path.join(d, "A.PNG"))
        check("覆盖守卫-大小写变体",
              os.path.normcase(os.path.realpath(t)) != os.path.normcase(os.path.realpath(src)),
              "A.PNG 与 a.png 在 APFS 上同一文件，会被覆盖")

        # 硬链接
        alias = os.path.join(d, "alias.png")
        try:
            os.link(src, alias)
            t2 = io.safe_target(src, alias)
            safe = True
            try:
                safe = not os.path.samefile(t2, src)
            except OSError:
                pass
            check("覆盖守卫-硬链接", safe, "alias 与源同 inode，会被覆盖")
        except OSError:
            check("覆盖守卫-硬链接", True, "本文件系统不支持硬链接，跳过")

        # 同目录 --out 必须重定向
        t3 = io.safe_target(src, d)
        check("覆盖守卫-同目录重定向", "_clean" in t3, f"未重定向：{t3}")

        # --inplace 是唯一例外
        t4 = io.safe_target(src, None, inplace=True)
        check("覆盖守卫-inplace 显式允许",
              os.path.realpath(t4) == os.path.realpath(src), "显式覆盖应放行")


# ── postcheck verdict 三档（行为断言，不查源码字符串） ────────────
def test_postcheck_verdict():
    """2026-09-09 重写：原实现用 `'C' in stdout` / `'"pending"' in 源码`
    断言，属于「查源码里有没有这个词」，把 C/D 从 choices 删掉照样 PASS
    （实测确认）。改为构造图片跑真实进程，断言退出码。"""
    from PIL import Image
    pc = os.path.join(HERE, "postcheck.py")

    def run(*extra, img=None, track="A"):
        with tempfile.TemporaryDirectory() as d:
            if img is None:
                img = os.path.join(d, "white.png")
                Image.new("RGB", (1024, 1536), (252, 252, 252)).save(img)
            r = subprocess.run(
                [sys.executable, pc, img, "--track", track, "--no-log", *extra],
                capture_output=True, text=True)
            return r

    # 近白底 + 文字 ok → pass（rc 0）
    r = run("--text", "ok")
    check("postcheck 近白底+ok → pass(rc0)", r.returncode == 0,
          f"rc={r.returncode} {r.stdout[-120:]}")

    # 不传 --text → pending（rc 3），不得记成 pass
    r = run()
    check("postcheck 无 --text → pending(rc3)", r.returncode == 3,
          f"rc={r.returncode} 未核对文字却记了 pass")

    # --text bad → blocker（rc 1）
    r = run("--text", "bad")
    check("postcheck --text bad → blocker(rc1)", r.returncode == 1,
          f"rc={r.returncode}")

    # 白底泛黄 → **pending + paper_warm**（2026-09-18 契约反转）
    # 原契约是「泛黄 → blocker（允许定向重生）」。校准实测推翻了它：坑 33 证明
    # 重生改不了纸白偏色（同一提示词两版纸白都是 R-B +5.5），判 blocker 等于每张
    # 白扣 5–10 积分。意图必须保留——泛黄图**不得静默记 pass**；方向换成
    # 「pending + 指向 paper_white.py 这个免费确定性修复」。
    with tempfile.TemporaryDirectory() as d:
        img = os.path.join(d, "yellow.png")
        Image.new("RGB", (1024, 1536), (254, 252, 245)).save(img)
        r = run("--text", "ok", img=img)
        check("带泛黄的白底图不再判 blocker（重生改不了偏色）", r.returncode != 1,
              f"rc={r.returncode} 仍在逼着重生")
        check("带泛黄的白底图不得计 pass（rc3 + paper_warm）",
              r.returncode == 3 and "paper_warm" in r.stdout and "paper_white" in r.stdout,
              f"rc={r.returncode} stdout 里没有 paper_warm/paper_white 指向")

    # 纸底暖色 = 材质色，不是缺陷：既不许 pass 变 blocker，也不该报 pending
    with tempfile.TemporaryDirectory() as d:
        img = os.path.join(d, "paper.png")
        Image.new("RGB", (1024, 1536), (236, 232, 222)).save(img)
        r = run("--text", "ok", img=img)
        check("纸底暖色不判 blocker", r.returncode != 1, f"rc={r.returncode} 纸底风格被误杀")
        check("纸底暖色只给提示（paper_warm_hint）",
              "paper_warm_hint" in r.stdout and "paper_warm]" not in r.stdout,
              "纸底被当成需要处理的偏色")

    # C/D 必须被 argparse 接受（rc=2 才是「参数不支持」）
    for t in ("C", "D"):
        r = run("--text", "ok", track=t)
        check(f"postcheck --track {t} 可用", r.returncode in (0, 1, 3),
              f"rc={r.returncode} 类型 {t} 无法验收")


# ── 面向用户的 CLI 必须 --help 可用（catch argparse 崩溃类缺陷） ────
CLI_ENTRYPOINTS = [
    "measure.py", "postcheck.py", "preflight.py", "fill_meta.py",
    "dewm_v10.py", "pick_wm.py", "audit_wm.py", "explore.py",
    "build_storyboard.py", "rmwm_light.py",
]


def test_cli_help():
    """2026-09-09 新增：measure.py 的 help 串含裸 `%`（"顶部 25% 留白"），
    argparse 走 %-格式化时抛 ValueError —— 任何 Python 版本、连正常出图路径
    一起崩（main() 里 add_argument 就炸）。原冒烟测试只 import 模块，
    抓不到这类「CLI 根本起不来」。这里只测面向用户的入口；
    基准/诊断脚本（bench_*/probe_k_bias/metric_flat）按设计要传图或环境变量，
    `--help` 不是它们的契约，故排除。"""
    for base in CLI_ENTRYPOINTS:
        f = os.path.join(HERE, base)
        if not os.path.exists(f):
            continue
        r = subprocess.run([sys.executable, f, "--help"],
                           capture_output=True, text=True, timeout=30)
        check(f"--help 可用：{base}", r.returncode == 0,
              f"rc={r.returncode} {(r.stderr or '').strip()[-140:]}")


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


# ── 坑 27：top_noise 不得再当 blocker（纸纹假阳性） ──────────────
def test_top_noise_not_blocker():
    """2026-09-09 实测：13/13 张真实海报 top_noise ≥29（含已验收成品 50.1），
    阈值 6 无区分力，却挂在 blocker 上（= 允许一次定向重生 = 再扣 5-10 积分）。
    构造「中性底 + 细密织纹」的图：std 高但颜色中性、顶部未被实体侵入，
    必须不被 top_noise 单独判 blocker。"""
    from PIL import Image
    import random
    random.seed(0)
    W, H = 1024, 1536
    im = Image.new("RGB", (W, H), (250, 250, 250))
    px = im.load()
    for y in range(H):
        for x in range(0, W, 2):
            v = 250 + random.choice((-14, -7, 0, 7, 14))
            px[x, y] = (v, v, v)
    with tempfile.TemporaryDirectory() as d:
        img = os.path.join(d, "textured.png")
        im.save(img)
        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "postcheck.py"), img,
             "--track", "A", "--top", "--text", "ok", "--no-log"],
            capture_output=True, text=True)
        check("坑27 中性织纹底不被 top_noise 判 blocker",
              "top_noise" not in r.stdout or "留白被画成实体" not in r.stdout,
              f"仍按 top_noise 判 blocker：{r.stdout[-200:]}")

    # 源码层护栏：阈值不得再回到 blocker 分支
    src = open(os.path.join(HERE, "postcheck.py"), encoding="utf-8").read()
    body = src.split("def measure_findings", 1)[1].split("def export_textband", 1)[0]
    check("坑27 postcheck 不再用 top_noise>=6 判 blocker",
          "top_noise" not in body or ">=" not in body.split("top_noise")[1][:40],
          "top_noise 阈值又回到 blocker 分支")


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


# ── 类型 C 机械填槽 ──────────────────────────────────────────────
def test_fill_meta_track_c():
    fm = os.path.join(HERE, "fill_meta.py")
    r = subprocess.run([sys.executable, fm, "C", "--list"],
                       capture_output=True, text=True)
    check("fill_meta C --list 可用", r.returncode == 0 and "槽位" in r.stdout,
          f"rc={r.returncode}")

    sets = ["--set", "三比四=三比四", "--set", "浅灰/中灰=浅灰",
            "--set", "三分之二/四分之三=三分之二",
            "--set", "形态+材质+物理细节：褶皱/厚度/贴地承重=哑光自立纸袋",
            "--set", "哪个面=正面", "--set", "单色/双专色=单色",
            "--set", "纸材/涂层=未涂布哑光纸", "--set", "一/两=一",
            "--set", "色A=深焙棕", "--set", "+色B=",
            "--set", "一个隐喻物，一句话说死=冒烟火山",
            "--set", "跟随曲面/褶皱/压纹=跟随褶皱",
            "--set", "词1=SLOW", "--set", "词2=ROAST",
            "--set", "品类英文=COFFEE", "--set", "规格=250G"]
    r2 = subprocess.run([sys.executable, fm, "C"] + sets, capture_output=True, text=True)
    check("fill_meta C 组装成功", r2.returncode == 0, f"rc={r2.returncode} {r2.stderr[:120]}")
    check("fill_meta C 无残留【】槽位", "【" not in r2.stdout,
          "仍有未填槽位")
    check("fill_meta C 单专色清掉空括号", "（）" not in r2.stdout and "()" not in r2.stdout,
          "残留空括号（坑：单专色时 【+色B】 留空会留下（））")
    check("fill_meta C 文案逐字保留", "SLOW" in r2.stdout and "ROAST" in r2.stdout,
          "品牌名丢失")

    # 缺槽必须报错
    r3 = subprocess.run([sys.executable, fm, "C", "--set", "词1=X"],
                        capture_output=True, text=True)
    check("fill_meta C 缺槽报错", r3.returncode == 2,
          f"缺槽未报错 rc={r3.returncode}")


# ── 可解性门控（近白底不该硬解） ─────────────────────────────────
def test_solvability_guard():
    import numpy as np
    V10 = load("dewm_v10")
    V8 = load("dewm_v8")

    W, H = 1024, 1792
    a, (x0, y0) = V8.load_template(W, H)
    ah, aw = a.shape[:2]

    # 近白底：水印不可见也不可解 → 必须 no-op（返回原图）
    gt = np.full((H, W, 3), 252, np.uint8)
    out, st = V10.remove_watermark(gt)
    check("可解性门控-近白底 no-op",
          st.get("skipped") is not None and np.array_equal(out, gt),
          f"未跳过：{st.get('skipped')}")

    # 中灰底：可解 → 不得跳过
    gt2 = np.full((H, W, 3), 180, np.uint8)
    alpha = np.clip(1.0 * a[:, :, None], 0, 0.99)
    sub0 = gt2[y0:y0 + ah, x0:x0 + aw]
    wm = gt2.astype(np.float32).copy()
    wm[y0:y0 + ah, x0:x0 + aw] = alpha * 255.0 + (1 - alpha) * sub0.astype(np.float32)
    wm = np.clip(wm, 0, 255).astype(np.uint8)
    _, st2 = V10.remove_watermark(wm)
    check("可解性门控-中灰底正常处理",
          st2.get("skipped") is None, f"误跳过：{st2.get('skipped')}")

    # 关闭门控时近白底也应硬解（供 A/B 用）
    _, st3 = V10.remove_watermark(gt, guard=False)
    check("可解性门控可关闭", st3.get("skipped") is None, "guard=False 仍跳过")



# ── 坑 28：选版必须同时看「残留」与「结构损伤」 ──────────────────
def test_pick_wm_damage_aware():
    """2026-09-12 实测：pick_wm 旧判据（纯 |amp|）选了 v7 整区 inpaint，
    残留 amp -0.20 判 CLEAN，画面却把水印压着的黑色图形整块啃掉。

    判据 = 候选在**笔画核心区**偏离「反解族结构参照」多少。构造合成图验证：
      结构化内容 → inpaint 偏离大、必须被罚，总分翻转
      纯平底     → 没有结构可毁，不得被罚
      只改抗锯齿边缘 → **不得判为损伤**（第一版判据正是在这里翻的车：它量的
      其实是紧贴笔画的边缘像素，腐蚀 2px 后已知破坏样本全部归零，已弃用）
      异口径成员 → **不得入参照族**（第三版判据修正：v6 固定 k≡1 与 v8/v9 的自适应
      k̂ 不同口径，入族会让深色图上正确的 v8/v9 被判成偏离 13.6 —— 口径差不是损伤）
    """
    import cv2
    import numpy as np
    au = load("audit_wm")
    V8 = load("dewm_v8")

    W, H = 1024, 1536
    a, (x0, y0) = V8.load_template(W, H)
    ah, aw = a.shape[:2]
    a3 = a[:, :, None]

    def simulate(orig):
        wm = orig.copy()
        sub = orig[y0:y0 + ah, x0:x0 + aw].astype(np.float32)
        wm[y0:y0 + ah, x0:x0 + aw] = np.clip(
            a3 * 255.0 + (1 - a3) * sub, 0, 255).astype(np.uint8)
        return wm

    def pointwise(wm):
        """反解族行为：逐像素还原，保留笔画底下的真实结构。"""
        out = wm.copy()
        sub = wm[y0:y0 + ah, x0:x0 + aw].astype(np.float32)
        out[y0:y0 + ah, x0:x0 + aw] = np.clip(
            (sub - a3 * 255.0) / (1 - a3), 0, 255).astype(np.uint8)
        return out

    def inpaint_like_v7(wm):
        mask = np.zeros((H, W), np.uint8)
        region = cv2.dilate((a > 0.05).astype(np.uint8) * 255,
                            np.ones((3, 3), np.uint8), 1)
        mask[y0:y0 + ah, x0:x0 + aw] = region
        return cv2.inpaint(wm, mask, 3, cv2.INPAINT_TELEA)

    def fringe_only(wm, ref):
        """只把抗锯齿边缘（α<0.02）涂改掉，笔画核心一个字不动。"""
        out = ref.copy()
        yy, xx = np.where(a3[:, :, 0] < 0.02)
        out[y0 + yy, x0 + xx] = 255
        return out

    # ① 水印底下压着结构
    orig = np.full((H, W, 3), 242, np.uint8)
    cv2.circle(orig, (x0 + 100, y0 + 45), 72, (18, 18, 18), -1)
    cv2.rectangle(orig, (x0 + 150, y0 + 15), (x0 + 205, y0 + 95), (30, 30, 200), -1)
    wm = simulate(orig)
    ref = pointwise(wm)          # 反解族参照（等价于模型族里残留最低那版）

    d_ref = au.estimate_damage(wm, ref, ref=ref, ref_name="v8")
    d_ip = au.estimate_damage(wm, inpaint_like_v7(wm), ref=ref, ref_name="v8")
    check("坑28 候选＝结构参照时偏离为 0",
          d_ref["dev_core"] == 0.0 and d_ref["penalty"] == 0.0,
          f"dev={d_ref['dev_core']} pen={d_ref['penalty']}")
    check("坑28 inpaint 在笔画核心区偏离参照 → 判损伤",
          d_ip["dev_core"] > au.DEV_FLOOR and d_ip["penalty"] > 0.0,
          f"dev={d_ip['dev_core']:.2f} pen={d_ip['penalty']:.2f}")

    # ② 只改抗锯齿边缘 → 必须放行（第一版判据的死因）
    d_fr = au.estimate_damage(wm, fringe_only(wm, ref), ref=ref, ref_name="v8")
    check("坑28 只改抗锯齿边缘不判损伤（不重蹈旧判据覆辙）",
          d_fr["penalty"] == 0.0 and d_fr["dev_core"] == 0.0,
          f"dev={d_fr['dev_core']} pen={d_fr['penalty']}")

    # ③ 合成真实反例的残留分（inpaint 残留更低）→ 总分必须翻转
    resid_inpaint, resid_pointwise = 0.20, 2.22
    check("坑28 总分翻转：低残留的 inpaint 不再胜出",
          resid_inpaint + d_ip["penalty"] > resid_pointwise + d_ref["penalty"],
          f"inpaint={resid_inpaint + d_ip['penalty']:.2f} "
          f"vs 反解={resid_pointwise + d_ref['penalty']:.2f}")

    # ④ 纯平底：没有结构可毁 → inpaint 不得被罚
    flat = np.full((H, W, 3), 236, np.uint8)
    wmf = simulate(flat)
    reff = pointwise(wmf)
    d_flat = au.estimate_damage(wmf, inpaint_like_v7(wmf), ref=reff, ref_name="v8")
    check("坑28 纯平底 inpaint 不罚（无结构可毁）",
          d_flat["penalty"] == 0.0, f"实际 {d_flat['penalty']}")

    # ⑤ 上限：罚分必须封顶，否则 inpaint 永远无法在极端残留时兜底
    check("坑28 损伤分有上限",
          d_ip["penalty"] <= au.DEV_CAP, f"{d_ip['penalty']} > {au.DEV_CAP}")

    # ⑥ 结构参照必须取自反解族（跑真实的 v6/v8/v9 管线）
    _, sname, sresid = au.structure_reference(wm)
    check("坑28 结构参照取自反解族",
          sname in au.MODEL_FAMILY, f"参照={sname}")
    check("坑28 反解族各版残留都被计算",
          set(sresid) == set(au.MODEL_FAMILY), f"{sorted(sresid)}")

    # ⑦ 族内必须同口径（2026-09-12 第三次迭代）
    #    v6 固定 k≡1 + max(1-α,0.29) 硬截断；v8/v9 逐图最小二乘拟合 k̂。
    #    混作一族时，03_labor 上 v6 用 k=1 反解出的「残留最低」被选为参照，
    #    反过来把目检正确的 v8/v9 判成偏离 13.6 / 损伤 10.6，最终选中发浑的版本。
    #    深色区里两个 k 的差会被 1/(1-α) 放大成十几灰度级 —— 那是口径差。
    check("坑28 结构参照族排除口径不同的 v6（固定 k≡1）",
          "v6" not in au.MODEL_FAMILY, f"MODEL_FAMILY={au.MODEL_FAMILY}")
    check("坑28 结构参照族排除 inpaint 的 v7",
          "v7" not in au.MODEL_FAMILY, f"MODEL_FAMILY={au.MODEL_FAMILY}")

    # ⑧ 反向保护：v6/v7 仍须作为**候选**参与竞争，只是不当参照。
    #    删掉它们会让平底 / 极端残留场景失去兜底路径。
    pw = load("pick_wm")
    check("坑28 v6/v7 仍作为候选参与竞争（仅不作参照）",
          set(pw.VERSIONS) == {"v6", "v7", "v8", "v9"}, f"{pw.VERSIONS}")


# ── 坑 29：干净图与「歧义取舍」不得被静默处理 ─────────────────────
def test_pick_wm_noop_policy():
    """2026-09-12 全库复检实测两件事：

    ① **v9 零改动是合法判定**：dewm_v9 的 K_RANGE 下限 0，水印模型不成立
       （k̂_raw ≤ 0）时输出 = 原图。此时若把它当普通候选，它会「因没动手而残留
       最低」胜出——但在干净图上这**恰恰是正解**（01_mistgate 实测：原图无水印，
       旧产物 v8 却因强制 k≥0.2 把画面压暗 13.87 灰度级）。
       故不排除它，而是**必须显式告知、且不写产物**（写一个与原图逐位相同的
       文件到 _clean/ 只会制造「已去水印」的假象）。

    ② **「残留更低却被罚下」必须报告而非自动裁决**：水印压在暗平坦区时，
       v7 的 inpaint 填成背景色既干净又无损，却被「偏离参照」误判为损伤；
       实测三类样本的 amp / R² / dev 全部交叠，无法用数值区分，只能交目检。
    """
    import numpy as np
    import cv2
    au = load("audit_wm")
    V8 = load("dewm_v8")
    W, H = 1024, 1536
    a, (x0, y0) = V8.load_template(W, H)

    base = (np.random.RandomState(7).rand(H, W, 3) * 30 + 120).astype(np.uint8)

    # ① 逐位相同 → 判「未动手」
    c0 = au.change_amount(base, base.copy())
    check("坑29 逐位相同 → 判未动手", c0["noop"] and c0["delta"] == 0.0,
          f"delta={c0['delta']}")

    # ② 只在水印区动了一点 → 不算未动手
    moved = base.copy()
    moved[y0:min(H, y0 + a.shape[0]), x0:min(W, x0 + a.shape[1])] = 255
    c1 = au.change_amount(base, moved)
    check("坑29 水印区有改动 → 不判未动手", not c1["noop"] and c1["delta"] > 1.0,
          f"delta={c1['delta']:.3f}")

    # ③ 改动量必须只统计模板框内 —— 框外大改也不该影响判定（否则误报）
    outside = base.copy()
    outside[:H // 2, :] = 255          # 上半张全改，水印框在下半张
    c2 = au.change_amount(base, outside)
    check("坑29 只统计模板框内（框外大改不算）", c2["noop"],
          f"delta={c2['delta']:.3f}")

    # ④ 尺寸不同 → 保守判为「未动手」，不让形状不合的候选参与比较
    c3 = au.change_amount(base, cv2.resize(base, (512, 768)))
    check("坑29 尺寸不同 → 判未动手（保守）", c3["noop"] and not c3["shape_ok"],
          f"{c3}")

    # ⑤ 端到端：干净图 → 报告「无需处理」且**不写产物**（写了就是制造假象）
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "blank.png")
        Image.new("RGB", (1024, 1536), (238, 236, 232)).save(p)
        out = os.path.join(d, "out")
        r = subprocess.run([sys.executable, os.path.join(HERE, "pick_wm.py"),
                            p, "--out-root", out],
                           capture_output=True, text=True)
        check("坑29 干净图正常退出", r.returncode == 0, r.stderr[-200:])
        check("坑29 干净图明确报告「无需处理」", "无需处理" in r.stdout,
              r.stdout[-260:])
        check("坑29 零改动不写产物",
              not os.path.exists(os.path.join(out, "_clean", "blank.png")),
              "产物被写出了")


def test_pick_wm_ambiguous_hold():
    """坑 29 增补：参照自身带残留时，**真正去干净的那版反被罚下** —— 此时不许写产物。

    实测 Design43-10（1024x1536 标准图，水印压在纯暗底）：
      v6  残留 93.79  损伤 12.00  总分 105.79
      v7  残留  0.05  损伤  7.86  总分   7.91   ← 目检：水印彻底抹净、手部结构完整
      v8  残留  5.72  损伤  0.00  总分   5.72   ← 目检：「AI生成 WORKBUDDY」清晰残留
      v9  残留  6.12  损伤  0.00  总分   6.12
    参照取自 MODEL_FAMILY(v8/v9)，而 v8 在本图**自身就带 5.72 残留** → 去得最干净的
    v7 反倒成了「偏离参照者」。该图 _clean/ 里的现任产物正是 v7（逐位相同），
    一旦重跑就会被 v8 覆盖掉——这就是本函数要拦的路径。

    规则：胜出版本残留高于某被罚下候选 ≥ AMBIG_DELTA 时，判「数值自相矛盾」，
    **不写产物**（拿不准就不动手），并在报告里把两个候选摆出来交目检。
    """
    P = load("pick_wm")

    def det(**kw):
        d = {k: {"resid": 1.0, "noop": False} for k in P.VERSIONS}
        for k, v in kw.items():
            d[k].update(v)
        return d

    # ① 典型矛盾：胜出 v8 残留 5.72，被罚下的 v7 只有 0.05
    d = det(v7={"resid": 0.05}, v8={"resid": 5.72}, v9={"resid": 6.12})
    got = P.ambiguous_pair(d, "v8")
    check("坑29 检出「残留更低却被罚下」", got == ("v7", 0.05), f"{got}")

    # ② 胜出者本身就是最干净的 → 无矛盾（不许误报）
    check("坑29 胜出者最干净时不误报", P.ambiguous_pair(d, "v7") is None,
          f"{P.ambiguous_pair(d, 'v7')}")

    # ③ 差距未达阈值 → 不报（避免把噪声级差异当矛盾）
    d2 = det(v7={"resid": 3.0}, v8={"resid": 5.72})
    check("坑29 差距未达阈值不报", P.ambiguous_pair(d2, "v8") is None,
          f"{P.ambiguous_pair(d2, 'v8')}")

    # ④ 零改动候选不参与比较：它表达的是「无需处理」，不是「去得更干净」
    d3 = det(v6={"resid": 9.0}, v7={"resid": 0.05, "noop": True},
             v8={"resid": 5.72}, v9={"resid": 8.0})
    check("坑29 零改动候选不作对照", P.ambiguous_pair(d3, "v8") is None,
          f"{P.ambiguous_pair(d3, 'v8')}")

    # ⑤ 胜出者零改动 → 走 noop 分支，不走本分支
    d4 = det(v8={"resid": 5.72, "noop": True})
    check("坑29 胜出者零改动不算矛盾", P.ambiguous_pair(d4, "v8") is None,
          f"{P.ambiguous_pair(d4, 'v8')}")

    # ⑥ 阈值改变即改变行为，必须与坑 29 的记录同步
    check("坑29 AMBIG_DELTA = 5.0", P.AMBIG_DELTA == 5.0, f"{P.AMBIG_DELTA}")


# ── 坑 28 副产物：同名文件的审计结果必须可区分 ───────────────────
def test_audit_unique_keys():
    """旧版 audit_wm 表格只打 basename：同一批传 6 个不同目录的同名文件时
    6 行长得一模一样，被误读成「结果互相覆盖」。JSON 里 name 也只是 basename，
    按 name 建索引的消费方会真的踩中。现在 key=绝对路径 + 显示名带父目录。
    """
    import json
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        for sub, color in (("d1", (250, 250, 250)), ("d2", (120, 30, 30))):
            os.makedirs(os.path.join(d, sub))
            Image.new("RGB", (1024, 1536), color).save(
                os.path.join(d, sub, "same.png"))
        out = os.path.join(d, "r.json")
        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "audit_wm.py"),
             os.path.join(d, "d1", "same.png"),
             os.path.join(d, "d2", "same.png"), "--json", out],
            capture_output=True, text=True)
        check("坑28 audit_wm 同名文件正常退出", r.returncode == 0, r.stderr[-200:])
        if r.returncode != 0:
            return
        data = json.load(open(out, encoding="utf-8"))
        check("坑28 同名文件产出 2 行", len(data) == 2, f"实际 {len(data)}")
        check("坑28 key 唯一（绝对路径，不用 basename）",
              len({row["key"] for row in data}) == 2,
              f"{[row['key'] for row in data]}")
        check("坑28 表格显示名带父目录消歧",
              "d1/same.png" in r.stdout and "d2/same.png" in r.stdout,
              "同名行仍无法区分")


def test_wm_metrics_reference_free():
    """坑 30：① amp 随背景变化（白底被压 ~26 倍）② 白蚀单向性可当参照无关的损伤判据。

    这两条都是 2026-09-13 复检时挖出来的：
    - amp = k̂·mean(a·(255−bg))。白纸底 (255−bg≈9) 与纯黑底 (≈238) 相差约 26 倍，
      而本技能的竖版海报绝大多数是白底 → **amp 在主力图种上几乎测不出残留**
      （03_labor 上 v7 有明显灰糊斑，amp 仅 0.21 判 CLEAN）。背景无关的量是 α̂ = k̂。
    - 白蚀单向性：I = α·C + (1−α)·orig ⇒ orig ≤ I（I ≤ 255 时恒成立），
      去白水印**只能变暗**。out > I 的像素必然是损伤，且**不需要参照图**。
    断言必须同时覆盖「能报」和「不误报」两侧。
    """
    import numpy as np
    import cv2
    from PIL import Image
    import audit_wm
    import dewm_v9
    import dewm_v13

    with tempfile.TemporaryDirectory() as d:
        # ---- ① 白蚀单向性：恒等不算违反 / 提亮才算 ----
        a = np.full((60, 80, 3), 128, np.uint8)
        v0 = audit_wm.brightening_violation(a, a)
        check("坑30 恒等输出无提亮违反", v0["bad_px"] == 0 and v0["max_lift"] == 0,
              str(v0))

        b = a.copy(); b[10, 10] = 138          # +10
        v1 = audit_wm.brightening_violation(a, b)
        check("坑30 单点提亮 10 被计入", v1["bad_px"] == 1 and v1["max_lift"] == 10,
              str(v1))

        c = a.copy(); c[10, 10] = 130          # 恰好 +2 = tol 边界
        check("坑30 tol 边界不误报（严格大于）",
              audit_wm.brightening_violation(a, c, tol=2)["bad_px"] == 0,
              "tol=2 时 +2 被判违法")

        dk = a.copy(); dk[::2, ::2] = 100      # 只变暗
        check("坑30 只变暗绝不违反（单向性）",
              audit_wm.brightening_violation(a, dk)["bad_px"] == 0,
              "变暗被误判成损伤")

        # ---- ② amp 的背景依赖性（本轮发现的度量缺陷）----
        wp = os.path.join(d, "white.png")
        Image.new("RGB", (1024, 1536), (250, 250, 250)).save(wp)
        dp = os.path.join(d, "dark.png")
        Image.new("RGB", (1024, 1536), (20, 20, 20)).save(dp)
        fw = audit_wm.background_factor(cv2.imread(wp))
        fd = audit_wm.background_factor(cv2.imread(dp))
        check("坑30 白底 bg_scale 远小于暗底（amp 被压）",
              fd / max(fw, 1e-6) > 10.0,
              f"白底 {fw:.2f} / 暗底 {fd:.2f}，比值不足 10，缺陷未复现")

        r = audit_wm.estimate_residual(cv2.imread(dp))
        check("坑30 estimate_residual 暴露背景无关的 alpha/bg_scale",
              "alpha" in r and "bg_scale" in r and abs(r["alpha"] - r["k"]) < 1e-9,
              f"keys={sorted(r)}")

        # ---- ③ v13：干净图必须逐位不变（无感底线）----
        img = cv2.imread(wp)
        out13, st13 = dewm_v13.remove_watermark(img)
        check("坑30 v13 干净图逐位不变（零改动）",
              np.array_equal(out13, img), f"k={st13['k']:.3f} 但输出被改动")

        # ---- ④ v13：合成本印图上残留必须显著下降 ----
        g = cv2.imread(dp)
        a_t, (x0, y0) = dewm_v9.load_template(1024, 1536)
        al = np.clip(0.91 * a_t, 0, 0.98)[:, :, None]
        sub = g[y0:y0 + a_t.shape[0], x0:x0 + a_t.shape[1]].astype(np.float32)
        g2 = g.copy()
        g2[y0:y0 + a_t.shape[0], x0:x0 + a_t.shape[1]] = np.clip(
            al * 255.0 + (1 - al) * sub, 0, 255).astype(np.uint8)
        k_before = audit_wm.estimate_residual(g2)["alpha"]
        out13b, st13b = dewm_v13.remove_watermark(g2)
        k_after = abs(audit_wm.estimate_residual(out13b)["alpha"])
        check("坑30 v13 合成本印残留显著下降",
              k_before > 0.5 and k_after < k_before * 0.25,
              f"拟合 k={k_before:.3f} → 残留 {k_after:.3f}")
        check("坑30 v13 不违反白蚀单向性",
              audit_wm.brightening_violation(g2, out13b)["bad_px"] == 0,
              str(audit_wm.brightening_violation(g2, out13b)))


def test_skill_frontmatter_window_free():
    """坑 31：run_tests.sh 用固定字符窗口读 front-matter，撑爆后报「missing front-matter」。

    同一个坑复发过两次（2048 → 4096）：报错信息把人引向「YAML 格式坏了」，
    真实原因是 description 里的版本变更记录越写越长，超出了读取窗口。
    闭合符位置与长度无关，按行定位即可。本测试既验行为、也**防止改回固定窗口**。
    """
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


def test_v13_wiener_invariants():
    """v13（Wiener 融合）的三条硬不变量 —— 2026-09-13 实测确认后锁死（坑 32）。

    ① **无水印图（k̂≤0）→ 输出逐位等于原图**：α = clip(k·a)，k≤0 时 α≡0，
       逐位 `np.where(α>0, blend, sub)` 全部取 sub。这是「无感」底线
       （对照 01_mistgate：干净图上任何改动都是净损失，v8 曾把画面压暗 13.87 灰阶）。
    ② **白蚀单向性**：去白水印只能变暗（orig ≤ I），任何提亮都是损伤。
       v13 靠 `B ← min(sub_bg, I)` 保证，**不再夹最终结果**——夹结果会在先验偏亮时
       把该减的地方也挡住。实测 87 张真水印图违反 0 px（v8 1800 / v12 3654）。
    ③ **Wiener 权重单调**：w = t²/(t²+c²) 随 α 增大而减小 → α 大处更信 inpaint、
       α 小处更信反解。这条正是 v13 能在低 conf 图上胜过纯反解的原因。
    """
    import numpy as np
    V13 = load("dewm_v13")
    V9 = load("dewm_v9")
    W, H = 1024, 1536
    a, (x0, y0) = V9.load_template(W, H)
    ah, aw = a.shape

    # ① 水印位置比周围暗 ⇒ 不符合「白蚀」模型 ⇒ k̂ ≤ 0 ⇒ 必须零改动
    flat = np.full((H, W, 3), 240, np.uint8)
    flat[y0:y0 + ah, x0:x0 + aw] = 170
    out, st = V13.remove_watermark(flat)
    check("坑32 v13 无水印图零改动（k̂≤0 ⇒ 输出逐位=原图）",
          np.array_equal(out, flat), f"k={st['k']:.3f}，输出与原图不同")

    # ② 注入水印后检查：单向性 + 只改模板框内
    base = (np.random.RandomState(11).rand(H, W, 3) * 60 + 150).astype(np.uint8)
    wm = base.copy()
    reg = wm[y0:y0 + ah, x0:x0 + aw].astype(np.float32)
    al = np.clip(0.85 * a, 0, 0.98)[:, :, None]
    wm[y0:y0 + ah, x0:x0 + aw] = np.clip(al * 255.0 + (1 - al) * reg, 0, 255).astype(np.uint8)
    out2, st2 = V13.remove_watermark(wm)
    d = out2.astype(np.int16) - wm.astype(np.int16)
    check("坑32 v13 白蚀单向性：无提亮（>1 灰阶即违反）",
          int(d.max()) <= 1, f"最大提亮 {int(d.max())} 灰阶")
    bx0, by0, bx1, by1 = st2["box"]
    mask = np.ones((H, W), bool)
    mask[by0:by1, bx0:bx1] = False
    check("坑32 v13 只改模板框内（框外逐位不变）",
          np.array_equal(out2[mask], wm[mask]), "框外像素被改动")

    # ③ Wiener 增益的单调性（设计意图，与实现解耦的数学断言）
    ok = True
    for c in (0.2, 1.0, 3.0, 10.0):
        ts = np.linspace(0.05, 1.0, 20)
        ws = ts * ts / (ts * ts + c * c)
        if not np.all(np.diff(ws) > 0):
            ok = False
    check("坑32 v13 Wiener 权重随 α 单调（α 大 ⇒ 更信 inpaint）",
          ok, "w=t²/(t²+c²) 非单调递增于 t")


def test_wm_auto_gate():
    """v1.13 新增自动水印识别。核心风险不是「认不出水印」，而是**误认**：
    自动模式判错 = 主动改坏一张已经画好的图，比报告模式看错一行字严重得多。

    因此这条断言钉死「高 amp 但低 R² 必须落 manual，不许 remove」：
    audit_wm 文档写明低 R² 是高频纹理的典型特征，而纸纹/网点/格边正是本技能
    主力产出（类型 A 纸纹、类型 E 精灵图）。实测分布见 scripts/wm_auto.py 文档。
    """
    wm = load("wm_auto")
    cases = [
        (0.5, 0.90, "skip", "无可见水印"),
        (-0.79, 0.20, "skip", "实测干净图（本机 3 张：amp -0.79~-0.69）"),
        (20.69, 0.76, "remove", "实测带水印图（本机 11 张：R² 0.76~0.96）"),
        (45.48, 0.96, "remove", "最强残留"),
        (5.0, 0.10, "manual", "高 amp 低 R² = 高频纹理误报，不许自动动手"),
        (2.0, 0.30, "manual", "R² 不足闸门"),
        (1.6, 0.88, "manual", "SUSPECT 区，交人 / pick_wm"),
    ]
    for amp, r2, want, why in cases:
        got, _ = wm.decide(amp, r2)
        check(f"wm_auto 闸门 amp={amp} R²={r2} → {want}", got == want,
              f"{why}；实际 {got}")


def test_wm_auto_never_touches_original():
    """自动去水印必须**不覆盖原图**（dewm_io 守卫的延伸保证）。

    原图被覆盖 = 不可回溯，且「去水印没去干净」时连重来的底都没了。
    用干净图跑 --remove：既不写文件，也绝不动原文件。
    """
    import hashlib
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "clean.png")
        Image.new("RGB", (1024, 1536), (250, 250, 250)).save(src)
        before = hashlib.sha256(open(src, "rb").read()).hexdigest()

        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "wm_auto.py"), src, "--remove"],
            capture_output=True, text=True)
        after = hashlib.sha256(open(src, "rb").read()).hexdigest()
        check("wm_auto 干净图不写输出",
              not os.path.exists(os.path.join(d, "clean_dewm.png")),
              "干净图被动了手")
        check("wm_auto 原图逐位未改", before == after, "原图被改坏")
        check("wm_auto --remove 干净图退出码 0", r.returncode == 0,
              f"rc={r.returncode}")


def _make_grid(path, cols=3, rows=3, W=1024, H=1024, gap=14):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(im)
    cw, ch = (W - gap * (cols + 1)) // cols, (H - gap * (rows + 1)) // rows
    for r in range(rows):
        for c in range(cols):
            x, y = gap + c * (cw + gap), gap + r * (ch + gap)
            dr.rectangle([x, y, x + cw, y + ch], fill=(30, 60, 90),
                         outline=(200, 40, 40), width=2)
    im.save(path)


def test_postcheck_track_e():
    """v1.13：类型 E 此前**零判定**（v1.12 加类型时漏了验收接线）。

    现在：给了 --expect-cells 才校验格数（不猜用户声明了几格），
    格数不符判 blocker，相符判 pass。
    """
    grid_metrics = load("measure").grid_metrics
    with tempfile.TemporaryDirectory() as d:
        img = os.path.join(d, "grid9.png")
        _make_grid(img, 3, 3)

        g = grid_metrics(img)
        check("类型E 网格量测识出 3×3=9", g["ok"] and g["cells"] == 9,
              f"cells={g.get('cells')} note={g.get('note')}")
        check("类型E 一致网格 cell_uniform=1.0", g.get("cell_uniform") == 1.0,
              f"实际 {g.get('cell_uniform')}")

        # 单格缩水必须被检出（E 硬规则：每格等比例、尺寸一致）
        small = os.path.join(d, "grid9_shrink.png")
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (1024, 1024), (255, 255, 255))
        dr = ImageDraw.Draw(im)
        gap, cw = 14, (1024 - 14 * 4) // 3
        for r in range(3):
            for c in range(3):
                w = cw - 60 if (r, c) == (1, 1) else cw
                x, y = gap + c * (cw + gap), gap + r * (cw + gap)
                dr.rectangle([x, y, x + w, y + cw], fill=(30, 60, 90),
                             outline=(200, 40, 40), width=2)
        im.save(small)
        g2 = grid_metrics(small)
        check("类型E 单格缩水被检出", (g2.get("cell_uniform") or 1) < 0.95,
              f"cell_uniform={g2.get('cell_uniform')} 未检出不一致")

        pc = os.path.join(HERE, "postcheck.py")

        def run(*extra):
            return subprocess.run([sys.executable, pc, img, "--track", "E",
                                   "--text", "ok", "--no-log", *extra],
                                  capture_output=True, text=True)

        r = run("--expect-cells", "9")
        check("类型E 格数相符 → pass(rc0)", r.returncode == 0,
              f"rc={r.returncode} {r.stdout[-160:]}")
        r = run("--expect-cells", "16")
        check("类型E 格数不符 → blocker(rc1)", r.returncode == 1,
              f"rc={r.returncode} 格数不符未拦")
        check("类型E 格数不符输出可读诊断", "格数不符" in r.stdout,
              "没说是哪一项不符")
        r = run()
        check("类型E 无 --expect-cells → 不猜格数(rc0)", r.returncode == 0,
              f"rc={r.returncode} 无声明值却拦了")


def test_postcheck_wm_not_false_blocker():
    """v1.13：自动水印不得把干净图降级成 pending。

    实测教训同 top_noise（坑 27）——纹理区的 amp 虚高但 R²≈0，
    若因此拦住交付，等于让误报逼出返工，每张白扣 5-10 积分。
    """
    with tempfile.TemporaryDirectory() as d:
        img = os.path.join(d, "grid9.png")
        _make_grid(img, 3, 3)
        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "postcheck.py"), img,
             "--track", "E", "--text", "ok", "--no-log"],
            capture_output=True, text=True)
        check("自动水印不把干净格图降级为 pending", r.returncode == 0,
              f"rc={r.returncode} 纹理误报拦住了交付：{r.stdout[-200:]}")

    # 源码层护栏：R² 闸门不得被绕过
    src = open(os.path.join(HERE, "wm_auto.py"), encoding="utf-8").read()
    body = src.split("def decide", 1)[1].split("def detect", 1)[0]
    check("wm_auto decide 保留 R² 闸门", "AUTO_R2_THR" in body,
          "R² 闸门被移除，自动模式将误改干净图")


def test_postcheck_dewm_backcompat():
    """v1.13 把 --dewm 的语义扩成 --wm auto/force/off，旧参数必须继续可用，
    否则既有文档（SKILL.md §3/§6、pitfalls）与用户习惯同时失效。
    """
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        img = os.path.join(d, "clean.png")
        Image.new("RGB", (1024, 1536), (250, 250, 250)).save(img)
        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "postcheck.py"), img,
             "--track", "A", "--dewm", "--text", "ok", "--no-log"],
            capture_output=True, text=True)
        check("postcheck 旧参数 --dewm 仍可用", r.returncode in (0, 1, 3),
              f"rc={r.returncode} {r.stderr[-160:]}")
        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "postcheck.py"), img,
             "--track", "A", "--wm", "off", "--text", "ok", "--no-log"],
            capture_output=True, text=True)
        check("postcheck --wm off 可用", r.returncode in (0, 1, 3),
              f"rc={r.returncode} {r.stderr[-160:]}")


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
      2. 体积预算：description ≤ 2,000 B、SKILL.md ≤ 35,000 B。
      3. 条件面文件必须真的被接线：文件存在、SKILL.md 提到、且进了 §4 加载
         协议表——否则就是「搬出去没人读」。
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

    orphans = [os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "references", "*.md"))
               if os.path.basename(p) not in skill]
    check("references/ 无孤儿文件（每个都在 SKILL.md 里被引用）", not orphans,
          f"未被引用: {orphans}")


# ── 验收结论必须可归因（reason 码 → runs.csv）──────────────────────
def test_reason_codes_recorded():
    """2026-09-18：runs.csv 此前只有 verdict（blocker/pending/pass），没有原因码，
    于是「为什么这张图要重出」只能靠翻日志猜；实测那条记账还长期只有 9 行。
    现在每行都带 reason（为什么没 pass）与 hint（诊断/建议），这里锁住三件事：
      ① 表头含 reason / hint；
      ② pending 行的 reason 必须写明是哪一个原因（本例 paper_warm）；
      ③ pass 行的 reason 为空 —— 空 reason 才代表「真的没问题」。
    """
    import csv
    from PIL import Image
    pc = os.path.join(HERE, "postcheck.py")

    def run_logged(rgb, track="A", log=None, extra=("--text", "ok")):
        with tempfile.TemporaryDirectory() as d:
            img = os.path.join(d, "t.png")
            Image.new("RGB", (1024, 1536), rgb).save(img)
            r = subprocess.run([sys.executable, pc, img, "--track", track,
                                "--log-path", log, *extra],
                               capture_output=True, text=True)
            return r

    with tempfile.TemporaryDirectory() as d:
        log = os.path.join(d, "runs.csv")
        run_logged((254, 252, 245), log=log)          # 白底泛黄 → pending
        run_logged((252, 252, 252), log=log)          # 中性纯白 → pass
        rows = list(csv.DictReader(open(log, encoding="utf-8")))
        check("runs.csv 表头含 reason / hint", {"reason", "hint"} <= set(rows[0]),
              f"列={list(rows[0])}")
        check("pending 行写明原因码（paper_warm）", rows[0]["reason"] == "paper_warm",
              f"reason={rows[0]['reason']!r}")
        check("pass 行 reason 为空（空 = 真的没问题）", rows[1]["reason"] == "",
              f"reason={rows[1]['reason']!r} verdict={rows[1]['verdict']}")

    # 类型 B 的「挤成一团」只给提示、不判 blocker（2026-09-18 校准决定的契约）
    # 旧口径 white%∈[30,65] 在已验收成品上触发 82.2%；替代候选 paper% 是以中位数
    # 为基准的，按定义恒 ≥50%，`paper%<30` 永远不会响。所以这里锁的是**不许**再
    # 拿它判 blocker，同时提示必须报出来（信号不丢）。
    with tempfile.TemporaryDirectory() as d:
        log = os.path.join(d, "b.csv")
        img = os.path.join(d, "crowd.png")
        # 大块结构，不用细线：measure 在 256 宽缩略图上算指标，细密线条会被重采样
        # 抹平（实测 1px 线 ×2 间距 → base 从 205 掉到 153），必须用整块色域构造
        im = Image.new("RGB", (1024, 1536), (205, 205, 205))   # 浅底（base≈205）
        px = im.load()
        for y in range(900, 1536):                             # 40% 被实体盖住
            for x in range(1024):
                px[x, y] = (100, 100, 100)
        im.save(img)
        r = subprocess.run([sys.executable, pc, img, "--track", "B", "--log-path", log,
                            "--text", "ok"], capture_output=True, text=True)
        rows = list(csv.DictReader(open(log, encoding="utf-8")))
        check("类型 B 留白偏少只提示不判 blocker（旧口径 82% 假拦）",
              rows and rows[0]["verdict"] != "blocker" and "crowded_hint" in rows[0]["hint"],
              f"verdict={rows[0]['verdict'] if rows else '无行'} "
              f"hint={rows[0]['hint'] if rows else '-'}")


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
# ── 缺依赖时必须说人话（普适性）────────────────────────────────────
def test_missing_dep_message():
    """2026-09-18：依赖不保证在每个解释器里都有（实测本机 managed 3.13 无 cv2、
    系统 python3 有）。用户直接调脚本时，缺依赖抛的是 `No module named 'cv2'`
    ——看不出该装什么、该换哪个解释器。这条锁住「人话 + 可执行的两条修复路径」，
    同时锁住**不得退化成 traceback**。
    """
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        shim = os.path.join(d, "shim")
        os.makedirs(shim)
        with open(os.path.join(shim, "cv2.py"), "w", encoding="utf-8") as f:
            f.write('raise ImportError("simulated missing cv2")\n')
        img = os.path.join(d, "a.png")
        Image.new("RGB", (64, 64), (250, 250, 250)).save(img)
        env = dict(os.environ, PYTHONPATH=shim)
        for script, extra in (("dewm_v10.py", []), ("pick_wm.py", [d])):
            r = subprocess.run([sys.executable, os.path.join(HERE, script), img, *extra],
                               capture_output=True, text=True, env=env)
            out = r.stdout + r.stderr
            check(f"{script} 缺 cv2 时给出人话而不是 traceback",
                  "Traceback" not in out and "依赖不可用" in out,
                  f"rc={r.returncode} out={out[-200:]!r}")
            check(f"{script} 缺依赖时提示换解释器这条可执行路径",
                  "换解释器重跑" in out and "workbuddy/binaries/python" in out,
                  f"out={out[-200:]!r}")
            check(f"{script} 缺依赖退出码为 2（环境未就绪，区别于用法错误）",
                  r.returncode == 2, f"rc={r.returncode}")


def main():
    print("== taxue-imagegen regression tests ==")
    for fn in (test_preflight_word_boundary, test_preflight_slot_detection,
               test_preflight_tracks_and_sizes, test_overwrite_guard,
               test_postcheck_verdict, test_cli_help,
               test_fill_meta_track_c,
               test_solvability_guard,
               test_pick_wm_damage_aware,
               test_pick_wm_noop_policy,
               test_pick_wm_ambiguous_hold,
               test_audit_unique_keys,
               test_skill_frontmatter_window_free,
               test_wm_metrics_reference_free,
               test_v13_wiener_invariants,
               test_wm_auto_gate,
               test_wm_auto_never_touches_original,
               test_postcheck_track_e,
               test_postcheck_wm_not_false_blocker,
               test_postcheck_dewm_backcompat,
               test_doc_consistency, test_version_consistency,
               test_top_noise_not_blocker,
               test_surface_layering,
               test_reason_codes_recorded,
               test_pitfall_coverage,
               test_missing_dep_message,
               test_no_machine_paths):
        print(f"\n[{fn.__name__}]")
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            check(f"{fn.__name__} 执行异常", False, repr(e))

    failed = [r for r in _results if not r[0]]
    print(f"\n== summary: {len(_results) - len(failed)}/{len(_results)} passed ==")
    for _, label, why in failed:
        print(f"  FAIL {label}  <- {why}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
