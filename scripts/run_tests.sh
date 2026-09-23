#!/usr/bin/env bash
# Full test suite for taxue-imagegen. Exits non-zero on any failure.
# Usage: bash scripts/run_tests.sh
#
# 两处都能跑：
#   - 发布仓库（含 README/CHANGELOG/.github）→ 全部检查
#   - 本地 skill 目录（仅 SKILL.md + references + scripts）→ 跳过发布资产检查
# 这样「本地绿、CI 红」不会再出现：同一套脚本，按环境自动取舍。
set -euo pipefail

# 测试跑出来的调用不算「使用数据」——否则 scripts/logs/usage.jsonl 会被
# 每次跑测试灌进上百条噪声，把 log_report.py 的统计淹掉。
# 子进程（含被测脚本的 subprocess 调用）全部继承，一处设好即可。
export TAXUE_LOG=0

cd "$(dirname "$0")/.."
echo "== taxue-imagegen test suite =="

# ── 选解释器 ────────────────────────────────────────────────────────────
# 测试需要 cv2 + numpy + PIL。裸 `python3` 不保证带它们：本机 PATH 首选是
# managed 3.13.12（无 cv2），会让 3 条本可通过的检查**假失败**，把人往错方向带。
# 顺序：显式 $PYTHON → managed venv → PATH 里的 python3 → 常见系统路径。
pick_python() {
    local cand
    for cand in "${PYTHON:-}" \
                "$HOME/.workbuddy/binaries/python/envs/default/bin/python3" \
                "$(command -v python3 || true)" \
                /opt/homebrew/bin/python3 \
                /usr/bin/python3; do
        [ -n "$cand" ] && [ -x "$cand" ] || continue
        if "$cand" -c "import cv2, numpy, PIL" >/dev/null 2>&1; then
            printf '%s' "$cand"; return 0
        fi
    done
    return 1
}
if ! PYBIN="$(pick_python)"; then
    echo "FAIL: 找不到同时具备 cv2 / numpy / PIL 的 python3" >&2
    echo "      可显式指定：PYTHON=/path/to/python3 bash scripts/run_tests.sh" >&2
    exit 1
fi
echo "python: $PYBIN"

pass=0
fail=0
skip=0

# 是否为完整发布仓库（决定是否检查 README/hero 等发布资产）
IS_REPO=0
[ -f README.md ] && [ -f CHANGELOG.md ] && IS_REPO=1

echo ""
echo "[1/8] import-check all scripts"
ok=1
for f in scripts/*.py; do
    if "$PYBIN" -c "
import importlib.util, os, pathlib, sys
p = pathlib.Path('$f')
# 必须把脚本自己所在的目录放进 sys.path —— 这正是「python3 scripts/x.py」的真实
# 运行方式（此时 sys.path[0] 就是 scripts/）。少了这一行，任何顶层 import _log
# 或 from dewm_io import ... 都会假失败，把人引到「脚本坏了」的错方向上。
# 2026-09-23 加：接本地日志时 31 个脚本全被这一步判红，实际都能正常跑。
# 【注意】本代码块在双引号里展开，注释中不得出现反引号或 $()，否则被 bash 当命令执行。
sys.path.insert(0, os.path.dirname(os.path.abspath(str(p))))
spec = importlib.util.spec_from_file_location(p.stem, p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
" 2>/dev/null; then
        echo "  OK $f"
    else
        echo "  FAIL $f"
        ok=0
    fi
done
if [ "$ok" -eq 1 ]; then pass=$((pass+1)); else fail=$((fail+1)); fi

echo ""
echo "[2/8] SKILL.md front-matter"
if "$PYBIN" - <<'PY'
import sys
# 【不要改回固定窗口】历史上这里是 f.read(2048)，撑爆后报「missing front-matter」——
# 看着像 YAML 坏了，其实是长度超窗，两次把人引向错误方向（2048→4096 又复发一次）。
# 闭合符位置与 front-matter 长度无关，按行定位即可，**永不需要调大常数**。
with open("SKILL.md", encoding="utf-8") as f:
    lines = f.read().splitlines()
if not lines or lines[0].strip() != "---":
    print("FAIL: SKILL.md missing front-matter (首行不是 ---)"); sys.exit(1)
end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "---"), None)
if end is None:
    print("FAIL: SKILL.md missing front-matter (找不到闭合 ---)"); sys.exit(1)
fm = "\n".join(lines[1:end])
print(f"OK: front-matter {len(fm)} 字符 / {end - 1} 行（长度无关定位）")
for key in ("name:", "description:"):
    if key not in fm:
        print(f"FAIL: SKILL.md front-matter missing {key}"); sys.exit(1)

# ── YAML 合法性（2026-09-18 新增）──────────────────────────────────
# 实测教训：description 的折叠块里只要有一行**顶格**（列 0），块标量就提前结束，
# yaml.safe_load 直接 ScannerError —— 而宿主是用 yaml.parse 读 front-matter 的。
# 老版本正是这样：触发词段有两行顶格，整个 description 解析不下来，
# 而原来的检查只找 "description:" 这个字符串，全绿放行。所以这里必须真解析。
try:
    import yaml
except ImportError:
    print("SKIP: 未装 PyYAML，跳过 YAML 合法性检查（CI 会装；本地可 pip install pyyaml）")
else:
    try:
        doc = yaml.safe_load(fm)
    except Exception as e:
        print(f"FAIL: front-matter 不是合法 YAML → {type(e).__name__}: {str(e)[:160]}")
        sys.exit(1)
    if not isinstance(doc, dict) or not isinstance(doc.get("description"), str):
        print("FAIL: front-matter 解析后 description 不是字符串（折叠块可能提前结束）")
        sys.exit(1)
    print(f"OK: front-matter 是合法 YAML，description 解析出 {len(doc['description'].encode())} B")

# 体积预算不在本步骤做：单一真源在 scripts/test_regressions.py 的
# SURFACE_BUDGETS（[4/8] 会跑到），避免同一组数字两处维护。
print("OK: SKILL.md front-matter valid")
PY
then
    pass=$((pass+1))
else
    fail=$((fail+1))
fi

echo ""
echo "[3/8] preflight smoke test on Track A template"
if PYTHONPATH=scripts "$PYBIN" - <<'PY'
import re, sys, subprocess, tempfile, os
text = open("references/poster-v5.md", encoding="utf-8").read()
m = re.search(r"^```\n(.*?)^```$", text, re.S | re.M)
if not m:
    print("FAIL: poster-v5.md has no ``` fenced block"); sys.exit(1)
body = m.group(1)
print(f"OK: extracted Track A template, {len(body)} chars, {body.count(chr(10))} lines")
with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
    f.write(body)
    tmp = f.name
try:
    r = subprocess.run(
        [sys.executable, "scripts/preflight.py", tmp, "--track", "A"],
        capture_output=True, text=True, timeout=20,
    )
    print("preflight rc:", r.returncode)
    out = r.stdout.strip()
    if out:
        for line in out.splitlines()[:8]:
            print("  >", line)
    # 0 = pass, 1 = has BLOCK (template with unreplaced slots triggers BLOCK by design — that is expected)
    if r.returncode not in (0, 1):
        print("FAIL: preflight returned", r.returncode); sys.exit(1)
    print("OK: preflight ran without error")
finally:
    os.unlink(tmp)
PY
then
    pass=$((pass+1))
else
    fail=$((fail+1))
fi

echo ""
echo "[4/8] regression tests (assertion-based, per fixed bug)"
if "$PYBIN" scripts/test_regressions.py; then
    pass=$((pass+1))
else
    fail=$((fail+1))
fi

echo ""
echo "[5/8] critical files exist"
missing=""
for f in scripts/fill_meta.py scripts/postcheck.py scripts/preflight.py \
         scripts/measure.py scripts/wm_auto.py scripts/dewm_v10.py scripts/dewm_io.py \
         scripts/test_regressions.py \
         references/poster-v5.md references/crowd-illustration.md \
         references/packaging-editorial.md references/storyboard.md \
         references/pitfalls.md references/size-and-params.md \
         sub-skills/verify/SKILL.md sub-skills/verify/evidence.md; do
    if [ ! -f "$f" ]; then
        missing="$missing $f"
    fi
done
if [ -z "$missing" ]; then
    echo "  OK"
    pass=$((pass+1))
else
    echo "  FAIL missing:$missing"
    fail=$((fail+1))
fi

echo ""
echo "[6/8] release assets"
if [ "$IS_REPO" -eq 0 ]; then
    echo "  SKIP（本地 skill 目录，无 README/CHANGELOG/hero）"
    skip=$((skip+1))
else
    missing=""
    for f in README.md README.en.md CHANGELOG.md LICENSE ASSET-LICENSE.md \
             assets/readme/hero.png assets/readme/hero.svg; do
        [ -f "$f" ] || missing="$missing $f"
    done
    if [ -z "$missing" ]; then
        echo "  OK"
        pass=$((pass+1))
    else
        echo "  FAIL missing:$missing"
        fail=$((fail+1))
    fi
fi

echo ""
echo "[7/8] privacy: no machine-local absolute paths"
leaks=$(grep -rnE '/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/' \
    --include='*.py' --include='*.sh' --include='*.md' --include='*.yml' --include='*.yaml' \
    --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=_research . 2>/dev/null \
    | grep -vE '/(Users|home)/(runner|example|user|yourname)/' \
    | grep -vE 'Users\|home\|runner' || true)
if [ -z "$leaks" ]; then
    echo "  OK"
    pass=$((pass+1))
else
    echo "  FAIL: machine-local absolute paths found:"
    echo "$leaks" | sed 's/^/    /' | head -20
    fail=$((fail+1))
fi

echo ""
echo "[8/8] publish guard: local archive stays local-only"
# 归档目录 _research/ 只本地留存，永不进入公开上传。两道检查：
#   1) git 跟踪状态 + .gitignore 规则是否生效
#   2) 待提交文件里不得残留黑名单词；黑名单本身也放在 _research/ 内，
#      避免守卫代码把敏感词写进发布文件（自我泄漏）。
guard_fail=0
if [ -d .git ]; then
    tracked=$(git ls-files _research/ 2>/dev/null || true)
    if [ -n "$tracked" ]; then
        echo "  FAIL: _research/ 被 git 跟踪（应被 .gitignore 忽略）："
        echo "$tracked" | sed 's/^/    /'
        guard_fail=1
    fi
    if ! git check-ignore -q _research/ 2>/dev/null; then
        echo "  FAIL: .gitignore 未忽略 _research/"
        guard_fail=1
    fi

    kwfile="_research/guard-keywords.txt"
    if [ -f "$kwfile" ]; then
        pat=$(grep -vE '^[[:space:]]*(#|$)' "$kwfile" | paste -sd'|' -)
        # 用换行分隔（-z 的 NUL 无法在 bash 变量中保存，会把文件名拼成一串）
        files=$(git ls-files --cached --others --exclude-standard \
                -- '*.md' '*.py' '*.sh' 2>/dev/null)
        if [ -n "$pat" ] && [ -n "$files" ]; then
            hits=$(printf '%s\n' "$files" | while IFS= read -r f; do
                       [ -f "$f" ] && grep -nIE "$pat" "$f" 2>/dev/null \
                           | sed "s|^|$f:|"
                   done || true)
            if [ -n "$hits" ]; then
                echo "  FAIL: 待提交文件残留归档关键词："
                echo "$hits" | sed 's/^/    /' | head -10
                guard_fail=1
            fi
        fi
    else
        # `${kwfile}` 必须加花括号：紧跟其后的全角「）」是多字节，而部分 bash
        # （本机 5.3.15 实测）会把它的字节当成变量名的一部分 → 变量名成了 `kwfile）`
        # → `set -u` 判未绑定 → **整步静默退出 1**。这一行在 else 分支里，
        # 只有「检出里没有 _research/」时才会执行，所以本地（有 _research/）永远看不到，
        # 而干净检出/CI 会走到——实测干净检出上 [8/8] 就死在这里。
        echo "  SKIP 黑名单缺失（${kwfile}）"
    fi
fi
if [ "$guard_fail" -eq 0 ]; then
    echo "  OK（归档未跟踪，待提交文件无残留）"
    pass=$((pass+1))
else
    fail=$((fail+1))
fi

echo ""
echo "== summary =="
echo "  pass: $pass"
echo "  fail: $fail"
echo "  skip: $skip"

if [ "$fail" -gt 0 ]; then
    exit 1
fi
echo "all checks passed"
