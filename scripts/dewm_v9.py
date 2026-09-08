#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dewm v9 — v8 自适应反解 + 锚点对齐（自适应定位）。

【为什么需要 v9】
v8 解决了「强度失配」（平台逐图调不透明度 → 最小二乘拟合 k + 守卫，坑 18），
但仍假设水印**位置固定**（模板锚定右下角）。GargantuaX/gemini-watermark-remover
（875 forks）的 adaptiveDetector 证明：真实平台的水印会因画幅、版本迭代、
渲染 snap 而平移/缩放——位置失配时反解会把干净区「过减」出暗影，
同时真水印残留，比强度失配破坏更大。

【v9 = v8 管线 + 三重评分对齐（coarse-to-fine template matching 移植）】
  ① 灰度 NCC（权重 0.5）——字形亮度结构与 α 模板相关
  ② Sobel 梯度 NCC（权重 0.3）——对白平衡/亮度漂移免疫，只看结构
  ③ 局部方差比（权重 0.2）——水印使局部方差下降，作为佐证
  在右下角预期位置 ±28px 窗口、尺度 {0.92,0.96,1.0,1.04,1.08} 内搜索，
  取综合分最高者作为 (x, y, scale)，再走 v8 的 k 拟合 + 守卫 + 定点回退。
  置信度 < 0.35 时回退基准位置并告警（可能无水印 / 反白款 → rmwm_light）。

【模型】与 v8 一致：wm = α·C + (1-α)·orig，α = k·a；a 先经几何对齐再拟合 k。

【用法】（输出纪律与 dewm_io 一致：默认落 _clean/，永不覆盖原图）
  python3 dewm_v9.py a.png                 # 对齐 + 反解 → a.png 所在目录 _clean/
  python3 dewm_v9.py a.png --check         # 只报诊断（offset/scale/confidence/k/R²）
  python3 dewm_v9.py a.png --no-align      # 关闭对齐（= v8 行为，A/B 用）
  python3 dewm_v9.py a.png --refine 1      # α 残差精修轮数（默认 0，待实测）

依赖：opencv-python-headless、numpy（零模型，~0.5s/张）
"""

import argparse
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dewm_io import imread_any, imwrite_any, safe_target, add_common_args, save_crop  # noqa: E402

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "wm_alpha_1024.npz")
BASE_W, BASE_H = 1024, 1536

# v8 守卫参数（保持一致，便于消融）——v9.1：k̂ 下限放开到 0，
# 强制 k̂≥0.2 会对干净图过减出暗影（F 用例实测损伤源）
ALPHA_GUARD = 0.92
K_RANGE = (0.0, 3.00)
CORE_THR = 0.15


# v9 对齐参数（参照 GargantuaX adaptiveDetector.py）
SEARCH_RADIUS = 28          # 平移搜索半径（px）
SCALES = (1.0, 0.98, 1.02, 0.96, 1.04, 1.06, 0.92, 1.08)
W_SPATIAL, W_GRAD, W_VAR = 0.5, 0.3, 0.2
CONF_THRESHOLD = 0.35


def load_template(W, H):
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError(f"缺少 α 模板: {TEMPLATE_PATH}")
    z = np.load(TEMPLATE_PATH)
    tm, tbox = z["alpha"], z["box"]
    s = W / BASE_W
    bw = int(round((tbox[2] - tbox[0]) * s))
    bh = int(round((tbox[3] - tbox[1]) * s))
    a = cv2.resize(tm, (bw, bh), interpolation=cv2.INTER_LINEAR)
    return a.astype(np.float32), (W - bw, H - bh)


def _grad_mag(x):
    gx = cv2.Sobel(x, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(x, cv2.CV_32F, 0, 1, ksize=3)
    return np.sqrt(gx * gx + gy * gy)


def _pearson(x, y):
    x = x - x.mean()
    y = y - y.mean()
    d = float(np.sqrt((x * x).sum() * (y * y).sum()))
    return float((x * y).sum() / d) if d > 1e-6 else 0.0


def detect_and_align(gray, alpha, base_x, base_y,
                     search=SEARCH_RADIUS, scales=SCALES):
    """三重评分搜索最佳 (x, y, scale)，粗到细两段式。

    段一（粗筛）：全框 空间 NCC + 梯度 NCC → 每尺度取 top-8 候选。
    段二（精验证）：字形掩膜 Pearson——dev = patch − medianBlur(patch)，
    只在 α>0.3 的笔画像素上比对 dev 与 α 的相关。平白角落（海报常态）
    全框 NCC 被平白区稀释，掩膜 Pearson 直接度量「笔画亮度 bump 与
    模板形状的一致性」，是平底场景的主证据。
    返回 (confidence, x, y, scale)。
    """
    ah0, aw0 = alpha.shape
    H, W = gray.shape[:2]
    best = None
    for s in scales:
        bw, bh = max(8, int(round(aw0 * s))), max(8, int(round(ah0 * s)))
        px, py = max(0, base_x - search), max(0, base_y - search)
        qx, qy = min(W, base_x + bw + search), min(H, base_y + bh + search)
        if qx - px < bw or qy - py < bh:
            continue
        patch = gray[py:qy, px:qx]
        tpl = cv2.resize(alpha, (bw, bh), interpolation=cv2.INTER_LINEAR)

        ncc = cv2.matchTemplate(patch, tpl, cv2.TM_CCOEFF_NORMED)
        gncc = cv2.matchTemplate(_grad_mag(patch), _grad_mag(tpl),
                                 cv2.TM_CCOEFF_NORMED)
        comb = W_SPATIAL * np.clip(ncc, 0, 1) + W_GRAD * np.clip(gncc, 0, 1)

        # 段二数据：局部背景估计（medianBlur 仅用于打分，不用于反解）
        dev = patch - cv2.medianBlur(patch.astype(np.uint8), 31).astype(np.float32)
        tpl_core = tpl > 0.3
        tpl_dev = tpl[tpl_core]

        flat = np.argsort(comb, axis=None)[-8:]
        for k in flat:
            cy, cx = divmod(int(k), comb.shape[1])
            cand_x, cand_y = px + cx, py + cy
            reg_dev = dev[cy:cy + bh, cx:cx + bw]
            masked = _pearson(reg_dev[tpl_core], tpl_dev)

            reg = gray[cand_y:cand_y + bh, cand_x:cand_x + bw]
            ref = gray[max(0, cand_y - bh):cand_y, cand_x:cand_x + bw]
            vs = 0.0
            if ref.size and reg.size and float(ref.std()) > 5.0:
                vs = float(np.clip(1.0 - reg.std() / max(float(ref.std()), 1e-6), 0, 1))
            score = max(float(comb[cy, cx]) + W_VAR * vs, masked)
            if best is None or score > best[0]:
                best = (score, cand_x, cand_y, s)
    if best is None:
        return 0.0, base_x, base_y, 1.0
    return best


def refine_alpha(wm_sub, a, iters=1, blend=0.5):
    """α 残差精修：模板 α 打底，字形核心区小步修正（默认关，待实测）。

    wm_sub: H'×W'×3 float32；a: H'×W' float32
    """
    a_cur = a.copy()
    core = a > 0.4
    for _ in range(max(0, iters)):
        rec0 = (wm_sub - 255.0 * a_cur[:, :, None]) / np.maximum(1 - a_cur[:, :, None], 0.29)
        denom = np.maximum(255.0 - rec0, 0.29)
        a_new = (wm_sub - rec0) / denom
        step = np.clip(a_new.mean(axis=2), 0.0, 0.9)
        a_cur = np.where(core, (1 - blend) * a_cur + blend * step, a_cur)
        a_cur = np.clip(a_cur, 0.0, 0.9)
    return a_cur


def _remove_at(img, a, x0, y0, C=255.0, alpha_guard=ALPHA_GUARD, force_k=None):
    """v8 管线（k 拟合 + 守卫 + 定点回退），在任意对齐框内执行。

    与 v8 的差异：
      1. 水印框按模板实际框操作（支持任意对齐位置，v8 锚定右下角）
      2. k̂ 下限 0（v8 强制 ≥0.2 会对干净图过减出暗影；干净角 k̂ 恒为负→0→零改动）
    注：曾试验 dewm2 式逐像素模型校验门（|wm−pred|>tol 保持原样），
    在马赛克等高频纹理上被背景代理误差误触发，byzantine A 掉到 27.55dB
    （v8 为 50.35），已删除——模板管线的干净图保护由 k̂ 下限 0 承担。
    """
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

    core_m = a > CORE_THR
    y_obs = sub_wm - sub_bg
    x_mod = a3 * (C - sub_bg)
    num = float((x_mod * y_obs)[core_m].sum())
    den = float((x_mod * x_mod)[core_m].sum()) + 1e-6
    k_raw = num / den
    ss_res = float(((y_obs - k_raw * x_mod)[core_m] ** 2).sum())
    ss_tot = float((y_obs[core_m] ** 2).sum()) + 1e-6
    r2 = 1.0 - ss_res / ss_tot
    k = float(force_k) if force_k is not None else float(np.clip(k_raw, *K_RANGE))

    alpha_raw = k * a3
    alpha = np.clip(alpha_raw, 0.0, alpha_guard)
    rec = (sub_wm - alpha * C) / (1.0 - alpha)
    alpha_raw = k * a3
    alpha = np.clip(alpha_raw, 0.0, alpha_guard)
    rec = (sub_wm - alpha * C) / (1.0 - alpha)
    out_of_bounds = (rec < -1.0) | (rec > 256.0)
    ill_cond = alpha_raw > alpha_guard
    unstable = out_of_bounds.any(axis=2) | (ill_cond[:, :, 0] if ill_cond.ndim == 3 else ill_cond)
    out_sub = np.where(unstable[:, :, None], sub_bg, rec)

    out = img.astype(np.float32).copy()
    out[y0:y1, x0:x1] = out_sub
    stats = {
        "k": k, "k_raw": k_raw, "r2": r2,
        "unstable_px": int(unstable.sum()), "core_px": int(core_m.sum()),
        "box": (x0, y0, x1, y1),
    }
    return np.clip(out, 0, 255).astype(np.uint8), stats


def remove_watermark(img, C=255.0, align=True, refine_iters=0, force_k=None):
    """v9.1 入口。返回 (输出图, 诊断 dict)。align=False 等价 v8 + 逐像素门。

    v9.1（2026-09-08）：删除 conf 拒动手门（真实 18 图 18/18 假阴性——
    NCC 信号被平白角与满纹理角同时稀释，见坑 21）。
    干净图保护改由两个机制承担：
      ① k̂ 下限 0 → 无水印时反解自然退化为 no-op；
      ② dewm2 式逐像素模型校验门 → 内容与模型不符的像素保持原样。
    对齐（align=True）在 conf≥0.35 时启用，仅作为位置精化，不再做门神。
    """
    H, W = img.shape[:2]
    a, (bx, by) = load_template(W, H)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)

    conf, x, y, s = 0.0, bx, by, 1.0
    aligned = False
    if align:
        conf, x, y, s = detect_and_align(gray, a, bx, by)
        if conf >= CONF_THRESHOLD:
            aligned = (x, y, s) != (bx, by, 1.0)
            if s != 1.0:
                bw = int(round(a.shape[1] * s))
                bh = int(round(a.shape[0] * s))
                a = cv2.resize(a, (bw, bh), interpolation=cv2.INTER_LINEAR)
        else:
            x, y, s = bx, by, 1.0

    out, st = _remove_at(img, a, x, y, C=C, force_k=force_k)

    if refine_iters > 0:
        bh, bw = a.shape[:2]
        if y + bh <= H and x + bw <= W:
            sub_wm = img[y:y + bh, x:x + bw].astype(np.float32)
            a_ref = refine_alpha(sub_wm, a, iters=refine_iters)
            out, st = _remove_at(img, a_ref, x, y, C=C, force_k=force_k)

    st.update({"align": aligned, "conf": float(conf),
               "offset": (x - bx, y - by), "scale": float(s)})
    return out, st


def main():
    ap = argparse.ArgumentParser(description="dewm v9 自适应反解 + 锚点对齐")
    ap.add_argument("paths", nargs="+")
    add_common_args(ap)
    ap.add_argument("--check", action="store_true", help="只报诊断，不写文件")
    ap.add_argument("--no-align", action="store_true", help="关闭锚点对齐（= v8 行为）")
    ap.add_argument("--refine", type=int, default=0, help="α 残差精修轮数（默认 0）")
    ap.add_argument("--force-k", type=float, default=None, help="跳过 k 拟合（调试）")
    ap.add_argument("--color", type=float, default=255.0, help="水印色 C（默认 255）")
    args = ap.parse_args()

    multi = len(args.paths) > 1
    for path in args.paths:
        img = imread_any(path)
        if img is None:
            print(f"skip  {path} (unreadable)")
            continue
        out, st = remove_watermark(img, C=args.color, align=not args.no_align,
                                   refine_iters=args.refine, force_k=args.force_k)
        name = os.path.basename(path)
        tag = (f"align={'Y' if st['align'] else 'N'} off={st['offset']} "
               f"s={st['scale']:.2f} conf={st['conf']:.2f}")
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
