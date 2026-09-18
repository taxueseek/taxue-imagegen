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
    bg = cv2.medianBlur(im.astype(np.uint8), 31).astype(np.float32)
    gbg = cv2.cvtColor(bg.astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float32)
    r = gray - gbg

    sub = r[y:H, x:Wd]
    ry0, ry1 = max(0, y - (H - y)), y
    ref = r[ry0:ry1, x:Wd]
    rms = float(np.sqrt((sub ** 2).mean()))
    rms_ref = float(np.sqrt((ref ** 2).mean())) if ref.size else 0.0
    p3 = 100.0 * float((np.abs(sub) > 3).mean())
    p8 = 100.0 * float((np.abs(sub) > 8).mean())
    print(f"{label:<28} RMS={rms:6.2f}  (对照带 {rms_ref:5.2f})  "
          f"|r|>3 {p3:5.1f}%  |r|>8 {p8:5.1f}%")
    return rms


if __name__ == "__main__":
    for p in sys.argv[1:]:
        metric(p, os.path.basename(os.path.dirname(p)) + "/" + os.path.basename(p))
