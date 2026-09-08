"""dewm v6 / v7 / v8 合成基准对比（含消融）。

方法：
  1. 取真实图翻转 180°（原干净左上角 → 右下角），作为精确 ground truth
  2. 注入已知强度水印：wm = clip(k_true·a·255 + (1-k_true·a)·orig)
     k_true 模拟平台逐图调整不透明度
  3. 跑各版本，在真实水印区（右下 224x106）比对 ground truth
  4. 指标：PSNR（越高越好）、最大绝对误差、误差标准差

版本：
  v6   静态 α 反解，无守卫
  v7   整区 inpaint
  v8g  k=1 强制 + 边界守卫          → 隔离「守卫」贡献
  v8   最小二乘拟合 k + 守卫（默认） → 完整 v8
  v8e  v8 + 梯度掩码收尾            → 隔离「收尾」贡献（实测有害）

用法：python3 bench_dewm.py
"""
import os
import sys

import cv2
import numpy as np

SCRIPTS = "/Users/taxuexunxian/.workbuddy/skills/taxue-imagegen/scripts"
sys.path.insert(0, SCRIPTS)

import dewm as v6mod          # noqa: E402
import dewm_v7 as v7mod       # noqa: E402
import dewm_v8 as v8mod       # noqa: E402

IMGS = [
    "/Users/taxuexunxian/WorkBuddy/2026-09-07-23-36-47/generated-images/v5_wave2/01_surreal.png",
    "/Users/taxuexunxian/WorkBuddy/2026-09-07-23-36-47/generated-images/v5_wave2/03_popart.png",
    "/Users/taxuexunxian/WorkBuddy/2026-09-07-23-36-47/generated-images/v5_wave2/05_woodcut.png",
    "/Users/taxuexunxian/WorkBuddy/2026-09-07-23-36-47/generated-images/v5_wave2/06_qinglv.png",
    "/Users/taxuexunxian/WorkBuddy/2026-09-07-23-36-47/generated-images/v5_wave2/08_nouveau.png",
    "/Users/taxuexunxian/WorkBuddy/2026-09-07-23-36-47/generated-images/v5_wave2/09_byzantine.png",
    "/Users/taxuexunxian/WorkBuddy/2026-09-07-23-36-47/generated-images/v5_art_test/07_prayer.png",
]

K_TRUES = [0.8, 1.0, 1.3]
VARIANTS = ["v6", "v7", "v8g", "v8", "v8e"]


def inject(orig, a, x0, y0, k_true, C=255.0):
    alpha = np.clip(k_true * a[:, :, None], 0.0, 0.99)
    wm = alpha * C + (1.0 - alpha) * orig[y0:, x0:].astype(np.float32)
    out = orig.astype(np.float32).copy()
    out[y0:, x0:] = wm
    return np.clip(out, 0, 255).astype(np.uint8)


def metrics(rec, gt, x0, y0):
    r = rec[y0:, x0:].astype(np.float32)
    g = gt[y0:, x0:].astype(np.float32)
    err = r - g
    mse = float((err ** 2).mean())
    psnr = 10 * np.log10(255.0 ** 2 / (mse + 1e-9))
    return psnr, float(np.abs(err).max()), float(err.std())


def run_all(wm):
    o6, _ = v6mod.remove_watermark(wm)
    o7, _ = v7mod.inpaint_watermark(wm)
    o8g, _ = v8mod.remove_watermark(wm, force_k=1.0)
    o8, st = v8mod.remove_watermark(wm)
    o8e, _ = v8mod.remove_watermark(wm, use_edge=True)
    return {"v6": o6, "v7": o7, "v8g": o8g, "v8": o8, "v8e": o8e}, st


def main():
    a, (x0, y0) = v8mod.load_template(1024, 1536)
    print(f"α 模板: shape={a.shape} max={a.max():.3f} 锚点右下角 ({x0},{y0})")
    print(f"测试: {len(IMGS)} 种底子 × {len(K_TRUES)} 种不透明度 = {len(IMGS)*len(K_TRUES)} 组\n")

    hdr = f"{'底子':<13} {'k_true':>6} |" + "".join(f" {v+' PSNR':>9}" for v in VARIANTS) \
          + f" | {'v8 k̂':>6} {'R²':>5}"
    print(hdr)
    print("-" * len(hdr))

    agg = {v: [] for v in VARIANTS}
    byz = {v: [] for v in VARIANTS}

    for p in IMGS:
        img = cv2.imread(p, cv2.IMREAD_COLOR)
        if img is None:
            continue
        gt = cv2.flip(img, -1).copy()
        name = os.path.basename(p).replace(".png", "")
        is_byz = "byzantine" in name

        for k_true in K_TRUES:
            wm = inject(gt, a, x0, y0, k_true)
            outs, st = run_all(wm)
            row = f"{name:<13} {k_true:>6.2f} |"
            for v in VARIANTS:
                ps = metrics(outs[v], gt, x0, y0)[0]
                agg[v].append(ps)
                if is_byz:
                    byz[v].append(ps)
                row += f" {ps:>9.2f}"
            row += f" | {st['k']:>6.2f} {st['r2']:>5.2f}"
            print(row)

    print("-" * len(hdr))
    print(f"{'平均 PSNR':<13} {'':>6} |" + "".join(f" {np.mean(agg[v]):>9.2f}" for v in VARIANTS))
    print(f"{'最差 PSNR':<13} {'':>6} |" + "".join(f" {np.min(agg[v]):>9.2f}" for v in VARIANTS))
    print(f"{'byzantine均':<13} {'':>6} |" + "".join(f" {np.mean(byz[v]):>9.2f}" for v in VARIANTS))
    print("\n注：PSNR 越高越好。>40dB 基本无痕，30-40 轻微可见，<30 明显瑕疵。")
    print("     v8g=k固定1.0+守卫（隔离守卫贡献）  v8=拟合k+守卫  v8e=v8+梯度收尾")


if __name__ == "__main__":
    main()
