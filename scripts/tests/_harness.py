#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_harness — 回归测试的公共底座（load / check / 结果收集 / 体积预算）。

2026-09-18：test_regressions.py 单文件长到 1,304 行，按被测域拆成
scripts/tests/ 下的五个模块；本文件只放它们共享的机制，断言本体一律在各域模块里。

契约（不要改）：
  - `python3 scripts/test_regressions.py` 的退出码：0=全过，1=有失败；
    run_tests.sh 第 [4/8] 步与 CI 都只认它。
  - check() 的输出格式（"ok  "/"FAIL "）被人眼与文档依赖，改动需同步说明。
"""
import importlib.util
import os
import sys

# scripts/ 目录：被测模块按文件路径加载，普通 import（import audit_wm 等）也靠它
SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(SCRIPTS)
HERE = SCRIPTS  # 各域模块沿用旧名 HERE（= scripts/），断言正文零改动
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

# ── 常驻面 / 触发面体积预算（唯一真源；2026-09-18 定）────────────────
# 定这两个数的理由：优化轮把 description 从 9,717 B（占本机 82 个 skill 描述总长
# 的 18.7%、中位数的 28 倍）压到 1,786 B；SKILL.md 从 52,317 B 一路压到
# 29,652 B（1.19 轮 34,228 B，1.20 轮再砍 §3 步4 与 §8 的重复叙述）。
# 预算不是「刚好等于现状」，而是留余量挡住回涨——真要突破，请连同理由
# 一起改这里，不要为了通过而调大。
SURFACE_BUDGETS = {"description": 2000, "skill_md": 36000}

_results = []


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check(label, cond, why=""):
    _results.append((bool(cond), label, why))
    mark = "ok  " if cond else "FAIL"
    print(f"  {mark} {label}" + (f"  <- {why}" if not cond and why else ""))
