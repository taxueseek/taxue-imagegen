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

覆盖率守卫（v1.19，2026-09-18 实测事故后加）：
判据「与中值背景的偏差 > thresh」在**高频纹理 / 深色实色底**上会退化成
「整块掩膜」——木刻网点底的基础掩膜率就有 43.7%，再经 7×7 核 --dilate 2
膨胀后达 99.9%，于是 Telea 从整块边界向内扩散 = 整块抹平，且边界像素含
邻接文字/异材质时还会啃字、渗色（坑 35）。
故 mask 覆盖率 > 40% 时**拒绝写出**并给出整改提示；确要继续须显式 --force。
这类背景（深色实色块 + 高频纹理 / 水印跨材质）请改用分材质填充，
不要用本脚本，也不要绕过 dewm 的 conf 门控（坑 35 第四节）。

输出纪律（坑 13 教训④）：结果默认写 `原名_light.ext`，**任何路径下都不会覆盖原图**；
--out 传目录时写 `目录/原名.ext`，此时与原图同名但不同目录，仍不覆盖；
--out 传文件名时只允许单张输入（多张会互相覆盖，直接报错）。
"""
import _log
import argparse, glob, os, sys
try:
    import cv2
    import numpy as np
except ImportError as _e:          # 缺依赖时说人话，别甩 traceback（见 scripts/_env.py）
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import _env
    _env.die(_e, ['cv2', 'numpy'])

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dewm_io import guard_target  # noqa: E402

DEFAULT_BOX = (820, 1430, 1024, 1536)  # 1024x1536 参考坐标
COVERAGE_LIMIT = 0.40                  # 掩膜覆盖率硬上限：超过即判判据失效（坑 35）


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


def process(path, out_dir, box, thresh, kernel, dilate_iter, check_only, force=False):
    img = imread_any(path)
    if img is None:
        print(f"skip  {path} (unreadable)")
        return
    h, w = img.shape[:2]
    sx, sy = w / 1024.0, h / 1536.0
    x0, y0, x1, y1 = [int(v * (sx if i % 2 == 0 else sy)) for i, v in enumerate(box)]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    roi = img[y0:y1, x0:x1]
    if roi.size == 0:
        print(f"refuse {os.path.basename(path)}: --box 换算后为空区域 x[{x0},{x1}] y[{y0},{y1}]；"
              f"注意 --box 是 1024x1536 参考坐标（本图 {w}x{h}，缩放比 {sx:.2f}x/{sy:.2f}y）")
        return
    bg = cv2.medianBlur(roi, kernel).astype(np.float64)
    dev = np.abs(roi.astype(np.float64) - bg).max(axis=2)
    m = (dev > thresh).astype(np.uint8) * 255
    m = cv2.dilate(m, np.ones((7, 7), np.uint8), iterations=dilate_iter)
    px = int((m > 0).sum())
    cov = px / float(roi.shape[0] * roi.shape[1])
    if check_only:
        print(f"check {os.path.basename(path)}  mask_px={px}  覆盖率={cov*100:.1f}%"
              f"  ROI={x1-x0}x{y1-y0}")
        return
    # 覆盖率守卫：>40% 判掩膜失效——纹理/深色实色底上判据会退化成整块掩膜，
    # inpaint 将从整块边界向内扩散 = 抹平整块（坑 35，2026-09-18 事故）
    if cov > COVERAGE_LIMIT and not force:
        print(f"refuse {os.path.basename(path)}: 掩膜覆盖率 {cov*100:.1f}% > "
              f"{COVERAGE_LIMIT*100:.0f}%，判掩膜失效。\n"
              f"        纹理/深色实色底上「偏差阈值」判据会抓满整块 ROI，inpaint 将抹平整块并啃掉邻接文字。\n"
              f"        改法：先 --check 看覆盖率 → 收紧 --box 到水印本体、降 --dilate 到 0-1、提高 --thresh；\n"
              f"        若背景是深色实色块 + 高频纹理（或水印跨材质），改用分材质填充（见坑 35），不要用本脚本。\n"
              f"        确要继续请加 --force。")
        return
    mask = np.zeros(img.shape[:2], np.uint8)
    mask[y0:y1, x0:x1] = m
    out = cv2.inpaint(img, mask, 5, cv2.INPAINT_TELEA)
    if out_dir and os.path.splitext(out_dir)[1].lower() in (".png", ".jpg", ".jpeg", ".webp"):
        dst = out_dir
    else:
        out_dir = out_dir or "."
        dst = os.path.join(out_dir, os.path.basename(path))
    # 坑 13 教训④：目标若与原图同路径，静默覆盖会毁掉原图。
    # 2026-09-23 修：原守卫只在「--out 传目录」分支做，且只比 `abspath`——
    # APFS 大小写变体、硬链接、符号链接三条路都绕得过去（dewm_io 头部正是这么踩出来的），
    # 而 `--out` 传文件路径那条分支**根本没有守卫**。统一交给 dewm_io.guard_target：
    # 判据（realpath + samefile + normcase）与同族完全一致，不在本文件重写一遍。
    dst = guard_target(path, dst, "_light")
    imwrite_any(dst, out)
    print(f"ok    {os.path.basename(path)}  mask_px={px} 覆盖率={cov*100:.1f}% -> {dst}")
    if cov > 0.25:
        print(f"warn  覆盖率 {cov*100:.1f}% 偏高，务必 4x 放大目检水印之外的区域（尤其文字），"
              f"确认没有啃字/渗色后再交付")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help="图片文件（支持 glob）")
    ap.add_argument("--out", default=".", help="输出目录（默认当前目录；与原图同路径时自动改写 原名_light.ext，不覆盖原图）")
    ap.add_argument("--box", default=",".join(map(str, DEFAULT_BOX)), help="处理区域 X0,Y0,X1,Y1（1024x1536 参考坐标，按尺寸比例换算）")
    ap.add_argument("--thresh", type=int, default=6, help="背景偏差阈值（越小抓得越多）")
    ap.add_argument("--kernel", type=int, default=51, help="中值模糊核（图形复杂时减小，如 31）")
    ap.add_argument("--dilate", type=int, default=2, help="掩膜膨胀轮数")
    ap.add_argument("--check", action="store_true", help="只检测不写文件")
    ap.add_argument("--force", action="store_true",
                    help="跳过掩膜覆盖率守卫（>40%% 时默认拒绝写出；强行继续前请先确认不是整块掩膜）")
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
        process(p, a.out, box, a.thresh, a.kernel, a.dilate, a.check, a.force)

if __name__ == "__main__":
    _log.run("rmwm_light", main)
