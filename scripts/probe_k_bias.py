#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证 k̂ 系统性低估的根因：bg 代理是否被弱水印像素污染。

假设：core mask 用 a>0.05，则 0.02<a<0.05 的弱水印像素未被掩蔽，
      inpaint 从这些「被提亮」的像素取材 → bg 偏亮 → y=wm-bg 偏小 → k̂ 偏小。

对照实验：把 mask 阈值放宽到 a>0.01（把所有受水印影响像素都排除在 inpaint 源之外）。
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
import dewm_v8 as v8mod  # noqa: E402

# 测试底图由环境变量提供（os.pathsep 分隔），仓库不携带原图：
#   TAXUE_BENCH_IMGS="a.png:b.png" python3 probe_k_bias.py
IMGS = [p for p in os.environ.get("TAXUE_BENCH_IMGS", "").split(os.pathsep) if p]


def fit_k(wm, a, x0, y0, mask_thr, C=255.0):
    """给定 mask 阈值，重做 k 拟合。"""
    H, W = wm.shape[:2]
    a3 = a[:, :, None]
    core_dil = (a > mask_thr).astype(np.uint8) * 255
    core_dil = cv2.dilate(core_dil, np.ones((3, 3), np.uint8), iterations=1)
    mask = np.zeros((H, W), np.uint8)
    mask[y0:y0 + core_dil.shape[0], x0:x0 + core_dil.shape[1]] = core_dil
    bg = cv2.inpaint(wm, mask, 3, cv2.INPAINT_TELEA).astype(np.float32)
    sub_bg = bg[y0:, x0:]
    sub_wm = wm[y0:, x0:].astype(np.float32)

    core_m = a > v8mod.CORE_THR
    y = sub_wm - sub_bg
    x = a3 * (C - sub_bg)
    k = float((x * y)[core_m].sum() / ((x * x)[core_m].sum() + 1e-6))
    return k


def main():
    if not IMGS:
        sys.exit("未指定测试底图：请设 TAXUE_BENCH_IMGS（os.pathsep 分隔的图片路径）后重跑。")
    a, (x0, y0) = v8mod.load_template(1024, 1536)
    print(f"{'底子':<14} {'k_true':>6} | {'k̂ (mask>0.05)':>14} {'k̂ (mask>0.01)':>14} {'k̂/mask0.01':>11}")
    print("-" * 60)
    for p in IMGS:
        img = cv2.imread(p, cv2.IMREAD_COLOR)
        gt = cv2.flip(img, -1).copy()
        name = p.split("/")[-1].replace(".png", "")
        for k_true in (0.8, 1.0, 1.3):
            alpha = np.clip(k_true * a[:, :, None], 0, 0.99)
            wm = gt.astype(np.float32).copy()
            wm[y0:, x0:] = alpha * 255.0 + (1 - alpha) * gt[y0:, x0:].astype(np.float32)
            wm = np.clip(wm, 0, 255).astype(np.uint8)
            k05 = fit_k(wm, a, x0, y0, 0.05)
            k01 = fit_k(wm, a, x0, y0, 0.01)
            print(f"{name:<14} {k_true:>6.2f} | {k05:>14.3f} {k01:>14.3f} {k01/k_true:>11.2f}")


if __name__ == "__main__":
    main()
