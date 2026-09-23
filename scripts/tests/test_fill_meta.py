#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fill_meta 域：类型 C 机械填槽（17 槽、空括号清理、缺槽报错）。"""
import os
import re
import subprocess
import sys

from _harness import HERE, check


# ── 类型 C 机械填槽 ──────────────────────────────────────────────
def test_fill_meta_track_c():
    fm = os.path.join(HERE, "fill_meta.py")
    r = subprocess.run([sys.executable, fm, "C", "--list"],
                       capture_output=True, text=True)
    check("fill_meta C --list 可用", r.returncode == 0 and "槽位" in r.stdout,
          f"rc={r.returncode}")

    sets = ["--set", "三比四=三比四", "--set", "浅灰/中灰=浅灰",
            "--set", "三分之二/四分之三=三分之二",
            "--set", "形态+材质+物理细节：褶皱/厚度/贴地承重=哑光自立纸袋",
            "--set", "哪个面=正面", "--set", "单色/双专色=单色",
            "--set", "纸材/涂层=未涂布哑光纸", "--set", "一/两=一",
            "--set", "色A=深焙棕", "--set", "+色B=",
            "--set", "一个隐喻物，一句话说死=冒烟火山",
            "--set", "跟随曲面/褶皱/压纹=跟随褶皱",
            "--set", "词1=SLOW", "--set", "词2=ROAST",
            "--set", "品类英文=COFFEE", "--set", "规格=250G"]
    r2 = subprocess.run([sys.executable, fm, "C"] + sets, capture_output=True, text=True)
    check("fill_meta C 组装成功", r2.returncode == 0, f"rc={r2.returncode} {r2.stderr[:120]}")
    check("fill_meta C 无残留【】槽位", "【" not in r2.stdout,
          "仍有未填槽位")
    check("fill_meta C 单专色清掉空括号", "（）" not in r2.stdout and "()" not in r2.stdout,
          "残留空括号（坑：单专色时 【+色B】 留空会留下（））")
    check("fill_meta C 文案逐字保留", "SLOW" in r2.stdout and "ROAST" in r2.stdout,
          "品牌名丢失")

    # 缺槽必须报错
    r3 = subprocess.run([sys.executable, fm, "C", "--set", "词1=X"],
                        capture_output=True, text=True)
    check("fill_meta C 缺槽报错", r3.returncode == 2,
          f"缺槽未报错 rc={r3.returncode}")


# ── 一类 bug：do_track_* 漏接内嵌 preflight ──────────────────────
def test_all_tracks_run_embedded_preflight():
    """文档承诺「A/B/C/E 组装完都自动过 preflight」，代码必须真的接线。

    2026-09-23 实测：`do_track_b` **从未调用** `run_preflight` —— A/C/E 三个分支都有，
    只有 B 漏了。而 SKILL.md §3 步 2 与 §8 都写着「全走它，组装完自动过 preflight」。
    「文档说检查过了、代码没检查」是最坏的一种不一致：用户会以为已经拦过了，直接提交。
    （与 v1.20.1 那个「定义了但 main() 漏接线、从未跑过的回归测试」属同一类缺陷。）

    判据两层：
      ① 静态：源码里四个 track 都要有 run_preflight 调用点（改回漏接线立刻红）；
      ② 行为：跑一次 `fill_meta B --theme <第一个主题>`，stderr 必须出现 preflight 结果行
         （不能只靠静态字符串——接线了但没输出等于没接）。

    另附一条**债务预算**：B 主题库命中坑1 的主题数当前是 5（4 个共用调色板句用色相词
    cream white / warm grey，1 个命中在文档段里）。本轮不阻断、也不改主题内容（改它要用
    hex 写法重跑出图验证），但**这个数不许再涨**——新主题若不按硬规则 1 写就会红。
    """
    fm_path = os.path.join(HERE, "fill_meta.py")
    src = open(fm_path, encoding="utf-8").read()
    missing = [t for t in ("A", "B", "C", "E")
               if f'run_preflight(' not in src
               or f'"{t}")' not in src and f'"{t}", ' not in src]
    # 更精确：逐 track 检查是否有把该 track 当第二参数的调用
    missing = [t for t in ("A", "B", "C", "E")
               if not re.search(r'run_preflight\([^)]*,\s*"%s"' % t, src)]
    check("四个类型都接了内嵌 preflight（静态判据）", not missing,
          f"漏接线：{'、'.join(missing)}")

    r = subprocess.run([sys.executable, fm_path, "B", "--theme", "猫"],
                       capture_output=True, text=True)
    blob = (r.stdout or "") + (r.stderr or "")
    check("fill_meta B 真的会报出 preflight 结果（行为判据）",
          "preflight" in blob or "坑1" in blob,
          f"stderr 里没有 preflight 结果：{(r.stderr or '')[-160:]}")

    # 债务预算：B 主题库命中数不得增长
    sys.path.insert(0, HERE)
    import importlib.util
    def _load(name):
        sp = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
        m = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(m)
        return m
    fm = _load("fill_meta")
    pf = _load("preflight")
    themes, order = fm.load_track_b_themes()
    hit = []
    for name in order:
        if any(lv == "BLOCK" for lv, _, _ in pf.check(themes[name].rstrip() + "\n", "B")):
            hit.append(name)
    check("B 主题库命中坑1 的数量不超过已登记债务（5）", len(hit) <= 5,
          f"涨到 {len(hit)} 个：{'、'.join(hit)}——新主题没按硬规则 1 写"
          f"（色相词要换成 hex 或纹理词）")


TESTS = [test_fill_meta_track_c, test_all_tracks_run_embedded_preflight]
