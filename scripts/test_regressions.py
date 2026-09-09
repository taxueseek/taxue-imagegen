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


# ── postcheck verdict 三档 ───────────────────────────────────────
def test_postcheck_verdict():
    r = subprocess.run([sys.executable, os.path.join(HERE, "postcheck.py"),
                        "--help"], capture_output=True, text=True)
    check("postcheck --track 支持 C/D",
          all(f"'{x}'" in r.stdout or x in r.stdout for x in ("C", "D")),
          "C/D 无法验收")
    src = open(os.path.join(HERE, "postcheck.py"), encoding="utf-8").read()
    check("postcheck 有 pending 档", '"pending"' in src,
          "文字未核对会被记为 pass")
    check("postcheck pending 退出码 3", "sys.exit(3)" in src,
          "退出码未区分")


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
               test_postcheck_verdict, test_fill_meta_track_c,
               test_solvability_guard,
               test_doc_consistency, test_no_machine_paths):
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
