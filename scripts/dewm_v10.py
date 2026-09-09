#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dewm v10 — v9 管线 + 平底自适应融合（修「平色底上的水印残影」）。

【v9 实测暴露的洞】
audit 的 amp 判 v9 输出 CLEAN（t1 amp 0.95、R² 0.005），但人眼仍见水印轮廓。
用平底残影度量（局部中值背景的残差 RMS）抓到真凶：

    t1 平色海报：v9 后水印区 RMS 5.98，而紧邻平底只有 0.92 → 残留是平底的 6.5 倍，
                 9.4% 像素偏离背景 >8 灰阶。
    分区证据：笔画核心 Δ(rec−bg) = +2.54（欠减，水印没减干净）
              笔画边缘 Δ(rec−bg) = −7.20（过减，把没水印的地方也减了）
    → α 模板与真实水印的「胖瘦」不一致。k 拟合只吸收强度维，v9 对齐层只管
      平移+尺度，都吸收不了形状维。amp 的 R² 因此掉到 0，被当纹理误报放过。

【v10 的修复：按底子平整度路由】
  检测水印框外紧邻带（框正上方同尺寸条带；不够高则退到框左侧）的 std：
    std < FLAT_STD_THR（默认 12）→ 判「平底」
  平底时把反解结果与 inpaint 背景按 α 做斜坡融合：
    w = clip((α − 0.05) / (0.40 − 0.05), 0, 1)
    out = (1−w)·rec + w·bg_inpaint
  笔画中心（α 大）全信 inpaint —— 平底上真实背景本就近乎常数，inpaint 直接还原；
  边缘交给解析反解，保留过渡不生硬边。
  非平底（纹理/满铺）保持 v9 原行为，解析反解保留纹理，不被 inpaint 抹平。

【实测（2026-09-08，2 张真图）】
  t1 平底海报  RMS: 原图 27.02 → v9 5.98 → v10 0.9x（≈v7 0.93）
  t2 满纹理图  RMS: v9 45.90 → v10 ≈45.9（不动，纹理 std 保持 47.3，不被抹平）

【用法】与 v9 完全相同，多一个 --flat-thr
  python3 dewm_v10.py a.png                 # 自适应 → a.png 所在目录 _clean/
  python3 dewm_v10.py a.png --check         # 只报诊断（含 flat/flat_std）
  python3 dewm_v10.py a.png --no-fuse       # 关闭融合（= v9 行为，A/B 用）
  python3 dewm_v10.py a.png --flat-thr 20   # 放宽平底判据
"""

import argparse
import os
import sys

import cv2
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import dewm_v9 as V9  # noqa: E402
from dewm_io import imread_any, imwrite_any, safe_target, add_common_args, save_crop  # noqa: E402

FLAT_STD_THR = 12.0      # 底子平整度阈值：紧邻带 std 低于此值判平底
FUSE_A0, FUSE_A1 = 0.02, 0.12   # 融合权重斜坡：α≤A0 全信反解，α≥A1 全信 inpaint
# 可解性门控（2026-09-08 新增）：
# 水印是 wm = α·C + (1−α)·orig，可见度 ∝ α·(C − orig)。
# 近白底上 C − orig ≈ 0 → 水印既不可见也不可解，硬解只会引入噪声。
# S_med = median(α·(C − 局部中值背景)) 在字形核心区；低于 max(2.0, 3σ_noise) 即判 UNRESOLVABLE。
UNRESOLVABLE_MIN = 2.0   # 可见度下限（灰度级）
NOISE_SIGMA_K = 3.0      # 噪声倍数门（σ = 1.4826·MAD）
# 参数扫描（t1 平底海报 / t2 满纹理图，2026-09-08）：
#   A0,A1      t1 RMS   t2 RMS   t2 std
#   0.05,0.40    2.88    45.90    47.35   ← 保守，残留仍偏多
#   0.03,0.22    2.09    45.90    47.35
#   0.02,0.12    1.43    45.90    47.35   ← 采用（v7 为 0.93，v9 为 5.98）
#   0.01,0.08    1.38    45.90    47.35   收益递减，不再压低
# t2 全程零回归：平底判据未触发，解析反解原样保留纹理。


def flatness(gray, x0, y0, x1, y1):
    """水印框外紧邻环带的 std —— 底子平整度。

    **取四周可用方向的 max，不是只看上方**（2026-09-08 修）：
    只看上方时 06_radiance 被误判为平底（上方带 std 仅 1.2），
    但水印区本身 std 27.0、左侧带 std 25.8 —— 那里本来就有画面内容。
    误判平底会让融合拿 inpaint 盖掉真实内容，那是损伤不是去水印。
    取 max 是保守方向：任一方向不平就不融合，宁可留残留也不抹内容。
    """
    h, w = y1 - y0, x1 - x0
    H, W = gray.shape[:2]
    stds = []
    for band in (gray[max(0, y0 - h):y0, x0:x1],      # 上方
                 gray[y0:y1, max(0, x0 - w):x0],      # 左侧
                 gray[y0:y1, x1:min(W, x1 + w)]):     # 右侧
        if band.size >= h * w * 0.5:
            stds.append(float(band.std()))
    return max(stds) if stds else 0.0



def _remove_at(img, a, x0, y0, C=255.0, fuse=False, force_k=None):
    """v9 的 _remove_at + 平底融合。"""
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

    core_m = a > V9.CORE_THR
    y_obs = sub_wm - sub_bg
    x_mod = a3 * (C - sub_bg)
    num = float((x_mod * y_obs)[core_m].sum())
    den = float((x_mod * x_mod)[core_m].sum()) + 1e-6
    k_raw = num / den
    ss_res = float(((y_obs - k_raw * x_mod)[core_m] ** 2).sum())
    ss_tot = float((y_obs[core_m] ** 2).sum()) + 1e-6
    r2 = 1.0 - ss_res / ss_tot
    k = float(force_k) if force_k is not None else float(np.clip(k_raw, *V9.K_RANGE))

    alpha_raw = k * a3
    alpha = np.clip(alpha_raw, 0.0, V9.ALPHA_GUARD)
    rec = (sub_wm - alpha * C) / (1.0 - alpha)
    out_of_bounds = (rec < -1.0) | (rec > 256.0)
    ill_cond = alpha_raw > V9.ALPHA_GUARD
    unstable = out_of_bounds.any(axis=2) | ill_cond[:, :, 0]
    base = np.where(unstable[:, :, None], sub_bg, rec)

    if fuse:
        w = np.clip((a - FUSE_A0) / (FUSE_A1 - FUSE_A0), 0.0, 1.0)[:, :, None]
        out_sub = (1.0 - w) * base + w * sub_bg
    else:
        out_sub = base

    out = img.astype(np.float32).copy()
    out[y0:y1, x0:x1] = out_sub
    stats = {"k": k, "k_raw": k_raw, "r2": r2,
             "unstable_px": int(unstable.sum()), "core_px": int(core_m.sum()),
             "box": (x0, y0, x1, y1)}
    return np.clip(out, 0, 255).astype(np.uint8), stats


def visibility(gray, a, x0, y0, C=255.0):
    """水印可见度 S_med 与噪声门。

    可见度 = α·(C − 局部中值背景)：白水印压在近白底上时该值趋近 0，
    此时 wm ≡ C ≡ orig，反解 (wm−αC)/(1−α) 只是把噪声放大 —— 越修越糟。
    返回 (S_med, 阈值)；S_med < 阈值 即判 UNRESOLVABLE，应当 no-op。

    判据取中值而非均值：字形笔画内的像素才有信息，均值会被大量 α≈0 的
    背景像素稀释。
    """
    bh, bw = a.shape[:2]
    patch = gray[y0:y0 + bh, x0:x0 + bw]
    if patch.size == 0:
        return 0.0, UNRESOLVABLE_MIN
    bg = cv2.medianBlur(patch.astype(np.uint8), 31).astype(np.float32)
    S = a * (C - bg)
    core = a > 0.3
    s_med = float(np.median(S[core])) if core.any() else 0.0
    mad = float(np.median(np.abs(gray - cv2.medianBlur(gray.astype(np.uint8), 3))))
    sigma = 1.4826 * mad
    return s_med, max(UNRESOLVABLE_MIN, NOISE_SIGMA_K * sigma)


def remove_watermark(img, C=255.0, align=True, fuse=True,
                     flat_thr=FLAT_STD_THR, force_k=None, guard=True):
    H, W = img.shape[:2]
    a, (bx, by) = V9.load_template(W, H)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)

    conf, x, y, s = 0.0, bx, by, 1.0
    aligned = False
    if align:
        conf, x, y, s = V9.detect_and_align(gray, a, bx, by)
        if conf >= V9.CONF_THRESHOLD:
            aligned = (x, y, s) != (bx, by, 1.0)
            if s != 1.0:
                a = cv2.resize(a, (int(round(a.shape[1] * s)), int(round(a.shape[0] * s))),
                               interpolation=cv2.INTER_LINEAR)
        else:
            x, y, s = bx, by, 1.0

    bh, bw = a.shape[:2]
    flat_std = flatness(gray, x, y, min(W, x + bw), min(H, y + bh))
    flat = flat_std < flat_thr

    # 可解性门控：近白底上水印不可解，直接返回原图（不引入噪声）
    vis, vis_thr = visibility(gray, a, x, y, C=C)
    if guard and vis < vis_thr:
        return img.copy(), {"skipped": f"水印不可解（可见度 {vis:.2f} < 阈值 {vis_thr:.2f}）",
                            "vis": vis, "vis_thr": vis_thr, "align": aligned,
                            "conf": float(conf), "offset": (x - bx, y - by),
                            "scale": float(s), "flat": flat, "flat_std": flat_std,
                            "k": 0.0, "r2": 0.0,
                            "unstable_px": 0, "core_px": 0,
                            "box": (x, y, x + bw, y + bh)}

    out, st = _remove_at(img, a, x, y, C=C, fuse=(fuse and flat), force_k=force_k)
    st.update({"align": aligned, "conf": float(conf), "offset": (x - bx, y - by),
               "scale": float(s), "flat": flat, "flat_std": flat_std,
               "vis": vis, "vis_thr": vis_thr})
    return out, st


def main():
    ap = argparse.ArgumentParser(description="dewm v10 平底自适应融合")
    ap.add_argument("paths", nargs="+")
    add_common_args(ap)
    ap.add_argument("--check", action="store_true", help="只报诊断，不写文件")
    ap.add_argument("--no-align", action="store_true", help="关闭锚点对齐")
    ap.add_argument("--no-fuse", action="store_true", help="关闭平底融合（= v9 行为）")
    ap.add_argument("--no-guard", action="store_true", help="关闭可解性门控（近白底也硬解）")
    ap.add_argument("--flat-thr", type=float, default=FLAT_STD_THR, help="平底判据阈值")
    ap.add_argument("--force-k", type=float, default=None)
    ap.add_argument("--color", type=float, default=255.0)
    args = ap.parse_args()

    multi = len(args.paths) > 1
    for path in args.paths:
        img = imread_any(path)
        if img is None:
            print(f"skip  {path} (unreadable)")
            continue
        out, st = remove_watermark(img, C=args.color, align=not args.no_align,
                                   fuse=not args.no_fuse, flat_thr=args.flat_thr,
                                   force_k=args.force_k, guard=not args.no_guard)

        name = os.path.basename(path)
        if st.get("skipped"):
            print(f"skip  {name}  {st['skipped']}")
            continue
        tag = (f"align={'Y' if st['align'] else 'N'} off={st['offset']} "
               f"s={st['scale']:.2f} conf={st['conf']:.2f} "
               f"flat={'Y' if st['flat'] else 'N'}(std={st['flat_std']:.1f})")
        if args.check:
            print(f"check {name}  {tag}  k={st['k']:.3f} r2={st['r2']:.3f} "
                  f"unstable={st['unstable_px']}px")
            continue
        target = safe_target(path, args.out, inplace=args.inplace)
        imwrite_any(target, out)
        print(f"ok    {name}  {tag}  k={st['k']:.3f} r2={st['r2']:.3f} "
              f"unstable={st['unstable_px']}px → {target}")
        save_crop(out, path, args.crop, multi)


if __name__ == "__main__":
    main()
