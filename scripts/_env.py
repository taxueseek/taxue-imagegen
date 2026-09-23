#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_env — 依赖自检：缺 numpy / PIL / cv2 时说人话，而不是甩一屏 traceback。

【为什么需要它】
本技能的脚本要 numpy + PIL（量测）与 opencv（去水印）。这些依赖**不保证**在
任何解释器里都有：实测本机 managed 解释器（3.13.12）没有 cv2，而系统 python3
有；`run_tests.sh` 因此专门做了解释器探测（并修过一次「裸 python3 导致 3 项假失败」）。

但**用户直接调用的脚本没有这层保护**：缺依赖时抛的是
`ModuleNotFoundError: No module named 'cv2'`，看不出该装什么、该换哪个解释器，
只能来人肉排查。这就是「未知使用环境的普适性」缺口。

【怎么用】
入口脚本把顶层重型 import 包一层：

    try:
        import numpy as np
        import cv2
    except ImportError as e:
        import os, sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import _env; _env.die(e)

`die()` 会打印：缺哪个包 → 两条修复路径（换解释器 / 装包）→ 本机可用的解释器长什么样，
然后以退出码 2 结束（与 argparse 的用法错误区分开：2 也是「环境没准备好」）。
"""
import os
import re
import subprocess
import sys

# 缺依赖时给出的两条修复路径。第一条优先：本技能在 WorkBuddy 里跑，
# 内置解释器一定带齐依赖，换过去最快也最不容易污染系统环境。
MANAGED_HINT = "~/.workbuddy/binaries/python/envs/default/bin/python3"
PKG_HINT = {"cv2": "opencv-python-headless", "PIL": "pillow", "numpy": "numpy"}

# 探针超时与缓存（2026-09-23 加）：
#   · 单次 30s × 最多 5 个候选 = 最坏 150s —— 「诊断」本身把用户挂住，比不诊断更糟。
#     10s 足够一次 import 完成（正常 <1s）；真挂住的解释器也不值得等。
#   · 同一进程内同一 (解释器, 模块集) 只探一次。
PROBE_TIMEOUT = 10
_PROBE_CACHE = {}


def _pkg_of(exc):
    """从异常里尽量确定「缺的是哪个包」。确定不了就返回 None——不猜。"""
    name = getattr(exc, "name", None)
    if not name:
        m = re.search(r"named '([A-Za-z_][\w.]*)'", str(exc))
        name = m.group(1) if m else None
    return (name or "").split(".")[0] or None


def _probe(path, modules):
    """候选解释器**真的能导入**这些模块吗。

    只判「文件存在」不够：CI runner 上 `/usr/bin/python3` 存在、却没有 cv2，
    照报它等于给出一条走不通的修复路径（2026-09-23 CI 实测，回归 192/194 卡在这里）。
    判不了（不知道缺哪个包）时返回 None —— 此时不排除候选，保守处理。
    """
    mods = sorted({m for m in (modules or []) if m})
    if not mods:
        return None
    key = (path, tuple(mods))
    if key in _PROBE_CACHE:
        return _PROBE_CACHE[key]
    try:
        r = subprocess.run([path, "-c", "import " + ", ".join(mods)],
                           capture_output=True, timeout=PROBE_TIMEOUT)
    except Exception:  # 解释器坏掉 / 超时 / 无执行权限，都算不可用
        _PROBE_CACHE[key] = False
        return False
    _PROBE_CACHE[key] = (r.returncode == 0)
    return _PROBE_CACHE[key]


def _living_interpreters(modules=None):
    """提示里只报**已验证能跑起来**的解释器（存在 + 能导入缺的那些模块），最多两个。

    `best_interpreter()` 的候选里有 WorkBuddy 内置路径——它只在 WorkBuddy 机上有；
    硬编码无条件推荐，会让其他机器上的第一条修复路径指向不存在的文件。
    「存在」仍然不够，见 `_probe`。
    """
    out = []
    cur = os.path.realpath(sys.executable)
    for c in best_interpreter():
        if os.path.realpath(c) == cur or not os.path.exists(c):
            continue
        if _probe(c, modules) is False:
            continue
        out.append(c)
        if len(out) == 2:
            break
    return out


def die(exc, modules=None):
    """报告缺失依赖并退出。`modules` 是本脚本真正需要的包（调用方最清楚）。

    给不出包名时**不猜、也不编 pip 命令**——只把两条修复路径和真实报错给出来，
    否则「pip install simulated missing cv2」这种假命令比 traceback 更误导。
    """
    pkg = _pkg_of(exc)
    print(f"❌ 依赖不可用：{exc}", file=sys.stderr)
    if modules:
        print("   本脚本需要：" + "、".join(modules), file=sys.stderr)
    # 探针探「缺的那个东西」：调用方给了 modules 就用它，否则用从异常里认出来的包名。
    # 两者都拿不到时 `_probe` 返回 None，候选只按存在性收——不猜，也不假装验证过。
    # 2026-09-23 修：**没有做探针时不能声称「已实测能导入」**——那正是 _env 存在的意义
    # （此前 `_env.die(ValueError('boom'))` 会打出「已实测能导入」而根本没探过任何东西）。
    probed = bool(modules or pkg)
    living = _living_interpreters(modules or ([pkg] if pkg else None))
    if living:
        how = "已实测能导入" if probed else "未做可用性验证，仅列出本机存在的解释器"
        print(f"   ① 换解释器重跑（{how}）：{' 或 '.join(living)}", file=sys.stderr)
    else:
        print("   ① 换解释器重跑：本机没找到已带齐依赖的解释器"
              "（WorkBuddy 内置那个一般已带齐，仅 WorkBuddy 机上有）", file=sys.stderr)
    if pkg:
        target = PKG_HINT.get(pkg, pkg)
        req = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
        if os.path.exists(req):
            print(f"   ② 或一次装齐：{sys.executable} -m pip install -r {req}"
                  f"（或单装 {target}）", file=sys.stderr)
        else:
            print(f"   ② 或装上它：{sys.executable} -m pip install {target}", file=sys.stderr)
    else:
        print("   ② 或按上面的报错装齐依赖后重跑", file=sys.stderr)
    print(f"   当前解释器：{sys.executable}", file=sys.stderr)
    raise SystemExit(2)


def best_interpreter():
    """本机可能可用的解释器候选（只用于提示，不用于实际切换进程）。"""
    cands = [os.environ.get("PYTHON"), MANAGED_HINT,
             "/opt/homebrew/bin/python3", "/usr/bin/python3", sys.executable]
    return [os.path.expanduser(c) for c in cands if c]
