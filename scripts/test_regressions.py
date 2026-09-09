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


# ── preflight track 支持 A/B/C/D + 尺寸表 ────────────────────────
def test_preflight_tracks_and_sizes():
    pf = load("preflight")
    check("TRACKS 含 A/B/C/D", set(pf.TRACKS) == {"A", "B", "C", "D"},
          f"实际 {pf.TRACKS}")
    check("TESTED_SIZES 含 1024x1792", "1024x1792" in pf.TESTED_SIZES,
          "类型 D 法定画幅会误报 WARN")
    r = subprocess.run([sys.executable, os.path.join(HERE, "preflight.py"),
                        "-", "--track", "C"], input="x", capture_output=True, text=True)
    check("preflight --track C 可用", r.returncode in (0, 1),
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

    # 泛黄图 → blocker（R-B 越界）
    with tempfile.TemporaryDirectory() as d:
        img = os.path.join(d, "yellow.png")
        Image.new("RGB", (1024, 1536), (254, 252, 245)).save(img)
        r = run("--text", "ok", img=img)
        check("postcheck 泛黄图 → blocker(rc1)", r.returncode == 1,
              f"rc={r.returncode} 泛黄未拦")

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
    check("SKILL.md 声明四种类型", "四种类型" in skill, "类型数漂移")
    check("SKILL.md 索引含 storyboard.md", "references/storyboard.md" in skill,
          "类型 D 规则文件未进索引")

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
    body = src.split("def measure_warnings", 1)[1].split("def export_textband", 1)[0]
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



def main():
    print("== taxue-imagegen regression tests ==")
    for fn in (test_preflight_word_boundary, test_preflight_slot_detection,
               test_preflight_tracks_and_sizes, test_overwrite_guard,
               test_postcheck_verdict, test_cli_help,
               test_fill_meta_track_c,
               test_solvability_guard,
               test_doc_consistency, test_version_consistency,
               test_top_noise_not_blocker,
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
