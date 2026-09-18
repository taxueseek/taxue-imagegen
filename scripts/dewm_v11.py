#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dewm v11 — v10 + 暗区迭代修正（修「黑色字体上的白色残留」）。

【用户目视反馈（2026-09-08）】
v10 处理完的 4 张候选里，1/2/3 号「黑色字体上出现白色残留」，4 号「文字字母中
有轻微问题」，而**非文字区看不出任何痕迹**。这个分布本身就是线索。

【根因：反解误差被 (255−orig) 放大，暗区权重是亮区的 15 倍】
    rec = (wm − α·255) / (1 − α)
    rec − orig = Δα · (255 − orig) / (1 − α)      ← Δα 是 α 的估计误差

同一张图 Δα 相同，但：
    黑字 orig≈20  → 放大 235/(1−α)
    白底 orig≈240 → 放大  15/(1−α)
实测 03_labor 深色区残留 +74.9 / 亮区 −4.2（17.8×），08_machine +74.0 / −6.0（12.4×）。
残留为正 = 偏白 = **欠减**。

**Δα 从哪来**：k 拟合要用 inpaint 估背景 bg，而 inpaint 在文字笔画上必然失效
（它不知道那里有字，会把字抹掉）→ 文字处 bg 偏高 → y_obs 偏小 → k 偏小 → 欠减。
这也是坑 21 教训 3 里「bg 代理误差在高频结构上 >14」的同一个病。

【修复：不依赖 inpaint 的迭代修正】
背景代理换成**反解结果自身的局部中值**（7×7 能跨过很细的水印笔画，不需要
知道底下有没有字）：
    for _ in range(iters):
        rec = (wm − α·255)/(1−α)
        med = medianBlur(rec, 7)                 # 无水印背景代理
        r   = rec − med                          # 残留
        Δα  = r·(1−α) / max(255−med, 20)         # 反解误差公式反推
        α  += Δα   (仅 α模板>0.1 的笔画区)
因为 Δα ∝ r，亮区残差小 → 修正量自动小，不会过减。

【关键修正：Δα 必须平滑，否则越修越糟（2026-09-08 目视后补做）】
第一版（无平滑）实测确实压下白残留，但**把中亮区（原图灰度 110~210）
压得更暗**：4 张候选的「中亮最差」从 v10 的 15.6 恶化到 22.2。
原因是中值滤波在纹理区自带 ±20 的误差，除以亮区的小分母 (255−med) 后
被放大 4 倍，噪声盖过了真正要修的水印残留。
形状失配是平滑的、中值误差是逐像素噪声 → 对 Δα 做高斯平滑即可分离：

    设置              暗区最差   中亮最差
    v10 基线            9.2      15.6
    2 轮 无平滑          0.4      22.2   ← 白残留换暗鬼影
    3 轮 平滑 σ≈2.6      0.5       1.1   ← 采用
    3 轮 平滑 σ≈5.0      0.4       1.0

内容保留同时变好：水印区 std 比 v10 的 0.965 → 0.987，
高频细节比 0.964 → 1.014，t2_manga 纹理 std 47.35 → 47.42（原图 48.29），
t1_poster（已目视确认干净）平底 RMS 保持 1.42 不变。

【用法】与 v10 相同，多两个开关
  python3 dewm_v11.py a.png                  # 自适应 → _clean/
  python3 dewm_v11.py a.png --check          # 只报诊断
  python3 dewm_v11.py a.png --iters 3        # 修正轮数（默认 3）
  python3 dewm_v11.py a.png --blur 0         # 关平滑（会出暗鬼影，仅 A/B 用）
  python3 dewm_v11.py a.png --no-dark        # 关闭暗区修正（= v10 行为，A/B 用）
"""

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

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import dewm_v10 as V10  # noqa: E402
from dewm_io import imread_any, imwrite_any, safe_target, add_common_args, save_crop  # noqa: E402

C = 255.0
DARK_ITERS = 3       # 修正轮数
DARK_KSIZE = 7       # 局部中值核（跨过水印笔画）
DARK_BLUR = 15       # Δα 平滑核：滤掉中值滤波的逐像素噪声（必有，见上）
DARK_A_THR = 0.1     # 只在 α 模板笔画区修正
DARK_DEN_FLOOR = 20.0   # (255−med) 的下限，防亮区除小数爆炸


def refine_alpha_dark(sub_wm, alpha, a, iters=DARK_ITERS, ksize=DARK_KSIZE,
                      blur=DARK_BLUR):
    """用反解结果的局部中值作背景代理，迭代修正 α。

    sub_wm: H'×W'×3 float32（含水印）
    alpha:  H'×W'   float32（当前 α = k·a）
    a:      H'×W'   float32（α 模板形状）
    blur:   Δα 高斯平滑核，0 表示不平滑（会引入暗鬼影，仅 A/B 用）
    """
    if iters <= 0:
        return alpha
    gw = cv2.cvtColor(np.clip(sub_wm, 0, 255).astype(np.uint8),
                      cv2.COLOR_BGR2GRAY).astype(np.float32)
    stroke = a > DARK_A_THR
    for _ in range(iters):
        rec = (gw - alpha * C) / (1.0 - alpha)
        med = cv2.medianBlur(np.clip(rec, 0, 255).astype(np.uint8),
                             ksize).astype(np.float32)
        r = rec - med
        d_alpha = r * (1.0 - alpha) / np.maximum(C - med, DARK_DEN_FLOOR)
        if blur:
            # 形状失配是平滑的，中值误差是逐像素噪声 —— 平滑把两者分开
            d_alpha = cv2.GaussianBlur(d_alpha, (blur, blur), 0)
        alpha = np.clip(alpha + np.where(stroke, d_alpha, 0.0), 0.0, V10.V9.ALPHA_GUARD)
    return alpha


def _remove_at(img, a, x0, y0, C_=C, fuse=False, force_k=None, iters=DARK_ITERS):
    """v10 的 _remove_at + 暗区迭代修正。"""
    H, W = img.shape[:2]
    bh, bw = a.shape[:2]
    x1, y1 = min(W, x0 + bw), min(H, y0 + bh)
    a = a[:y1 - y0, :x1 - x0]
    a3 = a[:, :, None]

    sub_wm = img[y0:y1, x0:x1].astype(np.float32)

    core = (a > 0.05).astype(np.uint8) * 255
    core = cv2.dilate(core, np.ones((3, 3), np.uint8), iterations=1)
    mask = np.zeros((H, W), dtype=np.uint8)
    mask[y0:y1, x0:x1] = core
    bg = cv2.inpaint(img, mask, 3, cv2.INPAINT_TELEA).astype(np.float32)
    sub_bg = bg[y0:y1, x0:x1]

    core_m = a > V10.V9.CORE_THR
    y_obs = sub_wm - sub_bg
    x_mod = a3 * (C_ - sub_bg)
    num = float((x_mod * y_obs)[core_m].sum())
    den = float((x_mod * x_mod)[core_m].sum()) + 1e-6
    k_raw = num / den
    ss_res = float(((y_obs - k_raw * x_mod)[core_m] ** 2).sum())
    ss_tot = float((y_obs[core_m] ** 2).sum()) + 1e-6
    r2 = 1.0 - ss_res / ss_tot
    k = float(force_k) if force_k is not None else float(np.clip(k_raw, *V10.V9.K_RANGE))

    alpha = np.clip(k * a, 0.0, V10.V9.ALPHA_GUARD)
    # ← v11 新增：不依赖 inpaint 的暗区迭代修正
    alpha = refine_alpha_dark(sub_wm, alpha, a, iters=iters)

    a3 = alpha[:, :, None]
    rec = (sub_wm - a3 * C_) / (1.0 - a3)
    out_of_bounds = (rec < -1.0) | (rec > 256.0)
    ill_cond = alpha > V10.V9.ALPHA_GUARD
    unstable = out_of_bounds.any(axis=2) | ill_cond
    base = np.where(unstable[:, :, None], sub_bg, rec)

    if fuse:
        w = np.clip((a - V10.FUSE_A0) / (V10.FUSE_A1 - V10.FUSE_A0), 0.0, 1.0)[:, :, None]
        out_sub = (1.0 - w) * base + w * sub_bg
    else:
        out_sub = base

    out = img.astype(np.float32).copy()
    out[y0:y1, x0:x1] = out_sub
    stats = {"k": k, "k_raw": k_raw, "r2": r2,
             "unstable_px": int(unstable.sum()), "core_px": int(core_m.sum()),
             "box": (x0, y0, x1, y1),
             "a_max": float(alpha.max()), "a_mean": float(alpha[a > 0.4].mean())
             if (a > 0.4).any() else 0.0}
    return np.clip(out, 0, 255).astype(np.uint8), stats


def remove_watermark(img, C_=C, align=True, fuse=True, flat_thr=V10.FLAT_STD_THR,
                     force_k=None, iters=DARK_ITERS):
    H, W = img.shape[:2]
    a, (bx, by) = V10.V9.load_template(W, H)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)

    conf, x, y, s = 0.0, bx, by, 1.0
    aligned = False
    if align:
        conf, x, y, s = V10.V9.detect_and_align(gray, a, bx, by)
        if conf >= V10.V9.CONF_THRESHOLD:
            aligned = (x, y, s) != (bx, by, 1.0)
            if s != 1.0:
                a = cv2.resize(a, (int(round(a.shape[1] * s)), int(round(a.shape[0] * s))),
                               interpolation=cv2.INTER_LINEAR)
        else:
            x, y, s = bx, by, 1.0

    bh, bw = a.shape[:2]
    flat_std = V10.flatness(gray, x, y, min(W, x + bw), min(H, y + bh))
    flat = flat_std < flat_thr

    out, st = _remove_at(img, a, x, y, C_=C_, fuse=(fuse and flat),
                         force_k=force_k, iters=iters)
    st.update({"align": aligned, "conf": float(conf), "offset": (x - bx, y - by),
               "scale": float(s), "flat": flat, "flat_std": flat_std})
    return out, st


def main():
    ap = argparse.ArgumentParser(description="dewm v11 暗区迭代修正")
    ap.add_argument("paths", nargs="+")
    add_common_args(ap)
    ap.add_argument("--check", action="store_true", help="只报诊断，不写文件")
    ap.add_argument("--no-align", action="store_true", help="关闭锚点对齐")
    ap.add_argument("--no-fuse", action="store_true", help="关闭平底融合")
    ap.add_argument("--no-dark", action="store_true", help="关闭暗区修正（= v10 行为）")
    ap.add_argument("--iters", type=int, default=DARK_ITERS, help="暗区修正轮数")
    ap.add_argument("--blur", type=int, default=DARK_BLUR, help="Δα 平滑核")
    ap.add_argument("--flat-thr", type=float, default=V10.FLAT_STD_THR)
    ap.add_argument("--force-k", type=float, default=None)
    ap.add_argument("--color", type=float, default=C)
    args = ap.parse_args()

    multi = len(args.paths) > 1
    for path in args.paths:
        img = imread_any(path)
        if img is None:
            print(f"skip  {path} (unreadable)")
            continue
        out, st = remove_watermark(img, C_=args.color, align=not args.no_align,
                                   fuse=not args.no_fuse, flat_thr=args.flat_thr,
                                   force_k=args.force_k,
                                   iters=0 if args.no_dark else args.iters)
        name = os.path.basename(path)
        tag = (f"align={'Y' if st['align'] else 'N'} off={st['offset']} "
               f"s={st['scale']:.2f} conf={st['conf']:.2f} "
               f"flat={'Y' if st['flat'] else 'N'}(std={st['flat_std']:.1f})")
        if args.check:
            print(f"check {name}  {tag}  k={st['k']:.3f} r2={st['r2']:.3f} "
                  f"αmax={st['a_max']:.2f} unstable={st['unstable_px']}px")
            continue
        target = safe_target(path, args.out, inplace=args.inplace)
        imwrite_any(target, out)
        print(f"ok    {name}  {tag}  k={st['k']:.3f} r2={st['r2']:.3f} "
              f"αmax={st['a_max']:.2f} unstable={st['unstable_px']}px → {target}")
        save_crop(out, path, args.crop, multi)


if __name__ == "__main__":
    main()
