#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""preflight 域：词边界（坑 23）、槽位检测（坑 24）、引号声明（坑 5）、track/尺寸表。"""
import os
import re
import subprocess
import sys

from _harness import HERE, ROOT, check, load


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


TESTS = [test_preflight_word_boundary, test_preflight_slot_detection,
         test_preflight_quote_declaration, test_preflight_tracks_and_sizes]
