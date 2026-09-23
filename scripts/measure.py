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

import _log
import argparse
import os
import sys

try:
    from PIL import Image, ImageChops, ImageStat
except ImportError as _e:          # 缺依赖时说人话，别甩 traceback（见 scripts/_env.py）
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import _env
    _env.die(_e, ['PIL'])


def _minmax(im):
    """min 通道图 / max 通道图 —— 等价于逐像素 min(p)/max(p)，但在 PIL 的 C 层完成。"""
    r, g, b = im.split()
    return (ImageChops.darker(ImageChops.darker(r, g), b),
            ImageChops.lighter(ImageChops.lighter(r, g), b))


def _count_gt(hist, t):
    """直方图里取值 **> t** 的像素数。

    `t + 1` 两端都要夹住：t=255 时越界（应为 0），t 为负时 Python 会把它当
    **负索引**，于是「求和最后几档」变成一个看着正常的错数——纸底极暗（base<8）
    时 `base-8` 就是负数，实测一张图因此把 paper% 从 0.2% 报成 100%。
    """
    return sum(hist[max(0, t + 1):]) if t + 1 <= 255 else 0


def _count_lt(hist, t):
    """直方图里取值 **< t** 的像素数。"""
    return sum(hist[:max(0, t)])


def _median_of_hist(hist, n):
    """直方图的中位数（最近秩），等价于 `sorted(values)[n // 2]`。"""
    target, cum = n // 2, 0
    for v, c in enumerate(hist):
        cum += c
        if cum > target:
            return float(v)
    return 0.0


def metrics(path, with_top=False):
    """量测一张图。返回 (PIL 图, 指标 dict)。

    2026-09-23：改用 PIL 的 C 层算子替代逐像素 Python 循环。
    原实现把 256 宽的缩略图展开成 9.8 万个 RGB 三元组，再对同一批像素做十几趟
    `min(p)`/`max(p)`（white% / near% / base / paper% / zone 三通道 / sat 各一趟，
    顶部区还有两趟重复的 `get_flattened_data()`），实测 1024×1536 上单次 126 ms ——
    这是 postcheck 默认路径里最大的一笔纯 Python 开销。
    现在 min/max 通道由 `ImageChops.darker/lighter` 给出，分布由直方图给出，
    带掩膜的均值由 `ImageStat.Stat(im, mask)` 给出，全部在 C 层完成。
    在**同一批 304 张真实成品**上与原实现逐字段比对：最大绝对误差 0.0（逐位一致），
    耗时 126 ms → 34 ms。等价性由 `tests/test_postcheck.py` 钉住。
    """
    im = Image.open(path).convert("RGB")
    W, H = im.size
    scale = 256.0 / W
    small = im.resize((256, max(1, int(H * scale))), Image.LANCZOS)
    n = small.size[0] * small.size[1]

    mn, mx = _minmax(small)
    hmin = mn.histogram()

    white_n = _count_gt(hmin, 240)
    near_n = _count_gt(hmin, 215)

    # 纸底基准：全图 min(RGB) 的中位数 ≈ 最大面积的纸色（2026-09-07 新增）。
    # 未涂布纸/浅灰底海报的白区恒在 215-235，原 white%(>240) 恒为 0 导致
    # 「留白够不够」「泛不泛黄」两项对纸底图完全失效——改用相对基准判定。
    base = _median_of_hist(hmin, n)

    # 留白区样本：相对纸底基准取值，纯白底与纸底图都适用。
    # 原式 `zone = [...] or near or white` 是「留白区为空就依次退回 near、white」；
    # white ⊆ near，所以退回实际只有 zone → near 两级，末级只是兜底写法。
    lo_zone = max(215, base - 8)
    if _count_gt(hmin, int(lo_zone)):
        thr = lo_zone
    elif near_n:
        thr = 215
    elif white_n:
        thr = 240
    else:
        thr = None
    if thr is not None:
        wr, wg, wb = ImageStat.Stat(small, mn.point(lambda v: 255 if v > thr else 0)).mean
    else:
        wr = wg = wb = 0.0

    # sat：max-min > 8 的像素，其 (max-min) 之和 ÷ 全图像素数。
    # 差值直方图里 Σ d·count[d]（d>8）与逐像素 sum 等价。
    hdiff = ImageChops.subtract(mx, mn).histogram()
    sat = sum(d * c for d, c in enumerate(hdiff) if d > 8) / n

    row = {
        "file": os.path.basename(path),
        "size": f"{W}x{H}",
        "base": base,
        "white%": white_n / n * 100,
        "paper%": _count_gt(hmin, int(base - 8)) / n * 100,
        "near%": near_n / n * 100,
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
        # 顶部四个计数全部来自 min 通道的直方图，一次算完——
        # 原实现对同一批顶部像素 `get_flattened_data()` 了两遍、又各扫一遍。
        tmn, _ = _minmax(top)
        th = tmn.histogram()
        tn = max(top.size[0] * top.size[1], 1)
        row["top_dark%"] = _count_lt(th, 150) / tn * 100
        # 顶部是否真的「空」：与纸底基准的偏离量（绝对比值对纸底图无意义）
        row["top_dev"] = abs((r + g + b) / 3 - base)
        row["top_white%"] = _count_gt(th, 240) / tn * 100
        # 纸底海报的相对口径：与全图纸底基准一致（绝对 240 对纸底图恒为 0，2026-09-07）
        t_lo = max(215, base - 8)
        row["top_zone%"] = _count_gt(th, int(t_lo)) / tn * 100

    return im, row


def grid_metrics(path, im=None, bg_tol=26, gap_frac=0.55, min_band=0.04):
    """类型 E 多格排版的网格结构量测（校验「声明 vs 产出」，不引入新阈值）。

    为什么需要它：类型 E 的硬要求写在 multigrid-layout.md §三——
      每格等比例、尺寸一致、间距可辨、格数等于 prompt 声明值。
    这些要求此前只在 **prompt 侧**被 fill_meta 校验（格数与清单条数一致），
    **图像侧从未验过**：模型完全可能把 4×4 画成 3×4、把格与格糊成一片、
    或让某一格尺寸跑偏。本函数补上这一环。

    `im` 可以传一张已打开并 convert("RGB") 过的图（`metrics()` 就会返回它）。
    2026-09-23 加：类型 E 的验收路径原先对同一张图**解码两次**（metrics 一次、
    这里一次，4K 图各约 130ms），而调用方 postcheck 手里一直握着那张图。

    做法：先取四边环带中位数当背景色（多格模板的格间是白/纯色净空），
    再按行、按列统计「接近背景的像素占比」，占比超 gap_frac 的行/列判为格间净空，
    被净空切开的连续段即格子带。返回格数、行列数、格宽高一致性。

    返回 dict：
      ok            是否成功解析
      cols, rows, cells        列数 / 行数 / 格数
      band_w, band_h           格子带宽度/高度列表（像素）
      uniform       格宽高一致性：min/max 比值，1.0 为完全一致
      gap_px        格间净空的典型宽度（像素，0 = 无净空/无缝）
      note          人可读说明（含解析失败原因）

    注意：本函数是**提示性量测**，不是硬判定。间隔极细（「无缝隙、边框像素对齐」
    这类 E 变体）或格内本身大片接近背景色时，连通性会被误判——所以调用方只在
    给了 --expect-cells 时才把它当判据，且不匹配时输出诊断而非直接判 blocker。
    """
    try:
        from PIL import Image
    except ImportError:
        return {"ok": False, "note": "需要 pillow"}

    if im is None:
        im = Image.open(path).convert("RGB")
    W, H = im.size
    scale = 256.0 / W
    small = im.resize((256, max(1, int(H * scale))), Image.LANCZOS)
    try:
        px = list(small.get_flattened_data())  # type: ignore[attr-defined]
    except AttributeError:
        px = list(small.getdata())
    w, h = small.size

    def lum(p):
        return (p[0] + p[1] + p[2]) / 3.0

    # 背景色 = 四边环带的中位数（多格模板的格间净空色）
    ring = []
    for x in range(w):
        ring.append(px[x])
        ring.append(px[(h - 1) * w + x])
    for y in range(h):
        ring.append(px[y * w])
        ring.append(px[y * w + w - 1])
    ring_l = sorted(lum(p) for p in ring)
    bg = ring_l[len(ring_l) // 2]

    is_bg = [abs(lum(p) - bg) <= bg_tol for p in px]

    def bands(axis_len, cross_len, idx_of):
        """返回 (格子带列表, 净空布尔列表)。cross_len = 另一轴的像素数。"""
        gaps = []
        for i in range(axis_len):
            n = sum(1 for j in range(cross_len) if is_bg[idx_of(i, j)])
            gaps.append(n / cross_len >= gap_frac)
        out, run = [], None
        for i, g in enumerate(gaps):
            if g:
                if run is not None:
                    out.append((run, i - run))
                    run = None
            else:
                if run is None:
                    run = i
        if run is not None:
            out.append((run, axis_len - run))
        thr = max(1, int(axis_len * min_band))
        kept = [(s, L) for s, L in out if L >= thr]
        return kept, gaps

    col_bands, col_gaps = bands(w, h, lambda i, j: j * w + i)
    row_bands, row_gaps = bands(h, w, lambda i, j: i * w + j)

    if not col_bands or not row_bands:
        return {"ok": False, "note": "未解析出网格（成片单格或背景色不占多数）",
                "cols": 0, "rows": 0, "cells": 0, "uniform": 0.0, "gap_px": 0}

    ws = [L for _, L in col_bands]
    hs = [L for _, L in row_bands]
    band_uni = min(min(ws) / max(ws), min(hs) / max(hs))

    # 逐格内容外接框：E 的硬规则是「每格等比例、尺寸一致」，只量行/列带不够——
    # 单格内缩不会改变带的边界（2026-09-12 实测：某格窄 60px，带级 uniform 仍为 1.0）。
    # 因此在每个「行带 × 列带」交叠矩形内，再向内扫出实际内容框，量真正的格尺寸。
    def content_box(x0, y0, x1, y1):
        bx0, by0, bx1, by1 = None, None, None, None
        for y in range(y0, y1):
            for x in range(x0, x1):
                if not is_bg[y * w + x]:
                    if bx0 is None or x < bx0:
                        bx0 = x
                    if bx1 is None or x > bx1:
                        bx1 = x
                    if by0 is None or y < by0:
                        by0 = y
                    if by1 is None or y > by1:
                        by1 = y
        if bx0 is None:
            return None
        return (bx0, by0, bx1 - bx0 + 1, by1 - by0 + 1)

    cell_w, cell_h = [], []
    for rs, rL in row_bands:
        for cs, cL in col_bands:
            # 向内各让 1px，避免把相邻格的边框算进本格
            box = content_box(cs + 1, rs + 1, cs + cL - 1, rs + rL - 1)
            if box:
                cell_w.append(box[2] * W / float(w))
                cell_h.append(box[3] * H / float(h))

    cell_uni = None
    if len(cell_w) >= 2 and max(cell_w) > 0 and max(cell_h) > 0:
        cell_uni = round(min(min(cell_w) / max(cell_w),
                             min(cell_h) / max(cell_h)), 3)

    def typical_gap(g):
        runs, cur = [], 0
        for v in g:
            if v:
                cur += 1
            elif cur:
                runs.append(cur)
                cur = 0
        if cur:
            runs.append(cur)
        inner = runs[1:-1] if len(runs) > 2 else runs
        return int(sum(inner) / len(inner) * (W / float(w))) if inner else 0

    gap_px = min(typical_gap(col_gaps), typical_gap(row_gaps))

    cells_n = len(col_bands) * len(row_bands)

    # 自洽性闸门：`ok` 的含义收窄为「**确实找到了一张多格网格**」（2026-09-23 修）。
    # 两条必要条件，都来自真实产出上的实测：
    #   ① 量得出格间净空（gap_px > 0）。背景色取「四边环带的中位数」，这条前提在
    #      **没有外边距的拼版**上不成立——环带里装的就是各格内容，中位色因此落在内容色上，
    #      `is_bg` 把大片内容判成背景，行列切分崩坏。实测一张真 3×3 接触表
    #      （1536²、九张不同的图）被报成 `ok=True, cols=1, rows=2, cells=2, gap_px=0`。
    #   ② 至少两格。读到 1 格的含义是「没找到网格结构」，不是「找到了一张 1 格的网格」——
    #      实测齐边 3×3（有外边距、格间无缝）被报成 `cells=1`，同样是自信的错答案。
    # 为什么非收不可：`ok=True` 在下游是**硬判据**——postcheck 见到 `--expect-cells` 不匹配
    # 就判 `[cell_count]` blocker，而 blocker =「允许一次定向重生」＝再扣 5–10 积分。
    # 这与坑 27（top_noise 13/13 全灭）同类：**提示性量测被当成硬判据**。
    # 方向上只会减少假 blocker，不会新增（最坏退回「请目检格数」）。
    #
    # 已知局限（本轮不修，已登记 CHANGELOG）：缩略到 256 宽后**极细的缝会消失**——
    # 实测 4px 缝的 3×3 被读成 4 格。缝宽小于原图宽度约 1% 时，本函数数不准格数。
    if gap_px <= 0 or cells_n < 2:
        why = ("未量出格间净空（无外边距拼版 / 无缝变体？）" if gap_px <= 0
               else "只读到单格，没找到网格结构")
        return {"ok": False, "note": f"{why}·解析不可信，请目检格数",
                "cols": len(col_bands), "rows": len(row_bands),
                "cells": cells_n, "uniform": round(band_uni, 3),
                "gap_px": 0}

    return {
        "ok": True,
        "cols": len(col_bands), "rows": len(row_bands),
        "cells": len(col_bands) * len(row_bands),
        "band_w": [int(L * W / float(w)) for L in ws],
        "band_h": [int(L * H / float(h)) for L in hs],
        "uniform": round(band_uni, 3),
        "cell_uniform": cell_uni,
        "cell_w": [int(v) for v in cell_w],
        "cell_h": [int(v) for v in cell_h],
        "gap_px": gap_px,
        "note": "",
    }


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
        sys.exit(2)   # 2 = 用法/输入错误（1 在本技能约定里是「blocker」，不要混用）

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
    _log.run("measure", main)
