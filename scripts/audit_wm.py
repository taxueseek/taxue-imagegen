#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_wm — 去水印质量审计：残留幅度 + 结构损伤（前者无需原图，后者需参照图）。

【为什么需要它】
「水印去干净了」只是质量的一半。另一半是「画面有没有被改坏」——坑 28 实测：
pick_wm 选的 v7 整区 inpaint 把水印抹成 0 残留（amp -0.20 判 CLEAN），
却把水印压着的黑色图形边缘整块啃掉。**只测残留的判据必然放过这种破坏。**

本模块提供两个互补的度量：

  ── ① estimate_residual（无需原图）────────────────────────────
  水印是加性扰动  I = orig + k·a·(C - orig)，a 为已知 α 模板。
  用 inpaint 估出「底下应该是什么」bg ≈ orig，则残差
      r = I - bg  ≈  k · a · (C - bg)
  对核心像素最小二乘拟合 k，即可量化残留：
      k̂      残留不透明度（0 = 无残留）
      amp    k̂·mean(a·(C-bg))，残留的平均灰度幅度（0-255 量级，人眼可感阈 ≈1.5）
      R²     残差与水印形状的吻合度（高 = 确实是水印形状而非纹理噪声）

  amp 高 **且** R² 高 → 真的有水印残留；
  amp 高但 R² 低 → 多半是高频纹理（马赛克/网点）造成的误报。

  ── ② estimate_damage（需「带水印原图」当参照）────────────────
  度量候选结果「结构有没有被改坏」，返回可直接与 |amp| 相加的 penalty。

  为什么要另立判据：v7 整区 inpaint 能把残留抹成 0（amp -0.20 判 CLEAN），
  但笔画底下的画面结构被邻域填充替换掉了 —— **残留分对这个失效模式完全失明**。

  做法：**以同族反解为结构参照**。v8/v9 是逐像素映射 out=(I-αC)/(1-α)，
  且**共用同一套 k̂ 最小二乘拟合口径**，在 α=0 处恒等于输入、在 α>0 处按已知模型
  还原，因此**能保留笔画底下的真实结构**（这是数学保证，不是经验）。
  参照 = 族内残留最低的那一版。

      dev = mean|灰度(候选) − 灰度(参照)|  在笔画核心区（α>0.15）
      penalty = clamp(dev − DEV_FLOOR, 0, DEV_CAP)

  实测分离度（dev，灰度级）：
      反例 v7 破坏 12.5 ／ 5 张已换修图 v7 21.7–29.7 ／ v8 与参照自身 0.0
      **纯平底 v7 仅 0.93**（平底上没有结构可毁，两种做法结果都是平的 → 不罚）
  减 DEV_FLOOR 是「低于该偏离不算结构损伤」的门限；封顶 DEV_CAP 保证反解族
  全军覆没（残留 ≥12）时仍轮到 v7 兜底。

  ⚠️ **族内必须同口径**（2026-09-12 第三次迭代）。曾把固定 k≡1 的 v6 与自适应拟合
  k̂ 的 v8/v9 混作一族：03_labor 上 v6 的「残留最低」被选为参照，反过来把目检正确
  的 v8/v9 判成偏离 13.6 / 损伤 10.6，最终选中一个发浑的版本。深色区两个 k 的差会被
  1/(1-α) 放大成十几灰度级——那是口径差，不是结构损伤。故 MODEL_FAMILY = (v8, v9)。

  ⚠️ 也试过改用 R²（拟合优度）挑参照，**同样被证伪**：v6 保守（k 小）→ 残留多、且残留
  的形状就是纯水印 → R² 反而最高（01_balance 0.85 / 05_index 0.86 / 07_prayer 0.88），
  拿它当参照会把 amp 仅 0.01–0.04 的正确候选罚掉。**R² 高只说明「残留像水印」，不说明
  「残留少」**——两个问题必须分开看。

  ⚠️ 曾经用过「水印空白带（α<0.02）被改了多少」当判据，**已被证伪并弃用**：
  把空白带向内腐蚀 2px 后，所有已知破坏样本的分数**全部归零**——说明它测到的
  只是紧贴笔画的抗锯齿边缘（任何去水印都会重建那圈像素），真正的破坏发生在
  **笔画内部**，空白带根本覆盖不到。看到「漂亮分离度」也要做腐蚀/置换实验验伪。

  ⚠️ **适用边界（2026-09-12 实测确认）**：本判据只在**同一次运行、同一张带水印原图**
  产出的多个候选之间比较时有效（即 pick_wm 的场景）。拿它去审计**历史产物**会系统性误报——
  不同代算法（v10 平底融合 / rmwm 系列 / 早期 dewm）在笔画区的输出本就与 v8/v9 不同，
  实测 4 张被判「偏离 16-34」的存量图**目视全部完好**，差异来自算法代差而非破坏。
  要审存量图，正确做法是用同一版管线重跑一遍、在**同代候选**之间比。

【用法】
  python3 audit_wm.py <目录或图片...>              # 残留审计表
  python3 audit_wm.py --ref 原图.png 候选1 候选2    # 残留 + 损伤 + 总分（选版决策用）
  python3 audit_wm.py <目录> --montage /tmp/m.png   # 三联目检图（当前 / v8 / 差×8）
  python3 audit_wm.py <目录> --json /tmp/a.json     # JSON（含唯一 key，不按文件名索引）

【v1.16 新增两条参照无关工具（坑 30）】
  ① estimate_residual 除 k/r2/amp 外返回 **alpha**(=k̂) 与 **bg_scale**：
     amp = k̂ · bg_scale，而 bg_scale 随底子变化（白纸底 ≈9 vs 纯黑底 ≈238，
     **amp 被压 26 倍**）→ 要背景无关的残留必须看 alpha，不要用 amp 比不同底子的图。
  ② brightening_violation(wm, out)：由 orig=(I−αC)/(1−α) ≤ I 推出的**白蚀单向性**
     ——去白水印只能变暗，`out > I` 的像素必然是损伤。**不需要参照图、不需要同口径、
     跨算法代有效**，绕开了坑 28/29 反复翻车的「挑参照」环节（实测 v7 违反 5674 px、
     v12 71 px、v13 0 px）。

【判定阈值】
  CLEAN    amp < 1.0
  SUSPECT  1.0 ≤ amp < 2.5 或 R² 异常
  DIRTY    amp ≥ 2.5

依赖：opencv-python-headless、numpy（零模型，~0.5s/张）
"""

import _log
import argparse
import glob
import json
import os
import sys

try:
    import cv2
    import numpy as np
except ImportError as _e:          # 缺依赖时说人话，别甩 traceback（见 scripts/_env.py）
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import _env
    _env.die(_e, ['cv2', 'numpy'])

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dewm_io import imread_any, imwrite_any  # noqa: E402
from dewm_v8 import load_template, remove_watermark  # noqa: E402

CORE_THR = 0.15
AMP_CLEAN = 1.0
AMP_DIRTY = 2.5

# ── 结构损伤度量参数（坑 28）──────────────────────────────────────
DMG_CORE_THR = 0.15    # 笔画核心：结构比对的取样区（避开抗锯齿边缘的干扰）
DMG_STROKE_THR = 0.05  # 与 dewm_v7 的 inpaint 掩膜阈值一致，仅作诊断
DEV_FLOOR = 3.0        # 偏离参照低于该灰度级不算结构损伤
DEV_CAP = 12.0         # 罚分上限：4.8×DIRTY 阈值，保 inpaint 在极端残留时仍能兜底
# 结构参照的候选集合：必须是**同一套 k̂ 估计口径**的逐像素反解。
#   v8 / v9  逐图最小二乘拟合 k̂，α 上限 0.92（v9 = v8 + 锚点对齐）
#   v6       固定 k≡1，靠 max(1-α, 0.29) 硬截断兜底 —— **口径不同，不入族**
# 教训（2026-09-12）：曾把 v6 一并放进族里，结果 03_labor 上 v6 用 k=1 反解出的
# 「残留最低」被选为参照，反过来把目检正确的 v8/v9 判成偏离 13.6 / 损伤 10.6，
# 最终选了一个发浑的版本。族内成员口径不一致时，「族内应当一致」的前提不成立。
MODEL_FAMILY = ("v8", "v9")

# ── 「未动手」判定（坑 28 第四次迭代）─────────────────────────────
# 模板框内平均绝对灰度改动低于此值 → 候选逐位等于原图，即「拒绝动手」。
# 为什么必须单列：dewm_v9 的 K_RANGE 下限为 0，无水印（k̂_raw ≤ 0）时输出 = 原图，
# 这是它对干净图的**正确保护**；但 pick_wm 原先把这种输出也当普通候选，于是
#   · 它因「没改动 → 残留最低」被选为结构参照；
#   · 拿原图当参照，任何真正去水印的候选都显得「偏离」→ 被罚 → 系统性偏向「什么都不做」。
# 01_mistgate 实测：原图无水印（模板区 r²=0.010），却因该逻辑选出一个过减 13.9 的版本。
NOOP_EPS = 0.01


def change_amount(orig, cand, thr=NOOP_EPS):
    """候选相对原图在模板框内的平均绝对灰度改动量 + 是否「未动手」。

    与 estimate_damage 的分工：
      · estimate_damage 量「相对结构参照的偏离」，需要参照，用来抓画面被改坏；
      · change_amount  量「相对原图改了多少」，**不需要参照、对 k̂ 口径不敏感**，
        用来识别拒绝动手的候选（输出 = 原图）。
    两者正交：一个候选可以「改了很多且改坏了」（damage 高、change 高），
    也可以「根本没改」（damage 因参照失守而失明、change = 0）。
    """
    if orig.shape != cand.shape:
        return {"delta": 0.0, "noop": True, "shape_ok": False}
    H, W = orig.shape[:2]
    a, (x0, y0) = load_template(W, H)
    y1, x1 = min(H, y0 + a.shape[0]), min(W, x0 + a.shape[1])
    if y1 <= y0 or x1 <= x0:
        return {"delta": 0.0, "noop": True, "shape_ok": False}
    go = cv2.cvtColor(orig[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).astype(np.float32)
    gc = cv2.cvtColor(cand[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).astype(np.float32)
    delta = float(np.abs(gc - go).mean())
    return {"delta": delta, "noop": delta < thr, "shape_ok": True}


def estimate_residual(img):
    """拟合残留不透明度。返回 dict(k, r2, amp, core_px)。"""
    H, W = img.shape[:2]
    a, (x0, y0) = load_template(W, H)
    a3 = a[:, :, None]

    core = (a > CORE_THR).astype(np.uint8) * 255
    core = cv2.dilate(core, np.ones((3, 3), np.uint8), iterations=1)
    mask = np.zeros((H, W), dtype=np.uint8)
    mask[y0:y0 + core.shape[0], x0:x0 + core.shape[1]] = core
    bg = cv2.inpaint(img, mask, 3, cv2.INPAINT_TELEA).astype(np.float32)

    sub = img[y0:, x0:].astype(np.float32)
    sub_bg = bg[y0:, x0:]

    core_m = a > CORE_THR
    y_obs = sub - sub_bg
    x_mod = a3 * (255.0 - sub_bg)
    num = float((x_mod * y_obs)[core_m].sum())
    den = float((x_mod * x_mod)[core_m].sum()) + 1e-6
    k = num / den
    ss_res = float(((y_obs - k * x_mod)[core_m] ** 2).sum())
    ss_tot = float((y_obs[core_m] ** 2).sum()) + 1e-6
    r2 = 1.0 - ss_res / ss_tot
    bg_scale = float(np.mean(x_mod[core_m])) if core_m.any() else 0.0
    amp = float(k * bg_scale) if core_m.any() else 0.0
    return {"k": float(k), "alpha": float(k), "r2": float(r2), "amp": amp,
            "bg_scale": bg_scale, "core_px": int(core_m.sum())}


def brightening_violation(wm, out, tol=2):
    """白蚀单向性检查 —— **不需要任何参照图**的硬损伤判据。

    【数学依据】白色水印的叠加式 I = α·C + (1−α)·orig（C=255）。整理得

        orig = (I − α·C)/(1 − α) ≤ I       （当且仅当 I ≤ 255，实测恒成立）

    即**去掉白色水印只会让像素变暗或不变，绝不可能变亮**。
    因此 out > wm + tol 的任何像素，都必然是「凭空调亮了本来没有水印的地方」
    —— 不是估计误差，是模型外的产物，判损伤。

    【实测（2026-09-13，10 张真水印图）】
        v7     违反 305–1276 px，最大提亮 7–248 灰阶  ← 整区 inpaint 的代价
        v8/v9  192–239 px
        v11/v12 1–18 px
        v13(Wiener) 0 px
    v7 的违反量最大，正好对应坑 28/29 里它「把水印压着的结构整块取代」的行为。

    返回 dict(bad_px, bad_ratio, max_lift)。
    """
    H, W = wm.shape[:2]
    gw = cv2.cvtColor(wm, cv2.COLOR_BGR2GRAY).astype(np.int16)
    go = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY).astype(np.int16)
    d = go - gw
    bad = d > tol
    return {"bad_px": int(bad.sum()), "bad_ratio": float(bad.mean()),
            "max_lift": int(d.max())}


def background_factor(img, box=None):
    """水印框内的「背景可用动态范围」 mean(a·(C−bg))，用于判断 amp 是否可信。

    ⚠️ 这是 2026-09-13 发现的口径缺陷：amp = k̂·本函数返回值。
    纯白纸底（bg≈246）时 C−bg≈9，纯黑底（bg≈17）时 ≈238 —— **同样的残留
    不透明度，白底图的 amp 会被压低约 26 倍**。而本技能处理的竖版海报绝大多数
    是白底，于是 amp 在主力图种上几乎测不出残留（03_labor 上 v7 明显有灰糊斑，
    amp 却只有 0.21 判 CLEAN）。
    需要背景无关的量时请用 estimate_residual()['alpha']（即 k̂ 本身）。
    """
    H, W = img.shape[:2]
    a, (x0, y0) = load_template(W, H)
    if box:
        x0, y0, x1, y1 = box
    else:
        x1, y1 = min(W, x0 + a.shape[1]), min(H, y0 + a.shape[0])
    a = a[:y1 - y0, :x1 - x0]
    sub = img[y0:y1, x0:x1].astype(np.float32)
    core = cv2.dilate((a > CORE_THR).astype(np.uint8) * 255,
                      np.ones((3, 3), np.uint8), 1)
    m = np.zeros((H, W), np.uint8)
    m[y0:y1, x0:x1] = core
    bg = cv2.inpaint(img, m, 3, cv2.INPAINT_TELEA).astype(np.float32)[y0:y1, x0:x1]
    cm = a > CORE_THR
    if not cm.any():
        return 0.0
    return float(np.mean((a[:, :, None] * (255.0 - bg))[cm]))


def build_model_outputs(img, family=MODEL_FAMILY):
    """反解族（MODEL_FAMILY）的输出。这一族逐像素映射、且**共用同一套 k̂ 最小二乘
    拟合口径**，能保留笔画底下的真实结构，故可作结构参照的候选集合。
    v9 判「无水印、拒动手」时其输出即原图。

    family 可显式传入以纳入口径不同的版本（如 "v6" 固定 k≡1），但那样族内一致性
    前提不再成立，只适合诊断，不适合做参照。
    """
    from dewm import remove_watermark as v6_remove
    from dewm_v8 import remove_watermark as v8_remove
    from dewm_v9 import remove_watermark as v9_remove

    v9_out, _ = v9_remove(img)
    lazy = {
        "v6": lambda: v6_remove(img)[0],
        "v8": lambda: v8_remove(img)[0],
        "v9": lambda: v9_out,
    }
    return {k: lazy[k]() for k in family}


def structure_reference(img, outs=None, resid=None):
    """结构参照 = 反解族里残留最低的一版。返回 (参照图, 版本名, {版本: 残留})。"""
    if outs is None:
        outs = build_model_outputs(img)
    if resid is None:
        resid = {k: abs(estimate_residual(v)["amp"]) for k, v in outs.items()}
    name = min(outs, key=lambda k: resid[k])
    return outs[name], name, resid


def estimate_damage(orig, cand, ref=None, ref_name=None):
    """度量候选相对「结构参照」的偏离。返回 dict，penalty 可直接与 |amp| 相加。

    orig : 带水印的原图（用来取水印模板位置）
    cand : 某个版本的输出
    ref  : 结构参照图（不给则内部按反解族残留最低者现算，多花约 1.5s）

    核心量 dev = 笔画核心区（α>0.15）内候选与参照的平均灰度偏离：
      · 同族反解（v8/v9，共用同一套 k̂ 最小二乘口径）还原出的结构一致 → dev≈0
      · inpaint 把笔画内部换成邻域平滑填充 → dev 达数十灰度级
      · 平底图上两种做法结果都是平的 → dev 自然接近 0（不误罚合法兜底）

    ⚠️ 参照必须与候选**口径一致**。拿固定 k≡1 的 v6 当参照，会在深色区把正常的
    v8/v9 判成「偏离十几灰度级」——那不是结构损伤，是两个 k 值经 1/(1-α) 放大后的
    口径差（2026-09-12 实测 03_labor：v6 k=0.746 vs v8 k=0.782 → dev 13.6）。
    故参照候选集只用 MODEL_FAMILY。
    """
    blank = {"shape_ok": False, "dev_core": 0.0, "dev_stroke": 0.0,
             "ref_name": ref_name or "", "penalty": 0.0, "capped": False}
    if orig.shape[:2] != cand.shape[:2]:
        return blank

    if ref is None:
        ref, ref_name, _ = structure_reference(orig)
    if ref.shape[:2] != cand.shape[:2]:
        return dict(blank, shape_ok=True)

    H, W = orig.shape[:2]
    a, (x0, y0) = load_template(W, H)
    bh, bw = a.shape[:2]
    y1, x1 = min(H, y0 + bh), min(W, x0 + bw)
    if y1 <= y0 or x1 <= x0:
        return blank
    a_sub = a[:y1 - y0, :x1 - x0]

    g_c = cv2.cvtColor(cand[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).astype(np.float32)
    g_r = cv2.cvtColor(ref[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).astype(np.float32)
    dev = np.abs(g_c - g_r)

    core = a_sub > DMG_CORE_THR
    stroke = a_sub > DMG_STROKE_THR
    dev_core = float(dev[core].mean()) if core.any() else 0.0
    dev_stroke = float(dev[stroke].mean()) if stroke.any() else 0.0

    raw = max(0.0, dev_core - DEV_FLOOR)
    penalty = min(DEV_CAP, raw)

    return {
        "shape_ok": True,
        "dev_core": dev_core,
        "dev_stroke": dev_stroke,
        "ref_name": ref_name or "",
        "penalty": penalty,
        "capped": raw > DEV_CAP,
    }


def verdict(amp):
    """有符号 amp 反映方向：正=水印残留（亮），负=v6 过减（暗）。
    两者都是缺陷，统一用 |amp| 评估严重度。
    """
    a = abs(amp)
    if a < AMP_CLEAN:
        return "CLEAN"
    if a < AMP_DIRTY:
        return "SUSPECT"
    return "DIRTY"


def collect(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            out.extend(sorted(glob.glob(os.path.join(p, "*.png"))) +
                       sorted(glob.glob(os.path.join(p, "*.jpg"))))
        else:
            out.append(p)
    return out


def build_montage(rows, cell_w=340, cell_h=200):
    """三联：当前 / v8 输出 / 差异×8（放大便于肉眼判断）。"""
    n = len(rows)
    canvas = np.full((n * cell_h, cell_w * 3 + 8 * 2, 3), 255, dtype=np.uint8)
    for i, r in enumerate(rows):
        cur = r["_cur"][-cell_h:, -cell_w:]
        new = r["_v8"][-cell_h:, -cell_w:]
        diff = np.clip(np.abs(cur.astype(np.float32) -
                              new.astype(np.float32)) * 8, 0, 255).astype(np.uint8)
        y = i * cell_h
        for j, im in enumerate((cur, new, diff)):
            x = j * (cell_w + 8)
            canvas[y:y + im.shape[0], x:x + im.shape[1]] = im
    return canvas


def display_names(paths):
    """同名文件加父目录前缀做区分。

    坑 28 的诱因就是这个：旧版表格只打 basename，同一批传 6 个不同目录的同名文件时
    6 行长得一模一样，看起来像「结果被互相覆盖」，实际是显示层无法区分。
    JSON 里 name 也只是 basename，按 name 建索引的消费方同样会踩。
    """
    base = [os.path.basename(p) for p in paths]
    dup = {b for b in base if base.count(b) > 1}
    out = []
    for p, b in zip(paths, base):
        if b in dup:
            parent = os.path.basename(os.path.dirname(os.path.abspath(p)))
            out.append(f"{parent}/{b}")
        else:
            out.append(b)
    return out


def audit_pair_table(ref_path, paths):
    """--ref 模式：候选 vs 参照原图，同时给残留与结构损伤，输出总分。

    总分 = |amp| + penalty，是 pick_wm 的选版依据；这里让人能直接看到
    「为什么这个版本赢」——只列 |amp| 会给出错误答案（坑 28）。
    """
    ref_img = imread_any(ref_path)
    if ref_img is None:
        sys.exit(f"参照图无法读取: {ref_path}")
    struct_ref, ref_name, _ = structure_reference(ref_img)
    print(f"参照原图: {ref_path}")
    print(f"结构参照 = 反解族残留最低者 [{ref_name}]（逐像素反解，保留笔画底下真实结构）")
    print(f"{'候选':<30}{'|amp|':>8}{'偏离参照':>10}{'笔画区':>9}"
          f"{'损伤分':>9}{'总分':>9}  判定")
    print("-" * 88)
    rows = []
    for p in paths:
        cand = imread_any(p)
        if cand is None:
            print(f"{os.path.basename(p):<30} (unreadable)")
            continue
        res = estimate_residual(cand)
        dmg = estimate_damage(ref_img, cand, ref=struct_ref, ref_name=ref_name)
        total = abs(res["amp"]) + dmg["penalty"]
        name = os.path.basename(p)
        print(f"{name:<30}{abs(res['amp']):>8.2f}{dmg['dev_core']:>10.2f}"
              f"{dmg['dev_stroke']:>9.2f}{dmg['penalty']:>9.2f}{total:>9.2f}"
              f"  {verdict(res['amp'])}")
        rows.append(dict(res, name=name, key=os.path.abspath(p), path=p,
                         damage=dmg, total=total, verdict=verdict(res["amp"])))
    print("-" * 88)
    print("总分越低越好。偏离参照 = 笔画核心区(α>0.15)内与反解族参照的平均灰度差：\n"
          "反解族彼此 ≈0，inpaint 涂抹达数十；低于 3 不算损伤，封顶 12")
    return rows


def main():
    ap = argparse.ArgumentParser(description="去水印残留 + 结构损伤审计")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--ref", help="参照原图；给出后同时报告结构损伤与总分。"
                                  "仅对「同一张原图、同一代管线」产出的多个候选有效——"
                                  "审计历史产物（不同代算法）会误报，见模块头「适用边界」")
    ap.add_argument("--montage", help="输出三联目检拼图")
    ap.add_argument("--json", dest="json_out", help="输出 JSON")
    args = ap.parse_args()

    paths = collect(args.paths)
    if not paths:
        sys.exit(2)   # 2 = 用法/输入错误（1 在本技能约定里是「blocker」，不要混用）

    if args.ref:
        rows = audit_pair_table(args.ref, paths)
        if args.json_out:
            with open(args.json_out, "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=2)
            print(f"JSON → {args.json_out}")
        return

    names = display_names(paths)
    print(f"{'图片':<30} {'k̂':>7} {'R²':>7} {'amp':>7} {'判定':>9}  {'v8最大改动':>10}")
    print("-" * 82)
    rows = []
    for p, name in zip(paths, names):
        img = imread_any(p)
        if img is None:
            print(f"{name:<30} (unreadable)")
            continue
        res = estimate_residual(img)
        v8, st = remove_watermark(img)
        H, W = img.shape[:2]
        a, (x0, y0) = load_template(W, H)
        d = np.abs(v8[y0:, x0:].astype(np.float32) -
                   img[y0:, x0:].astype(np.float32))
        core_m = a > CORE_THR
        maxd = float(d[core_m].max()) if core_m.any() else 0.0
        v = verdict(res["amp"])
        print(f"{name:<30} {res['k']:>7.3f} {res['r2']:>7.3f} {res['amp']:>7.2f} "
              f"{v:>9}  {maxd:>10.1f}")
        r = dict(res, name=name, path=p,
                 key=os.path.abspath(p),
                 dir=os.path.dirname(os.path.abspath(p)),
                 verdict=v, v8_max_delta=maxd,
                 v8_k=st["k"], v8_r2=st["r2"])
        if args.montage:
            r["_cur"] = img
            r["_v8"] = v8
        rows.append(r)

    print("-" * 82)
    dirty = [r for r in rows if r["verdict"] == "DIRTY"]
    susp = [r for r in rows if r["verdict"] == "SUSPECT"]
    print(f"合计 {len(rows)} 张：DIRTY {len(dirty)} / SUSPECT {len(susp)} / "
          f"CLEAN {len(rows) - len(dirty) - len(susp)}")
    print("注：amp 是残留灰度幅度（人眼可感阈 ≈1.5）；"
          "R² 高说明残差确实是水印形状，R² 低则多半是纹理误报")
    print("    本表只看残留。要判「画面有没有被改坏」须给 --ref 参照原图（坑 28）")

    if args.montage:
        m = build_montage([r for r in rows if "_cur" in r])
        imwrite_any(args.montage, m)
        print(f"\n三联目检图 → {args.montage}  （左=当前 中=v8 右=差异×8）")

    if args.json_out:
        for r in rows:
            r.pop("_cur", None)
            r.pop("_v8", None)
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print(f"JSON → {args.json_out}  （按 key=绝对路径 索引，勿用 name）")


if __name__ == "__main__":
    _log.run("audit_wm", main)