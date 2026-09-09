#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WorkBuddy 生图质量快检（配套 skill: taxue-imagegen）

指标：
  white%   白底/留白占比（min(RGB) > 240）
  near%    接近白占比（min(RGB) > 215）
  R-B      白区平均 R 减 B —— 泛黄指标，>=3 有前兆，>=6 已明显发黄
  sat      整体彩度：分子只计 max-min > 8 的像素，分母为全部像素
  top25    顶部区域（高度 4%–25%，中间 60% 宽）均色 + top_white% + R-B + noise（--top 开启）

用法：
  python3 measure.py a.png b.png c.png
  python3 measure.py --top poster.png          # 类型 A 海报：加测顶部留白
  python3 measure.py --grid /tmp/grid.png *.png
  python3 measure.py --cols 3 --tw 320 --grid /tmp/g.png *.png

判定阈值见 SKILL.md 第 4 节。
"""

import argparse
import os
import sys

try:
    from PIL import Image, ImageStat
except ImportError:
    sys.exit("需要 pillow：pip install pillow")


def metrics(path, with_top=False):
    im = Image.open(path).convert("RGB")
    W, H = im.size
    scale = 256.0 / W
    small = im.resize((256, max(1, int(H * scale))), Image.LANCZOS)
    # Pillow 14 起 getdata() 移除，优先用 get_flattened_data()
    try:
        px = list(small.get_flattened_data())  # type: ignore[attr-defined]
    except AttributeError:
        px = list(small.getdata())
    n = len(px)

    white = [p for p in px if min(p) > 240]
    near = [p for p in px if min(p) > 215]

    # 纸底基准：全图 min(RGB) 的中位数 ≈ 最大面积的纸色（2026-09-07 新增）。
    # 未涂布纸/浅灰底海报的白区恒在 215-235，原 white%(>240) 恒为 0 导致
    # 「留白够不够」「泛不泛黄」两项对纸底图完全失效——改用相对基准判定。
    mins = sorted(min(p) for p in px)
    base = float(mins[len(mins) // 2])

    # 留白区样本：相对纸底基准取值，纯白底与纸底图都适用
    lo_zone = max(215, base - 8)
    zone = [p for p in px if min(p) > lo_zone] or near or white
    wr = sum(p[0] for p in zone) / max(len(zone), 1)
    wg = sum(p[1] for p in zone) / max(len(zone), 1)
    wb = sum(p[2] for p in zone) / max(len(zone), 1)
    sat = sum(max(p) - min(p) for p in px if max(p) - min(p) > 8) / n

    row = {
        "file": os.path.basename(path),
        "size": f"{W}x{H}",
        "base": base,
        "white%": len(white) / n * 100,
        "paper%": sum(1 for p in px if min(p) > base - 8) / n * 100,
        "near%": len(near) / n * 100,
        "R-B": wr - wb,
        "sat": sat,
    }

    if with_top:
        top = im.crop((int(W * 0.20), int(H * 0.04), int(W * 0.80), int(H * 0.25)))
        st = ImageStat.Stat(top)
        r, g, b = st.mean
        row["top_R"] = r
        row["top_G"] = g
        row["top_B"] = b
        row["top_R-B"] = r - b
        row["top_noise"] = sum(st.stddev) / 3
        # 2026-09-09 新增：把 top_noise 拆成「高频织纹」与「低频结构」两层。
        # 实测 13/13 张真实海报 top_noise 全部 ≥29（阈值 6 全灭，包括用户已验收的
        # 成品 charming-girl-poster.png = 50.1），阈值不具区分力；而纸纹/网点本身
        # 就会把 std 顶上去。高斯模糊 σ=9 滤掉织纹后剩下的低频 std 才反映「有没有
        # 大块实体入侵」，top_dark% 反映「内容覆盖了多少面积」。
        try:
            from PIL import ImageFilter
            lowfreq = sum(ImageStat.Stat(top.filter(ImageFilter.GaussianBlur(9))).stddev) / 3
        except Exception:  # noqa: BLE001
            lowfreq = row["top_noise"]
        row["top_lf_std"] = lowfreq
        try:
            tpx_all = list(top.get_flattened_data())  # type: ignore[attr-defined]
        except AttributeError:
            tpx_all = list(top.getdata())
        row["top_dark%"] = sum(1 for p in tpx_all if min(p) < 150) / max(len(tpx_all), 1) * 100
        # 顶部是否真的「空」：与纸底基准的偏离量（绝对比值对纸底图无意义）
        row["top_dev"] = abs((r + g + b) / 3 - base)
        try:
            tpx = list(top.get_flattened_data())  # type: ignore[attr-defined]
        except AttributeError:
            tpx = list(top.getdata())
        row["top_white%"] = sum(1 for p in tpx if min(p) > 240) / max(len(tpx), 1) * 100
        # 纸底海报的相对口径：与全图纸底基准一致（绝对 240 对纸底图恒为 0，2026-09-07）
        t_lo = max(215, base - 8)
        row["top_zone%"] = sum(1 for p in tpx if min(p) > t_lo) / max(len(tpx), 1) * 100

    return im, row


def build_grid(imgs, out, cols=3, tw=320, gap=10):
    thumbs = []
    maxh = 0
    for _, im in imgs:
        w = tw
        h = max(1, int(tw * im.size[1] / im.size[0]))
        thumbs.append(im.resize((w, h), Image.LANCZOS))
        maxh = max(maxh, h)
    rows = (len(thumbs) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * tw + (cols + 1) * gap, rows * maxh + (rows + 1) * gap), (255, 255, 255))
    for i, t in enumerate(thumbs):
        x = gap + (i % cols) * (tw + gap)
        y = gap + (i // cols) * (maxh + gap)
        canvas.paste(t, (x, y))
    canvas.save(out)
    return out, canvas.size


def main():
    ap = argparse.ArgumentParser(description="WorkBuddy 生图质量快检")
    ap.add_argument("images", nargs="+", help="图片路径")
    ap.add_argument("--top", action="store_true", help="加测顶部 25%% 留白（类型 A 海报用）")
    ap.add_argument("--grid", metavar="OUT", help="同时输出一张拼图")
    ap.add_argument("--cols", type=int, default=3, help="拼图列数，默认 3")
    ap.add_argument("--tw", type=int, default=320, help="拼图缩略宽度，默认 320")
    args = ap.parse_args()

    rows = []
    imgs = []
    for p in args.images:
        if not os.path.exists(p):
            print(f"[skip] 不存在: {p}")
            continue
        im, row = metrics(p, args.top)
        rows.append(row)
        imgs.append((p, im))

    if not rows:
        sys.exit("没有可处理的图片")

    cols = ["file", "size", "base", "white%", "paper%", "near%", "R-B", "sat"]
    if args.top:
        cols += ["top_dev", "top_noise", "top_lf_std", "top_dark%", "top_R-B",
                 "top_white%", "top_zone%"]

    name_w = min(max(len(r["file"]) for r in rows) + 3, 50)
    widths = {"file": max(name_w, 6)}
    for c in cols:
        if c in widths:
            continue
        w = len(c) + 1
        for row in rows:
            v = row[c]
            v = f"{v:.1f}" if isinstance(v, float) else str(v)
            w = max(w, len(v) + 2)
        widths[c] = w

    print("".join(c.rjust(widths[c]) for c in cols))
    for row in rows:
        cells = []
        for c in cols:
            v = row[c]
            if isinstance(v, float):
                v = f"{v:.1f}"
            elif isinstance(v, str) and len(v) > name_w - 2:
                cut = max(3, name_w - 3)
                v = "…" + v[-cut:]
            cells.append(str(v).rjust(widths[c]))
        print("".join(cells))

    print()
    warn = []
    for idx, row in enumerate(rows, 1):
        # 2026-09-07 修复：原按尾部 26 字符截断，中文文件名被切成不可辨识的残字
        stem = os.path.splitext(row["file"])[0]
        tag = f"#{idx} {stem[:18]}"
        if row["R-B"] >= 3:
            warn.append(f"⚠️  {tag} 泛黄前兆 R-B={row['R-B']:.1f}（阈值 <3）")
        if args.top:
            if row["top_R-B"] >= 3:
                warn.append(f"⚠️  {tag} 顶部留白发黄 top_R-B={row['top_R-B']:.1f}")
            # top_noise 只作诊断（2026-09-09）：纸纹/网点使真实海报 std 恒 ≥29，
            # 阈值 6 无区分力。真正判「顶部被画脏」看 lf_std（去织纹低频结构）与 dark%。
            if row.get("top_dark%", 0) >= 40:
                warn.append(
                    f"⚠️  {tag} 顶部 40%+ 区域是实体内容 top_dark%={row['top_dark%']:.1f}"
                    f"（lf_std={row.get('top_lf_std', 0):.1f}，阈值 <40）"
                )
            if row["top_dev"] >= 12:
                warn.append(
                    f"⚠️  {tag} 顶部被内容侵入 top_dev={row['top_dev']:.1f}"
                    f"（顶部均值偏离纸底基准 {row['base']:.0f}，阈值 <12）"
                )
        if row["sat"] > 70:
            warn.append(f"⚠️  {tag} 饱和度偏高 sat={row['sat']:.1f}")
    print("\n".join(warn) if warn else "✅ 全部指标在阈值内")

    if args.grid and imgs:
        out, size = build_grid(imgs, args.grid, args.cols, args.tw)
        print(f"\ngrid -> {out}  {size[0]}x{size[1]}")


if __name__ == "__main__":
    main()
