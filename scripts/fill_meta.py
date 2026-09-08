#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fill_meta — 机械填槽组装出图提示词（配套 skill: taxue-imagegen）。

设计借鉴 taxue-halftone 的 fill_meta/lint_prompt 流水线，第一性原理：
**模板是已验证资产，不该由 LLM 每次手工重抄**——重抄一次消耗数百 output token，
还可能漏段、漏禁令、漏硬底线。本脚本做外科手术式填槽：精确替换、标点前置校验、
逐字声明与词数自动推导、残留槽位报告，组装完内嵌跑一遍 preflight。

模板单一真源：赛道 A = references/poster-v5.md §一 首个代码块；
赛道 B = references/crowd-themes.md 各主题节。脚本不内嵌模板文本，改模板只改 md。

用法：
  python3 fill_meta.py A --list
      列出赛道 A 全部槽位（必填 / 有默认 / 自动推导）
  python3 fill_meta.py A --set 视觉风格=浮世绘 --set 内容主题=无常 ... [--manpu] [--out FILE] [--allow-partial]
      填槽出稿；{N} 与 {逐字列出} 由 英文主标题/中文短句 自动推导；
      --manpu 按硬底线二选一（poster-v5.md §五）切换满铺型：删纯白背景与顶部留白条款
      填槽出稿；{N} 与 {逐字列出} 由 英文主标题/中文短句 自动推导
  python3 fill_meta.py B --list
      列出赛道 B 全部主题
  python3 fill_meta.py B --theme 鸟
      输出该主题完整英文提示词（正向 + 负向）
"""

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(os.path.dirname(HERE), "references")
SLOT_RE = re.compile(r"\{([^{}]+)\}")

# 有默认值的槽位（填空规则见 poster-v5.md §二）
DEFAULTS = {
    "比例": "2:3",
    "背景色": "明亮纯白（bright pure white），不是浅灰",
}

# 引号与槽位括号在任何文案槽都是非法字符（坑 5 / 坑 8）
FORBIDDEN_COPY = list("“”「」『』\"'‘’【】{}=＝")
FORBIDDEN_PLAIN = list("{}【】")


def fail(msg):
    print(f"fill_meta: {msg}", file=sys.stderr)
    sys.exit(2)


def load_track_a_template():
    """从 poster-v5.md 提取 §一 首个代码块（单一真源，不内嵌副本）。"""
    path = os.path.join(REF, "poster-v5.md")
    text = open(path, encoding="utf-8").read()
    m = re.search(r"^```$\n(.*?)^```$", text, re.S | re.M)
    if not m:
        fail("poster-v5.md 中没有找到 §一 模板代码块")
    return m.group(1).rstrip() + "\n"


def parse_slot(label):
    """槽位标签形如「比例，默认 2:3」→ (标签, 默认值 or None)。"""
    if "，默认" in label:
        name, _, default = label.partition("，默认")
        return name.strip(), default.strip()
    return label.strip(), None


def run_preflight(prompt, track):
    """组装结果直接过 preflight；返回 (是否有阻断, 输出行)。"""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "preflight", os.path.join(HERE, "preflight.py"))
        pf = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pf)
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ preflight 加载失败（{e}），请手动执行 preflight.py", file=sys.stderr)
        return False, []
    findings = pf.check(prompt, track)
    lines = []
    blocks = 0
    for level, pit, msg in findings:
        mark = "❌" if level == "BLOCK" else "⚠️"
        blocks += level == "BLOCK"
        lines.append(f"{mark} [{pit}] {msg}")
    if not findings:
        lines.append("✅ preflight 通过：无已知坑触发")
    return blocks > 0, lines


def do_track_a(args):
    template = load_track_a_template()
    slots = [(m.group(1)) for m in SLOT_RE.finditer(template)]

    # 解析槽位标签与默认值
    named = {}
    for raw in slots:
        name, default = parse_slot(raw)
        named[raw] = (name, default or DEFAULTS.get(name))

    auto_slots = {raw for raw, (name, _) in named.items()
                  if name in ("N", "把这几个字用顿号逐个列出")}
    required = [name for raw, (name, default) in named.items()
                if default is None and raw not in auto_slots]

    if args.list:
        print(f"赛道 A（v5.4）：{len(slots)} 个槽位，其中必填 {len(required)}，"
              f"自动推导 {len(auto_slots)}，有默认 {len(slots) - len(required) - len(auto_slots)}")
        for i, raw in enumerate(slots, 1):
            name, default = named[raw]
            if name in ("N", "把这几个字用顿号逐个列出"):
                kind = "自动推导"
                note = "← 由 英文主标题/中文短句 计算"
            elif default:
                kind = f"默认「{default}」"
                note = ""
            else:
                kind = "必填"
                note = ""
            print(f"  #{i} 「{name}」 {kind}{note}")
        return

    sets = {}
    for pair in args.set or []:
        if "=" not in pair:
            fail(f"--set 需要 KEY=VALUE：{pair}")
        key, value = pair.split("=", 1)
        sets[key.strip()] = value.strip()

    # 标点前置校验
    for key, value in sets.items():
        forbidden = FORBIDDEN_COPY if "标题" in key or "短句" in key else FORBIDDEN_PLAIN
        hit = [c for c in forbidden if c in value]
        if hit:
            fail(f"--set {key}=… 含非法字符「{''.join(hit)}」：{value}（坑 5/8：文案禁引号与标注字符）")
    if "英文主标题" in sets and re.search(r"[0-9]", sets["英文主标题"]):
        fail("--set 英文主标题=… 不应含数字（会被当成权重标注画进画面，坑 8）")

    # 自动推导
    if any(name == "N" for raw, (name, _) in named.items()) and "英文主标题" in sets:
        sets.setdefault("N", str(len(sets["英文主标题"].split())))
    if any(name == "把这几个字用顿号逐个列出" for raw, (name, _) in named.items()) and "中文短句" in sets:
        sets.setdefault("把这几个字用顿号逐个列出", "、".join(sets["中文短句"].replace(" ", "")))

    # 缺槽报告
    missing = [name for name in required if name not in sets]
    if missing and not args.allow_partial:
        fail("缺必填槽位：" + "、".join(missing) + "（--list 查看全部；--allow-partial 允许半成品）")

    # 精确替换（同标签多槽按顺序消费）
    result = template
    consumed = set()
    for raw in slots:
        name, default = named[raw]
        if name in consumed:
            continue
        value = sets.get(name, default)
        if value is None:
            continue
        result = result.replace("{" + raw + "}", value)
        consumed.add(name)

    leftover = re.findall(r"\{[^{}]+\}", result)
    if leftover and not args.allow_partial:
        fail(f"组装后仍有 {len(leftover)} 个残留槽位：{leftover[:5]}（--allow-partial 允许半成品）")

    # 满铺型二选一（poster-v5.md §五，2026-09-06 实测）：删纯白背景与顶部留白两条硬底线
    if getattr(args, "manpu", False):
        result, n1 = re.subn(r"- 背景：单一均匀纯色 [^\n]*\n  [^\n]*\n", "", result)
        result, n2 = re.subn(
            r"- 顶部 25% 为连续留白；留白是背景色的直接延续，\n  不得被画成纸条、横幅或任何有边缘的实体色块\n",
            "", result)
        if n1 and n2:
            result = result.replace(
                "【硬底线：以下为数值约束，不可协商】\n",
                "【硬底线：以下为数值约束，不可协商】\n- 主体为满铺型：场景铺满画面，"
                "纯白背景与顶部留白条款已按二选一主动放弃\n")
            print("manpu: 已切换满铺型（删除纯白背景 + 顶部留白条款）", file=sys.stderr)
        else:
            fail("manpu: 模板中未找到纯白/留白硬底线原文，模板可能已改动，请人工处理")

    print(result)
    blocked, lines = run_preflight(result, "A")
    for line in lines:
        print(line, file=sys.stderr)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(result)
        print(f"written: {args.out}", file=sys.stderr)
    sys.exit(1 if blocked else 0)


THEME_ALIASES = {
    "鸟": "主题一：鸟", "猫": "主题二：猫", "狗": "主题三：狗",
    "合影": "主题四", "休息": "主题四", "前行": "主题四",
    "百相": "主题五",
}


def load_track_b_themes():
    path = os.path.join(REF, "crowd-themes.md")
    text = open(path, encoding="utf-8").read()
    parts = re.split(r"(?m)^(## .*)$", text)
    themes = {}
    order = []
    for i in range(1, len(parts), 2):
        head = parts[i].strip()
        body = parts[i + 1]
        for alias, key in THEME_ALIASES.items():
            if head.startswith("## " + key):
                # 主题四按变体小节再拆
                if key == "主题四":
                    subs = re.split(r"(?m)^### ", body)
                    neg = ""
                    for sub in subs:
                        title_line = sub.split("\n")[0]
                        if "共用负向" in title_line:
                            neg = "### " + sub
                            continue
                        for a in ("合影", "休息", "前行"):
                            if a in title_line and a not in themes:
                                themes[a] = "### " + sub
                                order.append(a)
                    for a in ("合影", "休息", "前行"):
                        if a in themes and neg:
                            themes[a] = themes[a].rstrip() + "\n\n" + neg
                    continue
                themes[alias] = "## " + head[3:] + body
                order.append(alias)
    return themes, order


def do_track_b(args):
    themes, order = load_track_b_themes()
    if args.list:
        print(f"赛道 B：{len(order)} 个主题（提示词必须英文，默认 1024x1536）")
        for a in order:
            print(f"  {a}")
        return
    if not args.theme:
        fail("需要 --theme 主题名（--list 查看）")
    if args.theme not in themes:
        fail(f"主题「{args.theme}」不存在；可选：{'、'.join(order)}")
    section = themes[args.theme].rstrip() + "\n"
    print(section)
    note = (
        "\n--- 出图提示（fill_meta 自动附加，不进 prompt）---\n"
        "1. 提交「正向提示词」代码块全文；负向提示词按原工作流并入或单独处理\n"
        "2. 建议尺寸 1024x1536（2:3），quality=high\n"
        "3. 出图后跑 measure.py 验收（白底 30–65%、R-B<3、sat 20–60）\n"
    )
    print(note, file=sys.stderr)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(section)
        print(f"written: {args.out}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="机械填槽组装出图提示词（taxue-imagegen）")
    ap.add_argument("track", choices=["A", "B"], help="赛道 A=竖版概念海报，B=手绘群像")
    ap.add_argument("--set", action="append", help="KEY=VALUE，可多次")
    ap.add_argument("--theme", help="赛道 B 主题名（--list 查看）")
    ap.add_argument("--manpu", action="store_true", help="赛道 A 满铺型：删纯白背景与顶部留白硬底线（二选一）")
    ap.add_argument("--list", action="store_true", help="列出槽位/主题")
    ap.add_argument("--out", help="写入文件")
    ap.add_argument("--allow-partial", action="store_true", help="允许缺槽/残留槽位（半成品）")
    args = ap.parse_args()
    if args.track == "A":
        do_track_a(args)
    else:
        do_track_b(args)


if __name__ == "__main__":
    main()
