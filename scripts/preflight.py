#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""preflight — 出图前提示词静态检查（配套 skill: taxue-imagegen）。

第一性原理：返工的最大成本发生在「出图之后才发现提示词里有已知错误」。
四成左右的坑可以在提交前用文本规则拦住——把验收前置到提交前，
单张直出才有可能。每条规则注释标明对应的坑号（见 references/pitfalls.md）。

当前覆盖：pitfalls.md 共 37 个坑，其中 11 个可文本拦截（坑 1/3/5/8/9/10/11/12/14/16 + 残留槽位），
其余 26 个属像素级或工程级（去水印、并行撞名、路径名、纸白偏色等），需靠 postcheck / audit_wm /
paper_white 等运行时手段。
11/37 ≈ 30%，即**七成的坑在提交前拦不住**——preflight 是已知坑的防线，不是完备证明。
新翻车样本要回写 HUE_WORDS 等规则表，否则同类风险会静默放行。

用法：
  python3 preflight.py prompt.txt          # 检查提示词文件
  cat prompt.txt | python3 preflight.py -  # 从 stdin 读
  python3 preflight.py prompt.txt --track B

退出码：0 = 通过；1 = 存在 ❌ 阻断项（必须改完再出图）；2 = 用法错误。
⚠️（review 项）不阻断，但要逐条看完再提交。
"""

import _log
import argparse
import re
import sys

# ── 规则数据 ──────────────────────────────────────────────────────────────

# 坑 1：色相词是强色相指令。只查「正向使用」——同子句含否定词则放行
# （硬底线里的「无米白、奶油、象牙」是负向清单，不能误报）。
# 英文项一律 \b 词边界：否则 managed/staged/damaged 命中 aged、screaming 命中 cream、
# swarm/warmth 命中 warm —— 2026-09-08 实测 9/9 分镜 prompt 被误判（09_ferry 的
# "the only warmth" 被判色相违规）。中文项不加边界（子串即语义）。
#
# 2026-09-09 补：词表只收了「教科书色相词」，漏掉同义的**底色系复合词**。
# 实测翻车样本 v1 写 `warm bone-white` 被拦，v2 把 warm 换成 `neutral near-white,
# cool-grey balance` 就过了——但 `bone-white` 单独出现时原表直接放行（实测静默通过），
# 与 ivory/cream 同类，风险等价。这里只补**底色/纸材色系**的等价词。
#
# 两条边界（2026-09-09 定，均由实测决定，不靠推测）：
# ① 具体色名用于**光照/点缀**不算违规——实测记录写明「amber/honey/golden 是具体色名，
#    不是抽象色相词」，暖调叙事照样成立（storyboard 09_ferry 的 golden hour）。
#    所以 amber / honey / golden / rose / rosy 一律**不收**，收了就会拦住正常流程。
# ② 场景描述词（dusty road / murky river）不收——它们说的是**画面内容**不是底色，
#    且真实语料零出现，收了只会制造假阳性（实测："a dusty road at dawn" 会被判违规）。
#    词表只对「底色被推离中性白」负责。
# 2026-09-23 补：`\b` 挡不住「连字符复合词」——`middle-aged` 里 `aged` 前面是连字符，
# `\baged\b` 照样命中。实测类型 B 主题「休息」整条被判坑1，命中的却是
# "the middle-aged human man"（中年男人），与色相毫无关系。故给**单词项**加
# `(?<!-)` 前缀：连字符说明它是复合词的一部分，不是独立的色相词。
# 复合词项（off-white / bone-white / sun-bleached）不加，它们的连字符本就是设计的一部分。
HUE_WORDS = [
    r"(?<!-)\bwarm\b", r"(?<!-)\baged\b", r"(?<!-)\bvintage\b",
    r"(?<!-)\bfaded\b", r"(?<!-)\bunbleached\b",
    r"(?<!-)\bsepia\b", r"\bsun-bleached\b", r"(?<!-)\bcream\b",
    r"(?<!-)\bivory\b", r"(?<!-)\bbeige\b",
    r"(?<!-)\bkraft\b",
    r"\bbone[- ]?white\b", r"\boff[- ]?white\b", r"\beggshell\b", r"\bparchment\b",
    r"\boatmeal\b",
    r"做旧", r"复古纸", r"牛皮纸", r"米白", r"奶油色", r"象牙白",
    r"骨白", r"泛黄",
]
# 否定词同样要边界：ban 会命中 banner/urban，no 会命中 nothing 之外的词首
# （2026-09-08 实测：'banner with aged texture'、'urban vintage poster' 被误放行）。
NEGATION = re.compile(
    r"无|不|禁|避免|没有|不要|不得|证伪|示例|"
    r"\bnever\b|\bno\b|\bnot\b|\bavoid\b|\bwithout\b|\bban\b|\bbanned\b|\bexclude\b", re.I)

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
VERTICAL = re.compile(r"竖排|竖式|\bvertical\b", re.I)
# 排除 LOCK 标签（类型 D 的 STYLE LOCK / CHARACTER LOCK 是结构标签，不是竖排文案）：
# 2026-09-08 实测 9/9 分镜 prompt 被误判为「竖排多词英文」。
MULTI_WORD_EN = re.compile(r"\b[A-Z]{2,}\s+(?!LOCK\b)[A-Z]{2,}\b")

# 坑 12①：中文文案要逐字声明（锁字数锁字序），缺了就有缺字风险
CN_TEXT_DECL = re.compile(r"中文短句|中文文案|中文标题")
CN_VERBATIM = re.compile(r"恰好是|依次为|一字不多|逐字|exactly (?:the )?(?:these )?(?:characters|characters:)|in this exact order")

# 坑 14①：主标题穿插场景必须显式声明唯一性
INTERLEAVE = re.compile(r"穿插|环绕|interleav|intertwin|woven", re.I)
UNIQUENESS = re.compile(r"只出现一次|only once|不得再重复出现|出现一次")

# 坑 9：纯白背景要带「不是浅灰」（加强写法，坑 9 修复，组合验证中）
PURE_WHITE = re.compile(r"纯白|pure white", re.I)
NOT_GRAY = re.compile(r"不是浅灰|not light gray|非浅灰|bright pure white|明亮纯白")

# 尺寸：只放行已实测精确输出的画幅（references/size-and-params.md）
# 1024x1792 于 2026-09-08 分镜类型实测精确输出（实为 4:7，非精确 9:16）
# 1536x864 于 2026-09-23 实测 3/3 精确输出（见 SKILL.md §2 的更正：16:9 可直接要，
# 不必后期裁）。此前本表没跟着更新，于是「刚被实测证明可用」的尺寸反而被 preflight
# 报成「不在已实测表」——**规则比事实慢一步**，正是这类表最该防的。
TESTED_SIZES = {"1024x1024", "1024x1536", "1024x1280", "1152x1536", "1536x1024",
                "1024x1792", "1536x864"}
SIZE_TOKEN = re.compile(r"\b(\d{3,4})\s*[x×]\s*(\d{3,4})\b")

# 槽位：类型 A/B 用 {}，类型 C 模板用【】。两种都要能拦住未填槽位。
# 2026-09-08 实测：C 模板 17 个【】槽位在 preflight 下静默放行（只认 {}）。
SLOT_BRACE = re.compile(r"\{[^{}\n]{1,40}\}")
SLOT_CN = re.compile(r"【[^】\n]{1,40}】")

# 类型 A/B/D 模板用【】作**段落标题**而非槽位（见 references/poster-v5.md §一）。
# 2026-09-18 实测：A 类 prompt 100% 被误报「残留未填槽位 7 个」，把真 BLOCK 淹没。
# 2026-09-23 修：原判据是**硬编码白名单**（只认模板自带的那几个标题），而技能同时
#   规定「模板没覆盖的新需求才手写」（SKILL.md §3 步 2）——手写模板必然出现自定义段落
#   标题（如【版式骨架 · 四层】【工艺】），于是**手写必踩**，仍被报成「残留槽位」BLOCK。
#   中途试过「关键词表」，但【三比四】这类比例槽位与标题在关键词上无法区分
#   （回归测试 test_preflight.py 的坑 24 用例正是它）。
#   最终按**行位置**判：独占整行的【】= 段落标题；行内嵌的【】= 待填空槽。
#   C/E 走另一分支（其【】本就是槽位），不受影响。
LINE_ONLY_CN = re.compile(r"^[ \t]*(【[^】\n]{1,40}】)[ \t]*$", re.M)

# 各类型适用的规则（避免用 A 的规则误判 D 的结构标签，反之亦然）
TRACKS = ("A", "B", "C", "D", "E")


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
    # 2026-09-12：模板里用「」声明文案是常规写法（类型 A/C/E 均如此）。只要全文
    # 任何一处明写了「不出现引号字符」，即视为已声明，放行——与坑 10 的
    # manpu_decl「主动放弃即正确形态」同一模式。未声明时照旧拦截。
    no_quote_decl = bool(re.search(
        r"(不|无|不要|不得|禁|没有)[^。\n]{0,12}引号"
        r"|引号[^。\n]{0,8}(不|不出现在画面|不画)", text))
    for line in text.splitlines():
        if no_quote_decl:
            break
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

    # 坑 11 · 竖排多词英文（类型 A/C 文案型；D 的 STYLE/CHARACTER LOCK 是结构标签，跳过）
    # 2026-09-18 修假阳性：类型 A 模板自带条件句「主标题若竖排且多于一个词」，
    # 主标题只有 1 个词时该条款并不生效，却让 VERTICAL 字面命中而误报 BLOCK。
    # 检测前先剔除「若…竖排」这类条件子句。
    vertical_text = re.sub(r"若[^。\n]{0,20}?竖排", "", text)
    if track in ("A", "C") and VERTICAL.search(vertical_text) and MULTI_WORD_EN.search(text):
        out.append(("BLOCK", "坑11",
                    "竖排 + 多词英文：末字母会被复制到下一词首 —— "
                    "逐字母声明总数或拆成独立竖列（修复写法见坑 11）"))

    # 坑 12① · 中文文案逐字声明（类型 A 含中文短句时必查）
    if track == "A" and CN_TEXT_DECL.search(text) and not CN_VERBATIM.search(text):
        out.append(("WARN", "坑12A",
                    "中文文案未逐字声明（锁字数锁字序）—— 缺字/错字高发，"
                    "写法：「必须恰好是这 N 个字：…（依次为：…）」"))

    # 坑 14A · 主标题穿插唯一性（类型 A 限定：类型 B 的「穿插」指角色节奏，语义不同）
    if track == "A" and INTERLEAVE.search(text) and re.search(r"标题|title", text, re.I) \
            and not UNIQUENESS.search(text):
        out.append(("BLOCK", "坑14A",
                    "主标题穿插场景缺「只出现一次」显式声明 —— 约 50% 重复渲染，"
                    "底部文字带同步改两行制"))

    # 坑 9 · 纯白背景加强写法（提出未单因素验证，提醒不阻断；满铺型无纯白条款，跳过）
    if track in ("A", "B") and not manpu_decl and PURE_WHITE.search(text) \
            and not NOT_GRAY.search(text):
        out.append(("WARN", "坑9",
                    "纯白背景未带「明亮纯白/不是浅灰」加强写法 —— "
                    "风格词可能把底色压成浅灰（坑 9，写法待单因素验证）"))

    # 尺寸实测表
    # 2026-09-12：单格/单帧尺寸（如精灵图「单格 128×128」）不是输出画布尺寸，
    # 跳过该子句，避免误报（类型 E 多格排版实测）。
    CELL_SIZE_CTX = re.compile(r"单格|每格|单帧|每帧|frame|cell", re.I)
    for m in SIZE_TOKEN.finditer(text):
        # 2026-09-23 修：原先取 `text.find("\n", m.end())`，**末行无换行时返回 -1**，
        # 切片退化成 `[start:-1]` —— 最后一个字符被吃掉。实测同一句「画布 2000x3000 每帧」：
        # 不带尾换行时报「尺寸不在已实测表」，带上尾换行就通过。同一内容两种结论，
        # 而 prompt 文件有没有尾换行纯看编辑器——这类判据必须与文件结尾无关。
        nl = text.find("\n", m.end())
        line = text[text.rfind("\n", 0, m.start()) + 1:
                    len(text) if nl < 0 else nl]
        if CELL_SIZE_CTX.search(line):
            continue
        size = f"{m.group(1)}x{m.group(2)}"
        if size not in TESTED_SIZES:
            out.append(("WARN", "尺寸",
                        f"尺寸 {size} 不在已实测表（{', '.join(sorted(TESTED_SIZES))}）—— "
                        "先单张探一张，确认不裁剪不取整"))
            break

    # 坑 16：中文 prompt 长度阈值（2026-09-07 实测 150 字过 / 430 字挂，精确阈值未定位）
    if track in ("A", "C", "E"):
        cn_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        if cn_chars > 430:
            out.append(("WARN", "坑16",
                        f"中文 prompt 约 {cn_chars} 字，超过已知失败长度 430 字——"
                        "遇 internal server error 先按坑 16 压缩"
                        "（历史完整模板亦有通过案例，阈值未定位）"))

    # 坑 24 · 残留槽位：类型 A/B/D 用 {}，类型 C/E 用【】——两种都拦
    # （2026-09-08 实测：C 模板 17 个【】槽位此前被静默放行）
    # 2026-09-23：A/B/D 的【】按**行位置**豁免（见 LINE_ONLY_CN 注释）
    if track in ("C", "E"):
        cn_leftover = SLOT_CN.findall(text)
    else:
        section_titles = set(LINE_ONLY_CN.findall(text))
        cn_leftover = [t for t in SLOT_CN.findall(text) if t not in section_titles]
    leftover = SLOT_BRACE.findall(text) + cn_leftover
    if leftover:
        out.append(("BLOCK", "槽位",
                    f"残留未填槽位 {len(leftover)} 个：{leftover[:5]} —— 用 fill_meta.py 填齐或人工定值"))

    return out


def main():
    ap = argparse.ArgumentParser(description="出图前提示词静态检查（taxue-imagegen）")
    ap.add_argument("file", help="提示词文件路径，'-' 读 stdin")
    ap.add_argument("--track", choices=list(TRACKS), default="A",
                    help="A=竖版概念海报（默认），B=手绘群像，C=包装 Mockup，"
                         "D=叙事分镜，E=多格排版")
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
    _log.run("preflight", main)
