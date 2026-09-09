#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""postcheck — 出图后一次调用完成：量测 + 目检裁片 + 去水印 + 运行记账。

第一性原理：agent 循环里每个命令 = 一次模型往返（2-10s + tokens）。
v1.5.0 前验一张图要跑 measure、dewm、手动裁剪放大、人工记账 3-4 次调用；
本脚本合并为一。脚本实测 <1s，省的是往返轮次与目检准备时间。

用法：
  python3 postcheck.py a.png --track A --top
  python3 postcheck.py a.png --track A --top --dewm --text ok --note 'v5.4 首张'
  python3 postcheck.py a.png b.png --track B

每张图自动：
  1. 量测（复用 measure.metrics；--top 加测顶部留白，类型 A 必用）
  2. 导出底部文字带 2x 放大裁片 _textband.png（类型 A，目检逐字用；替代手动裁剪）
  3. --dewm 时执行 alpha 反解去水印，输出 _dewm.png（**不自动复测量去水印结果**：
     指标只取自原图。后处理过的图必须重跑一次 postcheck 才算通过，见 SKILL.md §6 纪律 4）
  4. 追加一行到 logs/runs.csv（时间/指标/文字判定/verdict），形成模板调优的数据反馈闭环

verdict 三档自动判定（与 SKILL.md §3 评审卡一致）：
  blocker  量测警告或 --text bad → 允许一次定向重生
  pending  指标在阈值内但文字未核对（未传 --text）→ 不得计 pass
  pass     指标在阈值内 且 文字逐字无误
退出码：0=pass，1=blocker，3=pending。
"""

import argparse
import csv
import os
import sys
from datetime import datetime

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "logs", "runs.csv")

CSV_COLS = ["ts", "file", "track", "size", "base", "white_pct", "paper_pct",
            "R-B", "sat", "top_noise", "top_dev", "text", "verdict", "note"]


def load_sibling(name, attr):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), os.path.join(HERE, name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, attr)


def measure_warnings(row, track, with_top):
    """与 SKILL.md §5 阈值一致的自动判定。返回警告列表。

    各类型适用阈值不同（2026-09-08 补齐 C/D）：
      A 海报   R-B / 顶部留白三项
      B 群像   R-B / 白底 30–65% / 饱和度 ≤70
      C 包装   灰底棚拍，R-B 阈值不适用（references/packaging-editorial.md §三 规则 8）
      D 分镜   叙事性暖色豁免，R-B 阈值不适用（references/storyboard.md §五）
    """
    warns = []
    if track in ("A", "B") and row["R-B"] >= 3:
        warns.append(f"泛黄前兆 R-B={row['R-B']:.1f}")
    if track == "B":
        if not (30 <= row["white%"] <= 65):
            warns.append(f"白底 {row['white%']:.0f}% 越界（30–65）")
        if row["sat"] > 70:
            warns.append(f"饱和度 {row['sat']:.1f} 偏高")
    if with_top and track == "A":
        if row.get("top_R-B", 0) >= 3:
            warns.append(f"顶部留白发黄 top_R-B={row['top_R-B']:.1f}")
        # top_noise 不再作为 blocker（2026-09-09 实测修正）：
        # 13/13 张真实海报 top_noise 全部 ≥29（阈值 6 全灭，连用户已验收的
        # charming-girl-poster.png=50.1 也拦），纸纹/网点/网点化网点本身就把 std
        # 顶上去 —— 阈值不具区分力，只会制造假 blocker（postcheck 判 blocker =
        # 允许一次定向重生 = 再扣 5-10 积分）。降级为诊断值打印，不参与判定。
        if row.get("top_dev", 0) >= 12:
            warns.append(f"顶部被内容侵入 top_dev={row['top_dev']:.1f}")
    return warns


def export_textband(path, im):
    """底部文字带 2x 放大裁片（类型 A 目检逐字用）。"""
    W, H = im.size
    y0 = int(H * 0.78)
    band = im.crop((0, y0, W, H))
    band = band.resize((W * 2, (H - y0) * 2), Image.LANCZOS)
    out = os.path.splitext(path)[0] + "_textband.png"
    band.save(out)
    return out


def append_log(row, track, text, verdict, note, no_log=False):
    """追加一行运行记录。no_log=True 时跳过（跑测试/验证不污染生产记账）。"""
    if no_log:
        return
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    new = not os.path.exists(LOG_PATH)
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(CSV_COLS)
        w.writerow([
            row.get("ts", ""), row["file"], track, row["size"],
            f"{row['base']:.0f}", f"{row['white%']:.1f}", f"{row['paper%']:.1f}",
            f"{row['R-B']:.1f}", f"{row['sat']:.1f}",
            f"{row.get('top_noise', 0):.1f}" if "top_noise" in row else "",
            f"{row.get('top_dev', 0):.1f}" if "top_dev" in row else "",
            text, verdict, note,
        ])


def process(path, args):
    metrics = load_sibling("measure.py", "metrics")
    im, row = metrics(path, args.top and args.track == "A")
    row["ts"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    warns = measure_warnings(row, args.track, args.top and args.track == "A")

    # 文字带裁片：A 有文字带必导；C 有品牌堆叠字，同样需要目检
    band = None
    if args.track in ("A", "C"):
        band = export_textband(path, im)

    dewm_out = None
    dewm_tag = ""
    if args.dewm:
        # v1.8 起默认 v10（v9 + 平底自适应融合）：平色底上 v9 会留肉眼可见的
        # 字形轮廓，而 audit 的 amp 判不出来（形状失配 → R²≈0 被当纹理放过）。
        remove_watermark = load_sibling("dewm_v10.py", "remove_watermark")
        import numpy as np
        import cv2
        data = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            warns.append("dewm: 读图失败")
        else:
            out_img, st = remove_watermark(img)
            if st.get("skipped"):
                # 「不可解」是正确结论而非缺陷：近白底上水印不可见也不可解，
                # 硬解只会引入噪声。记 info 不记 blocker（2026-09-08）。
                print(f"  ℹ️ 去水印跳过: {st['skipped']}")
            else:
                dewm_out = os.path.splitext(path)[0] + "_dewm.png"
                dewm_tag = (f"k={st['k']:.2f} r2={st['r2']:.2f} "
                            f"flat={'Y' if st.get('flat') else 'N'}"
                            f"(std={st.get('flat_std', 0):.1f})")
                ok, buf = cv2.imencode(".png", out_img)
                if ok:
                    buf.tofile(dewm_out)

    # verdict 三档（对齐 SKILL.md §3 评审卡）：
    #   blocker    量测越界 / 文字判 bad  → 允许一次定向重生
    #   pending    文字未核对（unverified）→ 不得计 pass，需逐字目检后回填
    #   pass       指标在阈值内 且 文字逐字无误
    text = args.text or "unverified"
    if warns or text == "bad":
        verdict = "blocker"
    elif text == "unverified":
        verdict = "pending"
    else:
        verdict = "pass"
    append_log(row, args.track, text, verdict, args.note or "", no_log=args.no_log)

    name = row["file"]
    print(f"{name}  white%={row['white%']:.1f} paper%={row['paper%']:.1f} "
          f"R-B={row['R-B']:.1f} sat={row['sat']:.1f} base={row['base']:.0f}")
    if "top_noise" in row:
        print(f"  top: dev={row['top_dev']:.1f} noise={row['top_noise']:.1f} "
              f"lf_std={row.get('top_lf_std', 0):.1f} dark%={row.get('top_dark%', 0):.1f} "
              f"R-B={row['top_R-B']:.1f} zone%={row['top_zone%']:.1f}")
        print("       (top_noise 仅诊断：纸纹/网点会把 std 顶到 30+，不参与 blocker 判定；"
              "判顶部是否真被画脏看 lf_std/dark% 并目检裁片)")
    if band:
        print(f"  目检裁片(2x): {band}")
    if dewm_out:
        print(f"  去水印(v10): {dewm_out}  {dewm_tag}")
    for wmsg in warns:
        print(f"  ⚠️ {wmsg}")
    print(f"  verdict={verdict} text={text} → runs.csv")
    return verdict


def main():
    ap = argparse.ArgumentParser(description="出图后一次调用：量测+裁片+去水印+记账")
    ap.add_argument("images", nargs="+")
    ap.add_argument("--track", choices=["A", "B", "C", "D"], default="A",
                    help="A=竖版概念海报（默认），B=手绘群像，C=包装 Mockup，D=叙事分镜")
    ap.add_argument("--top", action="store_true", help="加测顶部留白（类型 A 必用）")
    ap.add_argument("--dewm", action="store_true", help="顺带 alpha 反解去水印，输出 _dewm.png")
    ap.add_argument("--text", choices=["ok", "bad"], help="文案逐字目检结论（无视觉时先留空，明示用户核对）")
    ap.add_argument("--note", help="备注（模板版本、场景等）")
    ap.add_argument("--no-log", action="store_true",
                    help="不写 runs.csv（跑测试/验证时用，避免污染生产记账）")
    args = ap.parse_args()

    verdicts = []
    for p in args.images:
        if not os.path.exists(p):
            print(f"[skip] 不存在: {p}")
            continue
        verdicts.append(process(p, args))

    if not verdicts:
        sys.exit(2)
    if any(v == "blocker" for v in verdicts):
        print("\n❌ blocker —— 按三档评审卡：才允许一次定向重生，只改一项")
        sys.exit(1)
    if any(v == "pending" for v in verdicts):
        print("\n⏳ pending —— 指标在阈值内，但文字尚未逐字核对；"
              "目检后回填 --text ok/bad，pending 不得当作通过")
        sys.exit(3)
    print("\n✅ pass（指标在阈值内 + 文字逐字无误）")


if __name__ == "__main__":
    main()
