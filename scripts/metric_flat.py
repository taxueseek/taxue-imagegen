#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""平底残影度量 —— 比 audit 的 amp 更适合抓「平色底上的水印残影」。

audit 的 amp 是先拟合 k 再算幅度，对「形状失配」不敏感（R² 会掉到 0，
于是被判 CLEAN）。但平底场景里人眼看到的痕迹恰恰是形状失配造成的
笔画轮廓噪声。所以直接量：

    局部背景 bg = medianBlur(图, 31)      # 平底假设
    r = 图 − bg
    RMS(r) 在水印区内  +  |r| 超阈像素占比

平底图上 bg≈常数，理想值 RMS→0。纹理图（t2）此指标会含真实纹理，
需结合对照带比值一起看，不能单独下结论。
"""
import _log
import os
import sys

try:
    import cv2
    import numpy as np
except ImportError as _e:          # 缺依赖时说人话，别甩 traceback（见 scripts/_env.py）
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import _env
    _env.die(_e, ['cv2', 'numpy'])

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dewm_io import imread_any  # noqa: E402


def wm_box(im):
    H, Wd = im.shape[:2]
    s = Wd / 1024.0
    return Wd - int(round(224 * s)), H - int(round(106 * s))


def metric(path, label=""):
    im = imread_any(path)
    H, Wd = im.shape[:2]
    x, y = wm_box(im)
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32)
    # 只在水印框与其对照带所在的行段上算中值背景（2026-09-23）。
    # 下面只用到 `r[ry0:]`，而 `medianBlur(31)` 的垂直支撑是 ±15 行 ——
    # 从 ry0−16 起算，`r[ry0:]` 与「全图算一遍」**逐位相同**，却省掉上方大片
    # （典型 1024×1536 图上约 2/3 的行）。这是本脚本最贵的一步，实测占其总耗时 22%。
    # 之所以敢省：中值滤波的支撑有界且明确（ksize//2），不像 inpaint 那样靠不确定的
    # 传播范围——那种情形下裁窗必须靠实测逐张比对才敢说等价。
    ry0 = max(0, y - (H - y))
    top = max(0, ry0 - 16)
    bg = cv2.medianBlur(im[top:].astype(np.uint8), 31).astype(np.float32)
    gbg = cv2.cvtColor(bg.astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float32)
    r = gray[top:] - gbg          # r 的第 0 行 = 原图第 top 行，下面按此换算

    sub = r[y - top:H - top, x:Wd]
    ref = r[ry0 - top:y - top, x:Wd]
    rms = float(np.sqrt((sub ** 2).mean()))
    rms_ref = float(np.sqrt((ref ** 2).mean())) if ref.size else 0.0
    p3 = 100.0 * float((np.abs(sub) > 3).mean())
    p8 = 100.0 * float((np.abs(sub) > 8).mean())
    print(f"{label:<28} RMS={rms:6.2f}  (对照带 {rms_ref:5.2f})  "
          f"|r|>3 {p3:5.1f}%  |r|>8 {p8:5.1f}%")
    return rms


def _cli():
    # 没有 argparse 的入口脚本必须**自己认掉 -h/--help**：否则它被默默忽略并直接干活。
    # 2026-09-23（对抗性审查）：build_storyboard_ink.py --help 真写出 9 个 prompt 文件、
    # test_jimeng.py --help 跑整套 43 项测试。问「怎么用」的动作把活干了，比报错更糟。
    if any(a in ("-h", "--help") for a in sys.argv[1:]):
        print(__doc__.strip())
        return 0
    for p in sys.argv[1:]:
        metric(p, os.path.basename(os.path.dirname(p)) + "/" + os.path.basename(p))


if __name__ == "__main__":
    _log.run("metric_flat", _cli)
