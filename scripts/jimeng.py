#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jimeng.py — taxue-imagegen 的豆包/即梦适配层（v2.0，极简职责版）。

【唯一职责：尺寸适配，不改动 prompt 一个字】
模板与 fill_meta/preflight 是在 hunyuan 上验证过的资产，换运行环境（模型）本身
不构成改动它们的理由。因此本适配层：
  - 不改写、不重排、不补删模板生成的任何提示词内容；
  - 不过滤、不吞掉 preflight 的任何告警/阻断（原样透传，由 Agent 按实际效果判断）；
  - 不内建任何"变体/换背景色"之类的模板改写——这些走模板原生路径：
      * 换背景色：fill_meta 的正规槽位 `--set 背景色=…`（默认明亮纯白）
      * 满铺型（删纯白+顶部留白）：fill_meta 原生 `--manpu`
      * 穿插型等模板变体：按 references/poster-v5.md §一·乙 在模板层面定做
  - 只做一件环境相关的事：把比例映射成对应平台的出图像素尺寸。

工作流哲学：学好原版模板 → 忠实填槽出稿（效果原样）→ 实际出图发现问题再针对性
调整 → 验证有效后才回头更新模板。不在适配层做"预防性改写"，那只会引入新问题。

平台由分层信号链自动判断（只为决定用哪套尺寸）：
  S0 显式覆盖（--platform / TAXUE_IMAGEGEN_PLATFORM）
  S1 运行时环境变量（DOUBAO_OFFICE_* / WORKBUDDY_*）
  S2 解释器路径 → S3 cwd → S4 PATH → S5 安装目录 → S6 默认
  - 即梦（jimeng）：fill_meta 原样出稿，额外给出即梦 2K 像素尺寸
  - WorkBuddy：等价于直接跑 fill_meta（1K 尺寸），零适配

除本脚本自有参数（--sizes/--debug-platform/--platform）外，其余参数全部原样
透传给 fill_meta.py，因此 fill_meta 以后新增参数这里无需改动。

用法：
  python3 jimeng.py --sizes                       # 列出即梦推荐尺寸
  python3 jimeng.py --debug-platform              # 打印平台检测证据链
  python3 jimeng.py A --list                      # 透传：列类型 A 槽位
  python3 jimeng.py A --set 视觉风格=… --set 内容主题=… [--out FILE]  # 透传填槽+即梦尺寸
  python3 jimeng.py A --set 背景色=深墨黑 …        # 换背景色走正规槽位，不是适配层改写
  python3 jimeng.py A … --platform workbuddy      # 强制 WorkBuddy（等价直接跑 fill_meta）
"""

import _log
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FILL_META = os.path.join(HERE, "fill_meta.py")

# ── 即梦推荐尺寸（2K 级别，Seedream 5.0 Pro / lite 通用）──────────────────
JIMENG_SIZES = {
    "1:1":  (2048, 2048),
    "4:3":  (2304, 1728),
    "3:4":  (1728, 2304),
    "16:9": (2560, 1440),
    "9:16": (1440, 2560),
    "3:2":  (2496, 1664),
    "2:3":  (1664, 2496),
    "21:9": (3024, 1296),
    "4:5":  (1638, 2048),   # 非官方推荐，按 2K 短边换算
    "4:7":  (1462, 2560),   # 非官方推荐，分镜用近似 9:16
}
DEFAULT_RATIO = "2:3"  # 与 fill_meta.DEFAULTS["比例"] 保持一致


# ── 平台检测：分层信号链（仅用于决定采用哪套尺寸）─────────────────────────
# 运行时信号（谁在执行本进程）优先于安装痕迹（机器上装过什么）。
# 一台机器可能同时装了豆包和 WorkBuddy，"目录存在"不等于"正在其中运行"。
PLATFORM_FINGERPRINTS = {
    "jimeng": ["doubao", "doubaowork"],
    "workbuddy": ["workbuddy", "codebuddy"],  # 腾讯 CodeBuddy（.codebuddy.cn）
}
ENV_PREFIXES = {
    "jimeng": ("DOUBAO_OFFICE_",),
    "workbuddy": ("WORKBUDDY_", "CODEBUDDY_"),
}
INSTALL_DIRS = {
    "jimeng": [
        "~/Library/Application Support/DoubaoWork",
        "~/DoubaoWork",
        "~/.doubaowork",
        "~/AppData/Roaming/DoubaoWork",
        "~/.config/DoubaoWork",
    ],
    "workbuddy": [
        "~/.workbuddy",
        "~/AppData/Roaming/WorkBuddy",
    ],
}
VALID_PLATFORMS = ("jimeng", "workbuddy")


def _norm(s):
    """归一化：小写 + 去分隔符差异，便于模糊指纹匹配。"""
    return re.sub(r"[\s_\-.]", "", (s or "").lower())


def _match_platform(text):
    """文本命中哪个平台指纹；都不命中 None，都命中 'conflict'。"""
    if not text:
        return None
    norm = _norm(text)
    hits = {plat for plat, fps in PLATFORM_FINGERPRINTS.items()
            if any(_norm(fp) in norm for fp in fps)}
    if not hits:
        return None
    return "conflict" if len(hits) > 1 else next(iter(hits))


def probe_signals():
    """逐层采集信号，返回 [(层级, 信号名, 采样值, 判定)]。"""
    evidence = []

    # S1 · 运行时环境变量前缀
    env_name_hits = {"jimeng": [], "workbuddy": []}
    for key in os.environ:
        for plat, prefixes in ENV_PREFIXES.items():
            if any(key.startswith(p) for p in prefixes):
                env_name_hits[plat].append(key)
    for plat in VALID_PLATFORMS:
        if env_name_hits[plat]:
            evidence.append(("S1", f"环境变量前缀 {plat}",
                             ", ".join(sorted(env_name_hits[plat])[:3]), plat))

    # S1 补 · 其余环境变量值里的路径指纹（PATH 留到 S4）
    env_val_hits = {"jimeng": 0, "workbuddy": 0}
    for key, val in os.environ.items():
        if key == "PATH":
            continue
        verdict = _match_platform(val)
        if verdict in VALID_PLATFORMS:
            env_val_hits[verdict] += 1
    for plat in VALID_PLATFORMS:
        if env_val_hits[plat]:
            evidence.append(("S1", f"环境变量值含 {plat} 路径",
                             f"{env_val_hits[plat]} 个变量命中", plat))

    # S2 · 解释器路径
    for label, val in (("sys.executable", sys.executable),
                       ("sys.prefix", sys.prefix)):
        evidence.append(("S2", label, val, _match_platform(val)))

    # S3 · 工作目录
    evidence.append(("S3", "os.getcwd", os.getcwd(), _match_platform(os.getcwd())))

    # S4 · PATH 片段
    path_env = os.environ.get("PATH", "")
    path_verdict = None
    for seg in path_env.split(os.pathsep):
        v = _match_platform(seg)
        if v in VALID_PLATFORMS:
            path_verdict = v
            break
    first = path_env.split(os.pathsep)[0] if path_env else ""
    evidence.append(("S4", "PATH 片段", first + " …", path_verdict))

    # S5 · 安装目录兜底
    for plat in VALID_PLATFORMS:
        existing = [p for p in INSTALL_DIRS[plat]
                    if os.path.exists(os.path.expanduser(p))]
        if existing:
            evidence.append(("S5", f"{plat} 安装目录", existing[0], plat))

    return evidence


def _adjudicate(evidence):
    """纯函数裁决：逐层从强到弱，同层多数决，平票下沉，全无则默认 jimeng。"""
    for level in ("S1", "S2", "S3", "S4", "S5"):
        layer = [e for e in evidence if e[0] == level and e[3] in VALID_PLATFORMS]
        if not layer:
            continue
        votes = {}
        for e in layer:
            votes[e[3]] = votes.get(e[3], 0) + 1
        if len(votes) == 1:
            return next(iter(votes))
        top = max(votes.values())
        winners = [p for p, n in votes.items() if n == top]
        if len(winners) == 1:
            return winners[0]
        evidence.append((level, "同层信号冲突，下沉裁决", str(votes), "conflict"))
    return "jimeng"


def detect_platform(forced=None):
    """返回 (platform, evidence)。"""
    env_forced = os.environ.get("TAXUE_IMAGEGEN_PLATFORM", "").strip().lower()
    if forced and forced != "auto":
        return forced, [("S0", "--platform 显式指定", forced, forced)]
    if env_forced in VALID_PLATFORMS:
        return env_forced, [("S0", "环境变量 TAXUE_IMAGEGEN_PLATFORM",
                             env_forced, env_forced)]
    evidence = probe_signals()
    return _adjudicate(evidence), evidence


def format_evidence(evidence):
    lines = ["平台探测证据链（强 → 弱）："]
    for level, name, sample, verdict in evidence:
        sample = str(sample)
        if len(sample) > 70:
            sample = sample[:67] + "…"
        tag = {"jimeng": "→即梦", "workbuddy": "→WorkBuddy",
               "conflict": "冲突", None: "—"}.get(verdict, str(verdict))
        lines.append(f"  [{level}] {name:<28} {tag:<10} {sample}")
    return "\n".join(lines)


# ── 尺寸映射（本脚本唯一的环境差异适配）──────────────────────────────────
def get_jimeng_size(ratio=DEFAULT_RATIO):
    """比例 → 即梦像素 (width, height)；未知比例回退默认 2:3。"""
    return JIMENG_SIZES.get(ratio, JIMENG_SIZES[DEFAULT_RATIO])


def ratio_from_passthrough(rest):
    """从透传给 fill_meta 的参数里解析 `--set 比例=x`；缺省与 fill_meta 默认一致。

    **重复给 `--set 比例` 时取最后一个**（2026-09-23 修）：fill_meta 把 --set 收进
    dict（后者覆盖前者），而这里原先 `return` 第一个匹配 —— 于是
    `--set 比例=3:4 --set 比例=9:16` 的产物是 9:16，stderr 却报「比例 ratio：3:4 /
    width=1728 height=2304」。报出来的尺寸与真实产物不一致，比不报更误导。
    本函数只负责协商比例，不重写 prompt，故对齐到 fill_meta 的语义即正确解。
    """
    found = None
    for i, tok in enumerate(rest):
        if tok == "--set" and i + 1 < len(rest) and rest[i + 1].startswith("比例="):
            found = rest[i + 1].split("=", 1)[1].strip()
        elif tok.startswith("--set=比例="):
            found = tok.split("比例=", 1)[1].strip()
    return found if found else DEFAULT_RATIO


def print_sizes():
    print("即梦 Seedream 推荐尺寸（2K 级别，宽高比 1:16 ~ 16:1）：")
    print(f"  {'比例':<8} {'像素值':<16} {'总像素':<10} 用途")
    print("  " + "-" * 56)
    uses = {
        "1:1": "方图、社媒卡片、头像",
        "4:3": "横向标准、文章配图",
        "3:4": "竖版海报、小红书封面",
        "16:9": "宽屏、PPT、横版 Banner",
        "9:16": "手机全屏、短视频封面",
        "3:2": "横版摄影",
        "2:3": "竖版摄影、专辑/唱片封面（类型 A/B 默认）",
        "21:9": "超宽屏、电影感",
        "4:5": "社媒九宫格（自行换算）",
        "4:7": "分镜/漫剧（自行换算）",
    }
    for ratio, (w, h) in JIMENG_SIZES.items():
        print(f"  {ratio:<8} {w}×{h:<10} {w*h/1e6:.1f}M     {uses.get(ratio, '')}")


def main():
    # 只识别本脚本自有参数；其余全部原样透传给 fill_meta（含位置参数 track）
    ap = argparse.ArgumentParser(
        description="taxue-imagegen 豆包/即梦适配层：只换算尺寸，不改写 prompt，"
                    "其余参数原样透传 fill_meta"
    )
    ap.add_argument("--sizes", action="store_true", help="列出即梦推荐尺寸")
    ap.add_argument("--platform", choices=["jimeng", "workbuddy", "auto"],
                    default="auto", help="强制平台（默认分层信号链自动检测）")
    ap.add_argument("--debug-platform", action="store_true",
                    help="打印平台检测证据链")
    args, rest = ap.parse_known_args()

    if args.sizes:
        print_sizes()
        return

    platform, evidence = detect_platform(
        forced=None if args.platform == "auto" else args.platform
    )
    if args.debug_platform:
        note = "（--platform 覆盖）" if args.platform != "auto" else ""
        print(f"裁决结果：{platform}{note}\n", file=sys.stderr)
        print(format_evidence(evidence), file=sys.stderr)
        if not rest:
            return

    if not rest:
        ap.error("缺少 fill_meta 参数（如 A --set …）；--sizes 查尺寸、"
                 "--debug-platform 探测环境、A --list 查槽位")

    # 组装 fill_meta 命令，参数 100% 原样透传，不增删改写
    cmd = [sys.executable, FILL_META] + rest

    # WorkBuddy：等价直接跑 fill_meta，stdio 与退出码全部透传，零适配
    if platform == "workbuddy":
        result = subprocess.run(cmd)
        sys.exit(result.returncode)

    # 即梦：fill_meta 原样出稿（prompt 与 preflight 报告原样落到 stdout/stderr），
    # 仅在结束后追加"该用哪个即梦像素尺寸"，不触碰 prompt 内容。
    decisive = next((e for e in evidence if e[3] == platform
                     and e[0].startswith("S")), None)
    why = f"（依据 [{decisive[0]}] {decisive[1]}）" if decisive else ""
    result = subprocess.run(cmd)  # 不 capture：fill_meta 输出原样直达终端

    ratio = ratio_from_passthrough(rest)
    w, h = get_jimeng_size(ratio)
    print(f"\n--- 即梦出图尺寸 {why} ---", file=sys.stderr)
    print(f"  比例 ratio：{ratio}", file=sys.stderr)
    print(f"  width={w}  height={h}（model 用 seedream_5.0_pro）", file=sys.stderr)
    print("  注：prompt 与 preflight 均为 fill_meta 原样输出，本层未改写；"
          "若 preflight 报项在即梦实测不成立，按实际效果判断并走模板迭代，", file=sys.stderr)
    print("      不在适配层静默过滤。", file=sys.stderr)

    # 退出码沿用 fill_meta（preflight 阻断时同样非 0，不掩盖）
    sys.exit(result.returncode)


if __name__ == "__main__":
    _log.run("jimeng", main)
