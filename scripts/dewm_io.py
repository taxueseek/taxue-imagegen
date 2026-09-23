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

import _log

try:
    import cv2
    import numpy as np
except ImportError as _e:          # 缺依赖时说人话，别甩 traceback（见 scripts/_env.py）
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import _env
    _env.die(_e, ['cv2', 'numpy'])

CLEAN_SUBDIR = "_clean"
IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp")

# ── α 模板（水印几何的唯一真源）────────────────────────────────────
# 2026-09-23 收口：`load_template` 此前在 dewm / dewm_v7 / dewm_v8 / dewm_v9 里
# 各有一份**逐字等价**的副本（npz 里 alpha 本就是 float32，只有 dewm.py 多打一行
# 尺寸警告），于是同一条几何假设散在四处、改一处要记得改四处。全族（v10/v11/v12/v13、
# audit_wm、wm_auto、pick_wm、metric_flat 与各 bench）都经这里取模板，收在此处即全局生效。
TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "wm_alpha_1024.npz")
BASE_W, BASE_H = 1024, 1536


def load_template(W, H):
    """加载 α 模板并按宽度缩放、锚定右下角。返回 (α 模板 float32, (x0, y0))。

    **框必须夹进画面**（2026-09-23 修，一类崩溃的根）：模板框按宽度等比缩放
    （1024 宽时 224×106），画面比它矮或比它窄时 `H - bh` / `W - bw` 变负，
    调用方拿负偏移去切片 → 真实形状不符，报
    `ValueError: could not broadcast input array from shape (166,350) into …`（postcheck）
    或 `cv2.error`（dewm_v10 / pick_wm）—— 一张畸变尺寸的图能把整条验收打崩。
    实测 1600×100 得 y0=-66、1×1 得 bh=0（`cv2.resize` 直接报错）。

    夹取在**所有声明画幅上都是恒等变换**（1024x1024 / 1280 / 1536 / 1792 / 1152x1536 /
    1536x864 / 1536x1024 实测 fits=YES），所以正常路径零行为变化；只有装不下时才退化成
    「贴边小框」——那种尺寸下模板与真实水印本就不匹配，检测会自然判「无水印」。
    """
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError(f"缺少 α 模板: {TEMPLATE_PATH}")
    with np.load(TEMPLATE_PATH) as z:
        tm, tbox = z["alpha"], z["box"]
    s = W / BASE_W
    bw = max(1, min(int(round((tbox[2] - tbox[0]) * s)), W))
    bh = max(1, min(int(round((tbox[3] - tbox[1]) * s)), H))
    a = cv2.resize(tm, (bw, bh), interpolation=cv2.INTER_LINEAR)
    return a.astype(np.float32), (W - bw, H - bh)


def imread_any(p):
    """支持中文/空格路径的读图。读不出来一律返回 None，**不从 OpenCV 抛异常**。

    `cv2.imdecode` 对一个**空缓冲区**（0 字节文件、读空的文件）会直接抛
    `cv2.error: (-215:Assertion failed) !buf.empty()`，而截断文件只是返回 None
    （读图失败时 OpenCV 会先打一行 WARN，再给 None）。同一个「读不出来」，
    两种文件给出两种行为——0 字节那种把调用方的 `if img is None` 兜底整条绕过，
    直接把 traceback 甩给用户。2026-09-23 实测：`dewm_v10.py zero.png` 崩栈 rc=1，
    而 `dewm_v10.py trunc.png` 走的是「skip (unreadable)」的正常分支。

    这里是全族共用的唯一读图口，把空缓冲显式收敛成 None，两种情形就同一条路了。
    """
    data = np.fromfile(p, dtype=np.uint8)
    if data.size == 0:
        return None
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


def note_guard(script, why, name):
    """守卫被触发时记一笔本地日志。集中一处，调用方只递三个字段。"""
    _log.note(script, ev="guard_redirect", why=why, name=name)


def _is_image_path(s):
    return os.path.splitext(s)[1].lower() in IMG_EXTS


def _real(p):
    """归一化路径：realpath 消除符号链接与 ./ 差异。

    macOS 上 /tmp 是 /private/tmp 的符号链接，只比 abspath 会让
    「--out /tmp/x」与「cwd=/private/tmp/x」判为不同路径 → 守卫失效（实测翻车）。
    """
    return os.path.realpath(os.path.abspath(p))


def _same_file(a, b):
    """判断两个路径是否指向同一个文件（含大小写与硬链接变体）。

    2026-09-08 实测两个绕过：① APFS 大小写不敏感，--out 传 `A.PNG` 而源是 `a.png`，
    字符串比较判不等 → 原图被覆盖；② 硬链接 alias.png 与源同 inode，同样绕过。
    因此存在时优先 samefile()（比 inode），否则退回 normcase 字符串比较。
    """
    ra, rb = _real(a), _real(b)
    try:
        if os.path.exists(ra) and os.path.exists(rb):
            return os.path.samefile(ra, rb)
    except OSError:
        pass
    return os.path.normcase(ra) == os.path.normcase(rb)


def _redirect(src, why, name=None):
    """把输出重定向到源目录下的 _clean/ 子目录。

    `name` 让调用方保留自己的命名约定（rmwm 的 `_nw`、dewm2 的 `_dewm2` 等）；
    不给时用源文件名。

    **必须在这里 makedirs**（2026-09-23 修）：重定向的目标目录 `_clean/` 通常还不存在，
    而所有调用方都假定「守卫返回的路径就是可直接写的」。原先只有 `safe_target` 的
    正常分支建目录，走重定向分支时不建 —— 于是 `dewm_v10.py a.png --out <源目录>`
    这类调用会以 `FileNotFoundError: .../_clean/a.png` 崩掉。既有测试只断言了
    警告文案，没断言文件真被写出来，所以这条路径一直没被覆盖（也是同行评审本次发现）。
    """
    d = os.path.dirname(os.path.abspath(src))
    target = os.path.join(d, CLEAN_SUBDIR, name or os.path.basename(src))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    # 记一笔「守卫被触发」。这是本地日志最该收集的信号之一：它直接回答
    # 「防覆盖这条守卫在真实使用里到底被触发过几次、是谁触发的」——
    # 触发频率高说明调用方的 --out 习惯或文档示例有问题，该改文档而不是只加守卫。
    note_guard("dewm_io", why.split("（")[0], os.path.basename(src))
    print(f"  ⚠️  {why}\n      → 已重定向到 {target}（原图保持不变）", file=sys.stderr)
    return target


def guard_target(src, target, suffix=""):
    """目标路径守卫：target 若与源文件是**同一个文件**，改写 `_clean/` 下的安全名。

    只做这一件事，不接管既有命名规则——批量脚本的输出名各有约定（rmwm 带 `_nw`、
    dewm2 带 `_dewm2`、rmwm_light 带 `_light`、dewm_imprint 保持原名），统一它们会
    改变已发布的行为；而「不能等于源」这条与命名无关。

    2026-09-23 实测（对抗性审查）：dewm2 / rmwm / rmwm_light / dewm_imprint 四处
    **各自手写** `makedirs(out) + join(out, basename)`，`--out` 传源目录时全部
    **静默覆盖原图**；`--out <符号链接>` 还能绕过 rmwm_light 里那条只比 `abspath`
    的旧守卫。守卫本来就在本模块（`_real` + `_same_file` 连大小写变体与硬链接都堵死了），
    只是**没人调用**——写在库里却没接线的守卫，等于没有守卫。
    """
    if _same_file(target, src):
        stem, ext = os.path.splitext(os.path.basename(target))
        if ext.lower() not in IMG_EXTS:
            ext = os.path.splitext(src)[1] or ".png"
        return _redirect(src, "输出路径与源文件是同一个文件"
                              "（含大小写/硬链接/符号链接变体），拒绝覆盖",
                         stem + suffix + ext)
    d = os.path.dirname(os.path.abspath(target))
    if d:
        os.makedirs(d, exist_ok=True)
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
        if _same_file(out_abs, src_abs):
            return _redirect(src, "--out 指向源文件本身（含大小写/硬链接变体），拒绝覆盖")
        os.makedirs(os.path.dirname(out_abs), exist_ok=True)
        return out_abs

    # --out 是目录
    out_dir = _real(out)
    target = os.path.join(out_dir, os.path.basename(src))
    if _same_file(target, src_abs):
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
