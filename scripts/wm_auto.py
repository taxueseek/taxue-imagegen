#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wm_auto — 水印自动识别与条件去除（出图后验收的第一道自动门）。

【为什么需要它】
水印存在与否**不由本技能决定**：同一个宿主可能自动加水印、可能不加，
也可能随会员状态变化（2026-09-12 用户说明）。因此既不能「总是去水印」
（干净图上动手 = 主动改坏画面），也不能「从不去水印」（带水印图直接交付）。
唯一正确的形态是：**先识别，命中才动手**。

【识别原理】
复用 audit_wm.estimate_residual 的加性扰动拟合：
    I = orig + k·a·(C - orig)        a 为已知 α 模板
最小二乘解出 k、残差与水印形状的吻合度 R²、残留灰度幅度 amp。

【为什么自动模式必须加 R² 闸门（本模块的核心设计）】
audit_wm.verdict() 只看 |amp|，那是**报告模式**的口径——它的产出是给人看的一行字，
判错代价是误导。本模块是**行动模式**，判错的代价是改坏一张已经画好的图。

2026-09-12 在本机 14 张真实图上实测，两组分离清晰：

    组别        n     amp 区间        k̂ 区间      R² 区间
    干净图      3    -0.79 ~ -0.69  -0.05 ~ -0.04  0.02 ~ 0.29
    带水印图   11      1.62 ~ 45.48  0.90 ~ 1.40   0.76 ~ 0.96

|amp| 单独用也能分开这两组，但 audit_wm 自己的文档就写明「amp 高但 R² 低往往
是高频纹理造成的误报」（马赛克/网点）。纹理图正是本技能的主力产出（类型 A
纸纹、类型 E 精灵图），所以自动门取 **amp 与 R² 双条件**：
R² 高才说明残差确实呈水印形状，而非画面本身的高频内容。

R² 闸门取 0.50：实测两组分别落在 ≤0.29 与 ≥0.76，0.50 居中且两侧留有余量。
样本 n=14，样本量不大；若后续实测出现 0.29<R²<0.76 的图，走 manual 分支交人判断，
不擅自扩大到自动处理。

【安全设计：改完必须复检，失败退回原图】
dewm 家族是**去不覆盖原图**（dewm_io 守卫，输出落 _clean/）。
本模块沿用该纪律，并在去水印后**重新识别一次输出**：
  1. 复检 CLEAN           → 接受，报告 before/after 两组数字
  2. 复检仍 DIRTY/SUSPECT → 判「本地反解未能解决」，保留原图并建议 pick_wm / 云端，
                            绝不把一个更差的结果当成品
原图在任何分支下都不被修改。

依赖：opencv-python-headless、numpy（与 dewm 家族一致，零模型，~0.5s/张）
"""

import _log
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import cv2  # noqa: E402
    import numpy as np  # noqa: E402
except ImportError as _e:          # 缺依赖时说人话，别甩 traceback（见 scripts/_env.py）
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import _env
    _env.die(_e, ['cv2', 'numpy'])

from audit_wm import AMP_CLEAN, AMP_DIRTY, estimate_residual, verdict  # noqa: E402
from dewm_io import imread_any  # noqa: E402

# 自动门：amp 与 R² 双条件（见模块文档的实测依据）
AUTO_AMP_THR = AMP_CLEAN   # |amp| < 1.0 判干净，直接放过
AUTO_R2_THR = 0.50         # 自动动手要求的最低形状吻合度

# 决策三分支
SKIP = "skip"        # 无可见水印 → 不动手
REMOVE = "remove"    # 有水印且形状可确认 → 自动去除
MANUAL = "manual"    # 存疑（SUSPECT 或 R² 不足）→ 交人/pick_wm，不擅自处理


def decide(amp, r2):
    """自动门决策（纯函数，不读图）——自动模式的安全核心，独立可测。

    返回 (action, reason)。三分支：
      SKIP    |amp| 低于可见阈 → 无可见水印，不动手
      REMOVE  形状确认（DIRTY + R² 达标）→ 自动去除
      MANUAL  其余（SUSPECT / 高 amp 但低 R²）→ 交人，不擅自改画面

    「高 amp 但低 R²」必须落 MANUAL：audit_wm 文档写明那是高频纹理的典型特征，
    而纹理正是本技能主力产出（类型 A 纸纹、类型 E 精灵图）。放过它 = 主动改坏干净图。
    """
    a = abs(amp)
    v = verdict(amp)
    if a < AUTO_AMP_THR:
        return SKIP, f"|amp|={a:.2f} < {AUTO_AMP_THR}（无可见水印）"
    if v == "DIRTY" and r2 >= AUTO_R2_THR:
        return REMOVE, f"|amp|={a:.2f} 且 R²={r2:.2f} ≥ {AUTO_R2_THR}（形状确认）"
    if r2 < AUTO_R2_THR:
        return MANUAL, (f"|amp|={a:.2f} 高但 R²={r2:.2f} < {AUTO_R2_THR}，"
                        f"疑为高频纹理误报，不自动动手")
    return MANUAL, f"|amp|={a:.2f} 落在 SUSPECT 区，交人判断 / pick_wm"


def detect(path):
    """识别单张图的水印状态。返回 dict（含 k/r2/amp/verdict/action/reason）。

    不修改任何文件，可安全地先探测再决定。
    """
    img = imread_any(path)
    if img is None:
        return {"ok": False, "path": path, "action": MANUAL,
                "reason": "读图失败", "k": 0.0, "r2": 0.0, "amp": 0.0,
                "verdict": "UNREADABLE"}
    res = estimate_residual(img)
    action, reason = decide(res["amp"], res["r2"])
    return {"ok": True, "path": path, "action": action, "reason": reason,
            "k": res["k"], "r2": res["r2"], "amp": res["amp"],
            "verdict": verdict(res["amp"])}


def remove_and_verify(path, out_path=None):
    """识别通过后执行去水印，并复检输出。原图永不被修改。

    返回 dict：
      attempted    是否执行了去水印
      out_path     输出路径（失败或跳过时为 None）
      before/after 两组 {amp, r2, verdict}
      verified     复检是否 CLEAN
      note         人可读的结论（含「不可解」「复检未通过」等真实状态）
    """
    det = detect(path)
    out = {"attempted": False, "out_path": None, "detected": det,
           "before": {"amp": det["amp"], "r2": det["r2"], "verdict": det["verdict"]},
           "after": None, "verified": None, "note": ""}

    if not det["ok"]:
        out["note"] = f"跳过：{det['reason']}"
        return out
    if det["action"] == SKIP:
        out["note"] = f"跳过去水印：{det['reason']}"
        return out
    if det["action"] == MANUAL:
        out["note"] = f"不自动去水印，交人判断：{det['reason']}"
        return out

    src = imread_any(path)
    if src is None:
        out["note"] = "跳过：读图失败"
        return out

    import importlib.util
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location("dewm_v10", os.path.join(here, "dewm_v10.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out_img, st = mod.remove_watermark(src)
    out["attempted"] = True

    if st.get("skipped"):
        # 「不可解」是正确结论而非缺陷（近白底上水印不可见也不可解，
        # 硬解只会把噪声放大 1/(1-α) 倍）。不写文件、不判失败。
        out["note"] = f"水印不可解，未改动：{st['skipped']}"
        return out

    if out_path is None:
        base, ext = os.path.splitext(path)
        out_path = f"{base}_dewm{ext or '.png'}"
    ok, buf = cv2.imencode(".png", out_img)
    if not ok:
        out["note"] = "编码失败，未写文件"
        return out
    buf.tofile(out_path)
    out["out_path"] = out_path

    # 复检：改完必须重新识别一次，否则「改没改对」无从得知
    re_det = detect(out_path)
    out["after"] = {"amp": re_det["amp"], "r2": re_det["r2"], "verdict": re_det["verdict"]}
    if re_det["action"] == SKIP:
        out["verified"] = True
        out["note"] = (f"去水印完成并复检通过：amp {det['amp']:.2f} → {re_det['amp']:.2f}，"
                       f"R² {det['r2']:.2f} → {re_det['r2']:.2f}")
    else:
        out["verified"] = False
        out["note"] = (f"本地反解未能解决：amp {det['amp']:.2f} → {re_det['amp']:.2f}，"
                       f"R² {det['r2']:.2f} → {re_det['r2']:.2f}；"
                       f"原图未改动，建议 pick_wm.py 四版选优或走云端 erase")
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(description="水印自动识别（默认只探测不动手）")
    ap.add_argument("images", nargs="+")
    ap.add_argument("--remove", action="store_true",
                    help="识别为 REMOVE 时执行去水印并复检（原图不动）")
    args = ap.parse_args()

    rc = 0
    for p in args.images:
        if not os.path.exists(p):
            print(f"[skip] 不存在: {p}")
            rc = 2
            continue
        if args.remove:
            r = remove_and_verify(p)
            d = r["detected"]
            print(f"{os.path.basename(p)}  {d['action']:>6}  {d['reason']}")
            if r["out_path"]:
                print(f"  → {r['out_path']}")
            if r["note"]:
                print(f"  {r['note']}")
        else:
            d = detect(p)
            print(f"{os.path.basename(p):<40} k̂={d['k']:>7.3f} R²={d['r2']:>6.3f} "
                  f"amp={d['amp']:>7.2f}  {d['verdict']:>7}  → {d['action']}")
            print(f"  {d['reason']}")
    sys.exit(rc)


if __name__ == "__main__":
    _log.run("wm_auto", main)