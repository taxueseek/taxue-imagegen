#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_wm — 去水印残留审计（无需原图）。

【为什么需要它】
原图被覆盖后无法做 A/B 对比，但仍可判断「图上还残留多少水印」：

  水印是加性扰动  I = orig + k·a·(C - orig)，a 为已知 α 模板。
  用 inpaint 估出「底下应该是什么」bg ≈ orig，则残差
      r = I - bg  ≈  k · a · (C - bg)
  对核心像素最小二乘拟合 k，即可量化残留：
      k̂      残留不透明度（0 = 无残留）
      amp    k̂·mean(a·(C-bg))，残留的平均灰度幅度（0-255 量级，人眼可感阈 ≈1.5）
      R²     残差与水印形状的吻合度（高 = 确实是水印形状而非纹理噪声）

  amp 高 **且** R² 高 → 真的有水印残留；
  amp 高但 R² 低 → 多半是高频纹理（马赛克/网点）造成的误报。

【用法】
  python3 audit_wm.py <目录或图片...>            # 打印审计表
  python3 audit_wm.py <目录> --montage /tmp/m.png # 出三联目检图（当前 / v8 / 差×8）
  python3 audit_wm.py <目录> --json /tmp/a.json

【判定阈值】
  CLEAN    amp < 1.0
  SUSPECT  1.0 ≤ amp < 2.5 或 R² 异常
  DIRTY    amp ≥ 2.5

依赖：opencv-python-headless、numpy（零模型，~0.5s/张）
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
from dewm_v8 import load_template, remove_watermark  # noqa: E402

CORE_THR = 0.15
AMP_CLEAN = 1.0
AMP_DIRTY = 2.5


def estimate_residual(img):
    """拟合残留不透明度。返回 dict(k, r2, amp, core_px)。"""
    H, W = img.shape[:2]
    a, (x0, y0) = load_template(W, H)
    a3 = a[:, :, None]

    core = (a > CORE_THR).astype(np.uint8) * 255
    core = cv2.dilate(core, np.ones((3, 3), np.uint8), iterations=1)
    mask = np.zeros((H, W), dtype=np.uint8)
    mask[y0:y0 + core.shape[0], x0:x0 + core.shape[1]] = core
    bg = cv2.inpaint(img, mask, 3, cv2.INPAINT_TELEA).astype(np.float32)

    sub = img[y0:, x0:].astype(np.float32)
    sub_bg = bg[y0:, x0:]

    core_m = a > CORE_THR
    y_obs = sub - sub_bg
    x_mod = a3 * (255.0 - sub_bg)
    num = float((x_mod * y_obs)[core_m].sum())
    den = float((x_mod * x_mod)[core_m].sum()) + 1e-6
    k = num / den
    ss_res = float(((y_obs - k * x_mod)[core_m] ** 2).sum())
    ss_tot = float((y_obs[core_m] ** 2).sum()) + 1e-6
    r2 = 1.0 - ss_res / ss_tot
    amp = float(k * np.mean(x_mod[core_m])) if core_m.any() else 0.0
    return {"k": float(k), "r2": float(r2), "amp": amp,
            "core_px": int(core_m.sum())}


def verdict(amp):
    """有符号 amp 反映方向：正=水印残留（亮），负=v6 过减（暗）。
    两者都是缺陷，统一用 |amp| 评估严重度。
    """
    a = abs(amp)
    if a < AMP_CLEAN:
        return "CLEAN"
    if a < AMP_DIRTY:
        return "SUSPECT"
    return "DIRTY"


def collect(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            out.extend(sorted(glob.glob(os.path.join(p, "*.png"))) +
                       sorted(glob.glob(os.path.join(p, "*.jpg"))))
        else:
            out.append(p)
    return out


def build_montage(rows, cell_w=340, cell_h=200):
    """三联：当前 / v8 输出 / 差异×8（放大便于肉眼判断）。"""
    n = len(rows)
    canvas = np.full((n * cell_h, cell_w * 3 + 8 * 2, 3), 255, dtype=np.uint8)
    for i, r in enumerate(rows):
        cur = r["_cur"][-cell_h:, -cell_w:]
        new = r["_v8"][-cell_h:, -cell_w:]
        diff = np.clip(np.abs(cur.astype(np.float32) -
                              new.astype(np.float32)) * 8, 0, 255).astype(np.uint8)
        y = i * cell_h
        for j, im in enumerate((cur, new, diff)):
            x = j * (cell_w + 8)
            canvas[y:y + im.shape[0], x:x + im.shape[1]] = im
    return canvas


def main():
    ap = argparse.ArgumentParser(description="去水印残留审计")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--montage", help="输出三联目检拼图")
    ap.add_argument("--json", dest="json_out", help="输出 JSON")
    args = ap.parse_args()

    paths = collect(args.paths)
    if not paths:
        sys.exit("未找到图片")

    print(f"{'图片':<26} {'k̂':>7} {'R²':>7} {'amp':>7} {'判定':>9}  {'v8最大改动':>10}")
    print("-" * 78)
    rows = []
    for p in paths:
        img = imread_any(p)
        if img is None:
            print(f"{os.path.basename(p):<26} (unreadable)")
            continue
        res = estimate_residual(img)
        v8, st = remove_watermark(img)
        H, W = img.shape[:2]
        a, (x0, y0) = load_template(W, H)
        d = np.abs(v8[y0:, x0:].astype(np.float32) -
                   img[y0:, x0:].astype(np.float32))
        core_m = a > CORE_THR
        maxd = float(d[core_m].max()) if core_m.any() else 0.0
        v = verdict(res["amp"])
        name = os.path.basename(p)
        print(f"{name:<26} {res['k']:>7.3f} {res['r2']:>7.3f} {res['amp']:>7.2f} "
              f"{v:>9}  {maxd:>10.1f}")
        r = dict(res, name=name, path=p, verdict=v, v8_max_delta=maxd,
                 v8_k=st["k"], v8_r2=st["r2"])
        if args.montage:
            r["_cur"] = img
            r["_v8"] = v8
        rows.append(r)

    print("-" * 78)
    dirty = [r for r in rows if r["verdict"] == "DIRTY"]
    susp = [r for r in rows if r["verdict"] == "SUSPECT"]
    print(f"合计 {len(rows)} 张：DIRTY {len(dirty)} / SUSPECT {len(susp)} / "
          f"CLEAN {len(rows) - len(dirty) - len(susp)}")
    print("注：amp 是残留灰度幅度（人眼可感阈 ≈1.5）；"
          "R² 高说明残差确实是水印形状，R² 低则多半是纹理误报")

    if args.montage:
        m = build_montage([r for r in rows if "_cur" in r])
        imwrite_any(args.montage, m)
        print(f"\n三联目检图 → {args.montage}  （左=当前 中=v8 右=差异×8）")

    if args.json_out:
        for r in rows:
            r.pop("_cur", None)
            r.pop("_v8", None)
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print(f"JSON → {args.json_out}")


if __name__ == "__main__":
    main()
