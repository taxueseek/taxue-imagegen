#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_storyboard_ink.py — 向后兼容入口（已并入 build_storyboard.py）。

v1.10 起两个案例合并在 `build_storyboard.py`（数据与逻辑分离，去掉逐字重复的 main()）。
本文件保留为旧命令的转发壳，等价于：

    python3 build_storyboard.py --case ink

新代码请直接用后者；此壳仅保证既有文档/脚本里的旧路径继续可用。
"""
import _log
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from build_storyboard import CASES, build  # noqa: E402


def main():
    # 2026-09-23 修：本壳原先没有 argparse，于是 `--help` 被**默默忽略并直接干活**——
    # 实测 `python3 build_storyboard_ink.py --help` 真写出 9 个 prompt 文件。
    # 一个「问它怎么用」的动作把活干了，比报错更糟：调用方以为只是在看帮助。
    ap = argparse.ArgumentParser(
        description="兼容壳：等价于 build_storyboard.py --case ink（新代码请直接用后者）")
    ap.parse_args()
    cfg = CASES["ink"]
    out_dir = os.path.join(HERE, cfg["out"])
    build(out_dir, cfg["style"], cfg["char"], cfg["neg"], cfg["scenes"])


if __name__ == "__main__":
    _log.run("build_storyboard_ink", main)
