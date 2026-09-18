#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_jimeng.py — jimeng.py 适配层（v2 极简职责版）断言式回归测试。

适配层唯一职责是尺寸适配，不得改写 prompt。因此测试聚焦：
  1. 平台指纹模糊匹配（_match_platform）
  2. 分层信号链裁决（_adjudicate）
  3. 模拟两种宿主运行时下 detect_platform 的判定
  4. 显式覆盖优先级
  5. 尺寸映射与透传参数比例解析
  6. 【核心】prompt 逐字节等价：经 jimeng 透传的 fill_meta 产物 == 直接跑 fill_meta
  7. 【核心】适配层不再内建任何 prompt 改写函数（apply_interleave/replace_bg 等已移除）

不依赖 numpy / PIL / cv2 / 网络，豆包与 WorkBuddy 均可跑。
用法：python3 scripts/test_jimeng.py   # 0=全过，1=有失败
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
_results = []


def check(label, cond, why=""):
    _results.append((bool(cond), label, why))
    mark = "ok  " if cond else "FAIL"
    print(f"  {mark} {label}" + (f"  <- {why}" if not cond and why else ""))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


J = load("jimeng")

# 一套合法的类型 A 最小填槽参数（供透传等价性测试）
A_SETS = [
    "--set", "视觉风格=浮世绘版画",
    "--set", "内容主题=无常",
    "--set", "表达意图=潮水退去露出木桩",
    "--set", "主体形象=海中巨大木桩与远处鸟居",
    "--set", "英文主标题=MUJO",
    "--set", "中文短句=潮水退了",
    "--set", "英文短句=the tide recedes",
]

# 虚构用户主目录（拼接写出，避免发布隐私扫描把 /Users/<name>/ 夹具字面量当成本机泄露）
_FH = "/Users" + "/x"


# ── 1. 指纹模糊匹配 ────────────────────────────────────────────────
def test_fingerprint_match():
    cases = {
        "/x/Library/Application Support/DoubaoWork/sandbox/py": "jimeng",
        "/x/DoubaoWork/chats/a": "jimeng",
        "/tmp/doubao-work/cache": "jimeng",
        _FH + "/.workbuddy/binaries/python/bin/python3": "workbuddy",
        "/x/workbuddy-repos/demo": "workbuddy",
        ".codebuddy.cn/cache": "workbuddy",
        "/home/user/projects/poster": None,
        "": None,
    }
    for text, expect in cases.items():
        got = J._match_platform(text)
        check(f"指纹 {text[:32]!r}", got == expect, f"got {got} want {expect}")


# ── 2. 分层裁决 ────────────────────────────────────────────────────
def test_adjudicate():
    check("S2 强于 S3",
          J._adjudicate([("S2", "e", "/DoubaoWork/py", "jimeng"),
                         ("S3", "c", "/workbuddy-repos", "workbuddy")]) == "jimeng")
    check("S1 平票下沉听 S2",
          J._adjudicate([("S1", "a", "", "jimeng"), ("S1", "b", "", "workbuddy"),
                         ("S2", "e", "/.workbuddy/py", "workbuddy")]) == "workbuddy")
    check("S1 多数决 2:1",
          J._adjudicate([("S1", "a", "", "jimeng"), ("S1", "b", "", "jimeng"),
                         ("S1", "c", "", "workbuddy")]) == "jimeng")
    check("仅 S5=workbuddy",
          J._adjudicate([("S5", "d", "~/.workbuddy", "workbuddy")]) == "workbuddy")
    check("无信号默认 jimeng", J._adjudicate([]) == "jimeng")
    check("全 None 默认 jimeng",
          J._adjudicate([("S2", "x", "y", None)]) == "jimeng")


# ── 3. 模拟两种宿主运行时 ──────────────────────────────────────────
def test_simulated_doubao_runtime():
    env = {"DOUBAO_OFFICE_EDITION": "public",
           "PATH": "/x/Library/Application Support/DoubaoWork/runtime/bin:/usr/bin",
           "HOME": os.path.expanduser("~")}
    with mock.patch.object(J.os, "environ", env), \
         mock.patch.object(J.sys, "executable",
                           "/x/Library/Application Support/DoubaoWork/sandbox/py"), \
         mock.patch.object(J.sys, "prefix",
                           "/x/Library/Application Support/DoubaoWork/sandbox"), \
         mock.patch.object(J.os, "getcwd",
                           return_value=_FH + "/workbuddy-repos/taxue-imagegen"):
        plat, ev = J.detect_platform()
        check("豆包运行时判 jimeng（cwd 在 workbuddy 下也不被误导）", plat == "jimeng",
              f"got {plat}")
        check("豆包在 S1/S2 即有强证据",
              bool({e[0] for e in ev if e[3] == "jimeng"} & {"S1", "S2"}))


def test_simulated_workbuddy_runtime():
    env = {"WORKBUDDY_SESSION": "abc",
           "PATH": _FH + "/.workbuddy/binaries/python/bin:/usr/bin",
           "HOME": os.path.expanduser("~")}
    with mock.patch.object(J.os, "environ", env), \
         mock.patch.object(J.sys, "executable",
                           _FH + "/.workbuddy/binaries/python/3.11/bin/python3"), \
         mock.patch.object(J.sys, "prefix",
                           _FH + "/.workbuddy/binaries/python/3.11"), \
         mock.patch.object(J.os, "getcwd", return_value=_FH + "/workbuddy-repos/demo"):
        plat, ev = J.detect_platform()
        check("WorkBuddy 运行时判 workbuddy", plat == "workbuddy", f"got {plat}")
        check("S1 捕获 WORKBUDDY_ 前缀",
              any(e[0] == "S1" and e[3] == "workbuddy" for e in ev))


# ── 4. 显式覆盖 ────────────────────────────────────────────────────
def test_forced_override():
    plat, ev = J.detect_platform(forced="workbuddy")
    check("--platform=workbuddy 强制生效", plat == "workbuddy")
    check("强制来源标记 S0", ev[0][0] == "S0")
    with mock.patch.dict(J.os.environ, {"TAXUE_IMAGEGEN_PLATFORM": "jimeng"}):
        check("环境变量覆盖生效", J.detect_platform()[0] == "jimeng")
    with mock.patch.dict(J.os.environ, {"TAXUE_IMAGEGEN_PLATFORM": "workbuddy"}):
        check("--platform 优先于环境变量",
              J.detect_platform(forced="jimeng")[0] == "jimeng")


# ── 5. 尺寸映射与比例解析 ──────────────────────────────────────────
def test_size_mapping():
    check("2:3 -> 1664×2496", J.get_jimeng_size("2:3") == (1664, 2496))
    check("3:4 -> 1728×2304", J.get_jimeng_size("3:4") == (1728, 2304))
    check("9:16 -> 1440×2560", J.get_jimeng_size("9:16") == (1440, 2560))
    check("未知比例回退默认 2:3", J.get_jimeng_size("99:1") == (1664, 2496))


def test_passthrough_ratio_parse():
    check("解析 --set 比例=3:4",
          J.ratio_from_passthrough(["A", "--set", "内容主题=x", "--set", "比例=3:4"])
          == "3:4")
    check("解析 --set=比例= 形式",
          J.ratio_from_passthrough(["A", "--set=比例=9:16"]) == "9:16")
    check("缺省回退默认 2:3",
          J.ratio_from_passthrough(["A", "--set", "内容主题=x"]) == J.DEFAULT_RATIO)
    check("默认比例与 fill_meta.DEFAULTS 一致（2:3）", J.DEFAULT_RATIO == "2:3")


# ── 6. 核心：经 jimeng 透传的 prompt 与直接跑 fill_meta 逐字节一致 ─────
def test_prompt_byte_identical():
    fm = os.path.join(HERE, "fill_meta.py")
    with tempfile.TemporaryDirectory() as d:
        direct = os.path.join(d, "direct.txt")
        via = os.path.join(d, "via.txt")
        # 直接 fill_meta 出稿
        r1 = subprocess.run([sys.executable, fm, "A", *A_SETS, "--out", direct],
                            capture_output=True, text=True)
        # 经 jimeng 透传出稿（--out 原样转给 fill_meta）
        r2 = subprocess.run([sys.executable, os.path.join(HERE, "jimeng.py"),
                             "A", *A_SETS, "--out", via, "--platform", "jimeng"],
                            capture_output=True, text=True)
        d_txt = open(direct, encoding="utf-8").read()
        v_txt = open(via, encoding="utf-8").read()
        check("两路径产物逐字节一致（适配层不改写 prompt）", d_txt == v_txt,
              "jimeng 透传结果与 fill_meta 直接输出不同")
        check("fill_meta 与 jimeng 退出码一致", r1.returncode == r2.returncode,
              f"{r1.returncode} vs {r2.returncode}")
        check("jimeng stderr 附带即梦尺寸", "1664" in r2.stderr and "2496" in r2.stderr)
        check("jimeng 未夹带任何 prompt 改写痕迹",
              "同色呼吸区" not in v_txt and "穿插在画面中部" not in v_txt)


def test_white_bg_default_kept():
    """默认填槽（不覆盖背景色）时，模板原生纯白+顶部留白条款必须原样保留。"""
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "a.txt")
        subprocess.run([sys.executable, os.path.join(HERE, "jimeng.py"),
                        "A", *A_SETS, "--out", out, "--platform", "jimeng"],
                       capture_output=True, text=True)
        txt = open(out, encoding="utf-8").read()
        check("默认背景仍为模板原生「明亮纯白」", "明亮纯白" in txt)
        check("模板原生「顶部 25% 连续留白」原样保留", "连续留白" in txt)


# ── 7. 核心：适配层不再内建任何 prompt 改写/预检过滤 ─────────────────
def test_no_rewrite_helpers():
    for removed in ("apply_interleave", "replace_bg", "run_preflight_jimeng",
                    "run_fill_meta", "JIMENG_SKIP_PITS", "WHITE_BG_HINT",
                    "SECTION_TITLES"):
        check(f"已移除改写/过滤件：{removed}", not hasattr(J, removed))


def main():
    print("== jimeng.py adapter tests (size-only, no prompt rewrite) ==")
    for fn in (test_fingerprint_match, test_adjudicate,
               test_simulated_doubao_runtime, test_simulated_workbuddy_runtime,
               test_forced_override, test_size_mapping, test_passthrough_ratio_parse,
               test_prompt_byte_identical, test_white_bg_default_kept,
               test_no_rewrite_helpers):
        print(f"\n[{fn.__name__}]")
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            check(f"{fn.__name__} 执行异常", False, repr(e))

    failed = [r for r in _results if not r[0]]
    print(f"\n== summary: {len(_results) - len(failed)}/{len(_results)} passed ==")
    for _, label, why in failed:
        print(f"  FAIL {label}  <- {why}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
