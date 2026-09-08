#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pick_wm — 对每张图跑 v6 / v7 / v8 / v9 四种去水印，按残留签名分选最佳。

【为什么需要】
v6 反解：白底完美，深/红底放大噪点
v7 inpaint：兜底，纹理被抹平
v8 自适应拟合：低对比水印更干净，但在已平滑区会过拟合出鬼影
v9 v8 + 锚点对齐：位置/尺度漂移场景修复（bench 平均 +12.4dB）；干净图拒动手

四版各有所长，靠肉眼挑图不靠谱；靠单一版本又会在某些图翻车。
正确做法：每张跑四版，按「残留签名分」自动选最低的。

【判分】
对每版输出 I_k 拟合残差不透明度 k̂_k 与平均灰度幅度 amp_k = |k̂_k|·mean(...)。
**amp 越低越好**；amp 接近 0 视为干净，≥ 2.5 视为残留明显。
再叠加一个「远离 0 的方向一致性」惩罚：k̂ 与签名方向（正/负）应在多次重跑
时保持稳定——但这里只跑一次，所以只看 |amp|。

对 v6/v7/v8/v9 四版分别打分后选 amp 最小者。

【用法】
  python3 pick_wm.py <目录或图片...> --out-root <基准目录>  # 写 <基准>/<原目录>/_clean/...
  python3 pick_wm.py <dir> --json /tmp/pick.json              # 出选版 JSON
  python3 pick_wm.py <dir> --montage /tmp/pick.png            # 四版对比拼图

依赖：dewm_io / dewm / dewm_v7 / dewm_v8 / dewm_v9 / audit_wm（同目录）
"""

import argparse
import glob
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dewm_io import imread_any, imwrite_any  # noqa: E402
from dewm import remove_watermark as v6_remove  # noqa: E402
from dewm_v7 import inpaint_watermark as v7_remove  # noqa: E402
from dewm_v8 import remove_watermark as v8_remove  # noqa: E402
from dewm_v9 import remove_watermark as v9_remove  # noqa: E402
from audit_wm import estimate_residual  # noqa: E402


def collect(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            out.extend(sorted(glob.glob(os.path.join(p, "*.png"))) +
                       sorted(glob.glob(os.path.join(p, "*.jpg"))))
        else:
            out.append(p)
    return out


def dir_to_root(src, out_root):
    """把 <out_root>/<原父目录>/_clean/ 解析为输出目录，原图直接所在目录则用 _clean/。"""
    parent = os.path.basename(os.path.dirname(os.path.abspath(src))) or "root"
    return os.path.join(out_root, parent, "_clean")


def pick_one(img):
    """对一张图跑四版，签名分最低的胜出。返回 (winner_name, out_img, scores)。"""
    v6_out, _ = v6_remove(img)
    v7_out, _ = v7_remove(img)
    v8_out, _ = v8_remove(img)
    v9_out, st9 = v9_remove(img)
    if st9.get("skipped"):
        v9_out = img  # v9 判无水印拒动手 → 残留即原水印，amp 自然高

    scores = {
        "v6": abs(estimate_residual(v6_out)["amp"]),
        "v7": abs(estimate_residual(v7_out)["amp"]),
        "v8": abs(estimate_residual(v8_out)["amp"]),
        "v9": abs(estimate_residual(v9_out)["amp"]),
    }
    winner = min(scores, key=scores.get)
    return winner, {"v6": v6_out, "v7": v7_out, "v8": v8_out, "v9": v9_out}[winner], scores


def build_pick_montage(rows, cell_w=240, cell_h=200):
    """每图一行 5 列：原 / v6 / v7 / v8 / v9 + 头部行（每列标题）。"""
    n = len(rows)
    pad = 6
    keys = ("orig", "v6", "v7", "v8", "v9")
    canvas_h = pad * 2 + cell_h + 40 + n * (cell_h + pad)
    canvas_w = pad * 6 + cell_w * 5
    canvas = np.full((canvas_h, canvas_w, 3), 255, dtype=np.uint8)
    for j, label in enumerate(("original", "v6", "v7", "v8", "v9")):
        x = pad + j * (cell_w + pad) + cell_w // 2 - len(label) * 5
        cv2.putText(canvas, label, (x, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
    y0 = 40
    for i, r in enumerate(rows):
        ys = y0 + i * (cell_h + pad)
        for j, key in enumerate(keys):
            xs = pad + j * (cell_w + pad)
            im = r["_imgs"][key][-cell_h:, -cell_w:]
            canvas[ys:ys + im.shape[0], xs:xs + im.shape[1]] = im
        # 在左侧留白里写文件名 + 赢家（先转灰底再写字）
        name_y = ys + 30
        cv2.putText(canvas, r["name"][:20], (4, name_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1, cv2.LINE_AA)
        cv2.putText(canvas, f"-> {r['winner']}", (4, name_y + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 128, 0), 1, cv2.LINE_AA)
    return canvas


def main():
    ap = argparse.ArgumentParser(description="v6/v7/v8 三版选最佳")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out-root", default=None,
                    help="输出根目录（默认写到 <原图所在目录>/_clean/）")
    ap.add_argument("--json", dest="json_out", help="选版结果 JSON")
    ap.add_argument("--montage", help="四列对比拼图（原 / v6 / v7 / v8）")
    args = ap.parse_args()

    paths = collect(args.paths)
    if not paths:
        sys.exit("未找到图片")

    print(f"{'图片':<24} {'v6':>8} {'v7':>8} {'v8':>8} {'v9':>8}  {'胜出':>5}")
    print("-" * 76)
    rows = []
    for p in paths:
        img = imread_any(p)
        if img is None:
            continue
        winner, out, scores = pick_one(img)
        # 同时拿各版输出用于拼图
        v6_out, _ = v6_remove(img)
        v7_out, _ = v7_remove(img)
        v8_out, _ = v8_remove(img)
        v9_out, st9 = v9_remove(img)
        if st9.get("skipped"):
            v9_out = img
        name = os.path.basename(p)
        print(f"{name:<24} {scores['v6']:>8.2f} {scores['v7']:>8.2f} "
              f"{scores['v8']:>8.2f} {scores['v9']:>8.2f}  {winner:>5}")
        r = {"name": name, "path": p, "winner": winner, "scores": scores}
        if args.montage:
            r["_imgs"] = {"orig": img, "v6": v6_out, "v7": v7_out,
                          "v8": v8_out, "v9": v9_out}
        rows.append(r)

        # 写盘
        if args.out_root:
            out_dir = os.path.join(args.out_root, "_clean")
        else:
            out_dir = os.path.join(os.path.dirname(os.path.abspath(p)), "_clean")
        os.makedirs(out_dir, exist_ok=True)
        imwrite_any(os.path.join(out_dir, name), out)

    print("-" * 76)
    cnt = {"v6": 0, "v7": 0, "v8": 0, "v9": 0}
    for r in rows:
        cnt[r["winner"]] += 1
    print(f"合计 {len(rows)} 张：v6 胜 {cnt['v6']} / v7 胜 {cnt['v7']} / "
          f"v8 胜 {cnt['v8']} / v9 胜 {cnt['v9']}")
    print("已写入各图所在目录的 _clean/ 子目录（不覆盖原图）")

    if args.montage:
        m = build_pick_montage(rows)
        imwrite_any(args.montage, m)
        print(f"\n五列对比拼图 → {args.montage}  （原 / v6 / v7 / v8 / v9，标绿=胜出）")

    if args.json_out:
        for r in rows:
            r.pop("_imgs", None)
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print(f"JSON → {args.json_out}")


if __name__ == "__main__":
    main()
