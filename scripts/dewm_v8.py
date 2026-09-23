#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dewm v8 — 自适应反解 + 置信度门控 + 梯度掩码收尾。

【为什么需要 v8】
  v6  静态 α 模板反解，无门控。白底稳定（0.2s、零残留），
      但深/金底子上 1-α 被压到 0.29，误差放大 3.4 倍 → 红蓝噪点（坑 18）。
  v7  整区 inpaint 兜底。噪点没了，但真实纹理被抹平，且要人工判断何时用哪个。
  v8  把两条分支合成一条自适应流水线，核心是「先验证、再决定」：
      ① 最小二乘拟合当前图的实际不透明度 k（平台可能逐图调不透明度）
      ② 反解 + 数值守卫（α 上限、结果范围）
      ③ 逐像素不稳定检测 → 只在不稳定处退回 inpaint，稳定处保留真实纹理
      ④ 梯度掩码收尾（只柔化字形边缘的高频残差，干净区不动）

【模型】
  合成：wm = α·C + (1-α)·orig,  α = k · a   (a = 标定 α 模板, k = 当前图缩放)
  反解：orig = (wm - α·C) / (1-α)
  k 拟合（最小二乘，只在字形核心像素上）：
      wm - bg = k · a · (C - bg)      bg = inpaint 代理的 orig
      y = wm - bg ;  x = a·(C-bg)  →  k = Σ(x·y) / Σ(x²)
  拟合优度 R² 可用于拒绝「模板与当前图不匹配」的情形。

【用法】
  python3 dewm_v8.py a.png                     # 输出到 a.png 所在目录的 _clean/a.png
  python3 dewm_v8.py *.png                     # 批量，全部进 _clean/（原图不动）
  python3 dewm_v8.py *.png --out ~/clean/      # 指定输出目录（不得是源目录本身）
  python3 dewm_v8.py a.png --inplace           # 原地覆盖（危险，需显式声明）
  python3 dewm_v8.py a.png --check             # 只报诊断（k / R² / 不稳定像素数）
  python3 dewm_v8.py a.png --edge              # 开启梯度掩码收尾（默认关；实测有损）
  python3 dewm_v8.py a.png --crop /tmp/z.png   # 4x 放大目检裁片

【永不覆盖原图】
输出路径统一由 dewm_io.safe_target() 解析：默认落 `<源目录>/_clean/<原名>`；
`--out` 若指向源文件或源目录则自动重定向到 _clean/ 并告警；
只有显式 `--inplace` 才允许覆盖。保留原图才能做去水印效果的 A/B 对比。
详见 dewm_io.py 头部说明。

依赖：opencv-python-headless、numpy（零模型，~0.4s/张）
"""

import _log
import argparse
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
from dewm_io import imread_any, imwrite_any, safe_target, add_common_args, save_crop  # noqa: E402

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "wm_alpha_1024.npz")
BASE_W, BASE_H = 1024, 1536

# 守卫参数
ALPHA_GUARD = 0.92      # α 上限：超过则 1-α 太小，反解病态 → 判不稳定
K_RANGE = (0.20, 3.00)  # k 的合理范围
CORE_THR = 0.15         # 拟合 k 时视为「字形核心」的 α 阈值
OVER_MARGIN = 8.0       # 反解结果低于背景代理多少算「过减」


def load_template(W, H):
    """加载 α 模板并按宽度缩放、锚定右下角。返回 (α 模板, (x0, y0))。"""
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError(f"缺少 α 模板: {TEMPLATE_PATH}")
    z = np.load(TEMPLATE_PATH)
    tm, tbox = z["alpha"], z["box"]
    s = W / BASE_W
    bw, bh = int(round((tbox[2] - tbox[0]) * s)), int(round((tbox[3] - tbox[1]) * s))
    a = cv2.resize(tm, (bw, bh), interpolation=cv2.INTER_LINEAR)
    return a.astype(np.float32), (W - bw, H - bh)


def _core_mask(a, H, W, x0, y0):
    """字形核心区掩膜（全图尺寸，供 inpaint 用）。"""
    core = (a > 0.05).astype(np.uint8) * 255
    core = cv2.dilate(core, np.ones((3, 3), np.uint8), iterations=1)
    mask = np.zeros((H, W), dtype=np.uint8)
    mask[y0:y0 + core.shape[0], x0:x0 + core.shape[1]] = core
    return mask


def remove_watermark(img, C=255.0, use_edge=False, alpha_guard=ALPHA_GUARD,
                     force_k=None):
    """自适应反解去水印。返回 (输出图, 诊断字典)。

    use_edge: 梯度掩码收尾。**默认关闭** —— 合成基准实测它会把反解出的真实
              纹理抹平（平均 56.90dB → 51.05dB，byzantine 49.69 → 31.19）。
              文献里那步是给「反解失败」兜底的，反解成功时纯属破坏。
    force_k:  跳过最小二乘拟合，直接用给定的 k（调试/消融用）。
    """
    H, W = img.shape[:2]
    a, (x0, y0) = load_template(W, H)
    a3 = a[:, :, None]

    sub_wm = img[y0:, x0:].astype(np.float32)

    # ① 局部背景代理：inpaint 掉水印区，估计「底下应该是什么」
    mask = _core_mask(a, H, W, x0, y0)
    bg = cv2.inpaint(img, mask, 3, cv2.INPAINT_TELEA).astype(np.float32)
    sub_bg = bg[y0:, x0:]

    # ② 最小二乘拟合当前图的实际不透明度 k
    core_m = a > CORE_THR
    y_obs = sub_wm - sub_bg                    # 观测到的增量
    x_mod = a3 * (C - sub_bg)                  # k=1 时模型预测的增量
    num = float((x_mod * y_obs)[core_m].sum())
    den = float((x_mod * x_mod)[core_m].sum()) + 1e-6
    k_raw = num / den
    # 拟合优度 R²（1 - SS_res/SS_tot）
    ss_res = float(((y_obs - k_raw * x_mod)[core_m] ** 2).sum())
    ss_tot = float((y_obs[core_m] ** 2).sum()) + 1e-6
    r2 = 1.0 - ss_res / ss_tot
    k = float(force_k) if force_k is not None else float(np.clip(k_raw, *K_RANGE))

    # ③ 反解 + 数值守卫
    alpha_raw = k * a3
    alpha = np.clip(alpha_raw, 0.0, alpha_guard)
    rec = (sub_wm - alpha * C) / (1.0 - alpha)

    # ④ 逐像素不稳定检测
    # 判据只用「物理边界」，不跟 bg 比大小：
    #   bg 是 inpaint 平滑代理，高频真实纹理（如金色马赛克）本身就与 bg 差很多，
    #   用 rec<bg-δ 判「过减」会把正确恢复出的纹理误杀（实测 byzantine 全军覆没）。
    #   orig 物理上必在 [0,255]，越界必定是模型不成立或误差放大 → 才退回 bg。
    out_of_bounds = (rec < -1.0) | (rec > 256.0)
    ill_cond = alpha_raw > alpha_guard         # 1-α 太小，除法病态
    unstable = out_of_bounds | ill_cond

    out_sub = np.where(unstable, sub_bg, rec)

    # ⑤ 梯度掩码收尾：只柔化字形边缘（抗锯齿处模型最不准）
    if use_edge:
        gx = cv2.Sobel(a, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(a, cv2.CV_32F, 0, 1, ksize=3)
        grad = np.abs(gx) + np.abs(gy)
        gm = (grad > 0.05).astype(np.uint8)
        gm = cv2.dilate(gm, np.ones((3, 3), np.uint8), iterations=1)
        edge = (gm > 0)[:, :, None] & ~unstable
        out_sub = np.where(edge, 0.5 * rec + 0.5 * sub_bg, out_sub)

    out = img.astype(np.float32).copy()
    out[y0:, x0:] = out_sub

    stats = {
        "k": k, "k_raw": k_raw, "r2": r2,
        "unstable_px": int(unstable.sum()),
        "core_px": int(core_m.sum()),
        "box": (x0, y0, W, H),
    }
    return np.clip(out, 0, 255).astype(np.uint8), stats


def main():
    ap = argparse.ArgumentParser(description="dewm v8 自适应反解去水印")
    ap.add_argument("paths", nargs="+")
    add_common_args(ap)
    ap.add_argument("--check", action="store_true", help="只报诊断，不写文件")
    ap.add_argument("--edge", action="store_true",
                    help="开启梯度掩码收尾（默认关；实测有损，仅反解失败时考虑）")
    ap.add_argument("--force-k", type=float, default=None,
                    help="跳过最小二乘拟合，直接用给定 k（调试用）")
    ap.add_argument("--color", type=float, default=255.0, help="水印色 C（默认 255）")
    args = ap.parse_args()

    multi = len(args.paths) > 1
    for path in args.paths:
        img = imread_any(path)
        if img is None:
            print(f"skip  {path} (unreadable)")
            continue
        out, st = remove_watermark(img, C=args.color, use_edge=args.edge,
                                   force_k=args.force_k)
        name = os.path.basename(path)
        if args.check:
            print(f"check {name}  k={st['k']:.3f} r2={st['r2']:.3f} "
                  f"unstable={st['unstable_px']}/{st['core_px'] * 3}px")
            continue
        target = safe_target(path, args.out, inplace=args.inplace)
        imwrite_any(target, out)
        print(f"ok    {name}  k={st['k']:.3f} r2={st['r2']:.3f} "
              f"unstable={st['unstable_px']}px → {target}")
        save_crop(out, path, args.crop, multi)


if __name__ == "__main__":
    _log.run("dewm_v8", main)