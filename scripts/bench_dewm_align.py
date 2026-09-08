"""dewm 位置/尺度维基准：v6 vs v8 vs v9（对齐）三方 A/B。

方法（与 bench_dewm.py 同源，扩展两个维度）：
  1. 真实图翻转 180° 作精确 ground truth（干净左上角 → 右下角）
  2. 注入水印：wm = clip(k·a'·255 + (1-k·a')·orig)
     a' = α 模板按 scale 缩放后放在 (x0+dx, y0+dy)
     —— 模拟平台水印的位置漂移 / 尺寸变化 / 强度调整
  3. 比对区域 = 漂移水印框 ∪ 基准框（同时抓「残留」与「过减损伤」）
  4. 指标：PSNR、v9 找到的 offset/scale 与真值的偏差

用例矩阵：
  A  k=1.0, dx=0,  dy=0,  s=1.0    → 无失配回归测试（v9 不应劣于 v8）
  B  k=1.0, dx=8,  dy=-5, s=1.0    → 平移失配（v6/v8 应显著劣化）
  C  k=1.0, dx=14, dy=10, s=1.0    → 大平移
  D  k=1.0, dx=0,  dy=0,  s=1.06   → 尺度失配（1152 宽画幅的 snap 场景）
  E  k=0.8, dx=6,  dy=-4, s=1.0    → 强度+位置复合失配

用法：python3 bench_dewm_align.py
"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dewm as v6mod          # noqa: E402
import dewm_v8 as v8mod       # noqa: E402
import dewm_v9 as v9mod       # noqa: E402

# 测试底图由环境变量提供（os.pathsep 分隔），仓库不携带原图：
#   TAXUE_BENCH_IMGS="a.png:b.png" python3 bench_dewm_align.py
IMGS = [p for p in os.environ.get("TAXUE_BENCH_IMGS", "").split(os.pathsep) if p]

CASES = [
    # (name, k_true, dx, dy, scale)  水印贴右下角，漂移只能向左上（dx/dy ≤ 0）
    ("A 无失配",   1.0,  0,  0, 1.0),
    ("B 平移小",   1.0, -6, -5, 1.0),
    ("C 平移大",   1.0, -14, -9, 1.0),
    ("D 尺度失配", 1.0,  0,  0, 1.06),
    ("E 复合",     0.8, -6, -4, 1.0),
    ("F 干净图",   None, 0,  0, 1.0),
]


def inject_shift(orig, a, x0, y0, k_true, scale, C=255.0):
    """把缩放后的 α 模板放到 (x0+dx, y0+dy) 处混合。返回 (水印图, 实际框)。"""
    H, W = orig.shape[:2]
    if scale != 1.0:
        bw = int(round(a.shape[1] * scale))
        bh = int(round(a.shape[0] * scale))
        a2 = cv2.resize(a, (bw, bh), interpolation=cv2.INTER_LINEAR)
    else:
        a2 = a
    px, py = x0 + (a.shape[1] - a2.shape[1]), y0 + (a.shape[0] - a2.shape[0])
    # 锚定右下角语义：缩放后右下角对齐，再加平移
    px = max(0, min(W - a2.shape[1], px + 0))
    py = max(0, min(H - a2.shape[0], py + 0))
    px = max(0, min(W - a2.shape[1], px))
    py = max(0, min(H - a2.shape[0], py))
    alpha = np.clip(k_true * a2[:, :, None], 0.0, 0.99)
    sub = orig[py:py + a2.shape[0], px:px + a2.shape[1]].astype(np.float32)
    wm_sub = alpha * C + (1.0 - alpha) * sub
    out = orig.astype(np.float32).copy()
    out[py:py + a2.shape[0], px:px + a2.shape[1]] = wm_sub
    box = (px, py, px + a2.shape[1], py + a2.shape[0])
    return np.clip(out, 0, 255).astype(np.uint8), box


def metrics_psnr(rec, gt, box, base_box):
    """漂移框 ∪ 基准框 区域 PSNR。"""
    H, W = rec.shape[:2]
    x0 = min(box[0], base_box[0]); y0 = min(box[1], base_box[1])
    x1 = max(box[2], base_box[2]); y1 = max(box[3], base_box[3])
    x1 = min(x1, W); y1 = min(y1, H)
    r = rec[y0:y1, x0:x1].astype(np.float32)
    g = gt[y0:y1, x0:x1].astype(np.float32)
    mse = float(((r - g) ** 2).mean())
    return 10 * np.log10(255.0 ** 2 / (mse + 1e-9))


def main():
    if not IMGS:
        sys.exit("未指定测试底图：请设 TAXUE_BENCH_IMGS（os.pathsep 分隔的图片路径）后重跑。")
    a, (x0, y0) = v8mod.load_template(1024, 1536)
    print(f"α 模板 {a.shape}，基准锚点 ({x0},{y0})；对齐窗口 ±{v9mod.SEARCH_RADIUS}px，"
          f"尺度 {v9mod.SCALES}\n")

    agg = {"v6": [], "v8": [], "v9": []}
    print(f"{'用例':<10} {'底子':<11} | {'v6':>7} {'v8':>7} {'v9':>7} | "
          f"{'v9 offset':>12} {'scale':>5} {'conf':>5}")
    print("-" * 86)

    for p in IMGS:
        img = cv2.imread(p, cv2.IMREAD_COLOR)
        if img is None:
            print(f"[skip] {p}")
            continue
        gt = cv2.flip(img, -1).copy()
        name = os.path.basename(p).replace(".png", "")

        for cname, k, dx, dy, sc in CASES:
            if k is None:
                # F 干净图：不注入水印，v9 应拒绝动手（skipped），v6/v8 会过减损伤
                wm = gt.copy()
                box = (x0, y0, x0 + a.shape[1], y0 + a.shape[0])
            else:
                if sc != 1.0:
                    bw = int(round(a.shape[1] * sc))
                    bh = int(round(a.shape[0] * sc))
                    a2 = cv2.resize(a, (bw, bh), interpolation=cv2.INTER_LINEAR)
                else:
                    a2 = a
                px = max(0, min(1024 - a2.shape[1], x0 + dx))
                py = max(0, min(1536 - a2.shape[0], y0 + dy))
                alpha = np.clip(k * a2[:, :, None], 0.0, 0.99)
                sub = gt[py:py + a2.shape[0], px:px + a2.shape[1]].astype(np.float32)
                wm_sub = alpha * 255.0 + (1.0 - alpha) * sub
                wm = gt.astype(np.float32).copy()
                wm[py:py + a2.shape[0], px:px + a2.shape[1]] = wm_sub
                wm = np.clip(wm, 0, 255).astype(np.uint8)
                box = (px, py, px + a2.shape[1], py + a2.shape[0])
            base_box = (x0, y0, x0 + a.shape[1], y0 + a.shape[0])

            o6, _ = v6mod.remove_watermark(wm)
            o8, _ = v8mod.remove_watermark(wm)
            o9, st9 = v9mod.remove_watermark(wm)
            if st9.get("skipped"):
                o9 = wm  # v9 拒绝动手 → 输出 = 输入 = GT，无损

            ps = {v: metrics_psnr(o, gt, box, base_box)
                  for v, o in (("v6", o6), ("v8", o8), ("v9", o9))}
            for v in agg:
                agg[v].append(ps[v])
            ox, oy = st9["offset"]
            print(f"{cname:<10} {name:<11} | {ps['v6']:>7.2f} {ps['v8']:>7.2f} "
                  f"{ps['v9']:>7.2f} | {ox:>5},{oy:>6} {st9['scale']:>10.2f} "
                  f"{st9['conf']:>9.2f}")
        print()

    print("-" * 86)
    print(f"{'平均 PSNR':<22} |" + "".join(f" {np.mean(agg[v]):>7.2f}" for v in ("v6", "v8", "v9")))
    print(f"{'最差 PSNR':<22} |" + "".join(f" {np.min(agg[v]):>7.2f}" for v in ("v6", "v8", "v9")))
    print("\n判读：A 行 v9 应≈v8（对齐不伤好 case）；B-E 行 v9 应显著高于 v6/v8。")


if __name__ == "__main__":
    main()
