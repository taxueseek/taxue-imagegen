#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""postcheck 域：verdict 三档（坑 27/33 契约）、CLI --help、类型 E 格数、
自动水印不误拦、--dewm 兼容、reason 码记账。"""
import os
import subprocess
import sys
import tempfile

from _harness import HERE, check, load


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


TESTS = [test_postcheck_verdict, test_cli_help, test_top_noise_not_blocker,
         test_postcheck_track_e, test_postcheck_wm_not_false_blocker,
         test_postcheck_dewm_backcompat, test_reason_codes_recorded]
