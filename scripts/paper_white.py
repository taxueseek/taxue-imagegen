#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""paper_white — 纸白归正与背景去斑（配套 skill: taxue-imagegen）。

问题：hunyuan-image 在「纯白纸底 + 平版印刷」类海报上**稳定**产出暖偏色纸白，
实测两版同一提示词的纸白均值为 R≈237.6 / G≈235.5 / B≈232.0（R-B≈5.5），
只靠提示词压不下来（v2 已把「R、G、B 三通道数值几乎相等」写进硬底线，R-B 反而 5.1→5.5），
postcheck 因此稳定判 `R-B≥3 泛黄前兆` + `white%` 极低（白底像素几乎为 0）。

做法（只动纸白，不动画面）：
1. 纸白掩膜 = 低饱和（max-min 小）且高亮度（min 通道大）的像素；
2. 归一化卷积求纸白局部均值（只由纸白像素贡献，墨线不参与 → 不产生光晕）；
3. 在纸白权重高的地方把像素拉向该局部均值（去网点/去纸纹，std 6 → ~1）；
4. 按通道做白点归正，把纸白拉到目标中性白（默认 250）。

墨、字、彩色强调区（权重≈0）逐位不变；输出永不覆盖原图（落 _clean/）。
"""
import _log
import argparse
import os
import sys

try:
    import numpy as np
    from PIL import Image
except ImportError as _e:          # 缺依赖时说人话，别甩 traceback（见 scripts/_env.py）
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import _env
    _env.die(_e, ['numpy', 'PIL'])

TARGET = 250.0        # 纸白目标亮度（留 5 级余量，避免削顶）
BLUR_RADIUS = 16      # 纸白局部均值半径
FLATTEN = 0.90        # 去斑强度（1.0 = 完全拍平）


def _box_mean(a, r):
    """盒式均值：输出 (i,j) = 原图 [i-r, i+r] × [j-r, j+r] 的均值（边缘按 edge 扩展）。

    用积分图实现，任意半径 O(N)。

    2026-09-23 修（对抗性审查实测）：padding 原为 `((r+1, r), (r+1, r))`，
    即上下/左右不对称。积分图那段索引取的是 **pad 行 [i, i+2r]**，
    在不对称 padding 下它对应的原图行是 `[i-r-1, i+r-1]` —— 窗口整体**向左上偏一格**。
    脉冲响应实测：半径 r=1 时脉冲落在输出 [5,7] 而不是 [4,6]；按 BLUR_RADIUS=16 放大，
    局部均值的取样位置系统性偏移 16px，边界与渐变处的「局部背景」因此取错。
    改 padding 为对称 `(r, r)` 即可：此时 pad 第 p 行对应原图第 p-r 行，
    同一个索引表达式正好落在 [i-r, i+r]，是 docstring 一直声称的居中邻域。
    """
    h, w = a.shape
    pad = np.pad(a, ((r, r), (r, r)), mode="edge")
    ii = pad.cumsum(0).cumsum(1)
    ii = np.pad(ii, ((1, 0), (1, 0)), mode="constant")
    win = (2 * r + 1) ** 2
    return (ii[2 * r + 1:2 * r + 1 + h, 2 * r + 1:2 * r + 1 + w]
            - ii[:h, 2 * r + 1:2 * r + 1 + w]
            - ii[2 * r + 1:2 * r + 1 + h, :w]
            + ii[:h, :w]) / win


def smoothstep(lo, hi, x):
    t = np.clip((x - lo) / (hi - lo), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def process(path, out_dir=None, target=TARGET, flatten=FLATTEN, radius=BLUR_RADIUS,
            dry=False):
    im = np.asarray(Image.open(path).convert("RGB")).astype(np.float64)
    mx = im.max(axis=2)
    mn = im.min(axis=2)
    # 纸白度：够亮 + 够不饱和
    paperness = smoothstep(200.0, 232.0, mn) * (1.0 - smoothstep(12.0, 28.0, mx - mn))
    w_flat = smoothstep(0.55, 0.90, paperness)
    w_gain = smoothstep(0.20, 0.70, paperness)

    # 归一化卷积：只用纸白像素算局部均值
    den = _box_mean(paperness, radius)
    den = np.maximum(den, 1e-6)
    local = np.stack([_box_mean(im[..., c] * paperness, radius) / den for c in range(3)],
                     axis=-1)

    out = im + (local - im) * (flatten * w_flat)[..., None]

    mask = paperness > 0.75
    if mask.sum() < 1000:
        raise SystemExit("纸白像素太少（<1000），不是白底海报，拒绝处理")
    means = np.array([out[..., c][mask].mean() for c in range(3)])
    gains = target / means
    gains = np.clip(gains, 0.90, 1.15)
    out = out * (1.0 + (gains - 1.0) * w_gain[..., None])
    out = np.clip(np.rint(out), 0, 255).astype(np.uint8)

    before = np.array([im[..., c][mask].mean() for c in range(3)])
    after = np.array([out[..., c][mask].mean() for c in range(3)])
    b_std = np.array([im[..., c][mask].std() for c in range(3)]).mean()
    a_std = np.array([out[..., c][mask].std() for c in range(3)]).mean()
    report = (f"纸白均值 R-B {before[0]-before[2]:+.2f} → {after[0]-after[2]:+.2f}；"
              f"亮度 {before.mean():.1f} → {after.mean():.1f}；"
              f"纸白 std {b_std:.2f} → {a_std:.2f}；通道增益 "
              + "/".join(f"{g:.4f}" for g in gains))

    if dry:
        return report, None

    out_dir = out_dir or os.path.join(os.path.dirname(os.path.abspath(path)), "_clean")
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(path))[0]
    dst = os.path.join(out_dir, base + "_paperwhite.png")
    if not dst.endswith(".png"):
        dst += ".png"
    Image.fromarray(out).save(dst)
    return report, dst


def main():
    ap = argparse.ArgumentParser(description="纸白归正 + 背景去斑（taxue-imagegen）")
    ap.add_argument("image")
    ap.add_argument("--out-dir", default=None, help="默认落同目录 _clean/")
    ap.add_argument("--target", type=float, default=TARGET)
    ap.add_argument("--flatten", type=float, default=FLATTEN)
    ap.add_argument("--radius", type=int, default=BLUR_RADIUS)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    try:
        report, dst = process(a.image, a.out_dir, a.target, a.flatten, a.radius, a.dry_run)
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(2)
    print(report)
    if dst:
        print("输出:", dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(_log.run("paper_white", main))
