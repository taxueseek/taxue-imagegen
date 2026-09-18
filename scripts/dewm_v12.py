#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dewm v12 — v11 + 对齐空白守卫（修「水印被挪到空白处、原处没处理」）。

【用户目视反馈（2026-09-08）】
4 张候选里第 2 张「还是有点白色水印的痕迹」，且这一张是唯一的
conf=0.50 / off=(15,6) / s=0.92 触发了对齐的图。

【根因：对齐搜索被打分函数推向空白区】
v9 的 detect_and_align 里有一个方差项：

    ref = 候选框正上方的条带
    vs  = clip(1 - reg.std() / ref.std(), 0, 1)
    score = max(comb + W_VAR * vs, masked)

设计初衷是「水印压在平底上 → 水印区比周围平」。但这是把因果搞反了：
水印是**白色**叠加（wm = α·255 + (1−α)·orig），压在纯白底上
wm ≡ 255 ≡ orig，**既不可见也不可解**。真正留有可见水印的地方，
一定是有内容（有暗部）的地方。于是这一项实际在做的事是：
    「谁最像一张白纸，谁就是水印位置」

实测 3 张触发对齐的图，无一例外：
    文件名                          默认框std  对齐框std
    设计一张竖版…09-06T08-13-21       21.3       1.3
    竖版…朱红石青平涂…14-58-02         9.5       1.5
    竖版…中国美术片…15-28-55           7.6       4.8
对齐框 std 全部 < 5（近乎纯白），默认框 std 全部更高。
以 09-06T08-13-21 为例，对齐框上拟合 k=0.58 / R²=0.21（噪声级），
默认框 k=1.03 / R²=0.82 —— 水印明明在默认位置，却被挪走去处理了一块白纸。
后果不是「处理错了地方」，而是**原处压根没动**，水印原样留着。

【修复：两刀（消融见下，缺一不可）】
1. 砍掉 W_VAR 项：score = max(comb, masked)。
2. 相对守卫 ALIGN_STD_RATIO：候选框 std < 0.7 × 默认框 std 时跳过。

【为什么必须是「相对」而不是绝对阈值（重要，踩过）】
先试的绝对守卫 `std >= 6.0` 看着更干净，实测**直接把真漂移也拒掉**：
注入漂移基准上 平均 PSNR 50.36 → 44.85、偏移命中 16/20 → 10/20。
原因：漂移水印常落在画面本身较平的位置，注入后 std 仍可能 < 6，
「平」不等于「没水印」——白色水印压在中等亮度的平底上照样可见。
相对守卫比的是「候选框 vs 默认框」，两边量的是同一段内容，
真漂移时比值接近 1，漂到白纸时比值塌到 0.06~0.16，区分度极大。

【为什么不选「R² 更高的那个」】
R² 要先跑完 k 拟合才有，等于把定位变成「先试两遍再挑」，
而且 R² 在极暗/极亮区会退化（坑 22 已证明 amp/R² 会瞎)。
相对 std 是 O(1) 前置过滤，语义也更硬：白纸上不可能有白色水印。

【消融（4 底图 × 5 用例注入漂移 + 3 张真实图）】
    组合                注入漂移 平均/最差 PSNR  命中   真实图回落默认
    v9 原样               50.36 / 29.60        16/20     0/3
    只去 W_VAR            50.36 / 29.60        16/20     2/3
    去 W_VAR + 绝对std≥6   44.85 / 29.60        10/20     3/3   ← 甲组崩了
    去 W_VAR + 相对0.5     50.36 / 29.60        16/20     2/3
    去 W_VAR + 相对0.7     50.36 / 29.60        16/20     3/3   ← 采用

【用法】与 v11 相同
  python3 dewm_v12.py a.png             # 自适应 → _clean/
  python3 dewm_v12.py a.png --check     # 只报诊断
  python3 dewm_v12.py a.png --no-guard  # 关空白守卫（= v11 行为，A/B 用）
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
import dewm_v11 as V11  # noqa: E402
import dewm_v10 as V10  # noqa: E402
from dewm_io import imread_any, imwrite_any, safe_target, add_common_args, save_crop  # noqa: E402

V9 = V10.V9

ALIGN_STD_RATIO = 0.7   # 候选框 std / 默认框 std 的下限：低于此视为漂到白纸


def detect_and_align(gray, alpha, base_x, base_y,
                     search=V9.SEARCH_RADIUS, scales=V9.SCALES,
                     ratio=ALIGN_STD_RATIO):
    """v9 的两段式搜索，减去 W_VAR 空白奖励，加上相对空白守卫。

    与 v9 的差异只有两处（其余逐行一致，保证可 A/B）：
      - 方差项 W_VAR * vs 删除（它在显式奖励「越平越像水印」）
      - 候选框 std < ratio × 默认框 std 时 continue
    """
    ah0, aw0 = alpha.shape
    H, W = gray.shape[:2]
    best = None
    std_ref = float(gray[base_y:base_y + ah0, base_x:base_x + aw0].std())
    std_floor = ratio * std_ref
    for s in scales:
        bw, bh = max(8, int(round(aw0 * s))), max(8, int(round(ah0 * s)))
        px, py = max(0, base_x - search), max(0, base_y - search)
        qx, qy = min(W, base_x + bw + search), min(H, base_y + bh + search)
        if qx - px < bw or qy - py < bh:
            continue
        patch = gray[py:qy, px:qx]
        tpl = cv2.resize(alpha, (bw, bh), interpolation=cv2.INTER_LINEAR)

        ncc = cv2.matchTemplate(patch, tpl, cv2.TM_CCOEFF_NORMED)
        gncc = cv2.matchTemplate(V9._grad_mag(patch), V9._grad_mag(tpl),
                                 cv2.TM_CCOEFF_NORMED)
        comb = V9.W_SPATIAL * np.clip(ncc, 0, 1) + V9.W_GRAD * np.clip(gncc, 0, 1)

        dev = patch - cv2.medianBlur(patch.astype(np.uint8), 31).astype(np.float32)
        tpl_core = tpl > 0.3
        tpl_dev = tpl[tpl_core]

        flat = np.argsort(comb, axis=None)[-8:]
        for k in flat:
            cy, cx = divmod(int(k), comb.shape[1])
            cand_x, cand_y = px + cx, py + cy
            reg = gray[cand_y:cand_y + bh, cand_x:cand_x + bw]
            # ← v12 守卫：比默认框平太多 = 漂到白纸上了，跳过
            if float(reg.std()) < std_floor:
                continue
            reg_dev = dev[cy:cy + bh, cx:cx + bw]
            masked = V9._pearson(reg_dev[tpl_core], tpl_dev)
            score = max(float(comb[cy, cx]), masked)
            if best is None or score > best[0]:
                best = (score, cand_x, cand_y, s)
    if best is None:
        return 0.0, base_x, base_y, 1.0
    return best


def remove_watermark(img, C_=255.0, align=True, fuse=True,
                     flat_thr=V10.FLAT_STD_THR, force_k=None,
                     iters=V11.DARK_ITERS, guard=True):
    H, W = img.shape[:2]
    a, (bx, by) = V9.load_template(W, H)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)

    conf, x, y, s = 0.0, bx, by, 1.0
    aligned = False
    if align:
        if guard:
            conf, x, y, s = detect_and_align(gray, a, bx, by)
        else:
            conf, x, y, s = V9.detect_and_align(gray, a, bx, by)
        if conf >= V9.CONF_THRESHOLD:
            aligned = (x, y, s) != (bx, by, 1.0)
            if s != 1.0:
                a = cv2.resize(a, (int(round(a.shape[1] * s)), int(round(a.shape[0] * s))),
                               interpolation=cv2.INTER_LINEAR)
        else:
            x, y, s = bx, by, 1.0

    bh, bw = a.shape[:2]
    flat_std = V10.flatness(gray, x, y, min(W, x + bw), min(H, y + bh))
    flat = flat_std < flat_thr

    out, st = V11._remove_at(img, a, x, y, C_=C_, fuse=(fuse and flat),
                             force_k=force_k, iters=iters)
    st.update({"align": aligned, "conf": float(conf), "offset": (x - bx, y - by),
               "scale": float(s), "flat": flat, "flat_std": flat_std})
    return out, st


def main():
    ap = argparse.ArgumentParser(description="dewm v12 对齐空白守卫")
    ap.add_argument("paths", nargs="+")
    add_common_args(ap)
    ap.add_argument("--check", action="store_true", help="只报诊断，不写文件")
    ap.add_argument("--no-align", action="store_true", help="关闭锚点对齐")
    ap.add_argument("--no-fuse", action="store_true", help="关闭平底融合")
    ap.add_argument("--no-dark", action="store_true", help="关闭暗区修正")
    ap.add_argument("--no-guard", action="store_true", help="关闭空白守卫（= v11 行为）")
    ap.add_argument("--iters", type=int, default=V11.DARK_ITERS)
    ap.add_argument("--flat-thr", type=float, default=V10.FLAT_STD_THR)
    ap.add_argument("--force-k", type=float, default=None)
    ap.add_argument("--color", type=float, default=255.0)
    args = ap.parse_args()

    multi = len(args.paths) > 1
    for path in args.paths:
        img = imread_any(path)
        if img is None:
            print(f"skip  {path} (unreadable)")
            continue
        out, st = remove_watermark(img, C_=args.color, align=not args.no_align,
                                   fuse=not args.no_fuse, flat_thr=args.flat_thr,
                                   force_k=args.force_k, guard=not args.no_guard,
                                   iters=0 if args.no_dark else args.iters)
        name = os.path.basename(path)
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
        x0, y0, x1, y1 = st["box"]
        tag = (f"align={'Y' if st['align'] else 'N'} off={st['offset']} "
               f"s={st['scale']:.2f} conf={st['conf']:.2f} "
               f"boxstd={g[y0:y1, x0:x1].std():5.1f} "
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
