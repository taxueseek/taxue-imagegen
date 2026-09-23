#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_log — 本技能的本地使用日志（只落本地，永不进发布仓）。

【它解决什么问题】
改这个技能的现行流程是「踩到一个坑 → 写进 references/pitfalls.md → 顺手再富化一遍
SKILL.md」。于是常驻面一路涨到 31.5 KB、pitfalls.md 涨到 114 KB，而**「这件事到底
发生过几次」从来没有数据**——写不写进文档全靠印象，结果只增不减。

本模块把每次脚本调用记成一行 JSONL：**数据先落地，攒够频次再回写文档**。
这是把「改技能」从直觉驱动改成数据驱动的那一层，也是「不动不动就改写技能」的落点。

【它不是什么】（与既有机制的边界）
  · 不是出图质量记账 —— 那是 `scripts/logs/runs.csv`，由 postcheck 写，含量测指标
    与 verdict。两者不重叠：runs.csv 回答「这张图怎么样」，usage.jsonl 回答
    「这个技能被怎么用、哪里在报错、哪里在变慢」。
  · 不记提示词正文、不记参数值、不记绝对路径 —— 只记开关名与文件名。
    日志是会被贴进 issue、发给别人看的东西，写进去就收不回来。
  · 不联网、不上传、不影响主流程：写不进去就静默跳过（fail-open）。

【落点与轮转】
  scripts/logs/usage.jsonl   每行一个 JSON 对象
  超过 MAX_BYTES 轮转一份 `.1`（最多留 KEEP_BACKUPS 份），防无限增长。
  该目录已被 `.gitignore` 排除（本地产物），`sync_release.sh` 也排除 logs。

【一行接入】（入口脚本固定两处，`scripts/tests` 有对应门禁）
    import _log                      # 顶部
    ...
    if __name__ == "__main__":
        _log.run("postcheck", main)  # 底部

【关掉】
  环境变量 TAXUE_LOG=0。run_tests.sh 与 CI 都设了它 —— 测试跑的调用不算使用数据。

【看数据】
  python3 scripts/log_report.py
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(HERE, "logs")
LOG_PATH = os.path.join(LOG_DIR, "usage.jsonl")

MAX_BYTES = 2 * 1024 * 1024   # 2 MiB ≈ 上万次调用，够看趋势了
KEEP_BACKUPS = 2
_TRUTHY = ("1", "true", "yes", "on")


def enabled():
    """日志默认开；TAXUE_LOG=0/false/no/off/空 时关（测试与 CI 用它止噪）。"""
    v = os.environ.get("TAXUE_LOG")
    return True if v is None else v.strip().lower() in _TRUTHY


def _where():
    """这次调用跑在哪种宿主上（真源 / 发布仓 / 其它）。只看路径形状，不记路径本身。

    「换宿主就出问题」是本技能反复踩的一类坑（见 references/jimeng-env.md、
    CHANGELOG v1.21.1）。把宿主当维度记下来，普适性问题才有数据可查。
    """
    p = HERE.replace(os.sep, "/")
    if "/.workbuddy/skills/" in p:
        return "workbuddy"
    if "/workbuddy-repos/" in p:
        return "release"
    return "other"


def _flags(argv):
    """只收开关名，丢掉值 —— 值里可能有路径、提示词、文件名。

    `--set 视觉风格=…` 这类「值」一律不进日志；只看用了哪些开关。
    """
    out = []
    for a in (argv or [])[1:]:
        if a.startswith("-") and not a.startswith("---") and len(a) > 1:
            name = a.split("=", 1)[0]
            if name not in out:
                out.append(name)
    return out[:12]


def _rotate():
    """超过上限就轮转：usage.jsonl → .1 → .2，最旧的一份丢弃。"""
    try:
        if os.path.getsize(LOG_PATH) < MAX_BYTES:
            return
    except OSError:
        return
    oldest = f"{LOG_PATH}.{KEEP_BACKUPS}"
    if os.path.exists(oldest):
        try:
            os.remove(oldest)
        except OSError:
            pass
    for i in range(KEEP_BACKUPS - 1, 0, -1):
        src, dst = f"{LOG_PATH}.{i}", f"{LOG_PATH}.{i + 1}"
        if os.path.exists(src):
            try:
                os.replace(src, dst)
            except OSError:
                pass
    try:
        os.replace(LOG_PATH, f"{LOG_PATH}.1")
    except OSError:
        pass


def emit(**fields):
    """写一行 JSONL。**任何失败都吞掉** —— 日志不能拖垮主流程。

    并发安全：单次 `os.write` 到 O_APPEND 打开的描述符。POSIX 保证小于 PIPE_BUF
    （Linux 4096 / macOS 512 字节以上）的单次写是原子的。本技能明确鼓励并行出图与
    并行验收（SKILL.md §3 步 3），若用普通缓冲写，两个进程的行会交错、把 JSONL 写坏。
    一行实际约 150-250 字节，落在安全区内。
    """
    if not enabled():
        return
    try:
        fields.setdefault("ev", "run")
        fields.setdefault("ts", time.strftime("%Y-%m-%d %H:%M:%S"))
        line = json.dumps(fields, ensure_ascii=False, sort_keys=True) + "\n"
        os.makedirs(LOG_DIR, exist_ok=True)
        _rotate()
        fd = os.open(LOG_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
    except Exception:   # noqa: BLE001 —— 故意全吞：日志坏了也不许影响出图
        pass


def run(script, fn):
    """跑入口主函数，并把这次调用记一行。退出码与异常**原样透传**，绝不改写。

    用法：`_log.run("postcheck", main)`。返回值即 `fn()` 的返回值。
    """
    if not enabled():
        return fn()
    t0 = time.perf_counter()
    code, err = 0, ""
    try:
        return fn()
    except SystemExit as e:
        # 与其他脚本的退出码约定保持一致（0=pass / 1=blocker / 2=用法或环境 / 3=pending）
        code = 0 if e.code is None else (e.code if isinstance(e.code, int) else 1)
        raise
    except BaseException as e:   # noqa: BLE001 —— 先记再抛，不改语义
        code, err = 1, type(e).__name__
        raise
    finally:
        emit(script=script, code=code, err=err,
             ms=round((time.perf_counter() - t0) * 1000, 1),
             flags=_flags(sys.argv), host=_where(),
             py=f"{sys.version_info[0]}.{sys.version_info[1]}")


def note(script, **fields):
    """记一条自定义事件（不进主流程时也用得着，如守卫拒绝写出、判据退化中止）。

    不改变任何返回值，纯旁路。
    """
    emit(script=script, ev=fields.pop("ev", "note"), **fields)
