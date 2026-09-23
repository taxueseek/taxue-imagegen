#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dewm2.py —— 逐像素·带校验的反向 Alpha 去水印（零模型 / 经典 CV / 亚秒级）

与旧 dewm.py 的区别：
  dewm.py  = 用一张【全局标定死的 α 模板 + 固定白色 + 固定几何】反解，换模型/换位置/压文字即失效。
  dewm2.py = 不依赖任何标定模板。把水印像素当作「仍掺着原图信息的混合像素」，逐像素：
       观测 C = B·(1-α) + W·α   →   还原 B = (C - W·α) / (1-α)
     其中 B 用大核中值滤波从局部估出，W 在【白/灰/黑】多候选里试，α 用向量投影解，
     并且——还原前先反算 predicted=B+α(W-B)，只有与实际像素 RMS 误差 ≤ 容差 才执行。
     这道「校验门」保证压在深色文字上的像素（拟合不上）被跳过 → 绝不误伤内容；
     白底上的半透明水印（拟合得上）被干净还原。

用法：
  python dewm2.py IMG [IMG ...] [--box X0,Y0,X1,Y1] [--full]
        [--bk 15] [--tol 10] [--dilate 1] [--passes 2]
        [--colors "255,255,255;210,210,210;180,180,180;150,150,150;120,120,120;0,0,0"]
        [--amin 0.03 --amax 0.97] [--inpaint] [--out DIR] [--check]

默认只处理右下角 ROI（多数生图模型把 "AI 生成" 类水印放这里）；--box 自定义，--full 全图。
输出默认写到 <原名>_dewm2.<ext>，永不覆盖原图。
"""
import _log
import argparse, os, sys, glob

try:
    import numpy as np
    import cv2
except ImportError as _e:          # 缺依赖时说人话，别甩 traceback（见 scripts/_env.py）
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import _env
    _env.die(_e, ['numpy', 'cv2'])

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dewm_io import guard_target  # noqa: E402


def parse_colors(s):
    out = []
    for tok in s.split(";"):
        tok = tok.strip()
        if not tok:
            continue
        parts = [int(x) for x in tok.split(",")]
        if len(parts) == 1:
            parts = parts * 3
        assert len(parts) == 3, f"bad color {tok!r}"
        out.append(np.array(parts, dtype=np.float64))
    return out


def load_rgb(path):
    im = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if im is None:
        raise SystemExit(f"读不到图片：{path}")
    alpha = None
    if im.ndim == 2:  # gray
        im = cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)
    elif im.shape[2] == 4:  # BGRA
        alpha = im[:, :, 3:4]
        im = cv2.cvtColor(im, cv2.COLOR_BGRA2BGR)
    elif im.shape[2] == 3:
        im = im.copy()
    else:
        im = cv2.cvtColor(im[:, :, :3], cv2.COLOR_BGR2GRAY)
        im = cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)
    return im, alpha  # im is BGR uint8, HxWx3


def save_rgb(path, bgr, alpha):
    if alpha is not None:
        bgra = np.concatenate([bgr, alpha], axis=2)
        cv2.imwrite(path, bgra)
    else:
        cv2.imwrite(path, bgr)


def default_box(w, h):
    # bottom-right corner band where most generators put the mark
    x0 = int(w * 0.55)
    y0 = int(h * 0.86)
    return (x0, y0, w, h)


def process(path, args, colors):
    bgr, alpha = load_rgb(path)
    h, w = bgr.shape[:2]

    if args.full:
        box = (0, 0, w, h)
    else:
        box = args.box if args.box else default_box(w, h)
    x0, y0, x1, y1 = [int(v) for v in box]
    # scale box if given in 1024x1536 reference coords
    if args.ref:
        rw, rh = [int(v) for v in args.ref.split(",")]
        sx, sy = w / rw, h / rh
        x0, y0, x1, y1 = int(x0 * sx), int(y0 * sy), int(x1 * sx), int(y1 * sy)
    x0 = max(0, min(x0, w - 1)); x1 = max(x0 + 1, min(x1, w))
    y0 = max(0, min(y0, h - 1)); y1 = max(y0 + 1, min(y1, h))

    img = bgr.astype(np.float64)

    # candidate mask = ROI (analyze, not repaint)
    roi = np.zeros((h, w), dtype=np.uint8)
    roi[y0:y1, x0:x1] = 1

    if args.check:
        # quick estimate of how many pixels look like a removable semi-transparent mark
        n = _one_pass(img, roi, colors, args, return_count=True)
        print(f"check {os.path.basename(path)}  ROI_px={int(roi.sum())}  fit_px={n}")
        return None

    for _ in range(max(1, args.passes)):
        img = _one_pass(img, roi, colors, args)

    if args.inpaint:
        # optional fallback: pixels inside ROI still strongly deviating from a smooth bg
        bg = cv2.medianBlur(img.astype(np.uint8), max(3, args.bk | 1))
        resid = np.abs(img - bg.astype(np.float64)).sum(2)
        hard = ((roi > 0) & (resid > args.inpaint_thresh)).astype(np.uint8)
        if hard.sum():
            img = cv2.inpaint(img.astype(np.uint8), hard, 3, cv2.INPAINT_TELEA).astype(np.float64)

    out = np.clip(img, 0, 255).astype(np.uint8)

    stem, ext = os.path.splitext(path)
    if args.out:
        # 输出守卫（dewm_io.guard_target）：--out 传源目录时 join(basename) 会静默覆盖
        # 原图；同族其它脚本用 safe_target，本脚本的输出名沿用原名，故走 guard_target。
        target = guard_target(path, os.path.join(args.out, os.path.basename(path)), "_dewm2")
    else:
        target = f"{stem}_dewm2{ext}"
    save_rgb(target, out, alpha)
    return target


def _one_pass(img, roi, colors, args, return_count=False):
    h, w = img.shape[:2]
    bk = args.bk if args.bk % 2 == 1 else args.bk + 1
    bk = max(3, bk)
    # local background estimate: large-kernel median kills thin watermark strokes,
    # but keeps thick content → content pixels end up with alpha≈0 → protected.
    B = cv2.medianBlur(img.astype(np.uint8), bk).astype(np.float64)

    # dilate ROI so faint anti-aliased watermark edges are included
    if args.dilate > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                      (2 * args.dilate + 1, 2 * args.dilate + 1))
        mask = cv2.dilate(roi, k)
    else:
        mask = roi

    sel = mask > 0
    C = img[sel]                 # Nx3
    Bb = B[sel]                  # Nx3
    n = C.shape[0]

    # stability guards: the mark is an ACHROMATIC (gray) overlay on a LIGHT background.
    # Only pixels in that regime can be safely un-blended; saturated/dark content
    # (e.g. blue letter strokes) must be left untouched, else per-pixel fitting
    # misfires at edges and injects color speckle.
    chroma = C.max(1) - C.min(1)          # Nx  (0 = gray)
    bbg = Bb.mean(1)                       # Nx  local background brightness
    regime = (chroma <= args.maxchroma) & (bbg >= args.minbg)

    best_err = np.full(n, np.inf)
    best_val = np.zeros(n, dtype=bool)
    best_new = C.copy()

    for W in colors:
        d = W - Bb                       # Nx3  (watermark - background)
        denom = (d * d).sum(1)           # N
        num = ((C - Bb) * d).sum(1)      # N
        with np.errstate(divide="ignore", invalid="ignore"):
            a = np.where(denom > 1e-6, num / denom, 0.0)
        predicted = Bb + a[:, None] * d
        err = np.sqrt(((C - predicted) ** 2).mean(1))
        valid = regime & (denom > 1e-6) & (a > args.amin) & (a < args.amax) & (err <= args.tol)
        better = valid & (err < best_err)
        restored = (C - W[None, :] * a[:, None]) / np.clip(1.0 - a, 1e-3, None)[:, None]
        restored = np.clip(restored, 0, 255)
        idx = np.where(better)[0]
        if idx.size:
            best_err[idx] = err[idx]
            best_val[idx] = True
            best_new[idx] = restored[idx]

    if return_count:
        return int(best_val.sum())

    out = img.copy()
    full_new = img[sel].copy()
    full_new[best_val] = best_new[best_val]
    out[sel] = full_new
    return out


def main():
    ap = argparse.ArgumentParser(description="逐像素·带校验·反向Alpha 去水印（零模型）")
    ap.add_argument("files", nargs="+", help="图片文件（支持 glob）")
    ap.add_argument("--box", type=lambda s: tuple(int(x) for x in s.split(",")),
                    help="ROI X0,Y0,X1,Y1")
    ap.add_argument("--ref", help="若 --box 用参考坐标(如 1024,1536)，按比例换算")
    ap.add_argument("--full", action="store_true", help="处理整图")
    ap.add_argument("--bk", type=int, default=15, help="背景中值滤波核(奇数,越大越保守)")
    ap.add_argument("--tol", type=float, default=8.0, help="RMS 拟合容差(越小越保守)")
    ap.add_argument("--dilate", type=int, default=1, help="掩膜膨胀轮数")
    ap.add_argument("--passes", type=int, default=2, help="迭代轮数(处理多层/阴影)")
    ap.add_argument("--amin", type=float, default=0.03)
    ap.add_argument("--amax", type=float, default=0.97)
    ap.add_argument("--maxchroma", type=float, default=40.0,
                    help="只还原彩度<=此值的像素(水印是灰的;高彩度内容一律不碰)")
    ap.add_argument("--minbg", type=float, default=170.0,
                    help="只还原局部背景亮度>=此值的像素(灰水印压浅底才可靠)")
    ap.add_argument("--colors", default="255,255,255;235,235,235;215,215,215;195,195,195;175,175,175")
    ap.add_argument("--inpaint", action="store_true", help="对不透明残留做 Telea 兜底")
    ap.add_argument("--inpaint_thresh", type=float, default=90.0)
    ap.add_argument("--out", help="输出目录")
    ap.add_argument("--check", action="store_true", help="只统计命中像素，不写文件")
    args = ap.parse_args()

    colors = parse_colors(args.colors)
    files = []
    for f in args.files:
        files.extend(glob.glob(f) or [f])

    wrote = []
    failed = 0
    for f in files:
        try:
            t = process(f, args, colors)
            if t:
                wrote.append(t)
                print(f"ok    {os.path.basename(f)} -> {t}")
        except SystemExit as e:
            failed += 1
            print(f"skip  {f}: {e}")
        except Exception as e:
            failed += 1
            print(f"err   {f}: {type(e).__name__}: {e}")
    if wrote:
        print(f"\n共处理 {len(wrote)} 张")
    # 有输入却一张都没产出（或批量里出错）时不能静默 return 0（2026-09-23 修）：
    # 此前所有分支都不设退出码，于是「9 张全部读不了 / 全部抛异常」也是一句
    # 「共处理 0 张」+ 退出码 0，批量流程会把没做当成做好了。
    # 退出码 4 = 工具/输入错误（与 postcheck 的 4 同义），**不要据此当 blocker**。
    if failed:
        print(f"\n{failed}/{len(files)} 张未能处理（工具/输入错误，**不是 blocker**）",
              file=sys.stderr)
        sys.exit(4)


if __name__ == "__main__":
    _log.run("dewm2", main)
