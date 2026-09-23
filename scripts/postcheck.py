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
  blocker  真错，或 --text bad / 留白挤成一团 / 尺寸与格数不符 → 允许一次定向重生
  pending  能免费修的（纸白偏暖 → paper_white.py）、文字未核对、水印存疑 → 不得计 pass
  pass     指标在阈值内 且 文字逐字无误
退出码：0=pass，1=blocker，3=pending，**4=工具/环境错误（未判定，不是 blocker）**。

**为什么纸白偏暖走 pending 而不是 blocker**（2026-09-18）：
重生改不了这个偏色——坑 33 实测同一提示词两版，纸白均值都是 R237.6/G235.5/B232.0
（R-B=+5.5），把「三通道数值几乎相等」写进硬底线也纹丝不动。判 blocker 等于
每次白扣 5–10 积分。正确补救是 `paper_white.py` 确定性归正（免费、只动纸白像素）。

每行 findings 都带 **reason 码**，写进 runs.csv 的 `reason` / `hint` 两列，
这样「这张图为什么没通过 / 为什么被重出」可以直接统计，不必翻日志猜。
"""

import _log
import argparse
import csv
import os
import sys
from datetime import datetime

try:
    from PIL import Image
except ImportError as _e:          # 缺依赖时说人话，别甩 traceback（见 scripts/_env.py）
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import _env
    _env.die(_e, ['PIL'])

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "logs", "runs.csv")

CSV_COLS = ["ts", "file", "track", "size", "base", "white_pct", "paper_pct",
            "R-B", "sat", "top_noise", "top_dev", "text", "verdict",
            "reason", "hint", "note"]

# ── 判据阈值（唯一真源；改动必须同步 sub-skills/verify/evidence.md）──────
# 每个数值后面都跟着 2026-09-18 用 202 张**已归档成品**实测的触发率
# （复算工具：scripts/calibrate_thresholds.py）。触发率是选阈值的第一判据：
# postcheck 判 blocker = 允许一次定向重生 = 再扣 5–10 积分，判据在成品上高频
# 触发就不是检测器，而是积分黑洞（坑 27 的 top_noise 13/13 全灭就是这么来的）。
WHITE_BASE_MIN = 240.0   # base ≥ 此值才认为「这张图本该是白的」→ 触发率 4.3%
PAPER_WARM_RB = 3.0      # 留白区 R-B 达此值＝纸白被渲染成暖白（坑 33）
TOP_INTRUDE_DEV = 12.0   # 顶部低频结构偏离（仅诊断：成品触发率 64.9%，属风格张力）
TOP_ZONE_LOW = 50.0      # 顶部相对留白占比低于此值（仅诊断）
# 类型 B 的「挤成一团」：**只给提示，不判 blocker**。两个候选口径都被实测否掉：
#   · 旧口径 white%∈[30,65]：min(RGB)>240 在纸底图上恒为 0（measure.py 2026-09-07
#     已记录该缺陷），在 202 张已归档成品上触发 **82.2%**。
#   · 候选 paper%（min>base−8）：base 取的是中位数，按定义 ≈50% 的像素 ≥ base，
#     所以 paper% 恒 ≥50%（实测最小值 50.2）——`paper%<30` 是永远不可能触发的
#     结构性死判据，看着「0% 触发很干净」，其实是判据本身不会响。
#   · 候选 near%（min>215，浅色占比）：在 base≥200 的子集（n=83）里 `<40` 仍占 12%，
#     而本地没有成体系的负样本（真翻车图）来证明它抓的是「挤」而不是「画得满」。
# 结论：类型 B 的图像侧只报可测提示，拦「挤成一团」的职责在 prompt 侧
# （可数约束已并入主模板）+ 目检。见 sub-skills/verify/evidence.md 的校准记录。
CROWD_NEAR_PCT = 40.0    # 浅色占比低于此值 → 提示「可能挤成一团」（仅提示）
CROWD_BASE_MIN = 200.0   # 只对浅底图提示（暗底/满铺设计不适用留白占比）
SAT_MAX = 70.0           # 类型 B 平均饱和度上限 → 触发率 3.0%


_SIBLINGS = {}


def _sibling(name):
    """按名字加载 scripts/ 下的兄弟模块，**进程内只加载一次**。

    2026-09-23（对抗性审查实测）：原先每张图都重新 `exec_module` 一遍，`measure.py`
    16.3 ms/次、`wm_auto.py` 35.3 ms/次（含 cv2 / audit_wm / dewm_io 的导入链）——
    9 张一批就是 ~0.5 s，纯重复开销。这些模块是无状态的（常量 + 纯函数），
    跨图复用没有副作用；`--log-path` 这类状态本来是参数传入的，不靠模块全局。
    """
    mod = _SIBLINGS.get(name)
    if mod is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(name.replace(".py", ""),
                                                     os.path.join(HERE, name))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _SIBLINGS[name] = mod
    return mod


def measure_findings(row, track, with_top, expect_cells=None, grid=None):
    """按类型判定，返回 (blockers, pendings, hints)。

    每项是 `(reason_code, 中文说明)`。三条纪律来自 2026-09-18 用 202 张已归档
    成品做的校准（scripts/calibrate_thresholds.py 可复算）：

      1. **能免费修的，不许判 blocker。** 纸白偏暖由 `paper_white.py` 确定性归正
         （坑 33：提示词压不下来、重生只是再花 5–10 积分）→ 走 pending。
      2. **绝对值阈值必须分场景。** R-B 只在「本该是白」的图上判（base ≥ 240，
         该子集触发率 4.3%）；纸底/纹理底的暖色是材质色（子集触发率 63%），
         拿它判 blocker 等于禁止纸底风格——旧口径在成品上触发 46.5%。
      3. **风格张力不判 blocker。** 顶部留白被母题侵入在 4/9 风格里是设计结果
         （pitfalls 待解决表明写「不再重出」），旧口径触发 64.9% → 降为诊断。
         类型 B 的留白占比也换相对口径 paper%（旧 white% 在纸底图上恒为 0，
         触发 82.2%；paper% < 30 触发 0.0%）。

      A 海报   纸白偏暖（pending）/ 顶部侵入（诊断）
      B 群像   留白挤成一团 / 饱和度
      C 包装   灰底棚拍，暖色判据不适用（references/packaging-editorial.md §三 规则 8）
      D 分镜   叙事性暖色豁免；尺寸是声明值，不符即真错
      E 多格   格数 / 每格等比例 / 格间净空（references/multigrid-layout.md §三）
    """
    blockers, pendings, hints = [], [], []
    base = row.get("base", 0)

    # ── 纸白偏暖：能免费修 → pending（不是 blocker）─────────────────
    if track in ("A", "B") and row["R-B"] >= PAPER_WARM_RB:
        if base >= WHITE_BASE_MIN:
            pendings.append(("paper_warm",
                f"纸白偏暖 R-B={row['R-B']:.1f}（base={base:.0f}，本该是白）——"
                f"先跑 scripts/paper_white.py 确定性归正（免费、只动纸白像素），不要重生"))
        else:
            hints.append(("paper_warm_hint",
                f"纸底偏暖 R-B={row['R-B']:.1f}（base={base:.0f}）属材质色；"
                f"若要更中性可跑 paper_white.py"))

    if with_top and track == "A":
        if row.get("top_R-B", 0) >= PAPER_WARM_RB and base >= WHITE_BASE_MIN \
                and not any(c == "paper_warm" for c, _ in pendings):
            # 与上面是**同一件事**（留白偏暖），同一张图只报一条，避免并列两条
            # 让读者不知道信哪条（2026-09-18）
            pendings.append(("paper_warm",
                f"顶部留白偏暖 top_R-B={row['top_R-B']:.1f}（base={base:.0f}）——"
                f"先跑 scripts/paper_white.py，不要重生"))
        if row.get("top_dev", 0) >= TOP_INTRUDE_DEV or row.get("top_zone%", 100) < TOP_ZONE_LOW:
            hints.append(("top_intruded",
                f"顶部留白被内容侵入（dev={row.get('top_dev', 0):.1f} "
                f"zone%={row.get('top_zone%', 0):.1f}）——属风格张力，不判 blocker；"
                f"目检后自行取舍（pitfalls 待解决表）"))

    if track == "B":
        if base >= CROWD_BASE_MIN and row.get("near%", 100) < CROWD_NEAR_PCT:
            hints.append(("crowded_hint",
                f"浅色（留白）只占 {row.get('near%', 0):.0f}%（<{CROWD_NEAR_PCT:.0f}）"
                f"——可能挤成一团，请目检；拦它的正手在 prompt 侧的可数约束"))
        if row["sat"] > SAT_MAX:
            blockers.append(("sat_blown", f"饱和度 {row['sat']:.1f} > {SAT_MAX:.0f}"))

    # 类型 D：尺寸是声明值，不符即真错（storyboard.md §五「精确输出 1024x1792」）
    if track == "D" and row["size"] != "1024x1792":
        blockers.append(("size_mismatch",
                         f"尺寸不符：{row['size']}，类型 D 声明 1024x1792（4:7）"))

    if track == "E":
        hard, diag = grid_warnings(grid, expect_cells)
        blockers += [("cell_count", m) for m in hard]
        hints    += [("grid_diag", m) for m in diag]

    return blockers, pendings, hints


def grid_warnings(grid, expect_cells=None):
    """类型 E 的网格结构判定。返回 (硬警告, 诊断行)。

    判定口径的诚实边界（2026-09-12）：
      - 格数不符 = **硬警告**。fill_meta 已在 prompt 侧校验「格数=清单条数」，
        图像侧再对不上就是「说的和画的不是一回事」，属真错。
        仅在给了 --expect-cells 时才判，避免猜用户声明了几格。
      - 每格尺寸不一致 = **诊断行**，不判 blocker。阈值 0.90 来自本机合成基准
        （一致网格 cell_uniform=1.0，某格窄 60px=0.825、矮 30%=0.70），
        尚未在真实多格产出上重标，故只报不拦。
      - 网格解析失败 = **诊断行**。「无缝隙、边框像素对齐」是合法 E 变体，
        此时本就解析不出净空，误判成 blocker 等于禁止合法写法。
    """
    hard, diag = [], []
    if not grid or not grid.get("ok"):
        diag.append(f"网格未解析（{grid.get('note', '') if grid else '未量测'}）："
                    f"可能是「无缝隙」合法变体，请目检格数与间隔")
        return hard, diag
    if expect_cells and grid["cells"] != expect_cells:
        hard.append(f"格数不符：图上 {grid['cells']} 格（{grid['rows']}行×{grid['cols']}列），"
                    f"声明 {expect_cells} 格")
    cu = grid.get("cell_uniform")
    if cu is not None and cu < 0.90:
        diag.append(f"每格尺寸不一致 cell_uniform={cu:.2f}（<0.90，待真实产出重标）")
    if not grid.get("gap_px"):
        diag.append("格间未检出净空（可能是无缝隙变体，也可能是各格糊成一片）")
    return hard, diag


def export_textband(path, im):
    """底部文字带 2x 放大裁片（类型 A 目检逐字用）。"""
    W, H = im.size
    y0 = int(H * 0.78)
    band = im.crop((0, y0, W, H))
    band = band.resize((W * 2, (H - y0) * 2), Image.LANCZOS)
    out = os.path.splitext(path)[0] + "_textband.png"
    band.save(out)
    return out


def align_log(log_path):
    """把 runs.csv 的表头对齐到 CSV_COLS；返回 True 表示还需要写表头。

    **为什么不能只在文件不存在时写表头**（2026-09-18 实测）：
    v1.19 给 CSV_COLS 加了 reason / hint 两列，但老机器上那份 runs.csv 的表头还是
    旧的 14 列，而原实现只在「文件不存在」时写表头——于是此后每一行都会错位。
    实测本机 27 行里 15 行错位，表头最后一列 `note` 里装的其实是 reason 码，
    正好废掉 reason 码自己要解决的问题（「这张图为什么重出」可归因）。

    测试没拦住是因为 `test_reason_codes_recorded` 每次用全新的临时文件，
    **永远拿到新表头**——门禁只跑了「干净夹具」，没跑「从旧版升上来」的夹具。
    这里按列名迁移旧行（列义可映射就不丢历史），认不出表头时留备份后重开。
    """
    if not os.path.exists(log_path) or os.path.getsize(log_path) == 0:
        return True
    try:
        with open(log_path, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
    except (OSError, UnicodeDecodeError):   # 读不了就别动它，交给下游报错
        return False
    if not rows:
        return True
    head, data = rows[0], rows[1:]
    if head == CSV_COLS:
        return False

    bak = f"{log_path}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    try:
        with open(bak, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
    except OSError as e:
        print(f"warn    runs.csv 表头过旧且备份失败（{e}），本次不迁移", file=sys.stderr)
        return False

    with open(log_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLS)
        if set(head) <= set(CSV_COLS):
            # 逐行按**它自己的**列序归位。混排是旧表头的直接后果，两种行都要照顾：
            #   · 字段数 == 当前列数 → 该行本就是新列序（旧表头配新格式行），
            #     按旧列名映射会把末两列读成 hint / note，**丢数据**；
            #   · 否则按表头名映射，缺失列补空。
            # 实测：真实日志 27 行里 15 条是新格式行，其中 12 条带 note
            # （如「复刻版去水印」），一律按名映射会把它们全部改写掉。
            #
            # 只在「表头不符」时做这件事：表头已对而个别行偏短的日志，本工具自己
            # 写不出来（append_log 每次写满整行），真遇到也无法判定那些行按哪套
            # 列序排，猜比不猜更坏——那时按当前表头名映射会把旧 note 读成 reason。
            def emit(r):
                if len(r) == len(CSV_COLS):
                    w.writerow(r)
                else:
                    d = dict(zip(head, r))
                    w.writerow([d.get(c, "") for c in CSV_COLS])
            for r in data:
                emit(r)
            print(f"note    runs.csv 表头过旧（{len(head)} 列 ≠ {len(CSV_COLS)} 列），"
                  f"已按列名迁移 {len(data)} 行；原文件备份为 {os.path.basename(bak)}")
        else:
            # 认不出列义就不猜，留备份后重开——错位记账比如实记账更坏
            print(f"warn    runs.csv 表头无法识别，已备份为 {os.path.basename(bak)} "
                  f"并重新记账（原 {len(data)} 行不再并入）", file=sys.stderr)
    return False


def append_log(row, track, text, verdict, note, reason="", hint="", no_log=False,
               log_path=None):
    """追加一行运行记录。no_log=True 时跳过（跑测试/验证不污染生产记账）。"""
    if no_log:
        return
    log_path = log_path or LOG_PATH
    d = os.path.dirname(log_path)
    if d:                                # 裸文件名（cwd 下）时 dirname 为空，makedirs("") 会抛
        os.makedirs(d, exist_ok=True)
    need_header = align_log(log_path)
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if need_header:
            w.writerow(CSV_COLS)
        w.writerow([
            row.get("ts", ""), row["file"], track, row["size"],
            f"{row['base']:.0f}", f"{row['white%']:.1f}", f"{row['paper%']:.1f}",
            f"{row['R-B']:.1f}", f"{row['sat']:.1f}",
            f"{row.get('top_noise', 0):.1f}" if "top_noise" in row else "",
            f"{row.get('top_dev', 0):.1f}" if "top_dev" in row else "",
            text, verdict, reason, hint, note,
        ])


def process(path, args):
    metrics = _sibling("measure.py").metrics
    with_top = bool(args.top and args.track == "A")
    im, row = metrics(path, with_top)
    row["ts"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 类型 E：网格结构量测（格数 / 每格等比例 / 格间净空）。
    # **必须在唯一一次 measure_findings 之前量完**（2026-09-23 修）。
    # 原先是「先无 grid 调一次、再带 grid 调一次、结果相加」：第一次调用的
    # `grid_warnings(None)` 会留下一条假的「网格未解析（未量测）」，即使网格
    # 明明解析成功也照报——实测 3 行×1 列已正确识别，控制台仍并列打出
    # 「网格未解析（未量测）」，runs.csv 里也稳定出现两个 `grid_diag`。
    # 诊断里混进一条必然为假的行，代价是读者开始不信诊断。
    # 传 im：metrics() 已经把这张图解出来了，grid_metrics 不必再解码一次（类型 E 省一次全图解码）
    grid = _sibling("measure.py").grid_metrics(path, im) if args.track == "E" else None
    blockers, pendings, hints = measure_findings(
        row, args.track, with_top, args.expect_cells, grid)

    # 文字带裁片：A 有文字带必导；C 有品牌堆叠字，同样需要目检
    band = None
    if args.track in ("A", "C"):
        band = export_textband(path, im)

    # 水印：自动识别 → 命中才动手（v1.13 起默认 auto，见 scripts/wm_auto.py）
    # 为什么不再是无脑 --dewm：水印存在与否由宿主与会员状态决定，干净图上动手
    # 等于主动改坏画面。auto 模式先识别，且要求 amp 与 R² 双条件达标才动手。
    dewm_out = None
    dewm_tag = ""
    wm_state = None
    if args.wm != "off":
        wm_auto = vars(_sibling("wm_auto.py"))
        if args.wm == "force":
            wm = wm_auto["remove_and_verify"](path)
            if wm["attempted"] and wm["out_path"]:
                dewm_out = wm["out_path"]
                a, b = wm["before"], wm["after"]
                dewm_tag = (f"amp {a['amp']:.2f}→{b['amp']:.2f} "
                            f"R² {a['r2']:.2f}→{b['r2']:.2f}")
                if not wm["verified"]:
                    hints.append(("wm_failed", f"去水印复检未通过：{wm['note']}"))
            else:
                hints.append(("wm_skipped", f"去水印未执行：{wm['note']}"))
            wm_state = "forced"
        else:
            d = wm_auto["detect"](path)
            if d["action"] == "skip":
                wm_state = "none"
                hints.append(("wm_none", f"水印：无可见水印（{d['reason']}），未改动画面"))
            elif d["action"] == "manual":
                # 存疑分流（2026-09-12 实测修正）：
                #   R² 达标 → 确实存在形状吻合的残留，是真存疑 → 记 pending，
                #             正确补救是 pick_wm / 云端 erase，不是重生
                #   R² 不足 → audit_wm 文档写明这多半是高频纹理误报（格边、网点、
                #             马赛克），**不拦 pass**。让误报逼出返工，正是 top_noise
                #             那条教训（假 blocker 每张白扣 5-10 积分）
                if d["r2"] >= wm_auto["AUTO_R2_THR"]:
                    wm_state = "manual"
                    hints.append(("wm_manual",
                                   f"水印存疑，未自动处理：{d['reason']}；"
                                   f"建议 pick_wm.py 四版选优或云端 erase"))
                else:
                    wm_state = "none"
                    hints.append(("wm_texture",
                                   f"水印区有非水印形状的残差（amp={d['amp']:.2f} "
                                   f"R²={d['r2']:.2f}）：判为纹理/格边误报，不拦交付"))
            else:
                wm = wm_auto["remove_and_verify"](path)
                if wm["out_path"]:
                    dewm_out = wm["out_path"]
                    a, b = wm["before"], wm["after"]
                    dewm_tag = (f"amp {a['amp']:.2f}→{b['amp']:.2f} "
                                f"R² {a['r2']:.2f}→{b['r2']:.2f}")
                    wm_state = "removed" if wm["verified"] else "failed"
                    hints.append(("wm_removed", wm["note"]))
                else:
                    wm_state = "failed"
                    hints.append(("wm_failed", wm["note"]))

    # verdict 三档（对齐 SKILL.md §3 评审卡）：
    #   blocker    量测越界 / 文字判 bad  → 允许一次定向重生
    #   pending    文字未核对 或 水印待处理 → 不得计 pass，需处理后回填
    #   pass       指标在阈值内 且 文字逐字无误 且 水印已清零
    text = args.text or "unverified"
    if text == "bad":
        blockers.append(("text_bad", "文字逐字核对不通过（--text bad）"))
    if blockers:
        verdict = "blocker"
    elif text == "unverified":
        pendings.append(("text_unverified", "文字未核对（未传 --text），不得计 pass"))
        verdict = "pending"
    elif wm_state in ("manual", "failed"):
        pendings.append((f"wm_{wm_state}", "水印存疑或去除失败，需处理后回填"))
        verdict = "pending"
    elif pendings:
        verdict = "pending"
    else:
        verdict = "pass"
    reason = ",".join(c for c, _ in blockers) or ",".join(c for c, _ in pendings)
    hint = ",".join(c for c, _ in hints)
    append_log(row, args.track, text, verdict, args.note or "", reason, hint,
               no_log=args.no_log, log_path=args.log_path)

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
    if grid and grid.get("ok"):
        print(f"  网格: {grid['rows']}行×{grid['cols']}列 = {grid['cells']}格  "
              f"格间净空={grid['gap_px']}px  "
              f"格尺寸一致性={grid.get('cell_uniform')}")
    if dewm_out:
        print(f"  去水印: {dewm_out}  {dewm_tag}")
    for code, msg in hints:
        print(f"  · [{code}] {msg}")
    for code, msg in blockers:
        print(f"  ❌ [{code}] {msg}")
    for code, msg in pendings:
        print(f"  ⏳ [{code}] {msg}")
    # --no-log 时不能说「→ runs.csv」（2026-09-23 修）：文案声称落盘、实际没落，
    # 是那种「看起来有、其实没有」的记账，比不写更坏。
    print(f"  verdict={verdict} text={text} → "
          f"{'runs.csv' if not args.no_log else '（--no-log，未落盘）'}")
    return verdict


def exit_policy(verdicts, tool_errors, skipped):
    """跑完之后该以什么码退出 —— 这条优先级是本脚本对外唯一的契约，收在一处。

    原先散成五个 `if` 各自 print 一段文案，读者要核对「4 和 3 谁优先」得来回跳，
    而每次新增一类未判定状态（这轮就新增了 tool_errors 与 skipped）都要在 5 处插桩。
    现在它是纯函数：给定三类结果，返回 (退出码, 结语)。调用方只剩 sys.exit 一行。

    优先级（高 → 低）：
      2/4  一张都没判定出来：工具/环境问题 → 4；只是没给图/图都不存在 → 2
      1    有 blocker（真错，允许一次定向重生）
      4    有图未判定（工具/环境错误、路径不存在）——**不是 blocker，不要重生**
      3    都是 pending（待处理，不得计通过）
      0    pass
    """
    undecided = len(tool_errors) + len(skipped)
    if not verdicts:
        if undecided:
            return 4, "❌ 全部图片都因工具/环境错误未能判定 —— **不是 blocker，不要据此定向重生**；" \
                      "先修环境（依赖/路径/权限）再重跑"
        return 2, ""
    if any(v == "blocker" for v in verdicts):
        return 1, "❌ blocker —— 按三档评审卡：才允许一次定向重生，只改一项"
    if undecided:
        detail = "、".join([n for n, _ in tool_errors[:3]] + skipped[:3])
        return 4, (f"⚠️ 另有 {undecided} 张未判定（工具/环境错误或路径不存在，"
                   f"**不是 blocker，不要重生**）：{detail}")
    if any(v == "pending" for v in verdicts):
        return 3, ("⏳ pending —— 指标在阈值内，但仍有未结项（文字未逐字核对，"
                   "或水印存疑待 pick_wm / 云端处理）；处理完再回填，pending 不得当作通过")
    return 0, "✅ pass（指标在阈值内 + 文字逐字无误）"


def main():
    ap = argparse.ArgumentParser(description="出图后一次调用：量测+裁片+去水印+记账")
    ap.add_argument("images", nargs="+")
    ap.add_argument("--track", choices=["A", "B", "C", "D", "E"], default="A",
                    help="A=竖版概念海报（默认），B=手绘群像，C=包装 Mockup，D=叙事分镜，E=多格排版")
    ap.add_argument("--top", action="store_true", help="加测顶部留白（类型 A 必用）")
    ap.add_argument("--wm", choices=["auto", "force", "off"], default="auto",
                    help="水印处理：auto=自动识别并命中才去（默认），force=强制去，off=不动")
    ap.add_argument("--dewm", action="store_true",
                    help="等价 --wm force（保留旧参数；需要无条件去水印时用）")
    ap.add_argument("--expect-cells", type=int, default=None,
                    help="类型 E 声明格数，用于校验「说的和画的」是否一致（如 9 / 16）")
    ap.add_argument("--text", choices=["ok", "bad"], help="文案逐字目检结论（无视觉时先留空，明示用户核对）")
    ap.add_argument("--note", help="备注（模板版本、场景等）")
    ap.add_argument("--no-log", action="store_true",
                    help="不写 runs.csv（跑测试/验证时用，避免污染生产记账）")
    ap.add_argument("--log-path", default=None,
                    help="覆盖 runs.csv 位置（默认 scripts/logs/runs.csv；测试/CI 用临时文件）")
    args = ap.parse_args()
    if args.dewm:
        args.wm = "force"   # 旧参数语义保留，避免既有文档/脚本失效
    if args.expect_cells is not None and args.track != "E":
        # 格数只对类型 E 有意义。此前静默丢弃，用户以为校过了（2026-09-23 修）。
        ap.error(f"--expect-cells 只对类型 E 有效（当前 --track {args.track}）；"
                 f"要去掉该参数，或把 --track 改成 E")

    verdicts = []
    tool_errors = []
    skipped = []
    for p in args.images:
        if not os.path.exists(p):
            print(f"[skip] 不存在: {p}")
            skipped.append(os.path.basename(p))
            continue
        try:
            verdicts.append(process(p, args))
        except Exception as e:      # noqa: BLE001
            # **工具自身失败不是 blocker**（2026-09-23 修）。
            # 原先异常直接冒泡：Python 未捕获异常退出码就是 1，而 1 在本脚本的约定里
            # 表示 blocker。于是「读不了图 / runs.csv 写不进去 / 传了目录当图片」这类
            # 环境问题会被读成「这张图有毛病」，Agent 据此做一次定向重生，白扣 5–10 积分。
            # 现在收敛成显式退出码 4，并在文案里说清「不要据此重生」。
            msg = f"{type(e).__name__}: {e}"
            tool_errors.append((os.path.basename(p), msg))
            print(f"  ⚠️ [tool_error] {os.path.basename(p)}：{msg}", file=sys.stderr)

    code, message = exit_policy(verdicts, tool_errors, skipped)
    if message:
        print("\n" + message)
    sys.exit(code)


if __name__ == "__main__":
    _log.run("postcheck", main)
