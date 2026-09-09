#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_storyboard_ink.py — 向后兼容入口（已并入 build_storyboard.py）。

v1.10 起两个案例合并在 `build_storyboard.py`（数据与逻辑分离，去掉逐字重复的 main()）。
本文件保留为旧命令的转发壳，等价于：

    python3 build_storyboard.py --case ink

新代码请直接用后者；此壳仅保证既有文档/脚本里的旧路径继续可用。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from build_storyboard import CASES, build  # noqa: E402


def main():
    cfg = CASES["ink"]
    out_dir = os.path.join(HERE, cfg["out"])
    build(out_dir, cfg["style"], cfg["char"], cfg["neg"], cfg["scenes"])


if __name__ == "__main__":
    main()
