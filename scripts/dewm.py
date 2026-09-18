#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dewm — 自然去水印 v6：逆向 alpha 反解（2026-09-07 定稿）。

【演进史，皆为实测教训】
  rmwm      固定大框 inpaint → 框比水印大 20 倍，插值出光滑补丁（用户判"不自然"）
  dewm v2   单图字形检测 → Otsu 被深色笔画带偏，掩膜盖住薄纱漏掉水印
  dewm v3   固定字形模板 + inpaint/克隆 → 平台水印尺寸逐图可变，模板盖不全；
            seamlessClone 的"掩膜 bbox 对中 p"语义会把克隆区平移出画面
  dewm v5   固定角区检测 + 整区 Poisson 纸克隆 → 纸源污染、纸底低频不匹配
  dewm v6   逆向 alpha 反解（本版，源自 Gemini 社区工具 remove-ai-watermarks
            的可见水印算法思想）

【v6 原理——为什么不修复，而是反解】
水印是半透明白色覆盖层：wm = α·255 + (1-α)·orig。
它没有丢失信息，只是叠加了已知扰动——逐像素减掉即可，
水印下的内容（纸纹、网点、阴影、文字）被数学精确还原，而非猜测重画。
此前所有"修复"路线的根本错误：把可逆问题当成了不可逆的补全问题。

【α 模板标定（一次性，wm_alpha_1024.npz 随技能分发）】
1. 从归档库选角区无画面笔画的"干净角图"（≥2 张）
2. 每图：α_i = (sub - paper_i) / (255 - paper_i)，paper_i = 框内灰度中位数
3. 逐像素取中值 → 纸斑逐图随机被消除，字形恒定存活
4. 已实测标定：水印色 C=255，核心 α≈0.71，位置 1024x1536 右下角固定
   （三图拟合 dev=0.72·(255-paper) 严格成立）

【用法】
  python3 dewm.py a.png                        # 输出到 a.png 所在目录的 _clean/a.png
  python3 dewm.py *.png                        # 批量，全部进 _clean/（原图不动）
  python3 dewm.py a.png --out ~/final.png      # 指定目标文件（不得与源文件同名）
  python3 dewm.py *.png --out ~/clean/         # 指定目录（不得是源目录本身）
  python3 dewm.py a.png --inplace              # 原地覆盖（危险，需显式声明）
  python3 dewm.py a.png --check                # 只报检测统计，不写文件
  python3 dewm.py a.png --crop /tmp/zoom.png   # 输出水印区 4x 放大裁片（目检）

【永不覆盖原图】
输出路径统一由 dewm_io.safe_target() 解析：默认落 `<源目录>/_clean/<原名>`；
`--out` 若指向源文件或源目录则自动重定向到 _clean/ 并告警；
只有显式 `--inplace` 才允许覆盖。详见 dewm_io.py 头部说明。

依赖：opencv-python-headless、numpy（零模型，0.2s/张，内存 <100MB）
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dewm_io import imread_any, imwrite_any, safe_target, add_common_args, save_crop  # noqa: E402

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "wm_alpha_1024.npz")
BASE_W, BASE_H = 1024, 1536


def load_template(W, H):
    """加载 α 模板并按宽度缩放、锚定右下角。"""
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError(f"缺少 α 模板: {TEMPLATE_PATH}")
    z = np.load(TEMPLATE_PATH)
    tm, tbox = z["alpha"], z["box"]
    s = W / BASE_W
    bw, bh = int(round((tbox[2] - tbox[0]) * s)), int(round((tbox[3] - tbox[1]) * s))
    if abs(H / BASE_H - s) > 0.02:
        print(f"warning: 尺寸 {W}x{H} 非 {BASE_W}x{BASE_H}，按宽度缩放锚定右下角，未经验证")
    a = cv2.resize(tm, (bw, bh), interpolation=cv2.INTER_LINEAR)
    return a, (W - bw, H - bh)


def remove_watermark(img):
    """逆向 alpha 反解。返回 (输出图, 统计)。"""
    H, W = img.shape[:2]
    a, (x0, y0) = load_template(W, H)
    sub = img[y0:, x0:]
    rec = (sub - 255.0 * a[:, :, None]) / np.maximum(1 - a[:, :, None], 0.29)
    w = a > 0.02
    out = img.copy()
    region = out[y0:, x0:]
    region[w] = rec[w]
    stats = {"wm_px": int(w.sum()), "box": (x0, y0, W, H), "a_max": float(a.max())}
    return np.clip(out, 0, 255).astype(np.uint8), stats


def main():
    ap = argparse.ArgumentParser(description="逆向 alpha 反解去水印（零模型）")
    ap.add_argument("paths", nargs="+", help="图片路径")
    add_common_args(ap)
    ap.add_argument("--check", action="store_true", help="只报统计不写文件")
    args = ap.parse_args()

    multi = len(args.paths) > 1
    for path in args.paths:
        img = imread_any(path)
        if img is None:
            print(f"skip  {path} (unreadable)")
            continue
        out, st = remove_watermark(img)
        name = os.path.basename(path)
        if args.check:
            print(f"check {name}  wm_px={st['wm_px']} a_max={st['a_max']:.2f} box={st['box']}")
            continue
        target = safe_target(path, args.out, inplace=args.inplace)
        imwrite_any(target, out)
        print(f"ok    {name}  wm_px={st['wm_px']} → {target}")
        save_crop(out, path, args.crop, multi)


if __name__ == "__main__":
    main()
