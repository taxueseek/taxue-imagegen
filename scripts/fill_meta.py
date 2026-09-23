#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fill_meta — 机械填槽组装出图提示词（配套 skill: taxue-imagegen）。

设计借鉴 taxue-halftone 的 fill_meta/lint_prompt 流水线，第一性原理：
**模板是已验证资产，不该由 LLM 每次手工重抄**——重抄一次消耗数百 output token，
还可能漏段、漏禁令、漏硬底线。本脚本做外科手术式填槽：精确替换、标点前置校验、
逐字声明与词数自动推导、残留槽位报告，组装完内嵌跑一遍 preflight。

模板单一真源：类型 A = references/poster-v5.md §一 首个代码块；
类型 B = references/crowd-themes.md 各主题节。脚本不内嵌模板文本，改模板只改 md。

用法：
  python3 fill_meta.py A --list
      列出类型 A 全部槽位（必填 / 有默认 / 自动推导）
  python3 fill_meta.py A --set 视觉风格=浮世绘 --set 内容主题=无常 ... [--manpu] [--out FILE] [--allow-partial]
      填槽出稿；{N} 与 {逐字列出} 由 英文主标题/中文短句 自动推导；
      --manpu 按硬底线二选一（poster-v5.md §五）切换满铺型：删纯白背景与顶部留白条款
      填槽出稿；{N} 与 {逐字列出} 由 英文主标题/中文短句 自动推导
  python3 fill_meta.py B --list
      列出类型 B 全部主题
  python3 fill_meta.py B --theme 鸟
      输出该主题完整英文提示词（正向 + 负向）
"""

import _log
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


def write_out(path, text):
    """把组装结果写到 --out。**写失败是环境问题，不是内容问题**（2026-09-23 修）。

    此前四处都直接 `open(args.out, "w").write(...)`：目录不存在 → FileNotFoundError、
    `--out` 传目录 → IsADirectoryError，两者都是**未捕获异常 = 退出码 1**，而 1 在本脚本
    的契约里表示「preflight 有阻断项」——调用方会把「没写成功」读成「提示词有问题」。
    而 prompt 全文此时已经打到 stdout，很容易被当成「写成功了、只是有阻断」。

    故：目录先建；目标是目录则明确报错；写失败统一退出码 4（与 1/2 区分开）。
    """
    d = os.path.dirname(os.path.abspath(path))
    if os.path.isdir(path):
        fail(f"--out 指向的是一个目录：{path}（应给文件路径）")
    try:
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError as e:
        print(f"fill_meta: --out 写入失败（环境问题，不是提示词问题）：{e}", file=sys.stderr)
        sys.exit(4)
    print(f"written: {path}", file=sys.stderr)


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


def run_preflight(prompt, track, blocking=True):
    """组装结果直接过 preflight；返回 (是否有阻断, 输出行)。

    `blocking=False` 时**只报不拦**：调用方负责决定退出码。当前只有类型 B 用它，
    原因见 `do_track_b` 的注释。
    """
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
    return (blocks > 0 if blocking else False), lines


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
        print(f"类型 A（v5.4）：{len(slots)} 个槽位，其中必填 {len(required)}，"
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
        write_out(args.out, result)
    sys.exit(1 if blocked else 0)


THEME_ALIASES = {
    "鸟": "主题一：鸟", "猫": "主题二：猫", "狗": "主题三：狗",
    "合影": "主题四", "休息": "主题四", "前行": "主题四",
    "百相": "主题五",
}


def _parse_crowd_themes():
    """把 crowd-themes.md 拆成 {主题别名: 正文}。大多数主题的正文就是提示词，
    例外见 EXTERNAL_THEME_PROMPTS。"""
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


# 「正文即提示词」的例外。百相那一节在 crowd-themes.md 里留的是**档案**：
# 主题设计原理、变化轴、实测 v1/v2 的指标表、修复方向。真正的提示词已收编到独立文件
# （见该节末尾「完整提示词 v1 / v2 已收编为…」一行）。
#
# 这个例外不修会怎样（2026-09-23 实测）：`fill_meta B --theme 百相` 会把 4,485 字符的
# **中文方法说明 + 23 行指标表格 + 一行工作区出图路径**整段打印出来当提示词，
# 而真正的提示词一个字母都不在里面。与硬规则 5（元信息与内容物理分离）直接冲突——
# 那段东西一旦提交，指标表就有约 50% 概率被画进画面（坑 8）。
# 指向 v2 而不是 v1：SKILL.md §1/§4 写明的就是「v2（修复版）」。
EXTERNAL_THEME_PROMPTS = {"百相": "crowd-100-faces-prompt-v2.md"}


def load_prompt_block(path):
    """取文件里**第一个 fenced 代码块**——本技能约定的「可直接提交的提示词」存放形态。"""
    text = open(path, encoding="utf-8").read()
    m = re.search(r"^```\n(.*?)^```$", text, re.S | re.M)
    if not m:
        fail(f"{os.path.basename(path)} 里没有 fenced 提示词块")
    return m.group(1).rstrip() + "\n"


def load_track_b_themes():
    """从 crowd-themes.md 拼出类型 B 的 7 个主题；正文即提示词，例外见下表。"""
    themes, order = _parse_crowd_themes()
    for alias, fname in EXTERNAL_THEME_PROMPTS.items():
        if alias in themes:
            themes[alias] = load_prompt_block(os.path.join(REF, fname))
    return themes, order


def do_track_b(args):
    themes, order = load_track_b_themes()
    if args.list:
        print(f"类型 B：{len(order)} 个主题（提示词必须英文，默认 1024x1536）")
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
        write_out(args.out, section)
    # 2026-09-23 修：**类型 B 此前从未跑过内嵌 preflight**——A/C/E 三个 do_track_* 都有
    # `run_preflight(...)`，只有 B 漏了接线，而 SKILL.md §3 步 2 与 §8 都写着
    # 「A/B/C/E 全走它，组装完自动过 preflight」。文档说检查过、代码没检查，是最坏的一种
    # 不一致：用户会以为已经拦过了。（同 v1.20.1 那个「定义了但 main() 漏接线、从未跑过
    # 的回归测试」属同一类。）
    #
    # 为什么这一处**只报不拦**：B 的 prompt 正文就是主题库整段内容（全英文、历史实测 pass），
    # 而实测 7 个主题里 5 个携带色相词——4 个是共用的调色板句
    # `cream white, warm grey, grey-brown`，1 个（百相）命中在**文档段**里。
    # 直接改成拦会让文档里的默认入口 `fill_meta B --theme 猫` 当场退出 1。
    # 改主题库要用 §一·丙 已定的写法（色相词换成 hex）并重跑出图验证，属内容改动，
    # 已登记在 CHANGELOG 待实施；本轮先把「检查」这件事实补齐并如实报出来。
    blocked_b, lines_b = run_preflight(section, "B", blocking=False)
    for line in lines_b:
        print(line, file=sys.stderr)
    if any(l.startswith("❌") for l in lines_b):
        print("note  类型 B 的命中项**不阻断**（主题库为整段实测内容，改动需重跑验证）；"
              "逐条看过再提交，见 CHANGELOG「待实施」", file=sys.stderr)


def load_track_c_template():
    """从 packaging-editorial.md §一 提取代码块（单一真源，槽位用【】）。"""
    path = os.path.join(REF, "packaging-editorial.md")
    text = open(path, encoding="utf-8").read()
    m = re.search(r"^```\n(.*?)^```$", text, re.S | re.M)
    if not m:
        fail("packaging-editorial.md 中没有找到 §一 模板代码块")
    return m.group(1).rstrip() + "\n"


def load_track_e_template():
    """从 multigrid-layout.md §一 提取代码块（单一真源，槽位用【】）。"""
    path = os.path.join(REF, "multigrid-layout.md")
    text = open(path, encoding="utf-8").read()
    # §一 之后的第一个代码块才是模板（§四 另有示例代码块）
    sec1 = text.split("## 一、元提示词模板", 1)
    if len(sec1) < 2:
        fail("multigrid-layout.md 中没有找到 §一 标题")
    m = re.search(r"^```\n(.*?)^```$", sec1[1], re.S | re.M)
    if not m:
        fail("multigrid-layout.md §一 中没有找到模板代码块")
    return m.group(1).rstrip() + "\n"


# 格数槽位与「逐格清单」条数的对应：清单用「、」分隔，条数必须等于格数
GRID_COUNT_SLOT = "格数"
CELL_LIST_SLOT = "逐格清单"


def do_track_e(args):
    """类型 E 多格排版：按槽位名替换【】，校验格数与清单条数一致，组装完过 preflight。"""
    template = load_track_e_template()
    slots = re.findall(r"【([^】\n]+)】", template)
    unique = []
    for s in slots:
        if s not in unique:
            unique.append(s)

    if args.list:
        print(f"类型 E（多格排版）：{len(slots)} 处槽位，{len(unique)} 个不同名")
        for i, s in enumerate(unique, 1):
            n = slots.count(s)
            print(f"  #{i} 【{s}】" + (f"  ×{n}" if n > 1 else ""))
        return

    sets = {}
    for pair in args.set or []:
        if "=" not in pair:
            fail(f"--set 需要 KEY=VALUE：{pair}")
        key, value = pair.split("=", 1)
        sets[key.strip()] = value.strip()

    missing = [s for s in unique if s not in sets and not args.allow_partial]
    if missing:
        fail("缺槽位：" + "、".join(f"【{m}】" for m in missing)
             + "（--list 查看全部；--allow-partial 允许半成品）")

    # 格数 × 逐格清单条数一致性（2026-09-12：本类型最容易出的低级错）
    if GRID_COUNT_SLOT in sets and CELL_LIST_SLOT in sets:
        try:
            want = int(re.sub(r"[^0-9]", "", sets[GRID_COUNT_SLOT]) or "0")
        except ValueError:
            want = 0
        got = len([x for x in re.split(r"[、,，;；]", sets[CELL_LIST_SLOT]) if x.strip()])
        if want and got != want:
            fail(f"格数({want}) 与 逐格清单({got} 条) 不一致 —— "
                 "清单用「、」分隔，条数必须等于格数（见 multigrid-layout.md 硬规则 6）")

    result = template
    for s in unique:
        if s in sets:
            result = result.replace(f"【{s}】", sets[s])

    leftover = re.findall(r"【[^】\n]{1,40}】", result)
    if leftover and not args.allow_partial:
        fail(f"组装后仍有 {len(leftover)} 个残留槽位：{leftover[:5]}（--allow-partial 允许半成品）")

    print(result)
    blocked, lines = run_preflight(result, "E")
    for line in lines:
        print(line, file=sys.stderr)
    if args.out:
        write_out(args.out, result)
    sys.exit(1 if blocked else 0)


def do_track_c(args):
    """类型 C 包装 Mockup：按槽位名替换【】，缺槽报错，组装完过 preflight。"""
    template = load_track_c_template()
    slots = re.findall(r"【([^】\n]+)】", template)

    # 同名字槽位（如【色A】出现两次）一次赋值全部替换
    unique = []
    for s in slots:
        if s not in unique:
            unique.append(s)

    if args.list:
        print(f"类型 C（写实包装 Mockup）：{len(slots)} 处槽位，{len(unique)} 个不同名")
        for i, s in enumerate(unique, 1):
            n = slots.count(s)
            print(f"  #{i} 【{s}】" + (f"  ×{n}" if n > 1 else ""))
        return

    sets = {}
    for pair in args.set or []:
        if "=" not in pair:
            fail(f"--set 需要 KEY=VALUE：{pair}")
        key, value = pair.split("=", 1)
        sets[key.strip()] = value.strip()

    # 文案类槽位禁引号（坑 5）；【+色B】是前缀槽位，允许留空
    for key, value in sets.items():
        if key in ("词1", "词2", "品类英文", "规格"):
            hit = [c for c in FORBIDDEN_COPY if c in value]
            if hit:
                fail(f"--set {key}=… 含非法字符「{''.join(hit)}」：{value}（坑 5：文案禁引号）")

    missing = [s for s in unique if s not in sets and not args.allow_partial]
    if missing:
        fail("缺槽位：" + "、".join(f"【{m}】" for m in missing)
             + "（--list 查看全部；--allow-partial 允许半成品）")

    result = template
    for s in unique:
        if s in sets:
            result = result.replace(f"【{s}】", sets[s])

    # 可留空槽位（单专色时 【+色B】 为空）→ 连同紧邻的空括号一并清掉，
    # 避免出现「深焙棕（）。」这种残留（2026-09-08 实测发现）。
    result = re.sub(r"（\s*）", "", result)
    result = re.sub(r"\(\s*\)", "", result)

    leftover = re.findall(r"【[^】\n]{1,40}】", result)
    if leftover and not args.allow_partial:
        fail(f"组装后仍有 {len(leftover)} 个残留槽位：{leftover[:5]}（--allow-partial 允许半成品）")

    print(result)
    blocked, lines = run_preflight(result, "C")
    for line in lines:
        print(line, file=sys.stderr)
    if args.out:
        write_out(args.out, result)
    sys.exit(1 if blocked else 0)


def main():
    ap = argparse.ArgumentParser(description="机械填槽组装出图提示词（taxue-imagegen）")
    ap.add_argument("track", choices=["A", "B", "C", "E"],
                    help="A=竖版概念海报，B=手绘群像，C=包装 Mockup，E=多格排版")
    ap.add_argument("--set", action="append", help="KEY=VALUE，可多次")
    ap.add_argument("--theme", help="类型 B 主题名（--list 查看）")
    ap.add_argument("--manpu", action="store_true", help="类型 A 满铺型：删纯白背景与顶部留白硬底线（二选一）")
    ap.add_argument("--list", action="store_true", help="列出槽位/主题")
    ap.add_argument("--out", help="写入文件")
    ap.add_argument("--allow-partial", action="store_true", help="允许缺槽/残留槽位（半成品）")
    args = ap.parse_args()
    if args.track == "A":
        do_track_a(args)
    elif args.track == "B":
        do_track_b(args)
    elif args.track == "C":
        do_track_c(args)
    else:
        do_track_e(args)


if __name__ == "__main__":
    _log.run("fill_meta", main)
