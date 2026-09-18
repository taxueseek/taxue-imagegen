#!/usr/bin/env python3
"""rmwm_light.py — 去除「亮于背景」的浅色水印（rmwm.py 的互补脚本）。

rmwm.py 的 top-hat 掩膜只检暗于背景的字形；白平衡提亮后或白底海报上，
水印可能是比背景更亮的白字，rmwm 检不出（报 0.0000）。本脚本用
「大核中值模糊估计背景 + 双偏差掩膜 + Telea 修复」，亮暗通吃。

用法:
  python rmwm_light.py [--out DIR] [--box X0,Y0,X1,Y1] [--thresh N] FILE...
  python rmwm_light.py --check FILE...        # 只报告掩膜像素量，不写文件

默认框 (820,1430,1024,1536) 对应 1024x1536 竖版海报右下角；
其他尺寸按比例换算。水印压在复杂图形/纹理上时会留涂抹痕迹，
此时应收紧 --box 到水印实际区域并减小 --thresh 误差预算。

输出纪律（坑 13 教训④）：结果默认写 `原名_light.ext`，**任何路径下都不会覆盖原图**；
--out 传目录时写 `目录/原名.ext`，此时与原图同名但不同目录，仍不覆盖；
--out 传文件名时只允许单张输入（多张会互相覆盖，直接报错）。
"""
import argparse, glob, os, sys
try:
    import cv2
    import numpy as np
except ImportError as _e:          # 缺依赖时说人话，别甩 traceback（见 scripts/_env.py）
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import _env
    _env.die(_e, ['cv2', 'numpy'])

DEFAULT_BOX = (820, 1430, 1024, 1536)  # 1024x1536 参考坐标


def imread_any(path):
    """支持中文/非 ASCII 路径（cv2.imread 在 macOS 上对 unicode 路径返回 None）。

    2026-09-07 修复：本脚本原用 cv2.imread，遇到中文文件名（WorkBuddy 生图默认
    以提示词前若干字命名）会静默跳过，报 unreadable 而非报错，极难排查。
    """
    data = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise IOError(f"无法读取图片: {path}")
    return img


def imwrite_any(path, img):
    ext = os.path.splitext(path)[1].lower() or ".png"
    ok, buf = cv2.imencode(ext, img)
    if not ok:
        raise IOError(f"编码失败: {path}")
    buf.tofile(path)


def process(path, out_dir, box, thresh, kernel, dilate_iter, check_only):
    img = imread_any(path)
    if img is None:
        print(f"skip  {path} (unreadable)")
        return
    h, w = img.shape[:2]
    sx, sy = w / 1024.0, h / 1536.0
    x0, y0, x1, y1 = [int(v * (sx if i % 2 == 0 else sy)) for i, v in enumerate(box)]
    roi = img[y0:y1, x0:x1]
    bg = cv2.medianBlur(roi, kernel).astype(np.float64)
    dev = np.abs(roi.astype(np.float64) - bg).max(axis=2)
    m = (dev > thresh).astype(np.uint8) * 255
    m = cv2.dilate(m, np.ones((7, 7), np.uint8), iterations=dilate_iter)
    px = int((m > 0).sum())
    if check_only:
        print(f"check {os.path.basename(path)}  mask_px={px}")
        return
    mask = np.zeros(img.shape[:2], np.uint8)
    mask[y0:y1, x0:x1] = m
    out = cv2.inpaint(img, mask, 5, cv2.INPAINT_TELEA)
    src_abs = os.path.abspath(path)
    if out_dir and os.path.splitext(out_dir)[1].lower() in (".png", ".jpg", ".jpeg", ".webp"):
        dst = out_dir
    else:
        out_dir = out_dir or "."
        os.makedirs(out_dir, exist_ok=True)
        dst = os.path.join(out_dir, os.path.basename(path))
        # 坑 13 教训④：默认输出若与原图同路径，静默覆盖会毁掉原图——改写带后缀的新文件
        if os.path.abspath(dst) == src_abs:
            stem, ext = os.path.splitext(path)
            dst = stem + "_light" + (ext if ext.lower() in (".png", ".jpg", ".jpeg", ".webp") else ".png")
            print(f"warn  目标与原图同路径，改写为不覆盖原图: {dst}")
    imwrite_any(dst, out)
    print(f"ok    {os.path.basename(path)}  mask_px={px} -> {dst}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help="图片文件（支持 glob）")
    ap.add_argument("--out", default=".", help="输出目录（默认当前目录；与原图同路径时自动改写 原名_light.ext，不覆盖原图）")
    ap.add_argument("--box", default=",".join(map(str, DEFAULT_BOX)), help="处理区域 X0,Y0,X1,Y1（1024x1536 参考坐标，按尺寸比例换算）")
    ap.add_argument("--thresh", type=int, default=6, help="背景偏差阈值（越小抓得越多）")
    ap.add_argument("--kernel", type=int, default=51, help="中值模糊核（图形复杂时减小，如 31）")
    ap.add_argument("--dilate", type=int, default=2, help="掩膜膨胀轮数")
    ap.add_argument("--check", action="store_true", help="只检测不写文件")
    a = ap.parse_args()
    paths = []
    for p in a.files:
        paths += sorted(glob.glob(p)) if any(c in p for c in "*?[") else [p]
    if not paths:
        sys.exit("no input files")
    box = tuple(int(v) for v in a.box.split(","))
    if not a.check and len(paths) > 1 and os.path.splitext(a.out)[1].lower() in (".png", ".jpg", ".jpeg", ".webp"):
        sys.exit("错误：--out 传的是文件名但输入了多张图，结果会互相覆盖；请改传目录")
    for p in paths:
        process(p, a.out, box, a.thresh, a.kernel, a.dilate, a.check)

if __name__ == "__main__":
    main()
