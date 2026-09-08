#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dewm_io — 去水印脚本的共享 IO 层：硬保证「永不覆盖原图」。

【为什么要有这个模块】
2026-09-08 实测：批量去水印时用 `dewm.py *.png --out "$DIR"`（--out 传了源目录本身），
输出文件名与源文件名相同 → **原图被静默覆盖**。后果是无法再 A/B 对比去水印效果，
出了问题只能重新出图（积分成本 + 时间成本）。

根因不在「要不要覆盖」这个开关，而在于：脚本允许 target == source。
所以这里的策略是**从路径解析层堵死**，而不是靠调用者记得传对参数。

【三条硬规则】
1. 默认输出到 `<源目录>/_clean/<原名>` —— 原图原地不动，同名分目录，A/B 一眼可比。
2. `--out` 若解析到与源文件相同的路径（传目录或传同名文件都算），**自动重定向到 _clean/**
   并打印警告，绝不静默覆盖。
3. 确实要覆盖原图必须显式 `--inplace`（会打印醒目警告）。这是唯一例外，且是显性动作。

【用法（供 dewm / dewm_v7 / dewm_v8 调用）】
    from dewm_io import imread_any, imwrite_any, safe_target
    target = safe_target(src, args.out, inplace=args.inplace)

依赖：opencv-python-headless、numpy
"""

import os
import sys

import cv2
import numpy as np

CLEAN_SUBDIR = "_clean"
IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def imread_any(p):
    """支持中文/空格路径的读图。"""
    data = np.fromfile(p, dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def imwrite_any(p, img):
    """支持中文/空格路径的写图（自动建父目录）。"""
    d = os.path.dirname(os.path.abspath(p))
    if d:
        os.makedirs(d, exist_ok=True)
    ok, buf = cv2.imencode(os.path.splitext(p)[1] or ".png", img)
    if ok:
        buf.tofile(p)
    return ok


def _is_image_path(s):
    return os.path.splitext(s)[1].lower() in IMG_EXTS


def _real(p):
    """归一化路径：realpath 消除符号链接与 ./ 差异。

    macOS 上 /tmp 是 /private/tmp 的符号链接，只比 abspath 会让
    「--out /tmp/x」与「cwd=/private/tmp/x」判为不同路径 → 守卫失效（实测翻车）。
    """
    return os.path.realpath(os.path.abspath(p))


def _redirect(src, why):
    """把输出重定向到源目录下的 _clean/ 子目录。"""
    d = os.path.dirname(os.path.abspath(src))
    target = os.path.join(d, CLEAN_SUBDIR, os.path.basename(src))
    print(f"  ⚠️  {why}\n      → 已重定向到 {target}（原图保持不变）", file=sys.stderr)
    return target


def safe_target(src, out, inplace=False):
    """解析输出路径，保证不与源路径相同。

    src      源文件路径
    out      --out 参数（None / 目录 / 文件）
    inplace  True 时允许覆盖原图（调用方需用户显式要求）
    返回     最终输出路径
    """
    src_abs = _real(src)

    # 显式要求原地覆盖：唯一允许 target == source 的入口
    if inplace:
        if out is None:
            print(f"  ⚠️  --inplace：将覆盖原图 {src}", file=sys.stderr)
            return src_abs
        if _is_image_path(out):
            return _real(out)
        return os.path.join(_real(out), os.path.basename(src))

    # 未指定 --out：默认落在源目录的 _clean/ 下，同名
    if out is None:
        d = os.path.dirname(src_abs)
        return os.path.join(d, CLEAN_SUBDIR, os.path.basename(src))

    # --out 是具体文件
    if _is_image_path(out):
        out_abs = _real(out)
        if out_abs == src_abs:
            return _redirect(src, "--out 指向源文件本身，拒绝覆盖")
        os.makedirs(os.path.dirname(out_abs), exist_ok=True)
        return out_abs

    # --out 是目录
    out_dir = _real(out)
    target = os.path.join(out_dir, os.path.basename(src))
    if _real(target) == src_abs:
        return _redirect(src, "--out 目录就是源目录，同名会覆盖原图，拒绝覆盖")
    os.makedirs(out_dir, exist_ok=True)
    return target


def add_common_args(ap):
    """给 argparse 注入统一的输出相关参数。"""
    ap.add_argument("--out", help="目标文件或目录（默认写到 <源目录>/_clean/）")
    ap.add_argument("--inplace", action="store_true",
                    help="原地覆盖原图（危险，默认关闭；会破坏 A/B 对比能力）")
    ap.add_argument("--crop", help="输出水印区 4x 放大目检裁片")
    return ap


def save_crop(out_img, src_path, crop_arg, multi):
    """保存 4x 放大目检裁片（多图时逐图命名，避免互相覆盖）。"""
    if not crop_arg:
        return
    H, W = out_img.shape[:2]
    crop = out_img[max(0, H - 200):, max(0, W - 340):]
    if multi:
        cstem, cext = os.path.splitext(crop_arg)
        cp = f"{cstem}_{os.path.splitext(os.path.basename(src_path))[0][:24]}{cext or '.png'}"
    else:
        cp = crop_arg
    imwrite_any(cp, cv2.resize(crop, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST))
