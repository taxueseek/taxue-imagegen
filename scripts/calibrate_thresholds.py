#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""calibrate_thresholds — 用「已验收成品」反查每条验收判据的触发率。

【为什么需要它】
postcheck 的 blocker 在评审卡里等于「允许一次定向重生」，而重生 = 再扣 5–10 积分。
所以一条判据如果在本该通过的成品上频繁触发，它就不是检测器，而是**积分黑洞**。

本技能吃过两次这个亏，都是事后靠人肉发现的：
  · top_noise ≥ 6：13/13 张真实海报全灭（坑 27）——当时只把这一条降级了；
  · 同类病没被一起审：2026-09-18 拿 202 张已归档成品实测，R-B ≥ 3 触发 47%、
    顶部 top_dev ≥ 12 触发 65%、类型 B 的 white% 30–65 触发 82%。
    而纯白底子集里 R-B ≥ 3 只有 4%、纸底子集里 63% —— 说明它测的是
    「有没有用纸底风格」，不是「画得好不好」。

`sub-skills/verify/evidence.md` 早就写了纪律：「答不出在多少张什么图上实测、
两组数据分别多少的阈值，只能当诊断值，不许判 blocker」。本工具就是把这句话
变成可重复执行的东西——**用已验收成品当正样本，算每条判据的触发率**。

【怎么用】
  # 1) 看现状：每条候选判据在已验收成品上的触发率
  python3 calibrate_thresholds.py ~/Pictures/WorkBuddy

  # 2) 扫参数：给某个阈值扫一遍，挑触发率可接受的那个点
  python3 calibrate_thresholds.py <目录> --sweep top_zone
  python3 calibrate_thresholds.py <目录> --sweep base

  # 3) 存成 JSON 供 evidence.md 引用
  python3 calibrate_thresholds.py <目录> --json /tmp/calib.json

【判读纪律】
  · 正样本 = 你**留下来**的成品。它不等于「完美」，但「判据在它身上高频触发」
    一定说明判据与真实验收标准不符。
  · 触发率不是误报率：留图可能本来就带瑕疵。要定 blocker 还得有负样本
    （真翻车的图）——本地没有成体系的负样本，所以本工具只报数、不下结论。
  · 别只看总触发率：先按场景（白底/纸底、各 track）分组，分不开的阈值就是
    绝对值误用，应该改成相对量或分场景门控。
"""
import argparse
import glob
import importlib.util
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_metrics():
    spec = importlib.util.spec_from_file_location("measure", os.path.join(HERE, "measure.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.metrics


# 候选判据：名字 → (依赖字段, 判定函数(阈值), 现役是否 blocker)
RULES = {
    "R-B>=3（泛黄，现役 A/B blocker）": (lambda r, t=3.0: r["R-B"] >= t),
    "top_R-B>=3（顶部发黄，现役 A blocker）": (lambda r, t=3.0: r.get("top_R-B", 0) >= t),
    "top_dev>=12（顶部被侵入，现役 A blocker）": (lambda r, t=12.0: r.get("top_dev", 0) >= t),
    "white%∉[30,65]（现役 B blocker）": (lambda r, t=0: not (30 <= r["white%"] <= 65)),
    "sat>70（现役 B blocker）": (lambda r, t=70.0: r["sat"] > t),
    "top_zone%<50（纸底相对口径，候选）": (lambda r, t=50.0: r.get("top_zone%", 100) < t),
    "top_zone%<50 且 top_dark%≥40（候选：实体占满）":
        (lambda r, t=50.0: r.get("top_zone%", 100) < t and r.get("top_dark%", 0) >= 40),
    "paper%<30（纸底相对口径，候选替 B）": (lambda r, t=30.0: r.get("paper%", 100) < t),
}


def collect(paths):
    metrics = _load_metrics()
    files = []
    for p in paths:
        if os.path.isdir(p):
            files += [f for f in glob.glob(os.path.join(p, "**", "*.png"), recursive=True)
                      if not any(x in f for x in ("_clean", "_reports", "_tools", "_textband"))
                      and f.lower().endswith(".png")]
        else:
            files.append(p)
    rows = []
    for f in sorted(set(files)):
        try:
            _, r = metrics(f, True)
        except Exception as e:  # noqa: BLE001
            print(f"  跳过 {os.path.basename(f)}: {e}", file=sys.stderr)
            continue
        r["_path"] = f
        rows.append(r)
    return rows


def report(rows):
    n = len(rows)
    if not n:
        raise SystemExit("没读到图片")
    print(f"样本 n={n}（正样本＝已留存的成品）\n")
    print("=== 逐条判据触发率 ===")
    for name, fn in RULES.items():
        c = sum(1 for r in rows if fn(r))
        print(f"  {c:>4}/{n}  {100*c/n:5.1f}%   {name}")

    print("\n=== 按「底色是否为白」分组（分场景是否分得开）===")
    white = [r for r in rows if r["white%"] > 30]
    paper = [r for r in rows if r["white%"] <= 30]
    for label, grp in (("纯白底", white), ("纸底/纹理底", paper)):
        if not grp:
            continue
        rb = sum(1 for r in grp if r["R-B"] >= 3)
        print(f"  {label:<10} n={len(grp):>4}  R-B≥3 占 {100*rb/len(grp):5.1f}%  "
              f"base 中位 {statistics.median(r['base'] for r in grp):5.1f}  "
              f"paper% 中位 {statistics.median(r['paper%'] for r in grp):5.1f}")
    print("\n=== 分位数（挑阈值用）===")
    for key in ("base", "paper%", "white%", "R-B", "top_zone%", "top_dev", "top_dark%", "sat"):
        vals = sorted(r.get(key, 0) for r in rows)
        q = lambda p: vals[min(len(vals) - 1, int(len(vals) * p))]
        print(f"  {key:<11} p05={q(.05):7.1f} p25={q(.25):7.1f} 中位={statistics.median(vals):7.1f} "
              f"p75={q(.75):7.1f} p95={q(.95):7.1f}")


def sweep(rows, which):
    n = len(rows)
    print(f"=== {which} 扫描（触发率＝判 blocker 的比例，越低越好）===")
    if which == "base":
        # 用 base 当「本该是白」的门：base 以上才判 R-B
        for t in (230, 235, 240, 242, 244, 246, 248, 250):
            sub = [r for r in rows if r["base"] >= t]
            if not sub:
                print(f"  base≥{t}: 无样本")
                continue
            c = sum(1 for r in sub if r["R-B"] >= 3)
            print(f"  base≥{t}: 命中 {len(sub):>4}/{n} 张，其中 R-B≥3 占 {100*c/len(sub):5.1f}%")
    elif which == "top_zone":
        for t in (20, 30, 40, 50, 60, 70, 80):
            c = sum(1 for r in rows if r.get("top_zone%", 100) < t)
            c2 = sum(1 for r in rows if r.get("top_zone%", 100) < t and r.get("top_dark%", 0) >= 40)
            print(f"  top_zone%<{t}: 单独 {100*c/n:5.1f}%   与 dark%≥40 同时 {100*c2/n:5.1f}%")
    elif which == "paper":
        for t in (20, 30, 40, 50, 60):
            c = sum(1 for r in rows if r.get("paper%", 100) < t)
            print(f"  paper%<{t}: {100*c/n:5.1f}%")
    else:
        raise SystemExit(f"未知扫描目标 {which}")


def main():
    ap = argparse.ArgumentParser(description="用已验收成品反查验收判据的触发率")
    ap.add_argument("paths", nargs="*",
                    default=[os.path.expanduser("~/Pictures/WorkBuddy")],
                    help="成品目录（默认 ~/Pictures/WorkBuddy）")
    ap.add_argument("--sweep", choices=["base", "top_zone", "paper"], help="扫参数挑阈值")
    ap.add_argument("--json", help="把逐图量测与触发率写到 JSON")
    a = ap.parse_args()
    rows = collect(a.paths)
    report(rows)
    if a.sweep:
        print()
        sweep(rows, a.sweep)
    if a.json:
        out = {"n": len(rows),
               "trigger_rates": {name: sum(1 for r in rows if fn(r)) / len(rows)
                                 for name, fn in RULES.items()},
               "rows": rows}
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print(f"\nJSON → {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
