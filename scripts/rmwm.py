#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rmwm — 去掉 WorkBuddy 生图右下角「AI生成 WORKBUDDY」合规水印。

背景（2026-09-07 实测，WorkBuddy 5.5.3）：
  * ImageGen 工具背后是 miora_text_to_image，工具 schema 没有 LogoAdd/水印开关
    （additionalProperties=false），`footnote` 实测也无法替换或去掉水印。
  * 51CTO 那篇热文说的「改 buddy-cloud.py 加 LogoAdd=0」在本版实测**无效**——
    ImageGen 不走那个 Python 脚本，4 份副本全打补丁后出图照样带水印。
  * 自造直连 API 的技能也走不通：BUDDY_CLOUD_TOKEN 不在执行环境里，miora_* 未暴露。
  → 因此本脚本走第三条路：本地像素级修复，零凭证、升级免疫、可回溯处理存量图。

原理：水印位置固定（右下角，两行「AI生成」/「WORKBUDDY」，约 111x51 px @1024 宽），
用 OpenCV Telea inpaint 对右下角固定区域做修复，**区域外像素 0 改动**。

用法：
  python3 rmwm.py a.png b.png              # 输出 a_nw.png / b_nw.png（同目录）
  python3 rmwm.py ~/Pictures/x/*.png --out ~/Pictures/clean     # --out 是目录
  python3 rmwm.py a.png --out ~/final.png  # --out 带扩展名 = 指定目标文件名
  python3 rmwm.py a.png --inplace          # 原地覆盖（先备份 a.png.bak）
  python3 rmwm.py a.png --check            # 只检测有没有水印，不改图
  python3 rmwm.py a.png --pad 1.3          # 修复框放大 1.3 倍（没盖干净时加大）
  python3 rmwm.py *.png --only-if-wm       # 只处理检测出带水印的图

依赖：opencv-python-headless、numpy
  pip install opencv-python-headless

⚠️ 合规提醒：水印是平台「AI 生成内容」标识。公开发布（公众号/社媒）时，
   请改用平台自带的 AI 内容声明，不要默默去掉标识后当原创发布。
"""

import argparse
import os
import shutil
import sys

try:
    import cv2
    import numpy as np
except ImportError as _e:          # 缺依赖时说人话，别甩 traceback（见 scripts/_env.py）
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import _env
    _env.die(_e, ['cv2', 'numpy'])

# 水印修复框（相对整图尺寸的比例，2026-09-07 在 1024x1280 / 1024x1536 上实测校准）
# 覆盖 ~111x51px 的水印本体 + 安全余量
BOX_W_RATIO = 0.21   # 右下角区域宽度占比
BOX_H_RATIO = 0.075  # 右下角区域高度占比

# 检测阈值：区域内与中位亮度偏离 >30 的像素占比超过该值 → 判定有水印
DETECT_DIFF = 30
DETECT_RATIO = 0.004


def imread_any(path):
    """支持中文/非 ASCII 路径的读图（cv2.imread 在 macOS 上对 unicode 路径会失败）。"""
    data = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise IOError(f"无法读取图片: {path}")
    return img


def imwrite_any(path, img, ext=".png"):
    ok, buf = cv2.imencode(ext, img)
    if not ok:
        raise IOError(f"编码失败: {path}")
    buf.tofile(path)


def resolve_out_path(src, out, suffix="_nw"):
    """解析输出路径。

    --out 传**目录** → 目录 / 原名_nw.ext（原行为）。
    --out 传**文件路径**（带图片扩展名）→ 直接作为目标文件（2026-09-07 修复：
    传 `xxx.png` 曾被当成目录，产出 `xxx.png/原名_nw.png` 的嵌套目录）。
    """
    stem, ext = os.path.splitext(src)
    if ext.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        ext = ".png"
    if not out:
        return os.path.join(os.path.dirname(src), os.path.basename(stem) + suffix + ext)
    if os.path.splitext(out)[1].lower() in (".png", ".jpg", ".jpeg", ".webp"):
        return out
    return os.path.join(out, os.path.basename(stem) + suffix + ext)


def watermark_box(w, h, pad=1.0):
    """返回右下角修复框 (x0, y0, x1, y1)，坐标为闭开区间。"""
    bw = int(round(w * BOX_W_RATIO * pad))
    bh = int(round(h * BOX_H_RATIO * pad))
    bw, bh = min(bw, w), min(bh, h)
    return w - bw, h - bh, w, h


def detect(img, box):
    """检测框内是否疑似有水印。返回 (bool, 偏离像素占比)。"""
    x0, y0, x1, y1 = box
    region = img[y0:y1, x0:x1]
    if region.size == 0:
        return False, 0.0
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY).astype(np.float32)
    median = float(np.median(gray))
    dev = np.abs(gray - median) > DETECT_DIFF
    ratio = float(dev.mean())
    return ratio > DETECT_RATIO, ratio


def build_mask(img, box, full=False, thresh=18, ksize=25, dilate_iter=2):
    """构建修复掩膜。

    glyph 模式（默认）：top-hat / black-hat 形态学只抓「比周围结构细」的笔画
    （水印两行文字），再叠加亮度带过滤（水印灰度约 140-235，排除纯白留白与
    暗部大色块），膨胀 2 轮覆盖抗锯齿边缘。框内大块内容（留白、色块、红条）
    基本不误伤。⚠️ 不要用「与区域中位亮度比差异」的朴素做法——框内明暗双
    模态时会把整片白区误判为字形（2026-09-07 实测翻车案例）。
    full 模式：整个矩形框作为掩膜（兜底）。
    """
    x0, y0, x1, y1 = box
    mask = np.zeros(img.shape[:2], dtype=np.uint8)
    region = img[y0:y1, x0:x1]
    if region.size == 0:
        return mask
    if full:
        mask[y0:y1, x0:x1] = 255
        return mask
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
    tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, k)
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, k)
    glyph = ((tophat > thresh) | (blackhat > thresh)) & (gray > 140) & (gray < 235)
    glyph = (glyph.astype(np.uint8)) * 255
    glyph = cv2.dilate(glyph, np.ones((3, 3), np.uint8), iterations=dilate_iter)
    mask[y0:y1, x0:x1] = glyph
    return mask


def repair(img, box, method="telea", full=False):
    mask = build_mask(img, box, full=full)
    flag = cv2.INPAINT_TELEA if method == "telea" else cv2.INPAINT_NS
    return cv2.inpaint(img, mask, 3, flag)


def process(path, args):
    img = imread_any(path)
    h, w = img.shape[:2]
    box = watermark_box(w, h, args.pad)
    has_wm, ratio = detect(img, box)

    if args.check:
        print(f"{'有水印' if has_wm else '干净':6s} 偏离占比={ratio:.4f}  "
              f"box={box}  {os.path.basename(path)}")
        return

    if args.only_if_wm and not has_wm:
        print(f"skip   偏离占比={ratio:.4f}（未检出水印）  {os.path.basename(path)}")
        return

    out_img = repair(img, box, args.method, full=args.full)

    if args.inplace:
        if args.out:
            print("warn   --inplace 与 --out 同时给出，--out 被忽略（原地覆盖优先）")
        backup = path + ".bak"
        if not os.path.exists(backup):
            shutil.copy2(path, backup)
        target, ext = path, os.path.splitext(path)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".webp"):
            ext = ".png"
    else:
        target = resolve_out_path(path, args.out)
        ext = os.path.splitext(target)[1].lower()

    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    imwrite_any(target, out_img, ext)

    # 复核：修复后该区域应基本无残留
    _, after = detect(out_img, box)
    print(f"ok     {ratio:.4f} → {after:.4f}  box={box}  → {target}")


def main():
    ap = argparse.ArgumentParser(
        description="去掉 WorkBuddy 生图右下角「AI生成 WORKBUDDY」水印"
    )
    ap.add_argument("images", nargs="+", help="图片路径（支持多个）")
    ap.add_argument("--out", help="输出目录（默认与源文件同目录）")
    ap.add_argument("--inplace", action="store_true", help="原地覆盖，先备份 .bak")
    ap.add_argument("--check", action="store_true", help="只检测不改图")
    ap.add_argument("--only-if-wm", action="store_true", help="只处理检出水印的图")
    ap.add_argument("--pad", type=float, default=1.0, help="修复框缩放，默认 1.0")
    ap.add_argument("--method", choices=["telea", "ns"], default="telea",
                    help="修复算法，默认 telea（边缘更干净）")
    ap.add_argument("--full", action="store_true",
                    help="整框修复（默认只修水印字形，压着内容的角落用默认更安全）")
    args = ap.parse_args()

    if not args.check and args.out:
        # --out 传文件路径时不建目录；传目录时才创建
        if os.path.splitext(args.out)[1].lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            os.makedirs(args.out, exist_ok=True)

    for p in args.images:
        if not os.path.isfile(p):
            print(f"skip   文件不存在: {p}")
            continue
        try:
            process(p, args)
        except Exception as e:  # noqa: BLE001
            print(f"error  {os.path.basename(p)}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
