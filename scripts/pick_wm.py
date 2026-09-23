#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pick_wm — 对每张图跑 v6 / v7 / v8 / v9 四种去水印，按「残留 + 结构损伤」选最佳。

【为什么需要】
v6 反解：白底完美，深/红底放大噪点
v7 inpaint：兜底，纹理被抹平
v8 自适应拟合：低对比水印更干净，但在已平滑区会过拟合出鬼影
v9 v8 + 锚点对齐：位置/尺度漂移场景修复（bench 平均 +12.4dB）；干净图拒动手

四版各有所长，靠肉眼挑图不靠谱；靠单一版本又会在某些图翻车。
正确做法：每张跑四版，按总分选最低的。

【判分（v1.13 起，坑 28 修复）】
    score(v) = |amp(v)|  +  penalty(v)
               └ 残留    └ 结构损伤（estimate_damage）

  amp    残留幅度：水印还剩多少（越低越好）
  penalty 结构损伤：画面被改坏多少（越低越好）
          = clamp(笔画核心区内与「结构参照」的平均偏离 − 3, 0, 12)

**只看 |amp| 会选出破坏画面的版本**：v7 整区 inpaint 把水印抹平后残留天然 =0，
必然赢 |amp|，但它把水印底下的图形结构一起抹掉了（实测 amp -0.20 判 CLEAN，
画面却破损）。加入 penalty 后同一张图 v8 以 2.22 胜出 v7 的 9.69，与目检一致。

**结构参照 = 同族反解里残留最低的一版**（MODEL_FAMILY = v8/v9）。这一族逐像素
映射、**共用同一套 k̂ 最小二乘拟合口径**，按已知物理模型还原，能保留笔画底下的
真实结构（数学保证，非经验）；inpaint 是邻域填充，在笔画内部与参照必然大幅偏离。
因此判据的语义是「你能从反解拿到的东西，被涂抹替掉了多少」。封顶 12 保证反解族
全军覆没（残留 ≥12）时仍轮到 v7 兜底；水印底下本就是平色时偏离接近 0
（平底上两种做法结果都是平的），不误罚。

⚠️ **族内必须同口径**：v6 固定 k≡1、靠 max(1-α,0.29) 硬截断，与自适应拟合 k̂ 的
v8/v9 不是同一族。混作一族时 03_labor 上 v6 的「残留最低」被选为参照，反过来把
目检正确的 v8/v9 判成损伤，最终选中发浑的版本（2026-09-12，坑 28 第三次迭代）。
v6/v7 仍作为**候选**参与竞争，只是不当参照。

【用法】
  python3 pick_wm.py <目录或图片...>                      # 选版并写入 _clean/
  python3 pick_wm.py <dir> --legacy-score                 # 回退旧判据（纯 |amp|），A/B 用
  python3 pick_wm.py <dir> --json /tmp/pick.json          # 选版结果 JSON（含两套判据）
  python3 pick_wm.py <dir> --montage /tmp/pick.png        # 五列对比拼图
  python3 pick_wm.py <dir> --verbose                      # 逐版本打印残留/损伤明细

依赖：dewm_io / dewm / dewm_v7 / dewm_v8 / dewm_v9 / audit_wm（同目录）
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
from dewm import remove_watermark as v6_remove  # noqa: E402
from dewm_v7 import inpaint_watermark as v7_remove  # noqa: E402
from dewm_v8 import remove_watermark as v8_remove  # noqa: E402
from dewm_v9 import remove_watermark as v9_remove  # noqa: E402
from audit_wm import (  # noqa: E402
    AMP_CLEAN, AMP_DIRTY, MODEL_FAMILY, change_amount, estimate_damage,
    estimate_residual,
)

VERSIONS = ("v6", "v7", "v8", "v9")

# 胜出版本的残留高于某个被罚下候选这么多时，判为「数值自相矛盾」——两者取舍无法由
# 数值裁决（见下方分歧告警的成因注释）。这类图**不写入产物**：拿不准就不要动手，
# 否则会把上一轮选对的好产物覆盖成差的（Design43-10 实测：现任 _clean = v7 残留 0.05，
# 新判据会改选 v8 残留 5.72，一旦重跑就覆盖掉好产物）。
AMBIG_DELTA = 5.0


def ambiguous_pair(detail, winner):
    """「残留明显更低却被罚下」的候选 → (版本, 残留)；无则 None。"""
    wd = detail[winner]
    if wd.get("noop"):
        return None
    alt = min((k for k in VERSIONS
               if k != winner and not detail[k].get("noop")),
              key=lambda k: detail[k]["resid"], default=None)
    if alt and detail[alt]["resid"] + AMBIG_DELTA < wd["resid"]:
        return (alt, detail[alt]["resid"])
    return None


def collect(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            out.extend(sorted(glob.glob(os.path.join(p, "*.png"))) +
                       sorted(glob.glob(os.path.join(p, "*.jpg"))))
        else:
            out.append(p)
    return out


def build_versions(img):
    """跑四版，返回 {版本: 输出图}。v9 在 k̂≤0 时输出即原图（零改动）。"""
    v6_out, _ = v6_remove(img)
    v7_out, _ = v7_remove(img)
    v8_out, _ = v8_remove(img)
    v9_out, _ = v9_remove(img)
    return {"v6": v6_out, "v7": v7_out, "v8": v8_out, "v9": v9_out}


def score_versions(img, outs):
    """返回 (总分表, 明细表)。总分 = |amp| + 损伤 penalty。

    结构参照取同族反解（MODEL_FAMILY）里残留最低者——这一族共用同一套 k̂ 拟合
    口径、逐像素还原，能保留笔画底下的真实结构；候选在笔画核心区偏离参照多少，
    就是「结构被改坏多少」。参照复用本次已算出的 outs，不额外重跑。

    注意 v9 可能**零改动**（K_RANGE 下限 0：k̂_raw ≤ 0 时输出原图）。零改动的输出
    即原图，此时它作为参照是**合法**的——它表达的判断正是「这张图不需要处理」，
    其他版本偏离它即「改了不该改的地方」。故族内不剔除零改动成员；
    但胜出版本零改动时必须显式告知（否则会被误读成「已去水印」）。
    """
    resid = {k: abs(estimate_residual(outs[k])["amp"]) for k in VERSIONS}
    chg = {k: change_amount(img, outs[k]) for k in VERSIONS}
    fam = {k: outs[k] for k in MODEL_FAMILY}
    ref_name = min(fam, key=lambda k: resid[k])
    ref = fam[ref_name]

    total, detail = {}, {}
    for name in VERSIONS:
        dmg = estimate_damage(img, outs[name], ref=ref, ref_name=ref_name)
        total[name] = resid[name] + dmg["penalty"]
        detail[name] = {"resid": resid[name], "penalty": dmg["penalty"],
                        "score": total[name], "delta": chg[name]["delta"],
                        "noop": chg[name]["noop"], **dmg}
    return total, detail


def pick_one(img, legacy=False):
    """对一张图跑四版。返回 (胜出版本, 各版输出, 新判据总分, 明细, 旧判据总分)。

    总分相同则按 VERSIONS 顺序取前（v6 优先），保证可复现。

    **最小干预**（2026-09-12）：v9 判定无需处理（k̂≤0 → 零改动）且**原图残留本就在
    CLEAN 阈值内**时，直接取 v9。理由：原图已够干净，而任何实际改动都有代价——
    v8 的 k 下限 0.2 会在无水印图上强推反解把画面压暗（01_mistgate 实测 −13.87），
    v7 会抹平结构；改动量为 0 的结果天然保留全部画面信息。
    该规则**不影响任何残留 ≥1.0 的图**（它们照常竞争），只在「本来就干净」时生效。
    """
    outs = build_versions(img)
    total, detail = score_versions(img, outs)
    legacy_scores = {k: v["resid"] for k, v in detail.items()}

    if (not legacy and detail["v9"]["noop"]
            and detail["v9"]["resid"] < AMP_CLEAN):
        winner = "v9"
    else:
        table = legacy_scores if legacy else total
        winner = min(VERSIONS, key=lambda k: (table[k], VERSIONS.index(k)))
    return winner, outs, total, detail, legacy_scores


def build_pick_montage(rows, cell_w=240, cell_h=200):
    """每图一行 5 列：原 / v6 / v7 / v8 / v9 + 头部行（每列标题）。"""
    n = len(rows)
    pad = 6
    keys = ("orig", "v6", "v7", "v8", "v9")
    canvas_h = pad * 2 + cell_h + 40 + n * (cell_h + pad)
    canvas_w = pad * 6 + cell_w * 5
    canvas = np.full((canvas_h, canvas_w, 3), 255, dtype=np.uint8)
    for j, label in enumerate(("original", "v6", "v7", "v8", "v9")):
        x = pad + j * (cell_w + pad) + cell_w // 2 - len(label) * 5
        cv2.putText(canvas, label, (x, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
    y0 = 40
    for i, r in enumerate(rows):
        ys = y0 + i * (cell_h + pad)
        for j, key in enumerate(keys):
            xs = pad + j * (cell_w + pad)
            im = r["_imgs"][key][-cell_h:, -cell_w:]
            canvas[ys:ys + im.shape[0], xs:xs + im.shape[1]] = im
        name_y = ys + 30
        cv2.putText(canvas, r["name"][:20], (4, name_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1, cv2.LINE_AA)
        cv2.putText(canvas, f"-> {r['winner']}", (4, name_y + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 128, 0), 1, cv2.LINE_AA)
    return canvas


def main():
    ap = argparse.ArgumentParser(description="v6/v7/v8/v9 四版选最佳（残留 + 结构损伤）")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out-root", default=None,
                    help="输出根目录（默认写到 <原图所在目录>/_clean/）")
    ap.add_argument("--legacy-score", action="store_true",
                    help="回退旧判据（纯 |amp|，会选坏画面的版本，仅 A/B 用）")
    ap.add_argument("--verbose", action="store_true", help="逐版本打印残留/损伤明细")
    ap.add_argument("--json", dest="json_out", help="选版结果 JSON")
    ap.add_argument("--montage", help="五列对比拼图（原 / v6 / v7 / v8 / v9）")
    args = ap.parse_args()

    paths = collect(args.paths)
    if not paths:
        sys.exit(2)   # 2 = 用法/输入错误（1 在本技能约定里是「blocker」，不要混用）

    print(f"{'图片':<24}{'v6':>8}{'v7':>8}{'v8':>8}{'v9':>8}  {'胜出':>5} {'旧判据':>7}")
    print("-" * 76)
    rows = []
    diffs = []
    noops = []   # 判为「无需处理」而未写产物的图
    stale = []   # 其中 _clean/ 已存在旧产物、值得人工复核的
    held = []    # 判为「数值自相矛盾」而暂缓写入的图
    for p in paths:
        img = imread_any(p)
        if img is None:
            continue
        winner, outs, total, detail, legacy = pick_one(img, legacy=args.legacy_score)
        winner_new = min(VERSIONS, key=lambda k: (total[k], VERSIONS.index(k)))
        winner_old = min(VERSIONS, key=lambda k: (legacy[k], VERSIONS.index(k)))
        name = os.path.basename(p)
        flag = "⚠" if winner_new != winner_old else " "
        print(f"{name:<24}" + "".join(f"{total[k]:>8.2f}" for k in VERSIONS)
              + f"  {winner:>4}{flag} {winner_old:>6}")
        if winner_new != winner_old:
            diffs.append((name, winner_old, winner_new))
        if args.verbose:
            for k in VERSIONS:
                d = detail[k]
                print(f"    {k}  残留={d['resid']:>7.2f}  损伤={d['penalty']:>6.2f}"
                      f"  偏离参照={d['dev_core']:>6.2f}"
                      f"  改动量={d['delta']:>7.3f}"
                      f"  总分={d['score']:>7.2f}"
                      + ("   ← 结构参照" if k == d.get("ref_name") else "")
                      + ("   [未改动]" if d["noop"] else ""))

        r = {"name": name, "path": p, "winner": winner,
             "scores": total, "legacy_scores": legacy,
             "winner_new": winner_new, "winner_legacy": winner_old,
             "detail": detail}
        if args.montage:
            r["_imgs"] = {"orig": img, **outs}
        rows.append(r)

        out_dir = (os.path.join(args.out_root, "_clean") if args.out_root
                   else os.path.join(os.path.dirname(os.path.abspath(p)), "_clean"))
        # 只算一次（2026-09-23 修）：原先是 `elif ambiguous_pair(...)` 判一次、
        # 分支体内再算一次取结果，同一对候选被比较两遍（纯浪费，且两行读起来像两件事）。
        amb = ambiguous_pair(detail, winner)
        if detail[winner]["noop"]:
            # 胜出版本零改动 = 输出与原图逐位相同。写出它只会制造「已去水印」的假象，
            # 故不写产物；但要检查 _clean/ 里是否躺着旧算法的产物（可能含破坏）。
            noops.append(name)
            prev = os.path.join(out_dir, name)
            if os.path.exists(prev):
                stale.append((name, prev))
        elif amb:
            # 数值自相矛盾：残留更低的候选被结构损伤分罚下。谁更好只能目检，
            # 故不动手 —— 尤其不能覆盖 _clean/ 里可能更优的旧产物。
            held.append((name, winner, detail[winner]["resid"], amb[0], amb[1],
                         os.path.exists(os.path.join(out_dir, name))))
        else:
            os.makedirs(out_dir, exist_ok=True)
            imwrite_any(os.path.join(out_dir, name), outs[winner])

    print("-" * 76)
    cnt = {k: 0 for k in VERSIONS}
    for r in rows:
        cnt[r["winner"]] += 1
    print(f"合计 {len(rows)} 张：" + " / ".join(f"{k} 胜 {cnt[k]}" for k in VERSIONS))
    print("总分 = |残留 amp| + 结构损伤分（越低越好）；标 ⚠ 者两套判据选择不同")
    if diffs:
        print(f"\n⚠ 旧判据（纯 |amp|）会在 {len(diffs)} 张上改选：")
        for name, old, new in diffs[:8]:
            print(f"   {name[:40]:<42} 旧选 {old} → 新选 {new}")
        if len(diffs) > 8:
            print(f"   … 另有 {len(diffs) - 8} 张")
        print("   旧判据选中的 inpaint 版本残留分天然偏低，但画面结构会被抹掉（坑 28）")

    # 判为「无需处理」的图单列，不混进下面的残留给警（它的残留分 = 原图的残留，
    # 出现在「无干净候选」列表里会与「已处理但没去净」混为一谈）。
    if noops:
        print(f"\n⚠ {len(noops)} 张判定为「无需处理」，未写产物（保留原图）：")
        for n in noops[:8]:
            print(f"   {n}")
        if len(noops) > 8:
            print(f"   … 另有 {len(noops) - 8} 张")
        print("   含义：v9 的 k̂ ≤ 0 —— 水印模型在本图不成立（图本身干净，或水印几何")
        print("   超出标定模板）。此时「不动」是安全选择；若目检仍见水印，需人工介入。")
    if stale:
        print(f"\n⚠ 其中 {len(stale)} 张的 _clean/ 里已存在旧产物 —— 本次判定无需处理，"
              f"未覆盖它们：")
        for n, pth in stale[:8]:
            print(f"   {os.path.relpath(pth)}")
        if len(stale) > 8:
            print(f"   … 另有 {len(stale) - 8} 张")
        print("   旧产物可能由别的算法生成（如 v8 的 k 下限 0.2 会在无水印图上强推反解、")
        print("   把画面压暗）。它与「保留原图」二者只应留一个，**建议人工目检后取舍**。")

    # 全部候选都判 DIRTY 时不能静默交付：残留分可能来自纹理纸底误报（见 audit_wm 适用
    # 边界），也可能是真残留——两者都只能靠目检定夺，所以明说，而不是假装干净。
    dirty = [r for r in rows
             if not r["detail"][r["winner"]]["noop"]
             and r["detail"][r["winner"]]["resid"] >= AMP_DIRTY]
    if dirty:
        print(f"\n⚠ {len(dirty)} 张的胜出版本残留分仍 ≥ {AMP_DIRTY}（DIRTY），无干净候选：")
        for r in dirty[:6]:
            d = r["detail"][r["winner"]]
            print(f"   {r['name'][:40]:<42} {r['winner']}  残留 {d['resid']:.2f}"
                  f"  损伤 {d['penalty']:.2f}")
        if len(dirty) > 6:
            print(f"   … 另有 {len(dirty) - 6} 张")
        print("   成因两种：纹理纸底/渐变底把残留分顶高（非真残留，画面其实干净）；")
        print("   或确实没去干净。**必须目检**——确属残留时再考虑云端后处理（须用户同意）。")

    # 分歧告警：胜出版本的残留明显高于某个被罚下的候选 —— 这两者的取舍**无法由数值裁决**。
    # 已实测三类样本（坑 28 反例 / 03_labor / Design 系列）的 amp、R²、dev 全部交叠：
    #   · 水印压在**结构**上（文字/图形）：v7 的 inpaint 把结构抹掉 → 该罚 v7 ✅
    #   · 水印压在**暗平坦区**：v7 填成背景色既干净又无损，却被「偏离参照」误罚 ❌
    #     更深一层：参照取自 MODEL_FAMILY(v8/v9)，而该族在本图**本身就带残留**
    #     （v8 残留 5.72），于是「真正去干净的那个」反倒成了偏离者。
    # 故只报告、不自动裁决，并且**不写产物**（见 held），把选择权交回目检。
    if held:
        print(f"\n⚠ {len(held)} 张存在「残留明显更低却被罚下」的候选，**本次未写产物**：")
        for n, w, wr, alt, ar, had in held[:8]:
            tail = "（_clean/ 已有产物，保留未覆盖）" if had else "（_clean/ 无产物，需人工写入）"
            print(f"   {n[:36]:<38}胜出 {w}(残留 {wr:>6.2f})  ←→  {alt}(残留 {ar:>6.2f}){tail}")
        if len(held) > 8:
            print(f"   … 另有 {len(held) - 8} 张")
        print("   水印压在平坦区时，inpaint 的干净结果会被「偏离参照」误判成损伤；")
        print("   而参照自身带残留时，真正去干净的那版反成异类——两者谁更好**只能目检**")
        print("   （见 references/pitfalls.md 坑 29）。拿不准就不动手，避免覆盖更优的旧产物。")

    where = (os.path.join(args.out_root, "_clean") if args.out_root
             else "各图所在目录的 _clean/")
    written = len(rows) - len(noops) - len(held)
    if written:
        print(f"已写入 {written} 张 → {where}（不覆盖原图）")

    if args.montage:
        m = build_pick_montage(rows)
        imwrite_any(args.montage, m)
        print(f"\n五列对比拼图 → {args.montage}  （原 / v6 / v7 / v8 / v9，标绿=胜出）")

    if args.json_out:
        for r in rows:
            r.pop("_imgs", None)
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print(f"JSON → {args.json_out}")


if __name__ == "__main__":
    _log.run("pick_wm", main)