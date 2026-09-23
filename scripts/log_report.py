#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""log_report — 把本地使用日志读成一份「下一步该改什么」的清单（只读，不改任何东西）。

第一性原理：**改技能的动力应当来自数据，不是来自印象。**
过去每踩一次坑就写一节文档，于是 SKILL.md 31.5 KB、pitfalls.md 114 KB；
而「这个坑踩过几次」「这个脚本有没有人用」「哪一步在变慢」没有一处能答。
`scripts/_log.py` 把每次调用记成 JSONL，本脚本负责把那些行变成判断。

读两份日志（都只在本机，都不进发布仓）：
  scripts/logs/usage.jsonl   使用日志：谁被调用了、退出码、耗时、宿主   ← _log.py 写
  scripts/logs/runs.csv      出图记账：量测指标、verdict、reason/hint 码  ← postcheck.py 写

用法：
  python3 scripts/log_report.py              # 全量报告
  python3 scripts/log_report.py --days 7     # 只看最近 7 天
  python3 scripts/log_report.py --json       # 机器可读（喂给别的分析用）

退出码恒为 0：这是分析工具，不是门禁。数据不足时它明说「样本不够」，
不拿两三条记录编结论——那正是拍阈值的老毛病（见 sub-skills/verify/evidence.md）。
"""

import argparse
import collections
import csv
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(HERE, "logs")
USAGE = os.path.join(LOG_DIR, "usage.jsonl")
RUNS = os.path.join(LOG_DIR, "runs.csv")
ROTATED = (f"{USAGE}.1", f"{USAGE}.2")

# 样本量的诚实下限：低于它只报数、不给结论（与 calibrate_thresholds 的态度一致）
MIN_N_FOR_CLAIM = 5


def read_usage():
    """读全部使用日志（含轮转份）。坏行跳过并计数——从不因为一行坏了丢掉整份。"""
    rows, bad, files = [], 0, []
    for path in (USAGE,) + ROTATED:
        if not os.path.exists(path):
            continue
        files.append(path)
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        bad += 1
                        continue
                    if isinstance(obj, dict):
                        rows.append(obj)
                    else:
                        bad += 1
        except OSError:
            bad += 1
    return rows, bad, files


def read_runs():
    """读出图记账。表头不认识就明说，不猜列义（同 postcheck.align_log 的态度）。"""
    if not os.path.exists(RUNS):
        return [], []
    try:
        with open(RUNS, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except (OSError, UnicodeDecodeError):
        return [], ["runs.csv 读不了"]
    return rows, []


def entry_scripts():
    """本技能自带的所有入口脚本（含 main 的那些）——用于「谁从没被调用过」。

    判据是**顶格**的 `if __name__ == "__main__":`：_log.py 的 docstring 里写着
    这句用法示例（缩进状态），子串匹配会把它误收成入口，于是「从没被调用过」
    里永远挂着一条假记录。与 tests/test_docs_gates.py 的 _entry_scripts 同一判据。
    """
    out = []
    for name in sorted(os.listdir(HERE)):
        if not name.endswith(".py") or name.startswith("_"):
            continue
        p = os.path.join(HERE, name)
        try:
            if re.search(r'^if __name__ == "__main__":',
                         open(p, encoding="utf-8").read(), re.M):
                out.append(name[:-3])
        except OSError:
            continue
    return out


def within(rows, days):
    """只保留最近 N 天的记录。时间解析不了的**保留**——宁可多算，不要把数据悄悄丢掉。"""
    if not days:
        return rows
    cut = time.time() - days * 86400
    out = []
    for r in rows:
        try:
            t = time.mktime(time.strptime(str(r.get("ts", "")), "%Y-%m-%d %H:%M:%S"))
        except (ValueError, OverflowError):
            out.append(r)
            continue
        if t >= cut:
            out.append(r)
    return out


def pct(vals, q):
    """分位数（最近秩法）。样本少时也稳定，不引入插值假设。"""
    if not vals:
        return None
    s = sorted(vals)
    k = max(0, min(len(s) - 1, int(round(q * (len(s) - 1)))))
    return s[k]


def summarize(rows, runs):
    """把两份日志压成结构化摘要（报告与 --json 共用同一份计算，不重复实现）。"""
    by_script = collections.defaultdict(
        lambda: {"n": 0, "fail": 0, "ms": [], "codes": collections.Counter(),
                 "errs": collections.Counter()})
    hosts, pys, dates, flags = collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter()
    for r in rows:
        s = str(r.get("script", "?"))
        d = by_script[s]
        d["n"] += 1
        code = r.get("code", 0)
        d["codes"][code] += 1
        # **不要拿退出码当「崩溃」**（2026-09-23 自我修正）：本技能各脚本的退出码是
        # **判定值**，不是成败 —— postcheck 的 1/3/4 分别是 blocker / pending / 工具错误，
        # preflight 的 1 是「有阻断项」。按「非 0 即失败」统计，会把满屏正常判定报成
        # 80% 失败率（实测踩到）。真崩溃只认「抛异常」（err 非空）。
        if r.get("err"):
            d["fail"] += 1
            d["errs"][str(r["err"])] += 1
        ms = r.get("ms")
        if isinstance(ms, (int, float)):
            d["ms"].append(float(ms))
        hosts[str(r.get("host", "?"))] += 1
        pys[str(r.get("py", "?"))] += 1
        ts = str(r.get("ts", ""))[:10]
        if ts:
            dates[ts] += 1
        for fl in (r.get("flags") or []):
            flags[str(fl)] += 1

    verdicts, tracks, codes = collections.Counter(), collections.Counter(), collections.Counter()
    for row in runs:
        verdicts[str(row.get("verdict", ""))] += 1
        tracks[str(row.get("track", ""))] += 1
        for col in ("reason", "hint"):
            for c in str(row.get(col, "") or "").split(","):
                c = c.strip()
                if c:
                    codes[c] += 1
    # 非 run 的事件（守卫触发、判据退化中止…）。这些才是「哪个坑真在高频发生」的硬证据：
    # run 行只说「谁被跑过」，事件行说「哪条防线真的被撞到了」。
    events = collections.Counter()
    for r in rows:
        ev = str(r.get("ev", "run"))
        if ev != "run":
            events[(str(r.get("script", "?")), ev, str(r.get("why", "")))] += 1

    return {"by_script": by_script, "hosts": hosts, "pys": pys, "dates": dates,
            "flags": flags, "verdicts": verdicts, "tracks": tracks, "codes": codes,
            "events": events}


def report(rows, bad, files, runs, run_err):
    S = summarize(rows, runs)
    by_script = S["by_script"]
    print("=" * 68)
    print("taxue-imagegen 本地使用报告")
    print("=" * 68)
    print(f"使用日志：{len(rows):,} 条" + (f"（跳过坏行 {bad}）" if bad else "") +
          f"  来源 {len(files)} 份")
    if rows:
        ds = sorted(d for d in S["dates"] if d)
        if ds:
            print(f"时间跨度：{ds[0]} → {ds[-1]}（{len(ds)} 天有活动）")
    print(f"出图记账：{len(runs):,} 行" + (f"（{run_err[0]}）" if run_err else ""))
    if not rows and not runs:
        print("\n还没有数据。用一次技能（跑 fill_meta / postcheck 等）就会开始记。")
        return S

    # ── 1. 谁在用、谁没用过 ─────────────────────────────────────────────
    entries = entry_scripts()
    used = {s for s in by_script if by_script[s]["n"] > 0}
    unused = [e for e in entries if e not in used]
    print("\n-- 脚本调用（按次数）" + "-" * 42)
    if not by_script:
        print("  （无）")
    for s, d in sorted(by_script.items(), key=lambda kv: -kv[1]["n"]):
        p50, p95 = pct(d["ms"], 0.5), pct(d["ms"], 0.95)
        line = f"  {s:<24} {d['n']:>5} 次"
        if d["fail"]:
            line += f"  崩溃 {d['fail']}（{d['fail'] / d['n'] * 100:.0f}%）"
        if p50 is not None:
            line += f"  p50 {p50:,.0f}ms  p95 {p95:,.0f}ms"
        print(line)
        # 退出码是判定值：只在非 0 时列出，读者自己判断。含义随脚本而异，
        # 不在这里写死（postcheck 的 1 = blocker，fill_meta 的 1 = preflight 有阻断）。
        codes = {c: n for c, n in d["codes"].items() if c not in (0, None)}
        if codes:
            print("      退出码（含义随脚本而异）："
                  + "、".join(f"{c}×{n}" for c, n in sorted(codes.items(),
                                                            key=lambda kv: -kv[1])))
        if d["errs"]:
            for e, c in d["errs"].most_common(3):
                print(f"      ↳ {e} × {c}")
    if unused:
        print(f"\n  从没被调用过（{len(unused)}/{len(entries)}）：{'、'.join(unused[:12])}")
        print("  → 连续几轮仍是 0 的，是瘦身候选；也要排除「日志接入晚于它的使用」")

    # ── 2. 环境画像（普适性的证据面）──────────────────────────────────
    print("\n-- 环境画像" + "-" * 54)
    print("  宿主：" + ("、".join(f"{k}×{v}" for k, v in S["hosts"].most_common()) or "（无）"))
    print("  Python：" + ("、".join(f"{k}×{v}" for k, v in S["pys"].most_common()) or "（无）"))
    if S["flags"]:
        top = "、".join(f"{k}×{v}" for k, v in S["flags"].most_common(8))
        print(f"  常用开关：{top}")
    if len(S["hosts"]) > 1:
        print("  ↑ 出现多种宿主：换宿主相关的问题（references/jimeng-env.md、v1.21.1 的解释器坑）优先查这里")

    # ── 3. 防线被触发：日志里最有行动价值的一段 ──────────────────────
    if S["events"]:
        print("\n-- 防线被触发（事件）" + "-" * 42)
        for (script, ev, why), n in S["events"].most_common(10):
            print(f"  {n:>4}×  {script:<16} {ev:<16} {why}")
        print("  → 触发次数高的那条，问题多半不在守卫本身，而在调用方习惯或文档示例：")
        print("    该改文档/默认值，而不是继续加守卫。")

    # ── 4. 出图记账 ──────────────────────────────────────────────────
    if runs:
        print("\n-- 出图记账（runs.csv）" + "-" * 42)
        print("  verdict：" + "、".join(f"{k}×{v}" for k, v in S["verdicts"].most_common()))
        print("  类型：" + "、".join(f"{k}×{v}" for k, v in S["tracks"].most_common()))
        if S["codes"]:
            print("  出得最多的码（reason/hint 合并）：")
            for c, n in S["codes"].most_common(10):
                print(f"    {n:>4}  {c}")
        if len(S["codes"]) and len(runs) >= MIN_N_FOR_CLAIM:
            top_code, top_n = S["codes"].most_common(1)[0]
            rate = top_n / len(runs) * 100
            print(f"\n  → 最高频码 `{top_code}` 出现在 {rate:.0f}% 的记账行上。")
            print("    若它是 hint（只提示）而出现率又很高：说明提示没在改变行为，")
            print("    该考虑改默认值或改模板，而不是继续加提示。")
            print("    若它是 reason 且高频：按坑号回查 references/pitfalls.md，")
            print("    看能不能前移到 preflight 做出图前的文本拦截。")
    print("\n-- 判读纪律" + "-" * 56)
    print(f"  样本 < {MIN_N_FOR_CLAIM} 条的结论一律不可外推（同 evidence.md 的采集纪律）。")
    print("  要改文档，先让这里的数据指到同一件事，再动 SKILL.md / pitfalls.md。")
    return S


def main():
    ap = argparse.ArgumentParser(description="读本地使用日志，输出下一步该改什么（只读）")
    ap.add_argument("--days", type=int, default=None, help="只看最近 N 天")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = ap.parse_args()

    rows, bad, files = read_usage()
    rows = within(rows, args.days)
    runs, run_err = read_runs()

    if args.json:
        S = summarize(rows, runs)
        entries = entry_scripts()
        used = {s for s in S["by_script"] if S["by_script"][s]["n"] > 0}
        out = {
            "usage_rows": len(rows), "usage_bad_lines": bad, "runs_rows": len(runs),
            "hosts": dict(S["hosts"]), "python": dict(S["pys"]),
            "verdicts": dict(S["verdicts"]), "tracks": dict(S["tracks"]),
            "codes": dict(S["codes"]), "flags": dict(S["flags"]),
            "events": {f"{sc}/{e}/{w}": n for (sc, e, w), n in S["events"].items()},
            "scripts": {k: {"n": v["n"], "crashed": v["fail"],
                            "p50_ms": pct(v["ms"], 0.5), "p95_ms": pct(v["ms"], 0.95),
                            "errors": dict(v["errs"])}
                        for k, v in S["by_script"].items()},
            "never_called": [e for e in entries if e not in used],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    report(rows, bad, files, runs, run_err)
    return 0


if __name__ == "__main__":
    sys.exit(main())
