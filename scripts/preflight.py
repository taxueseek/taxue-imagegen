#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""preflight — 出图前提示词静态检查（配套 skill: taxue-imagegen）。

第一性原理：返工的最大成本发生在「出图之后才发现提示词里有已知错误」。
15 个坑里有一半可以在提交前用文本规则拦住——把验收前置到提交前，
单张直出才有可能。每条规则注释标明对应的坑号（见 references/pitfalls.md）。

用法：
  python3 preflight.py prompt.txt          # 检查提示词文件
  cat prompt.txt | python3 preflight.py -  # 从 stdin 读
  python3 preflight.py prompt.txt --track B

退出码：0 = 通过；1 = 存在 ❌ 阻断项（必须改完再出图）；2 = 用法错误。
⚠️（review 项）不阻断，但要逐条看完再提交。
"""

import argparse
import re
import sys

# ── 规则数据 ──────────────────────────────────────────────────────────────

# 坑 1：色相词是强色相指令。只查「正向使用」——同子句含否定词则放行
# （硬底线里的「无米白、奶油、象牙」是负向清单，不能误报）。
HUE_WORDS = [
    r"warm", r"aged", r"vintage", r"faded", r"unbleached", r"sepia",
    r"sun-bleached", r"cream", r"ivory", r"beige", r"kraft",
    r"做旧", r"复古纸", r"牛皮纸", r"米白", r"奶油色", r"象牙白",
]
NEGATION = re.compile(
    r"无|不|禁|避免|没有|不要|不得|证伪|示例|never|no\b|not\b|avoid|without|ban", re.I)

# 坑 8：权重/比例标注与文案连写（"TIDE = 100" 约 50% 被画进画面）
META_ADJACENT = re.compile(r"[=＝]\s*\d|\d\s*[=＝]")

# 坑 5：引号字符（装饰性引号会原样画出）
QUOTE_CHARS = "“”「」『』\"'‘’"

# 坑 10：满铺型主体与「纯白背景 + 顶部留白」硬底线直接冲突
FULLBLEED = re.compile(r"巨浪|铺满|充满画面|满版|沉浸|full[- ]bleed|immersive|fills? the (entire|whole)", re.I)
TOP_BAND = re.compile(r"顶部\s*25|顶部留白|留白带|top\s*25%|top (?:white )?margin", re.I)

# 坑 14B：向上动势母题，禁令赢不了母题，要改写动势方向
UP_MOTION = re.compile(r"飘带|飞升|升起|向上|展翅|腾空|扶摇|rising|upward|soaring|ascending", re.I)

# 坑 3：面积/密度百分比指令基本无效，要换成可数约束
AREA_PCT = re.compile(
    r"(?:白|留白|背景|white|background|space)[^。\n；;]{0,24}"
    r"(?:\d+\s*%|分之一|percent|proportion)", re.I)
DENSITY_WORD = re.compile(r"low[- ]to[- ]medium density|high density|generous white|密度(高|低|适中)", re.I)

# 坑 11：竖排多词英文，末字母被复制到下一词首
VERTICAL = re.compile(r"竖排|竖式|vertical", re.I)
MULTI_WORD_EN = re.compile(r"\b[A-Z]{2,}\s+[A-Z]{2,}\b")

# 坑 12①：中文文案要逐字声明（锁字数锁字序），缺了就有缺字风险
CN_TEXT_DECL = re.compile(r"中文短句|中文文案|中文标题")
CN_VERBATIM = re.compile(r"恰好是|依次为|一字不多|逐字|exactly (?:the )?(?:these )?(?:characters|characters:)|in this exact order")

# 坑 14①：主标题穿插场景必须显式声明唯一性
INTERLEAVE = re.compile(r"穿插|环绕|interleav|intertwin|woven", re.I)
UNIQUENESS = re.compile(r"只出现一次|只出现一次|only once|不得再重复出现|出现一次")

# 坑 9：纯白背景要带「不是浅灰」（加强写法，坑 9 修复，组合验证中）
PURE_WHITE = re.compile(r"纯白|pure white", re.I)
NOT_GRAY = re.compile(r"不是浅灰|not light gray|非浅灰|bright pure white|明亮纯白")

# 尺寸：只放行已实测精确输出的画幅（references/size-and-params.md）
TESTED_SIZES = {"1024x1024", "1024x1536", "1024x1280", "1152x1536", "1536x1024"}
SIZE_TOKEN = re.compile(r"\b(\d{3,4})\s*[x×]\s*(\d{3,4})\b")


def clauses(text):
    """把提示词拆成子句（行 > 句 > 逗号），供否定词上下文判断。"""
    for line in text.splitlines():
        for seg in re.split(r"[。；;！!？?\n]", line):
            for piece in seg.split("，"):
                if piece.strip():
                    yield piece.strip()


def check(text, track):
    """返回 [(级别, 坑号, 消息)]。级别：BLOCK / WARN。"""
    out = []

    # 坑 1 · 色相词正向使用
    hits = set()
    for c in clauses(text):
        if NEGATION.search(c):
            continue
        for w in HUE_WORDS:
            if re.search(w, c, re.I):
                hits.add(w)
    if hits:
        out.append(("BLOCK", "坑1",
                    f"色相词正向使用：{sorted(hits)} —— 强色相指令，改纹理词或移入负向清单"))

    # 坑 8 · 权重标注与文案连写
    for line in text.splitlines():
        if re.search(r"标题|文案|短句|title", line, re.I) and META_ADJACENT.search(line):
            out.append(("BLOCK", "坑8",
                        f"元信息与文案连写（约 50% 被画进画面）：{line.strip()[:50]}"))
            break

    # 坑 5 · 文案值带引号
    for line in text.splitlines():
        if re.search(r"标题|短句|文案|title", line, re.I) and any(q in line for q in QUOTE_CHARS):
            out.append(("BLOCK", "坑5",
                        f"文案行含引号字符（会被原样画出）：{line.strip()[:50]}"))
            break

    # 坑 10 / 坑 9 在满铺声明存在时跳过（「主动放弃」即正确形态，不与禁令冲突）
    manpu_decl = bool(re.search(r"主动放弃|满铺型", text))

    # 坑 10 · 满铺主体 × 顶部留白
    if not manpu_decl and FULLBLEED.search(text) and TOP_BAND.search(text):
        out.append(("BLOCK", "坑10",
                    "满铺型主体与「顶部留白/纯白背景」并存 —— 硬底线二选一，"
                    "满铺型主动放弃纯白与留白条款"))

    # 坑 14B · 向上动势 × 顶部留白
    if UP_MOTION.search(text) and TOP_BAND.search(text):
        out.append(("WARN", "坑14B",
                    "向上动势母题 + 顶部留白：禁令赢不了母题，"
                    "把动势改写为向下/垂落（例句见 pitfalls 坑 14）"))

    # 坑 3 · 面积/密度百分比（子句级检查，引用反例的子句带否定/证伪字样时放行）
    area_hits = [
        c for c in clauses(text)
        if AREA_PCT.search(c) or DENSITY_WORD.search(c)
    ]
    if area_hits:
        out.append(("WARN", "坑3",
                    f"面积/密度/占比类指令对模型基本无效（例：{area_hits[0][:30]}）—— "
                    "换可数约束（数量下限 + 最大 ≤ 1/4 画幅 + 最小 ≥ 1/12）"))

    # 坑 11 · 竖排多词英文
    if VERTICAL.search(text) and MULTI_WORD_EN.search(text):
        out.append(("BLOCK", "坑11",
                    "竖排 + 多词英文：末字母会被复制到下一词首 —— "
                    "逐字母声明总数或拆成独立竖列（修复写法见坑 11）"))

    # 坑 12① · 中文文案逐字声明（赛道 A 含中文短句时必查）
    if track == "A" and CN_TEXT_DECL.search(text) and not CN_VERBATIM.search(text):
        out.append(("WARN", "坑12A",
                    "中文文案未逐字声明（锁字数锁字序）—— 缺字/错字高发，"
                    "写法：「必须恰好是这 N 个字：…（依次为：…）」"))

    # 坑 14A · 主标题穿插唯一性（赛道 A 限定：赛道 B 的「穿插」指角色节奏，语义不同）
    if track == "A" and INTERLEAVE.search(text) and re.search(r"标题|title", text, re.I) \
            and not UNIQUENESS.search(text):
        out.append(("BLOCK", "坑14A",
                    "主标题穿插场景缺「只出现一次」显式声明 —— 约 50% 重复渲染，"
                    "底部文字带同步改两行制"))

    # 坑 9 · 纯白背景加强写法（提出未单因素验证，提醒不阻断；满铺型无纯白条款，跳过）
    if not manpu_decl and PURE_WHITE.search(text) and not NOT_GRAY.search(text):
        out.append(("WARN", "坑9",
                    "纯白背景未带「明亮纯白/不是浅灰」加强写法 —— "
                    "风格词可能把底色压成浅灰（坑 9，写法待单因素验证）"))

    # 尺寸实测表
    for m in SIZE_TOKEN.finditer(text):
        size = f"{m.group(1)}x{m.group(2)}"
        if size not in TESTED_SIZES:
            out.append(("WARN", "尺寸",
                        f"尺寸 {size} 不在已实测表（{', '.join(sorted(TESTED_SIZES))}）—— "
                        "先单张探一张，确认不裁剪不取整"))
            break

    # 坑 16：中文 prompt 长度阈值（2026-09-07 实测 150 字过 / 430 字挂，精确阈值未定位）
    if track == "A":
        cn_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        if cn_chars > 430:
            out.append(("WARN", "坑16",
                        f"中文 prompt 约 {cn_chars} 字，超过已知失败长度 430 字——"
                        "遇 internal server error 先按坑 16 压缩"
                        "（历史完整模板亦有通过案例，阈值未定位）"))

    # 残留槽位：模板 {槽位} 未填就提交（fill_meta --allow-partial 的半成品会在这里拦住）
    leftover = re.findall(r"\{[^{}\n]{1,40}\}", text)
    if leftover:
        out.append(("BLOCK", "槽位",
                    f"残留未填槽位 {len(leftover)} 个：{leftover[:5]} —— 用 fill_meta.py 填齐或人工定值"))

    return out


def main():
    ap = argparse.ArgumentParser(description="出图前提示词静态检查（taxue-imagegen）")
    ap.add_argument("file", help="提示词文件路径，'-' 读 stdin")
    ap.add_argument("--track", choices=["A", "B"], default="A",
                    help="赛道 A=竖版概念海报（默认），B=手绘群像")
    args = ap.parse_args()

    if args.file == "-":
        text = sys.stdin.read()
    else:
        try:
            with open(args.file, encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            print(f"无法读取 {args.file}: {e}", file=sys.stderr)
            sys.exit(2)

    if not text.strip():
        print("提示词为空", file=sys.stderr)
        sys.exit(2)

    findings = check(text, args.track)
    if not findings:
        print("✅ preflight 通过：无已知坑触发")
        return

    blocks = 0
    for level, pit, msg in findings:
        mark = "❌" if level == "BLOCK" else "⚠️"
        if level == "BLOCK":
            blocks += 1
        print(f"{mark} [{pit}] {msg}")
    total = len(findings)
    print(f"\n{total} 项：{blocks} 阻断，{total - blocks} 提醒"
          + (" —— 改完阻断项再出图" if blocks else " —— 逐条确认后可出图"))
    sys.exit(1 if blocks else 0)


if __name__ == "__main__":
    main()
