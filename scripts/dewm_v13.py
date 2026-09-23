#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dewm v13 — 最小方差（Wiener）融合。**实验候选，尚未并入 pick_wm 的选版池。**

【它想解决的问题】
v10 用「平底二值路由 + 线性斜坡」决定「多大程度相信 inpaint」：
    w_bg = clip((α − 0.02) / (0.12 − 0.02), 0, 1)      ← dewm_v10.FUSE_A0 / FUSE_A1
α≤0.02 全信解析反解，α≥0.12 已把 100% 交给 inpaint。
而反解 A=(I−αC)/(1−α) 的方差是 σ²/t²（t=1−α），背景先验 B 的方差是 σ_b²。
**最小方差（Wiener）融合**给出的最优权重是

    w_A = t² / (t² + (σ/σ_b)²)

同为 α=0.65（t=0.35）时 w_A≈0.66 —— 仍保留 66% 的解析反解。
即 **v10 对 inpaint 的信任远超统计最优**，这正是纹理底被抹平 / 平底出现糊斑的来源。

好处：连续、无阈值、不需要「平底/非平底」二值路由（少一个可能判错的开关）。

【物理可行域投影】
白色水印叠加式 I = α·C + (1−α)·orig ⇒ orig ≤ I（当 I ≤ 255 时恒成立），
去白水印**只能变暗**。故对背景先验取 B ← min(B, I)；由于 A ≤ I 本身成立，
blend ≤ I 自动满足，不必再夹最终结果（夹最终结果会在先验偏亮时挡住该减的地方）。

【实测证据（2026-09-13，两轮）—— 请连同反面证据一起读】

✅ 真实图库 87 张真水印图（判据：模板口径残留 κ̂ + 白蚀单向性违反）：
       κ̂>0.10（明显残留）              v13 **0.0%** ／ v12 18.4% ／ v8 9.2%
       白蚀违反像素（提亮 = 数学上不可能正确） v13 **0** ／ v12 3654 ／ v8 1800
       全图平均改动量                   v13 0.0285 ／ v8 0.0291
✅ 按「水印检测信心 conf」分组（本轮新增评测维度，是关键）：
       低 conf<0.25（26 张，模板与真实水印最不匹配）
           v13 残留 0.0% ／ v8 **30.8%**，且 v13 改动量更低（0.0175 vs 0.0223）
       中 0.25–0.55（34 张）：残留均 0%，v8 违亮 340px、v13 **0**
       高 conf≥0.55（27 张）：残留均 0%，v8 违亮 579px、v13 **0**
       → **v13 在全部三组都优于 v8，且在低 conf 组优势最大**
✅ 目检（用户亲口裁决过的两张标尺图，统一拉伸口径）：
       design43-10：v13 水印抹净、结构完好
       03_labor   ：v13 文字锐利（v7 把 g/s 糊成一团），"AI生成 WORKBUDDY"
                    痕迹比 v8 淡得多 —— 与 κ̂ 0.792 → −0.075 一致
✅ v13 唯一的代价是过度去除，实测**视觉不可见**：
       17 张判为过度去除的图，底色亮度中位 249（近纯白），
       实际压暗中位 1.1 灰阶、最大 3.1，压暗 >5 灰阶的图 **0 张**

❌ 反面证据（合成基准，有真值）：干净图人工叠加水印再与真值比 PSNR，
   **v8 全面优于 v13**（exact 47.7 vs 39.6；加 jpeg/笔形/边缘失配后 41.7 vs 38.8）。
   但该基准**对本方法失效**——它注入的永远是精确模板、conf 必然极高，
   **生成不出「低 conf」这个维度**，而那恰是 v13 唯一发挥作用的场景（占真水印图 30%）。
   → 这是**基准的盲区**，不是 v13 的缺陷（见 references/pitfalls.md 坑 32）。

【本轮（2026-09-13）试过并被实测否决的 6 类改进】
   ① 误差传播 σ_A = a·|I−C|/t²·se_k     → 合成 41.4，不如 const c≈0.35 的 42.4
   ② 逐像素动态 c = ρ·|I−C|/t²          → 低 conf 组残留 50%（灾难性）
   ③ 常数 c = 0.20 / 0.35 / 0.50        → 低 conf 组残留 11.5% / 7.7% / 3.8%，均不如现状 0%
   ④ 稳健 k 估计（IRLS 剔除离群）        → 改动量降 34%，但低 conf 组残留升至 12.5%
   ⑤ Navier-Stokes inpaint（替代 TELEA） → 残留 0% → 25%，全项更差
   ⑥ 用局部内容结构调节 c（保笔画）      → 笔画区梯度保留 0.355 → 0.558，但残留 0% → 6.9%
   **结论：v13 现状已是一个实测最优的工作点。**
   它的有效机制：大 c 把「水印核心区」交给 inpaint，在模板不匹配（低 conf）的图上
   补偿了反解的失配；而 t² 权重让「水印边缘（α 小）」仍走反解，保住了笔画结构。
   该机制属**歪打正着**（Laplacian σ 并非理论正确的量），但实测三组 conf 均成立。

【结论】v13 不并入 pick_wm 的 VERSIONS/MODEL_FAMILY，理由**不是它差**，而是：
并入后候选池从 4 版变 7 版（每张耗时约 3 倍），而它作为「低 conf 专用」的价值
尚未在选版算法里体现。要启用应先做 **conf 门控路由**（低 conf 图才交给 v13）。

【用法】
  python3 dewm_v13.py a.png            # → _clean/
  python3 dewm_v13.py a.png --check    # 只报诊断
  python3 dewm_v13.py a.png --sigma-b 5 --out-root /tmp/x
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

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import dewm_v9 as V9      # noqa: E402
import dewm_v10 as V10    # noqa: E402
import dewm_v12 as V12    # noqa: E402
from dewm_io import imread_any, imwrite_any, safe_target, add_common_args, save_crop  # noqa: E402

SIGMA_B = 5.0     # 背景先验不确定度（灰阶）。σ_b=5 时 03_labor/08_machine 残留最低；
                  # σ_b=3 过信先验（残留回升），12–20 过信反解（残留回升）
MARGIN = 24       # inpaint 裁剪外扩：只在「框 + MARGIN」里跑，代价从 O(全图) 降到 O(框)


def image_noise(img):
    """Laplacian-MAD 噪声估计。⚠️ 在有细密纹理的图上会把内容当噪声（见文件头反面证据）。"""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    lap = cv2.Laplacian(g, cv2.CV_32F, ksize=3)
    mad = np.median(np.abs(lap - np.median(lap)))
    return float(max(0.5, 1.4826 * mad / np.sqrt(6.0)))


def _bg_at(img, x0, y0, a):
    """只在「框 + MARGIN」的裁剪内 inpaint 再取子块。
    掩码只在框内，故与全图 inpaint 等价，但代价从 O(全图) 降到 O(框)。"""
    H, W = img.shape[:2]
    bh, bw = a.shape[:2]
    cx0, cy0 = max(0, x0 - MARGIN), max(0, y0 - MARGIN)
    cx1, cy1 = min(W, x0 + bw + MARGIN), min(H, y0 + bh + MARGIN)
    crop = img[cy0:cy1, cx0:cx1]
    core = (a > 0.05).astype(np.uint8) * 255
    core = cv2.dilate(core, np.ones((3, 3), np.uint8), iterations=1)
    m = np.zeros(crop.shape[:2], np.uint8)
    sx, sy = x0 - cx0, y0 - cy0
    eh = max(0, min(core.shape[0], m.shape[0] - sy))
    ew = max(0, min(core.shape[1], m.shape[1] - sx))
    if eh and ew:
        m[sy:sy + eh, sx:sx + ew] = core[:eh, :ew]
    bg = cv2.inpaint(crop, m, 3, cv2.INPAINT_TELEA)
    return bg[sy:sy + bh, sx:sx + bw].astype(np.float32)


def remove_watermark(img, C=255.0, sigma_b=SIGMA_B, align=True,
                     force_k=None, k_max=3.0, guard=True):
    H, W = img.shape[:2]
    a, (bx, by) = V9.load_template(W, H)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)

    conf, x, y, s = 0.0, bx, by, 1.0
    if align:
        fn = V12.detect_and_align if guard else V9.detect_and_align
        conf, x, y, s = fn(gray, a, bx, by)
        if conf >= V9.CONF_THRESHOLD:
            if s != 1.0:
                a = cv2.resize(a, (int(round(a.shape[1] * s)), int(round(a.shape[0] * s))),
                               interpolation=cv2.INTER_LINEAR)
        else:
            x, y, s = bx, by, 1.0

    a = a[:H - y, :W - x]
    bh, bw = a.shape[:2]
    sub = img[y:y + bh, x:x + bw].astype(np.float32)   # 必须与 a 同尺寸
    sub_bg = _bg_at(img, x, y, a)
    a3 = a[:, :, None]

    core_m = a > V9.CORE_THR
    y_obs = sub - sub_bg
    x_mod = a3 * (C - sub_bg)
    num = float((x_mod * y_obs)[core_m].sum())
    den = float((x_mod * x_mod)[core_m].sum()) + 1e-6
    k_raw = num / den
    r2 = 1.0 - float(((y_obs - k_raw * x_mod)[core_m] ** 2).sum()) / \
        (float((y_obs[core_m] ** 2).sum()) + 1e-6)
    # k ≤ 0 → α ≡ 0 → 输出逐位等于原图（干净图自动零改动，这是「无感」底线）
    k = float(force_k) if force_k is not None else float(np.clip(k_raw, 0.0, k_max))

    alpha = np.clip(k * a, 0.0, V9.ALPHA_GUARD)
    a3 = alpha[:, :, None]
    t = 1.0 - a3

    sig = image_noise(img)
    c = sig / max(1e-6, sigma_b)
    A_rec = np.clip((sub - a3 * C) / t, -64.0, 320.0)   # 无偏反解（病态区会飞）
    B = np.minimum(sub_bg, sub)                          # 物理约束只施加在先验上
    w = (t * t) / (t * t + c * c)                        # ← Wiener 增益
    blend = w * A_rec + (1.0 - w) * B
    out_sub = np.where(a3 > 0.0, blend, sub)             # 模板外逐位保持原样

    out = img.astype(np.float32).copy()
    out[y:y + bh, x:x + bw] = out_sub
    st = {"k": k, "k_raw": k_raw, "r2": r2, "sigma": sig, "c": c,
          "box": (x, y, x + bw, y + bh),
          "conf": float(conf), "offset": (x - bx, y - by), "scale": float(s),
          "a_max": float(alpha.max()), "alpha_max": float(alpha.max()),
          "unstable_px": 0, "core_px": int(core_m.sum()),
          "a_mean": float(alpha[a > 0.4].mean()) if (a > 0.4).any() else 0.0}
    return np.clip(out, 0, 255).astype(np.uint8), st


def main():
    ap = argparse.ArgumentParser(description="dewm v13 最小方差融合（实验候选）")
    ap.add_argument("paths", nargs="+")
    add_common_args(ap)
    ap.add_argument("--check", action="store_true", help="只报诊断，不写文件")
    ap.add_argument("--no-align", action="store_true")
    ap.add_argument("--no-guard", action="store_true", help="关闭空白守卫（用 v9 对齐）")
    ap.add_argument("--sigma-b", type=float, default=SIGMA_B)
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
                                   sigma_b=args.sigma_b, force_k=args.force_k,
                                   guard=not args.no_guard)
        name = os.path.basename(path)
        tag = (f"off={st['offset']} s={st['scale']:.2f} conf={st['conf']:.2f} "
               f"σ={st['sigma']:.2f} c={st['c']:.3f}")
        if args.check:
            print(f"check {name}  {tag}  k={st['k']:.3f} r2={st['r2']:.3f} "
                  f"αmax={st['alpha_max']:.2f}")
            continue
        target = safe_target(path, args.out, inplace=args.inplace)
        imwrite_any(target, out)
        print(f"ok    {name}  {tag}  k={st['k']:.3f} r2={st['r2']:.3f} → {target}")
        save_crop(out, path, args.crop, multi)


if __name__ == "__main__":
    _log.run("dewm_v13", main)