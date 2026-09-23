#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""去水印域：覆盖守卫、可解性门控、选版判据（坑 28/29）、度量缺陷（坑 30）、
v13 不变量（坑 32）、自动闸门、缺依赖人话报错。"""
import os
import subprocess
import sys
import tempfile

from _harness import HERE, check, load


# ── 坑 25：覆盖守卫（大小写 / 硬链接） ────────────────────────────
def test_overwrite_guard():
    io = load("dewm_io")
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "a.png")
        open(src, "wb").close()

        # 大小写变体
        t = io.safe_target(src, os.path.join(d, "A.PNG"))
        check("覆盖守卫-大小写变体",
              os.path.normcase(os.path.realpath(t)) != os.path.normcase(os.path.realpath(src)),
              "A.PNG 与 a.png 在 APFS 上同一文件，会被覆盖")

        # 硬链接
        alias = os.path.join(d, "alias.png")
        try:
            os.link(src, alias)
            t2 = io.safe_target(src, alias)
            safe = True
            try:
                safe = not os.path.samefile(t2, src)
            except OSError:
                pass
            check("覆盖守卫-硬链接", safe, "alias 与源同 inode，会被覆盖")
        except OSError:
            check("覆盖守卫-硬链接", True, "本文件系统不支持硬链接，跳过")

        # 同目录 --out 必须重定向
        t3 = io.safe_target(src, d)
        check("覆盖守卫-同目录重定向", "_clean" in t3, f"未重定向：{t3}")

        # --inplace 是唯一例外
        t4 = io.safe_target(src, None, inplace=True)
        check("覆盖守卫-inplace 显式允许",
              os.path.realpath(t4) == os.path.realpath(src), "显式覆盖应放行")


# ── 可解性门控（近白底不该硬解） ─────────────────────────────────
def test_solvability_guard():
    import numpy as np
    V10 = load("dewm_v10")
    V8 = load("dewm_v8")

    W, H = 1024, 1792
    a, (x0, y0) = V8.load_template(W, H)
    ah, aw = a.shape[:2]

    # 近白底：水印不可见也不可解 → 必须 no-op（返回原图）
    gt = np.full((H, W, 3), 252, np.uint8)
    out, st = V10.remove_watermark(gt)
    check("可解性门控-近白底 no-op",
          st.get("skipped") is not None and np.array_equal(out, gt),
          f"未跳过：{st.get('skipped')}")

    # 中灰底：可解 → 不得跳过
    gt2 = np.full((H, W, 3), 180, np.uint8)
    alpha = np.clip(1.0 * a[:, :, None], 0, 0.99)
    sub0 = gt2[y0:y0 + ah, x0:x0 + aw]
    wm = gt2.astype(np.float32).copy()
    wm[y0:y0 + ah, x0:x0 + aw] = alpha * 255.0 + (1 - alpha) * sub0.astype(np.float32)
    wm = np.clip(wm, 0, 255).astype(np.uint8)
    _, st2 = V10.remove_watermark(wm)
    check("可解性门控-中灰底正常处理",
          st2.get("skipped") is None, f"误跳过：{st2.get('skipped')}")

    # 关闭门控时近白底也应硬解（供 A/B 用）
    _, st3 = V10.remove_watermark(gt, guard=False)
    check("可解性门控可关闭", st3.get("skipped") is None, "guard=False 仍跳过")


# ── 坑 28：选版必须同时看「残留」与「结构损伤」 ──────────────────
def test_pick_wm_damage_aware():
    """2026-09-12 实测：pick_wm 旧判据（纯 |amp|）选了 v7 整区 inpaint，
    残留 amp -0.20 判 CLEAN，画面却把水印压着的黑色图形整块啃掉。

    判据 = 候选在**笔画核心区**偏离「反解族结构参照」多少。构造合成图验证：
      结构化内容 → inpaint 偏离大、必须被罚，总分翻转
      纯平底     → 没有结构可毁，不得被罚
      只改抗锯齿边缘 → **不得判为损伤**（第一版判据正是在这里翻的车：它量的
      其实是紧贴笔画的边缘像素，腐蚀 2px 后已知破坏样本全部归零，已弃用）
      异口径成员 → **不得入参照族**（第三版判据修正：v6 固定 k≡1 与 v8/v9 的自适应
      k̂ 不同口径，入族会让深色图上正确的 v8/v9 被判成偏离 13.6 —— 口径差不是损伤）
    """
    import cv2
    import numpy as np
    au = load("audit_wm")
    V8 = load("dewm_v8")

    W, H = 1024, 1536
    a, (x0, y0) = V8.load_template(W, H)
    ah, aw = a.shape[:2]
    a3 = a[:, :, None]

    def simulate(orig):
        wm = orig.copy()
        sub = orig[y0:y0 + ah, x0:x0 + aw].astype(np.float32)
        wm[y0:y0 + ah, x0:x0 + aw] = np.clip(
            a3 * 255.0 + (1 - a3) * sub, 0, 255).astype(np.uint8)
        return wm

    def pointwise(wm):
        """反解族行为：逐像素还原，保留笔画底下的真实结构。"""
        out = wm.copy()
        sub = wm[y0:y0 + ah, x0:x0 + aw].astype(np.float32)
        out[y0:y0 + ah, x0:x0 + aw] = np.clip(
            (sub - a3 * 255.0) / (1 - a3), 0, 255).astype(np.uint8)
        return out

    def inpaint_like_v7(wm):
        mask = np.zeros((H, W), np.uint8)
        region = cv2.dilate((a > 0.05).astype(np.uint8) * 255,
                            np.ones((3, 3), np.uint8), 1)
        mask[y0:y0 + ah, x0:x0 + aw] = region
        return cv2.inpaint(wm, mask, 3, cv2.INPAINT_TELEA)

    def fringe_only(wm, ref):
        """只把抗锯齿边缘（α<0.02）涂改掉，笔画核心一个字不动。"""
        out = ref.copy()
        yy, xx = np.where(a3[:, :, 0] < 0.02)
        out[y0 + yy, x0 + xx] = 255
        return out

    # ① 水印底下压着结构
    orig = np.full((H, W, 3), 242, np.uint8)
    cv2.circle(orig, (x0 + 100, y0 + 45), 72, (18, 18, 18), -1)
    cv2.rectangle(orig, (x0 + 150, y0 + 15), (x0 + 205, y0 + 95), (30, 30, 200), -1)
    wm = simulate(orig)
    ref = pointwise(wm)          # 反解族参照（等价于模型族里残留最低那版）

    d_ref = au.estimate_damage(wm, ref, ref=ref, ref_name="v8")
    d_ip = au.estimate_damage(wm, inpaint_like_v7(wm), ref=ref, ref_name="v8")
    check("坑28 候选＝结构参照时偏离为 0",
          d_ref["dev_core"] == 0.0 and d_ref["penalty"] == 0.0,
          f"dev={d_ref['dev_core']} pen={d_ref['penalty']}")
    check("坑28 inpaint 在笔画核心区偏离参照 → 判损伤",
          d_ip["dev_core"] > au.DEV_FLOOR and d_ip["penalty"] > 0.0,
          f"dev={d_ip['dev_core']:.2f} pen={d_ip['penalty']:.2f}")

    # ② 只改抗锯齿边缘 → 必须放行（第一版判据的死因）
    d_fr = au.estimate_damage(wm, fringe_only(wm, ref), ref=ref, ref_name="v8")
    check("坑28 只改抗锯齿边缘不判损伤（不重蹈旧判据覆辙）",
          d_fr["penalty"] == 0.0 and d_fr["dev_core"] == 0.0,
          f"dev={d_fr['dev_core']} pen={d_fr['penalty']}")

    # ③ 合成真实反例的残留分（inpaint 残留更低）→ 总分必须翻转
    resid_inpaint, resid_pointwise = 0.20, 2.22
    check("坑28 总分翻转：低残留的 inpaint 不再胜出",
          resid_inpaint + d_ip["penalty"] > resid_pointwise + d_ref["penalty"],
          f"inpaint={resid_inpaint + d_ip['penalty']:.2f} "
          f"vs 反解={resid_pointwise + d_ref['penalty']:.2f}")

    # ④ 纯平底：没有结构可毁 → inpaint 不得被罚
    flat = np.full((H, W, 3), 236, np.uint8)
    wmf = simulate(flat)
    reff = pointwise(wmf)
    d_flat = au.estimate_damage(wmf, inpaint_like_v7(wmf), ref=reff, ref_name="v8")
    check("坑28 纯平底 inpaint 不罚（无结构可毁）",
          d_flat["penalty"] == 0.0, f"实际 {d_flat['penalty']}")

    # ⑤ 上限：罚分必须封顶，否则 inpaint 永远无法在极端残留时兜底
    check("坑28 损伤分有上限",
          d_ip["penalty"] <= au.DEV_CAP, f"{d_ip['penalty']} > {au.DEV_CAP}")

    # ⑥ 结构参照必须取自反解族（跑真实的 v6/v8/v9 管线）
    _, sname, sresid = au.structure_reference(wm)
    check("坑28 结构参照取自反解族",
          sname in au.MODEL_FAMILY, f"参照={sname}")
    check("坑28 反解族各版残留都被计算",
          set(sresid) == set(au.MODEL_FAMILY), f"{sorted(sresid)}")

    # ⑦ 族内必须同口径（2026-09-12 第三次迭代）
    #    v6 固定 k≡1 + max(1-α,0.29) 硬截断；v8/v9 逐图最小二乘拟合 k̂。
    #    混作一族时，03_labor 上 v6 用 k=1 反解出的「残留最低」被选为参照，
    #    反过来把目检正确的 v8/v9 判成偏离 13.6 / 损伤 10.6，最终选中发浑的版本。
    #    深色区里两个 k 的差会被 1/(1-α) 放大成十几灰度级 —— 那是口径差。
    check("坑28 结构参照族排除口径不同的 v6（固定 k≡1）",
          "v6" not in au.MODEL_FAMILY, f"MODEL_FAMILY={au.MODEL_FAMILY}")
    check("坑28 结构参照族排除 inpaint 的 v7",
          "v7" not in au.MODEL_FAMILY, f"MODEL_FAMILY={au.MODEL_FAMILY}")

    # ⑧ 反向保护：v6/v7 仍须作为**候选**参与竞争，只是不当参照。
    #    删掉它们会让平底 / 极端残留场景失去兜底路径。
    pw = load("pick_wm")
    check("坑28 v6/v7 仍作为候选参与竞争（仅不作参照）",
          set(pw.VERSIONS) == {"v6", "v7", "v8", "v9"}, f"{pw.VERSIONS}")


# ── 坑 29：干净图与「歧义取舍」不得被静默处理 ─────────────────────
def test_pick_wm_noop_policy():
    """2026-09-12 全库复检实测两件事：

    ① **v9 零改动是合法判定**：dewm_v9 的 K_RANGE 下限 0，水印模型不成立
       （k̂_raw ≤ 0）时输出 = 原图。此时若把它当普通候选，它会「因没动手而残留
       最低」胜出——但在干净图上这**恰恰是正解**（01_mistgate 实测：原图无水印，
       旧产物 v8 却因强制 k≥0.2 把画面压暗 13.87 灰度级）。
       故不排除它，而是**必须显式告知、且不写产物**（写一个与原图逐位相同的
       文件到 _clean/ 只会制造「已去水印」的假象）。

    ② **「残留更低却被罚下」必须报告而非自动裁决**：水印压在暗平坦区时，
       v7 的 inpaint 填成背景色既干净又无损，却被「偏离参照」误判为损伤；
       实测三类样本的 amp / R² / dev 全部交叠，无法用数值区分，只能交目检。
    """
    import numpy as np
    import cv2
    au = load("audit_wm")
    V8 = load("dewm_v8")
    W, H = 1024, 1536
    a, (x0, y0) = V8.load_template(W, H)

    base = (np.random.RandomState(7).rand(H, W, 3) * 30 + 120).astype(np.uint8)

    # ① 逐位相同 → 判「未动手」
    c0 = au.change_amount(base, base.copy())
    check("坑29 逐位相同 → 判未动手", c0["noop"] and c0["delta"] == 0.0,
          f"delta={c0['delta']}")

    # ② 只在水印区动了一点 → 不算未动手
    moved = base.copy()
    moved[y0:min(H, y0 + a.shape[0]), x0:min(W, x0 + a.shape[1])] = 255
    c1 = au.change_amount(base, moved)
    check("坑29 水印区有改动 → 不判未动手", not c1["noop"] and c1["delta"] > 1.0,
          f"delta={c1['delta']:.3f}")

    # ③ 改动量必须只统计模板框内 —— 框外大改也不该影响判定（否则误报）
    outside = base.copy()
    outside[:H // 2, :] = 255          # 上半张全改，水印框在下半张
    c2 = au.change_amount(base, outside)
    check("坑29 只统计模板框内（框外大改不算）", c2["noop"],
          f"delta={c2['delta']:.3f}")

    # ④ 尺寸不同 → 保守判为「未动手」，不让形状不合的候选参与比较
    c3 = au.change_amount(base, cv2.resize(base, (512, 768)))
    check("坑29 尺寸不同 → 判未动手（保守）", c3["noop"] and not c3["shape_ok"],
          f"{c3}")

    # ⑤ 端到端：干净图 → 报告「无需处理」且**不写产物**（写了就是制造假象）
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "blank.png")
        Image.new("RGB", (1024, 1536), (238, 236, 232)).save(p)
        out = os.path.join(d, "out")
        r = subprocess.run([sys.executable, os.path.join(HERE, "pick_wm.py"),
                            p, "--out-root", out],
                           capture_output=True, text=True)
        check("坑29 干净图正常退出", r.returncode == 0, r.stderr[-200:])
        check("坑29 干净图明确报告「无需处理」", "无需处理" in r.stdout,
              r.stdout[-260:])
        check("坑29 零改动不写产物",
              not os.path.exists(os.path.join(out, "_clean", "blank.png")),
              "产物被写出了")


def test_pick_wm_ambiguous_hold():
    """坑 29 增补：参照自身带残留时，**真正去干净的那版反被罚下** —— 此时不许写产物。

    实测 Design43-10（1024x1536 标准图，水印压在纯暗底）：
      v6  残留 93.79  损伤 12.00  总分 105.79
      v7  残留  0.05  损伤  7.86  总分   7.91   ← 目检：水印彻底抹净、手部结构完整
      v8  残留  5.72  损伤  0.00  总分   5.72   ← 目检：「AI生成 WORKBUDDY」清晰残留
      v9  残留  6.12  损伤  0.00  总分   6.12
    参照取自 MODEL_FAMILY(v8/v9)，而 v8 在本图**自身就带 5.72 残留** → 去得最干净的
    v7 反倒成了「偏离参照者」。该图 _clean/ 里的现任产物正是 v7（逐位相同），
    一旦重跑就会被 v8 覆盖掉——这就是本函数要拦的路径。

    规则：胜出版本残留高于某被罚下候选 ≥ AMBIG_DELTA 时，判「数值自相矛盾」，
    **不写产物**（拿不准就不动手），并在报告里把两个候选摆出来交目检。
    """
    P = load("pick_wm")

    def det(**kw):
        d = {k: {"resid": 1.0, "noop": False} for k in P.VERSIONS}
        for k, v in kw.items():
            d[k].update(v)
        return d

    # ① 典型矛盾：胜出 v8 残留 5.72，被罚下的 v7 只有 0.05
    d = det(v7={"resid": 0.05}, v8={"resid": 5.72}, v9={"resid": 6.12})
    got = P.ambiguous_pair(d, "v8")
    check("坑29 检出「残留更低却被罚下」", got == ("v7", 0.05), f"{got}")

    # ② 胜出者本身就是最干净的 → 无矛盾（不许误报）
    check("坑29 胜出者最干净时不误报", P.ambiguous_pair(d, "v7") is None,
          f"{P.ambiguous_pair(d, 'v7')}")

    # ③ 差距未达阈值 → 不报（避免把噪声级差异当矛盾）
    d2 = det(v7={"resid": 3.0}, v8={"resid": 5.72})
    check("坑29 差距未达阈值不报", P.ambiguous_pair(d2, "v8") is None,
          f"{P.ambiguous_pair(d2, 'v8')}")

    # ④ 零改动候选不参与比较：它表达的是「无需处理」，不是「去得更干净」
    d3 = det(v6={"resid": 9.0}, v7={"resid": 0.05, "noop": True},
             v8={"resid": 5.72}, v9={"resid": 8.0})
    check("坑29 零改动候选不作对照", P.ambiguous_pair(d3, "v8") is None,
          f"{P.ambiguous_pair(d3, 'v8')}")

    # ⑤ 胜出者零改动 → 走 noop 分支，不走本分支
    d4 = det(v8={"resid": 5.72, "noop": True})
    check("坑29 胜出者零改动不算矛盾", P.ambiguous_pair(d4, "v8") is None,
          f"{P.ambiguous_pair(d4, 'v8')}")

    # ⑥ 阈值改变即改变行为，必须与坑 29 的记录同步
    check("坑29 AMBIG_DELTA = 5.0", P.AMBIG_DELTA == 5.0, f"{P.AMBIG_DELTA}")


# ── 坑 28 副产物：同名文件的审计结果必须可区分 ───────────────────
def test_audit_unique_keys():
    """旧版 audit_wm 表格只打 basename：同一批传 6 个不同目录的同名文件时
    6 行长得一模一样，被误读成「结果互相覆盖」。JSON 里 name 也只是 basename，
    按 name 建索引的消费方会真的踩中。现在 key=绝对路径 + 显示名带父目录。
    """
    import json
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        for sub, color in (("d1", (250, 250, 250)), ("d2", (120, 30, 30))):
            os.makedirs(os.path.join(d, sub))
            Image.new("RGB", (1024, 1536), color).save(
                os.path.join(d, sub, "same.png"))
        out = os.path.join(d, "r.json")
        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "audit_wm.py"),
             os.path.join(d, "d1", "same.png"),
             os.path.join(d, "d2", "same.png"), "--json", out],
            capture_output=True, text=True)
        check("坑28 audit_wm 同名文件正常退出", r.returncode == 0, r.stderr[-200:])
        if r.returncode != 0:
            return
        data = json.load(open(out, encoding="utf-8"))
        check("坑28 同名文件产出 2 行", len(data) == 2, f"实际 {len(data)}")
        check("坑28 key 唯一（绝对路径，不用 basename）",
              len({row["key"] for row in data}) == 2,
              f"{[row['key'] for row in data]}")
        check("坑28 表格显示名带父目录消歧",
              "d1/same.png" in r.stdout and "d2/same.png" in r.stdout,
              "同名行仍无法区分")


def test_wm_metrics_reference_free():
    """坑 30：① amp 随背景变化（白底被压 ~26 倍）② 白蚀单向性可当参照无关的损伤判据。

    这两条都是 2026-09-13 复检时挖出来的：
    - amp = k̂·mean(a·(255−bg))。白纸底 (255−bg≈9) 与纯黑底 (≈238) 相差约 26 倍，
      而本技能的竖版海报绝大多数是白底 → **amp 在主力图种上几乎测不出残留**
      （03_labor 上 v7 有明显灰糊斑，amp 仅 0.21 判 CLEAN）。背景无关的量是 α̂ = k̂。
    - 白蚀单向性：I = α·C + (1−α)·orig ⇒ orig ≤ I（I ≤ 255 时恒成立），
      去白水印**只能变暗**。out > I 的像素必然是损伤，且**不需要参照图**。
    断言必须同时覆盖「能报」和「不误报」两侧。
    """
    import numpy as np
    import cv2
    from PIL import Image
    import audit_wm
    import dewm_v9
    import dewm_v13

    with tempfile.TemporaryDirectory() as d:
        # ---- ① 白蚀单向性：恒等不算违反 / 提亮才算 ----
        a = np.full((60, 80, 3), 128, np.uint8)
        v0 = audit_wm.brightening_violation(a, a)
        check("坑30 恒等输出无提亮违反", v0["bad_px"] == 0 and v0["max_lift"] == 0,
              str(v0))

        b = a.copy(); b[10, 10] = 138          # +10
        v1 = audit_wm.brightening_violation(a, b)
        check("坑30 单点提亮 10 被计入", v1["bad_px"] == 1 and v1["max_lift"] == 10,
              str(v1))

        c = a.copy(); c[10, 10] = 130          # 恰好 +2 = tol 边界
        check("坑30 tol 边界不误报（严格大于）",
              audit_wm.brightening_violation(a, c, tol=2)["bad_px"] == 0,
              "tol=2 时 +2 被判违法")

        dk = a.copy(); dk[::2, ::2] = 100      # 只变暗
        check("坑30 只变暗绝不违反（单向性）",
              audit_wm.brightening_violation(a, dk)["bad_px"] == 0,
              "变暗被误判成损伤")

        # ---- ② amp 的背景依赖性（本轮发现的度量缺陷）----
        wp = os.path.join(d, "white.png")
        Image.new("RGB", (1024, 1536), (250, 250, 250)).save(wp)
        dp = os.path.join(d, "dark.png")
        Image.new("RGB", (1024, 1536), (20, 20, 20)).save(dp)
        fw = audit_wm.background_factor(cv2.imread(wp))
        fd = audit_wm.background_factor(cv2.imread(dp))
        check("坑30 白底 bg_scale 远小于暗底（amp 被压）",
              fd / max(fw, 1e-6) > 10.0,
              f"白底 {fw:.2f} / 暗底 {fd:.2f}，比值不足 10，缺陷未复现")

        r = audit_wm.estimate_residual(cv2.imread(dp))
        check("坑30 estimate_residual 暴露背景无关的 alpha/bg_scale",
              "alpha" in r and "bg_scale" in r and abs(r["alpha"] - r["k"]) < 1e-9,
              f"keys={sorted(r)}")

        # ---- ③ v13：干净图必须逐位不变（无感底线）----
        img = cv2.imread(wp)
        out13, st13 = dewm_v13.remove_watermark(img)
        check("坑30 v13 干净图逐位不变（零改动）",
              np.array_equal(out13, img), f"k={st13['k']:.3f} 但输出被改动")

        # ---- ④ v13：合成本印图上残留必须显著下降 ----
        g = cv2.imread(dp)
        a_t, (x0, y0) = dewm_v9.load_template(1024, 1536)
        al = np.clip(0.91 * a_t, 0, 0.98)[:, :, None]
        sub = g[y0:y0 + a_t.shape[0], x0:x0 + a_t.shape[1]].astype(np.float32)
        g2 = g.copy()
        g2[y0:y0 + a_t.shape[0], x0:x0 + a_t.shape[1]] = np.clip(
            al * 255.0 + (1 - al) * sub, 0, 255).astype(np.uint8)
        k_before = audit_wm.estimate_residual(g2)["alpha"]
        out13b, st13b = dewm_v13.remove_watermark(g2)
        k_after = abs(audit_wm.estimate_residual(out13b)["alpha"])
        check("坑30 v13 合成本印残留显著下降",
              k_before > 0.5 and k_after < k_before * 0.25,
              f"拟合 k={k_before:.3f} → 残留 {k_after:.3f}")
        check("坑30 v13 不违反白蚀单向性",
              audit_wm.brightening_violation(g2, out13b)["bad_px"] == 0,
              str(audit_wm.brightening_violation(g2, out13b)))


def test_v13_wiener_invariants():
    """v13（Wiener 融合）的三条硬不变量 —— 2026-09-13 实测确认后锁死（坑 32）。

    ① **无水印图（k̂≤0）→ 输出逐位等于原图**：α = clip(k·a)，k≤0 时 α≡0，
       逐位 `np.where(α>0, blend, sub)` 全部取 sub。这是「无感」底线
       （对照 01_mistgate：干净图上任何改动都是净损失，v8 曾把画面压暗 13.87 灰阶）。
    ② **白蚀单向性**：去白水印只能变暗（orig ≤ I），任何提亮都是损伤。
       v13 靠 `B ← min(sub_bg, I)` 保证，**不再夹最终结果**——夹结果会在先验偏亮时
       把该减的地方也挡住。实测 87 张真水印图违反 0 px（v8 1800 / v12 3654）。
    ③ **Wiener 权重单调**：w = t²/(t²+c²) 随 α 增大而减小 → α 大处更信 inpaint、
       α 小处更信反解。这条正是 v13 能在低 conf 图上胜过纯反解的原因。
    """
    import numpy as np
    V13 = load("dewm_v13")
    V9 = load("dewm_v9")
    W, H = 1024, 1536
    a, (x0, y0) = V9.load_template(W, H)
    ah, aw = a.shape

    # ① 水印位置比周围暗 ⇒ 不符合「白蚀」模型 ⇒ k̂ ≤ 0 ⇒ 必须零改动
    flat = np.full((H, W, 3), 240, np.uint8)
    flat[y0:y0 + ah, x0:x0 + aw] = 170
    out, st = V13.remove_watermark(flat)
    check("坑32 v13 无水印图零改动（k̂≤0 ⇒ 输出逐位=原图）",
          np.array_equal(out, flat), f"k={st['k']:.3f}，输出与原图不同")

    # ② 注入水印后检查：单向性 + 只改模板框内
    base = (np.random.RandomState(11).rand(H, W, 3) * 60 + 150).astype(np.uint8)
    wm = base.copy()
    reg = wm[y0:y0 + ah, x0:x0 + aw].astype(np.float32)
    al = np.clip(0.85 * a, 0, 0.98)[:, :, None]
    wm[y0:y0 + ah, x0:x0 + aw] = np.clip(al * 255.0 + (1 - al) * reg, 0, 255).astype(np.uint8)
    out2, st2 = V13.remove_watermark(wm)
    d = out2.astype(np.int16) - wm.astype(np.int16)
    check("坑32 v13 白蚀单向性：无提亮（>1 灰阶即违反）",
          int(d.max()) <= 1, f"最大提亮 {int(d.max())} 灰阶")
    bx0, by0, bx1, by1 = st2["box"]
    mask = np.ones((H, W), bool)
    mask[by0:by1, bx0:bx1] = False
    check("坑32 v13 只改模板框内（框外逐位不变）",
          np.array_equal(out2[mask], wm[mask]), "框外像素被改动")

    # ③ Wiener 增益的单调性（设计意图，与实现解耦的数学断言）
    ok = True
    for c in (0.2, 1.0, 3.0, 10.0):
        ts = np.linspace(0.05, 1.0, 20)
        ws = ts * ts / (ts * ts + c * c)
        if not np.all(np.diff(ws) > 0):
            ok = False
    check("坑32 v13 Wiener 权重随 α 单调（α 大 ⇒ 更信 inpaint）",
          ok, "w=t²/(t²+c²) 非单调递增于 t")


def test_wm_auto_gate():
    """v1.13 新增自动水印识别。核心风险不是「认不出水印」，而是**误认**：
    自动模式判错 = 主动改坏一张已经画好的图，比报告模式看错一行字严重得多。

    因此这条断言钉死「高 amp 但低 R² 必须落 manual，不许 remove」：
    audit_wm 文档写明低 R² 是高频纹理的典型特征，而纸纹/网点/格边正是本技能
    主力产出（类型 A 纸纹、类型 E 精灵图）。实测分布见 scripts/wm_auto.py 文档。
    """
    wm = load("wm_auto")
    cases = [
        (0.5, 0.90, "skip", "无可见水印"),
        (-0.79, 0.20, "skip", "实测干净图（本机 3 张：amp -0.79~-0.69）"),
        (20.69, 0.76, "remove", "实测带水印图（本机 11 张：R² 0.76~0.96）"),
        (45.48, 0.96, "remove", "最强残留"),
        (5.0, 0.10, "manual", "高 amp 低 R² = 高频纹理误报，不许自动动手"),
        (2.0, 0.30, "manual", "R² 不足闸门"),
        (1.6, 0.88, "manual", "SUSPECT 区，交人 / pick_wm"),
    ]
    for amp, r2, want, why in cases:
        got, _ = wm.decide(amp, r2)
        check(f"wm_auto 闸门 amp={amp} R²={r2} → {want}", got == want,
              f"{why}；实际 {got}")


def test_wm_auto_never_touches_original():
    """自动去水印必须**不覆盖原图**（dewm_io 守卫的延伸保证）。

    原图被覆盖 = 不可回溯，且「去水印没去干净」时连重来的底都没了。
    用干净图跑 --remove：既不写文件，也绝不动原文件。
    """
    import hashlib
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "clean.png")
        Image.new("RGB", (1024, 1536), (250, 250, 250)).save(src)
        before = hashlib.sha256(open(src, "rb").read()).hexdigest()

        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "wm_auto.py"), src, "--remove"],
            capture_output=True, text=True)
        after = hashlib.sha256(open(src, "rb").read()).hexdigest()
        check("wm_auto 干净图不写输出",
              not os.path.exists(os.path.join(d, "clean_dewm.png")),
              "干净图被动了手")
        check("wm_auto 原图逐位未改", before == after, "原图被改坏")
        check("wm_auto --remove 干净图退出码 0", r.returncode == 0,
              f"rc={r.returncode}")


# ── 缺依赖时必须说人话（普适性）────────────────────────────────────
def test_missing_dep_message():
    """2026-09-18：依赖不保证在每个解释器里都有（实测本机 managed 3.13 无 cv2、
    系统 python3 有）。用户直接调脚本时，缺依赖抛的是 `No module named 'cv2'`
    ——看不出该装什么、该换哪个解释器。这条锁住「人话 + 可执行的两条修复路径」，
    同时锁住**不得退化成 traceback**。
    """
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        shim = os.path.join(d, "shim")
        os.makedirs(shim)
        with open(os.path.join(shim, "cv2.py"), "w", encoding="utf-8") as f:
            f.write('raise ImportError("simulated missing cv2")\n')
        img = os.path.join(d, "a.png")
        Image.new("RGB", (64, 64), (250, 250, 250)).save(img)
        env = dict(os.environ, PYTHONPATH=shim)
        for script, extra in (("dewm_v10.py", []), ("pick_wm.py", [d])):
            r = subprocess.run([sys.executable, os.path.join(HERE, script), img, *extra],
                               capture_output=True, text=True, env=env)
            out = r.stdout + r.stderr
            check(f"{script} 缺 cv2 时给出人话而不是 traceback",
                  "Traceback" not in out and "依赖不可用" in out,
                  f"rc={r.returncode} out={out[-200:]!r}")
            # 2026-09-23 CI 修：原断言要求出现 "workbuddy/binaries/python"——那是**本机
            # 专有串**，CI runner 上必然没有（本地绿、CI 红，192/194）。改断言**行为**：
            # ① 必须给出「换解释器重跑」这条路径；② 若它点名了解释器，那些解释器必须
            # 真实存在；③ 一个都点不出来时必须明说「没找到」，不得含糊过去。
            line = next((l for l in out.splitlines() if "换解释器重跑" in l), "")
            named = [p for p in line.replace("：", " ").split() if p.startswith("/")]
            honest = all(os.path.exists(p) for p in named) if named else ("没找到" in line)
            check(f"{script} 缺依赖时提示换解释器这条可执行路径",
                  "换解释器重跑" in out and honest,
                  f"named={named} line={line!r}")
            check(f"{script} 缺依赖退出码为 2（环境未就绪，区别于用法错误）",
                  r.returncode == 2, f"rc={r.returncode}")

        # 判据本身单独测（不上 shim，用真实环境）：报出来的必须**真的能导入**依赖；
        # 本机有能导入的候选时不得一个都不报。这两条是 2026-09-23 那次 CI 红的根因守卫：
        # 原先只判「文件存在」，于是 runner 上的 /usr/bin/python3（无 cv2）被当成可用路径。
        env_mod = load("_env")
        found = env_mod._living_interpreters(["cv2", "numpy", "PIL"])
        check("_living_interpreters 只报真的能导入依赖的解释器",
              all(subprocess.run([p, "-c", "import cv2, numpy, PIL"],
                                 capture_output=True).returncode == 0 for p in found),
              f"found={found}")
        cur = os.path.realpath(sys.executable)
        good = [c for c in env_mod.best_interpreter()
                if os.path.exists(c) and os.path.realpath(c) != cur
                and subprocess.run([c, "-c", "import cv2, numpy, PIL"],
                                   capture_output=True).returncode == 0]
        check("_living_interpreters 不漏报：本机有能导入的候选时必须至少报出一个",
              (not good) or bool(found), f"good={good} found={found}")


TESTS = [test_overwrite_guard, test_solvability_guard, test_pick_wm_damage_aware,
         test_pick_wm_noop_policy, test_pick_wm_ambiguous_hold,
         test_audit_unique_keys, test_wm_metrics_reference_free,
         test_v13_wiener_invariants, test_wm_auto_gate,
         test_wm_auto_never_touches_original, test_missing_dep_message]
