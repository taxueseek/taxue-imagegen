#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_env — 依赖自检：缺 numpy / PIL / cv2 时说人话，而不是甩一屏 traceback。

【为什么需要它】
本技能的脚本要 numpy + PIL（量测）与 opencv（去水印）。这些依赖**不保证**在
任何解释器里都有：实测本机 managed 解释器（3.13.12）没有 cv2，而系统 python3
有；`run_tests.sh` 因此专门做了解释器探测（并修过一次「裸 python3 导致 3 项假失败」）。

但**用户直接调用的脚本没有这层保护**：缺依赖时抛的是
`ModuleNotFoundError: No module named 'cv2'`，看不出该装什么、该换哪个解释器，
只能来人肉排查。这就是「未知使用环境的普适性」缺口。

【怎么用】
入口脚本把顶层重型 import 包一层：

    try:
        import numpy as np
        import cv2
    except ImportError as e:
        import os, sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import _env; _env.die(e)

`die()` 会打印：缺哪个包 → 两条修复路径（换解释器 / 装包）→ 本机可用的解释器长什么样，
然后以退出码 2 结束（与 argparse 的用法错误区分开：2 也是「环境没准备好」）。
"""
import importlib
import os
import re
import sys

# 缺依赖时给出的两条修复路径。第一条优先：本技能在 WorkBuddy 里跑，
# 内置解释器一定带齐依赖，换过去最快也最不容易污染系统环境。
MANAGED_HINT = "~/.workbuddy/binaries/python/envs/default/bin/python3"
PKG_HINT = {"cv2": "opencv-python-headless", "PIL": "pillow", "numpy": "numpy"}


def _pkg_of(exc):
    """从异常里尽量确定「缺的是哪个包」。确定不了就返回 None——不猜。"""
    name = getattr(exc, "name", None)
    if not name:
        m = re.search(r"named '([A-Za-z_][\w.]*)'", str(exc))
        name = m.group(1) if m else None
    return (name or "").split(".")[0] or None


def die(exc, modules=None):
    """报告缺失依赖并退出。`modules` 是本脚本真正需要的包（调用方最清楚）。

    给不出包名时**不猜、也不编 pip 命令**——只把两条修复路径和真实报错给出来，
    否则「pip install simulated missing cv2」这种假命令比 traceback 更误导。
    """
    pkg = _pkg_of(exc)
    print(f"❌ 依赖不可用：{exc}", file=sys.stderr)
    if modules:
        print("   本脚本需要：" + "、".join(modules), file=sys.stderr)
    print(f"   ① 换解释器重跑（推荐，WorkBuddy 内置的带齐依赖）：{MANAGED_HINT}", file=sys.stderr)
    if pkg:
        target = PKG_HINT.get(pkg, pkg)
        print(f"   ② 或装上它：{sys.executable} -m pip install {target}", file=sys.stderr)
    else:
        print("   ② 或按上面的报错装齐依赖后重跑", file=sys.stderr)
    print(f"   当前解释器：{sys.executable}", file=sys.stderr)
    raise SystemExit(2)


def need(*names):
    """按需导入一组模块；缺任何一个就走 `die()` 的人话分支。

    返回 {名字: 模块}。给「只想在函数里用重型依赖」的脚本用，避免顶层 import
    把整个文件变成不可导入（`run_tests.sh` 的 import-check 会连坐）。
    """
    out = {}
    missing = []
    for n in names:
        try:
            out[n] = importlib.import_module(n)
        except ImportError:  # noqa: PERF203
            missing.append(n)
    if missing:
        class _E(ImportError):
            name = missing[0]
        die(_E(), modules=missing)
    return out


def best_interpreter():
    """本机可能可用的解释器候选（只用于提示，不用于实际切换进程）。"""
    cands = [os.environ.get("PYTHON"), MANAGED_HINT,
             "/opt/homebrew/bin/python3", "/usr/bin/python3", sys.executable]
    return [os.path.expanduser(c) for c in cands if c]
