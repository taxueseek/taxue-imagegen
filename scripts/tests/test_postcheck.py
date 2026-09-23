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


def test_no_duplicate_finding_codes():
    """一类 bug：同一行的 reason / hint 里，同一个码出现两次。

    2026-09-23 实测：类型 E 的 `measure_findings` 被调了**两次**——先不带 grid 调一次、
    再带 grid 调一次、结果相加。第一次那次拿不到 grid，`grid_warnings(None)` 于是留下
    一条「网格未解析（未量测）」；即使网格明明解析成功（实测 3 行×1 列已识别），控制台
    仍并列打出「未量测」与真实诊断，runs.csv 里也稳定出现两个 `grid_diag`。

    原有用例只断言退出码与「格数不符」字样，于是这条假诊断一路静默通过。教训不是
    「再补一条针对 grid 的断言」，而是：**凡把多个来源的 findings 相加，就可能加出重复**。
    故这里对 reason / hint 两列做通用判据——同一个码在同一行出现两次即失败，
    不针对任何一个具体码（将来任何一条重复叠加的路径都会被它抓住）。

    判据要有牙，夹具就不能是「完美网格」：完美网格下第二次调用不产出任何诊断，
    重复也就无从发生（实测确认过）。这里刻意让**一格缩水**——网格仍能解析、
    但会产出一条真实诊断，重复才暴露得出来。夹具选错，门禁就是摆设。

    另附一条直接回归：网格解析成功时，不得报「网格未解析（未量测）」。
    """
    import csv
    pc = os.path.join(HERE, "postcheck.py")
    with tempfile.TemporaryDirectory() as d:
        img = os.path.join(d, "grid9_ragged.png")
        # 一格缩水：网格可解析，但 cell_uniform < 0.90 → 必产出一条真实诊断
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
        im.save(img)
        log = os.path.join(d, "runs.csv")
        r = subprocess.run([sys.executable, pc, img, "--track", "E",
                            "--expect-cells", "9", "--text", "ok",
                            "--log-path", log],
                           capture_output=True, text=True)
        rows = list(csv.DictReader(open(log, encoding="utf-8")))
        dup = []
        for col in ("reason", "hint"):
            codes = [c.strip() for c in (rows[0].get(col) or "").split(",") if c.strip()]
            repeated = sorted({c for c in codes if codes.count(c) > 1})
            if repeated:
                dup.append(f"{col}: {repeated}")
        check("夹具确实产出了诊断（否则本门禁无牙）",
              "grid_diag" in [c.strip() for c in (rows[0].get("hint") or "").split(",")],
              f"hint={rows[0].get('hint')!r}——夹具没造出可重复的诊断")
        check("同一行的 reason/hint 不出现重复码", not dup, "；".join(dup))

        grid_ok = "网格: 3行×3列" in r.stdout
        check("E 轨一致网格能被量测到（判据前提成立）", grid_ok,
              f"没打出网格行：{r.stdout[-200:]}")
        if grid_ok:
            check("网格已解析时不报「未量测」假诊断", "未量测" not in r.stdout,
                  "网格明明解析成功，却仍报「网格未解析（未量测）」")


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

    注意本测试用**全新临时文件**，测不到「从旧版升上来的日志」那条路径
    （这正是它长期漏掉表头错位的原因）；那部分由 `test_log_header_migrated` 覆盖。
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


# ── 旧版 runs.csv 必须能续写（门禁只跑干净夹具的系统性盲区）──────────
def test_log_header_migrated():
    """2026-09-18：上面那条 test_reason_codes_recorded 每次用全新的临时文件，
    **永远拿到新表头**——于是「从旧版本升上来的 runs.csv」这条路径从来没被测过。

    实测后果：v1.19 给 CSV_COLS 加了 reason / hint，但表头只在文件不存在时写，
    老机器上那份 14 列表头一直留着，此后每行都错位（实测 27 行里 15 行，
    表头最后一列 `note` 里装的其实是 reason 码）——正好废掉 reason 码自己要
    解决的归因问题。所以这里补一个「旧表头夹具」：

      ① 表头被迁移到 CSV_COLS（长度与列名都对）；
      ② 旧行不丢，且 `note` 按**列名**归位（不是按位置硬塞）；
      ③ 新追加行的 reason / hint / note 各就各位；
      ④ 迁移前留了备份文件。
    """
    import csv
    import glob
    from PIL import Image

    pc = os.path.join(HERE, "postcheck.py")
    # v1.19 之前的表头：没有 reason / hint
    legacy_cols = ["ts", "file", "track", "size", "base", "white_pct", "paper_pct",
                   "R-B", "sat", "top_noise", "top_dev", "text", "verdict", "note"]

    with tempfile.TemporaryDirectory() as d:
        log = os.path.join(d, "runs.csv")
        with open(log, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(legacy_cols)
            # ① 旧格式行（14 字段，旧列序）
            w.writerow(["2026-01-01 00:00:00", "old_a.png", "A", "1024x1536", "35",
                        "7.0", "97.3", "-0.1", "67.8", "49.6", "49.5", "ok",
                        "blocker", "旧行备注 A"])
            w.writerow(["2026-01-02 00:00:00", "old_b.png", "B", "1024x1536", "200",
                        "0.0", "60.0", "1.0", "30.0", "20.0", "5.0", "ok",
                        "pass", "旧行备注 B"])
            # ② 新格式行（16 字段）却挂在旧表头下——这是最容易被迁移写坏的一类：
            #    它已经是当前列序，按旧表头名映射会把 reason 读成 note、note 丢掉。
            #    真实日志里 15 条新格式行有 12 条带 note，本夹具复现这个形状。
            w.writerow(["2026-01-03 00:00:00", "mix_c.png", "A", "1024x1536", "40",
                        "6.0", "96.0", "-0.2", "65.0", "48.0", "48.0", "ok",
                        "pass", "", "", "混排行备注 C"])
            w.writerow(["2026-01-04 00:00:00", "mix_d.png", "B", "1024x1536", "210",
                        "0.0", "58.0", "0.9", "29.0", "19.0", "4.0", "ok",
                        "pending", "text_unverified", "", "混排行备注 D"])

        img = os.path.join(d, "new.png")
        Image.new("RGB", (1024, 1536), (254, 252, 245)).save(img)   # 白底泛黄 → pending
        r = subprocess.run([sys.executable, pc, img, "--track", "A",
                            "--log-path", log, "--text", "ok"],
                           capture_output=True, text=True)
        check("postcheck 能在旧表头日志上续写", r.returncode in (0, 1, 3),
              f"rc={r.returncode} {r.stderr[-160:]}")

        raw = list(csv.reader(open(log, encoding="utf-8")))
        check("旧版 runs.csv 表头被迁移到当前 CSV_COLS",
              raw and len(raw[0]) == len(legacy_cols) + 2
              and {"reason", "hint"} <= set(raw[0]),
              f"迁移后表头={raw[0] if raw else None}")
        check("迁移后每行列数与表头一致（不再错位）",
              all(len(r_) == len(raw[0]) for r_ in raw[1:]),
              f"字段数集合={sorted({len(r_) for r_ in raw[1:]})}")

        rows = list(csv.DictReader(open(log, encoding="utf-8")))
        # 用 .get 取列：表头迁移失败时 DictReader 里没有 reason/hint 键，
        # 直接下标会抛 KeyError，把「诊断信息」变成一行 traceback。
        # 这里要让断言失败得可读——每一个都是「出了什么、期望什么」。
        def cell(r_, k):
            return r_.get(k, "<表头无此列>")
        check("旧行不丢且 note 按列名归位",
              len(rows) == 5 and cell(rows[0], "note") == "旧行备注 A"
              and cell(rows[1], "note") == "旧行备注 B",
              f"行数={len(rows)} note={[cell(r_, 'note') for r_ in rows[:2]]}")
        check("旧行缺失的新列为空（不把旧 verdict 塞进 reason）",
              cell(rows[0], "reason") == "" and cell(rows[0], "verdict") == "blocker",
              f"reason={cell(rows[0], 'reason')!r} verdict={cell(rows[0], 'verdict')!r}")
        # 混排行：note 必须原样留下，不能被 reason 顶掉（真实日志 12/15 行属此类）
        check("混排的新格式行 note 不被 reason 顶掉（不丢历史备注）",
              cell(rows[2], "note") == "混排行备注 C"
              and cell(rows[2], "reason") == ""
              and cell(rows[3], "note") == "混排行备注 D"
              and cell(rows[3], "reason") == "text_unverified",
              f"C: reason={cell(rows[2], 'reason')!r} note={cell(rows[2], 'note')!r}；"
              f"D: reason={cell(rows[3], 'reason')!r} note={cell(rows[3], 'note')!r}")
        check("迁移后新追加行各列就位",
              cell(rows[4], "verdict") == "pending"
              and cell(rows[4], "reason") == "paper_warm"
              and cell(rows[4], "note") == "",
              f"verdict={cell(rows[4], 'verdict')!r} reason={cell(rows[4], 'reason')!r} "
              f"note={cell(rows[4], 'note')!r}")
        check("迁移前留下备份（可回退）",
              glob.glob(log + ".bak-*"),
              "原文件没备份就原地改写了")

        # 表头已对齐后必须「不再迁移」：否则每次 postcheck 都会重写整个日志并多留
        # 一个 .bak——恒等映射的结果一样，内容上看不出来，但日志目录会被备份淹掉。
        # 判据不能用「备份个数」：备份名带秒级时间戳，同一秒内的两次迁移会撞名
        # （坑 17 的老问题），个数看起来没变。改用**备份内容**判定——若第二次真的
        # 又迁移了一次，备份会被覆盖成「迁移后」的 16 列表头版本。
        img2 = os.path.join(d, "new2.png")
        Image.new("RGB", (1024, 1536), (252, 252, 252)).save(img2)
        subprocess.run([sys.executable, pc, img2, "--track", "A",
                        "--log-path", log, "--text", "ok"],
                       capture_output=True, text=True)
        rows_after = list(csv.reader(open(log, encoding="utf-8")))
        baks = sorted(glob.glob(log + ".bak-*"))
        bak_head = list(csv.reader(open(baks[0], encoding="utf-8")))[0] if baks else []
        check("表头已对齐的日志不再迁移（备份仍是迁移前那份旧日志）",
              len(baks) == 1 and bak_head == legacy_cols and len(rows_after) == 7,
              f"备份 {len(baks)} 个、备份表头 {len(bak_head)} 列"
              f"（期望 {len(legacy_cols)}）、总行数 {len(rows_after)}（期望 7）")

    # 认不出的表头：不猜列义，留备份后重开。猜的代价是把别的工具的列当成本表列，
    # 于是「记账」变成编造——错位记账比如实记账更坏。
    with tempfile.TemporaryDirectory() as d:
        log = os.path.join(d, "runs.csv")
        with open(log, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["foo", "bar", "baz"])
            w.writerow(["1", "2", "3"])
        img = os.path.join(d, "t.png")
        Image.new("RGB", (1024, 1536), (252, 252, 252)).save(img)
        subprocess.run([sys.executable, pc, img, "--track", "A",
                        "--log-path", log, "--text", "ok"],
                       capture_output=True, text=True)
        raw = list(csv.reader(open(log, encoding="utf-8")))
        baks = sorted(glob.glob(log + ".bak-*"))
        merged = any("foo" in r or "baz" in r for r in raw[1:])
        current_cols = legacy_cols[:13] + ["reason", "hint", "note"]
        check("认不出的表头：留备份后重开，不把外来行并进来",
              raw[0] == current_cols and len(raw) == 2 and not merged and baks,
              f"表头={raw[0][:4]}… 行数={len(raw)}（期望 2）"
              f" 并入了外来行={merged} 备份={len(baks)}")


def test_exit_policy_precedence():
    """退出码优先级是 postcheck 对外唯一的契约，必须有断言把它钉住。

    2026-09-23 把它从散落的五个 if 收成纯函数 `exit_policy()`，这里逐条钉优先级：
    blocker(1) 压过「有图未判定」(4)；未判定压过 pending(3)；一张都没判定出来时
    区分「工具坏了」(4) 与「压根没给图」(2)；全 pass 才是 0。
    纯函数才好钉——这正是把它抽出来的理由之一。
    """
    P = load("postcheck").exit_policy
    cases = [
        ("全 pass → 0", ["pass", "pass"], [], [], 0),
        ("pending → 3", ["pending"], [], [], 3),
        ("有 blocker → 1", ["pass", "blocker"], [], [], 1),
        ("blocker 压过工具错误 → 1", ["blocker"], [("a.png", "X")], [], 1),
        ("有图未判定 → 4（不是 blocker）", ["pass"], [("a.png", "X")], [], 4),
        ("路径不存在也算未判定 → 4", ["pass"], [], ["gone.png"], 4),
        ("未判定压过 pending → 4", ["pending"], [("a.png", "X")], [], 4),
        ("全都没判定出来 → 4", [], [("a.png", "X")], [], 4),
        ("图全不存在 → 4", [], [], ["gone.png"], 4),
        ("什么都没跑 → 2", [], [], [], 2),
    ]
    for label, verdicts, errs, skipped, want in cases:
        code, msg = P(verdicts, errs, skipped)
        check(label, code == want, f"得 {code}，期望 {want}")
        check(f"{label}：该给用户一句话时就给", bool(msg) or want == 2,
              "只有「什么都没跑」允许静默")


def test_box_mean_window_is_centered():
    """`paper_white._box_mean` 的窗口必须**居中**——它决定「局部背景」取的是哪一块。

    2026-09-23（对抗性审查实测）：padding 曾是不对称的 `((r+1, r), (r+1, r))`，
    于是输出 (i,j) 取的是原图 [i-r-1, i+r-1] 的均值，**整格向左上偏一格**：
    半径 r=1 时脉冲落在输出 [5,7] 而不是 [4,6]。后果是纸白归正时「局部背景」
    系统性取错一格，凭据是它自己的 docstring 一直声称是居中 r 邻域。

    判据两条，都不依赖实现细节：
      ① 脉冲响应：单点脉冲的输出支撑必须是以脉冲位置为中心、边长 2r+1 的方格；
      ② 与朴素实现逐点比对：把「居中邻域 + edge 扩展」直接写一遍，两者必须一致。
    只做②会放过「两边一起错」的情形，只做①会放过边缘处理的错，所以两条都要。
    """
    import numpy as np
    pw = load("paper_white")

    for r in (1, 3, 7):
        n = 2 * r + 5
        a = np.zeros((n, n))
        c = n // 2
        a[c, c] = 1.0
        out = pw._box_mean(a, r)
        rows = [i for i in range(n) if out[i].any()]
        cols = [j for j in range(n) if out[:, j].any()]
        want = list(range(c - r, c + r + 1))
        check(f"盒式均值窗口居中（r={r}）：支撑 {rows}", rows == want,
              f"期望 {want}，实际 {rows} —— 窗口偏了")

    rng = np.random.default_rng(0)
    a = rng.random((37, 41)) * 255.0
    r = 5
    got = pw._box_mean(a, r)
    h, w = a.shape
    rs = np.clip(np.arange(h)[:, None] + np.arange(-r, r + 1)[None, :], 0, h - 1)
    cs = np.clip(np.arange(w)[:, None] + np.arange(-r, r + 1)[None, :], 0, w - 1)
    naive = np.stack([a[np.ix_(rs[i], cs[j])].mean()
                      for i in range(h) for j in range(w)]).reshape(h, w)
    check("盒式均值与「居中邻域 + edge 扩展」的朴素实现一致",
          np.abs(got - naive).max() < 1e-9,
          f"最大差 {np.abs(got - naive).max():.3e}")


def test_grid_metrics_refuses_unreliable_parse():
    """类型 E：`ok=True` 必须意味着「**确实找到了一张多格网格**」，不许是自信的错答案。

    2026-09-23 真实产出验收发现：一张真正的 3×3 接触表（1536²、九张不同的图、四周无外边距）
    被报成 `ok=True, cols=1, rows=2, cells=2, gap_px=0`。根因是背景色取「四边环带的中位数」，
    无外边距时环带里装的就是各格内容，中位色落在内容色上，`is_bg` 把大片内容判成背景。

    危害在下游：postcheck 见到 `--expect-cells 9` 就判 `[cell_count]` blocker，
    而 blocker =「允许一次定向重生」＝再扣 5–10 积分。与坑 27（top_noise 13/13 全灭）同类：
    **提示性量测被当成硬判据**。

    故 `ok=True` 加两条必要条件：① 量得出净空（gap_px>0）；② 至少两格。
    本用例钉的是「收窄后仍能正确分辨」，两侧都要测：

      该拒的：齐边拼版（格间无缝，实测被读成 cells=1）
      该收的：带净空的 3×3 / 2×2，格数必须准，不许因为收紧判据而误伤

    **已知局限（本用例不判失败，只登记）**：缩略到 256 宽后极细的缝会消失——
    实测 4px 缝的 3×3 被读成 4 格。缝宽小于原图宽度约 1% 时本函数数不准格数，
    故 `--expect-cells` 只在缝可见的前提下才可信（见 CHANGELOG 待实施）。
    """
    from PIL import Image, ImageDraw
    gm = load("measure").grid_metrics

    def sheet(n, gap, edge, size=768, seed=7, white_tiles=0):
        im = Image.new("RGB", (size, size), (255, 255, 255))
        dr = ImageDraw.Draw(im)
        rng = __import__("random").Random(seed)
        cw = (size - gap * (n + 1) - edge * 2) // n
        for r in range(n):
            for c in range(n):
                x = edge + gap + c * (cw + gap)
                y = edge + gap + r * (cw + gap)
                k = r * n + c
                col = ((235, 235, 235) if k < white_tiles
                       else (rng.randint(20, 90), rng.randint(20, 90), rng.randint(20, 90)))
                dr.rectangle([x, y, x + cw - 1, y + cw - 1], fill=col)
        return im

    with tempfile.TemporaryDirectory() as d:
        p1 = os.path.join(d, "flush.png")
        sheet(3, gap=0, edge=40).save(p1)          # 格间无缝：没有网格信号
        g1 = gm(p1)
        check("齐边拼版（格间无缝）不报自信格数", g1["ok"] is False,
              f"ok={g1['ok']} cells={g1.get('cells')} gap_px={g1.get('gap_px')}")
        check("拒绝时必须给出可读原因", bool(g1.get("note")),
              "ok=False 却不说明原因，读者分不清「还没解析」与「这张不算网格」")

        p2 = os.path.join(d, "gap3x3.png")
        sheet(3, gap=18, edge=40).save(p2)
        g2 = gm(p2)
        check("带净空的 3×3 仍 ok=True 且格数正确", g2["ok"] and g2["cells"] == 9,
              f"ok={g2['ok']} cells={g2.get('cells')} gap_px={g2.get('gap_px')}"
              f" —— 收紧判据不能把真判据一起废掉")

        p3 = os.path.join(d, "gap2x2.png")
        sheet(2, gap=18, edge=40).save(p3)
        g3 = gm(p3)
        check("带净空的 2×2 同样 ok=True 且格数正确", g3["ok"] and g3["cells"] == 4,
              f"ok={g3['ok']} cells={g3.get('cells')}")

        # 已知局限：只登记，不判失败（修它要改 256 缩略的比例，越出本轮范围）
        p4 = os.path.join(d, "hairline.png")
        sheet(3, gap=4, edge=0).save(p4)
        g4 = gm(p4)
        if g4["ok"] and g4["cells"] != 9:
            print(f"      登记  细缝(4px) 3×3 被读成 {g4['cells']} 格 —— 已知局限，"
                  f"缝宽 < 原图宽约 1% 时格数不可信（见 CHANGELOG 待实施）")



def test_prompt_archive():
    """`--prompt`：把这一版的提示词原文收进技能内存档，命名带风格/主题/主标题。

    2026-09-23 资产盘点：技能的「已验证资产」= 风格 + 它的提示词，但提示词一向由出图流程
    写在出稿批次目录（不在技能内、不在备份内），技能只记 verdict。代价实测过：一批 11 个
    「实测 pass」的风格只以文件名留在台账里，盘点时差点被判成「取不回来」永久丢掉。

    门禁钉三件事，缺一条这个功能就白做：
      ① 落点的**名字带风格/主题/主标题**（取自 --note 约定）——不然存档等于换个地方散落，
         下次盘点还得靠反推；② **同一版重复验收要幂等**（同内容不产生 v2）；
      ③ `--no-log` 时**不落盘**（跑测试/验证不污染生产存档，与 runs.csv 同一条纪律）。
    """
    pc = os.path.join(HERE, "postcheck.py")
    with tempfile.TemporaryDirectory() as d:
        from PIL import Image
        img = os.path.join(d, "a.png")
        Image.new("RGB", (1024, 1536), (250, 249, 247)).save(img)
        log = os.path.join(d, "runs.csv")
        arc = os.path.join(d, "arc")
        prompt = os.path.join(d, "src_prompt.txt")
        body = "设计一张横版 3:2 概念海报。\n\n【三项输入】\n视觉风格：青花釉下彩\n"
        open(prompt, "w", encoding="utf-8").write(body)
        note = "A/青花釉下彩/青花/COBALT"
        base = [sys.executable, pc, img, "--track", "A", "--text", "ok",
                "--log-path", log, "--prompt", prompt, "--archive-dir", arc, "--note", note]
        subprocess.run(base, capture_output=True, text=True)
        got = sorted(os.listdir(arc)) if os.path.isdir(arc) else []
        check("提示词按「风格__主题__主标题」落名（不靠反推就能列出来）",
              got == ["青花釉下彩__青花__COBALT.txt"], f"实际: {got}")
        if got:
            saved = open(os.path.join(arc, got[0]), encoding="utf-8").read()
            check("存档是逐字原文（不是摘要、不是路径）", saved == body,
                  f"落了 {len(saved)} B，原文 {len(body)} B")
        subprocess.run(base, capture_output=True, text=True)
        again = sorted(os.listdir(arc)) if os.path.isdir(arc) else []
        check("同一版重复验收幂等（不产生 __v2）", again == got, f"实际: {again}")
        arc2 = os.path.join(d, "arc2")
        subprocess.run(base + ["--no-log", "--archive-dir", arc2], capture_output=True, text=True)
        check("--no-log 时不落存档（与 runs.csv 同一条纪律）",
              not os.path.isdir(arc2), f"仍然建了: {os.listdir(arc2) if os.path.isdir(arc2) else ''}")



def test_metrics_vectorized_equivalent():
    """`measure.metrics` 的数值必须与「逐像素朴素实现」逐字段一致。

    2026-09-23：把 metrics 从「展开成 9.8 万个 RGB 三元组、对同一批像素做十几趟
    `min()/max()`」改成 PIL 的 C 层算子——`ImageChops` 出 min/max 通道、直方图出分布、
    `ImageStat.Stat(im, mask)` 出带掩膜均值。1024×1536 单次 126 ms → 34 ms，
    这是 postcheck 默认路径里最大的一笔纯 Python 开销。

    重写必须钉等价性：**快而错是最坏的结果**。参照实现就是改动前那一版，
    在原式与新版都覆盖的输入上逐字段比对。

    边界必须覆盖，且各对应一处真实陷阱：
      · 全黑图 → `base = 0`，`base - 8` 为负 —— 直方图切片会退化成**负索引**，
        实测把某张真图的 `paper%` 从 0.2% 报成 100%（`_count_gt` 的夹位就是为它加的）；
      · 全白图 → `base = 255`，`240 + 1` 越界 —— 不夹位会把「比白更白」算成有像素。
    只用中间调夹具的话，这两条都测不到。
    """
    import random
    import tempfile
    from PIL import Image
    met = load("measure")

    def naive(path):
        """改动前的实现（逐像素、多趟扫描）——等价性的参照。"""
        from PIL import ImageStat
        im = Image.open(path).convert("RGB")
        W, H = im.size
        scale = 256.0 / W
        small = im.resize((256, max(1, int(H * scale))), Image.LANCZOS)
        try:
            px = list(small.get_flattened_data())
        except AttributeError:
            px = list(small.getdata())
        n = len(px)
        white = [p for p in px if min(p) > 240]
        near = [p for p in px if min(p) > 215]
        mins = sorted(min(p) for p in px)
        base = float(mins[len(mins) // 2])
        lo_zone = max(215, base - 8)
        zone = [p for p in px if min(p) > lo_zone] or near or white
        wr = sum(p[0] for p in zone) / max(len(zone), 1)
        wb = sum(p[2] for p in zone) / max(len(zone), 1)
        sat = sum(max(p) - min(p) for p in px if max(p) - min(p) > 8) / n
        row = {"base": base, "white%": len(white) / n * 100,
               "paper%": sum(1 for p in px if min(p) > base - 8) / n * 100,
               "near%": len(near) / n * 100, "R-B": wr - wb, "sat": sat}
        top = im.crop((int(W * 0.20), int(H * 0.04), int(W * 0.80), int(H * 0.25)))
        st = ImageStat.Stat(top)
        r, g, b = st.mean
        row["top_R"], row["top_G"], row["top_B"] = r, g, b
        row["top_R-B"] = r - b
        row["top_noise"] = sum(st.stddev) / 3
        row["top_dev"] = abs((r + g + b) / 3 - base)
        try:
            tpx = list(top.get_flattened_data())
        except AttributeError:
            tpx = list(top.getdata())
        tn = max(len(tpx), 1)
        row["top_dark%"] = sum(1 for p in tpx if min(p) < 150) / tn * 100
        row["top_white%"] = sum(1 for p in tpx if min(p) > 240) / tn * 100
        row["top_zone%"] = sum(1 for p in tpx if min(p) > max(215, base - 8)) / tn * 100
        return row

    rng = random.Random(0)
    fields = ("base", "white%", "paper%", "near%", "R-B", "sat",
              "top_R", "top_G", "top_B", "top_R-B", "top_noise", "top_dev",
              "top_dark%", "top_white%", "top_zone%")
    worst, cases = {}, []
    with tempfile.TemporaryDirectory() as d:
        # 全黑 / 全白 / 纸底 / 渐变（含彩色）/ 随机噪声
        cases.append(("all-black", Image.new("RGB", (800, 600), (0, 0, 0))))
        cases.append(("all-white", Image.new("RGB", (800, 600), (255, 255, 255))))
        cases.append(("paper", Image.new("RGB", (1024, 1536), (236, 232, 222))))
        grad = Image.new("RGB", (900, 1200))
        gp = grad.load()
        for y in range(1200):
            for x in range(900):
                gp[x, y] = (x % 256, y % 256, (x + y) % 256)
        cases.append(("gradient", grad))
        noise = Image.new("RGB", (1024, 1536))
        np_ = noise.load()
        for y in range(1536):
            for x in range(1024):
                np_[x, y] = (rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255))
        cases.append(("noise", noise))

        for name, im in cases:
            p = os.path.join(d, name + ".png")
            im.save(p)
            ref, got = naive(p), met.metrics(p, True)[1]
            bad = [f for f in fields if abs(ref[f] - got[f]) > 1e-9]
            for f in fields:
                worst[f] = max(worst.get(f, 0.0), abs(ref[f] - got[f]))
            check(f"metrics 与朴素实现逐字段一致（{name}）", not bad,
                  f"不一致字段：{[(f, round(ref[f], 4), round(got[f], 4)) for f in bad][:4]}")

    # 边界值单独钉住：这两处正是直方图切片会踩到负索引 / 越界的地方。
    # 注意**不能凭直觉写期望值**——全黑图 base=0 ⇒ 原式 `min(p) > -8` 恒真 ⇒ paper% 是 100
    # （不是 0）。所以期望值一律取自朴素参照，而不是「应该是多少」的印象。
    # 真正要防的是「既非 0 也非 100 的错数」：不加夹位时 `hist[t+1:]` 在负 t 下退化成
    # 求最后几档之和，实测把一张真图的 paper% 报成 0.217%。
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "black.png")
        Image.new("RGB", (400, 400), (0, 0, 0)).save(p)
        row = met.metrics(p, True)[1]
        ref = naive(p)
        check("全黑图（base=0）paper% 与朴素实现一致", row["paper%"] == ref["paper%"],
              f"paper%={row['paper%']} 参照={ref['paper%']} base={row['base']} "
              f"—— 直方图切片落到负索引了")
        p = os.path.join(d, "white.png")
        Image.new("RGB", (400, 400), (255, 255, 255)).save(p)
        row = met.metrics(p, True)[1]
        ref = naive(p)
        check("全白图（base=255）top_white% 与朴素实现一致",
              row["top_white%"] == ref["top_white%"] == 100.0,
              f"top_white%={row['top_white%']} 参照={ref['top_white%']}")


TESTS = [test_prompt_archive, test_postcheck_verdict,
         test_cli_help,
         test_top_noise_not_blocker,
         test_postcheck_track_e,
         test_no_duplicate_finding_codes,
         test_postcheck_wm_not_false_blocker,
         test_postcheck_dewm_backcompat,
         test_reason_codes_recorded,
         test_log_header_migrated,
         test_exit_policy_precedence,
         test_box_mean_window_is_centered,
         test_grid_metrics_refuses_unreliable_parse,
         test_metrics_vectorized_equivalent]
