#!/usr/bin/env bash
# Full test suite for taxue-imagegen. Exits non-zero on any failure.
# Usage: bash scripts/run_tests.sh
#
# 两处都能跑：
#   - 发布仓库（含 README/CHANGELOG/.github）→ 全部检查
#   - 本地 skill 目录（仅 SKILL.md + references + scripts）→ 跳过发布资产检查
# 这样「本地绿、CI 红」不会再出现：同一套脚本，按环境自动取舍。
set -euo pipefail

cd "$(dirname "$0")/.."
echo "== taxue-imagegen test suite =="

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
    if python3 -c "
import importlib.util, pathlib
p = pathlib.Path('$f')
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
if python3 - <<'PY'
import re, sys
with open("SKILL.md", encoding="utf-8") as f:
    head = f.read(2048)
m = re.match(r"^---\n(.*?)\n---\n", head, re.S)
if not m:
    print("FAIL: SKILL.md missing front-matter"); sys.exit(1)
fm = m.group(1)
for key in ("name:", "description:"):
    if key not in fm:
        print(f"FAIL: SKILL.md front-matter missing {key}"); sys.exit(1)
print("OK: SKILL.md front-matter valid")
PY
then
    pass=$((pass+1))
else
    fail=$((fail+1))
fi

echo ""
echo "[3/8] preflight smoke test on Track A template"
if PYTHONPATH=scripts python3 - <<'PY'
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
if python3 scripts/test_regressions.py; then
    pass=$((pass+1))
else
    fail=$((fail+1))
fi

echo ""
echo "[5/8] critical files exist"
missing=""
for f in scripts/fill_meta.py scripts/postcheck.py scripts/preflight.py \
         scripts/measure.py scripts/dewm_v10.py scripts/dewm_io.py \
         scripts/test_regressions.py \
         references/poster-v5.md references/crowd-illustration.md \
         references/packaging-editorial.md references/storyboard.md \
         references/pitfalls.md references/size-and-params.md; do
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
        echo "  SKIP 黑名单缺失（$kwfile）"
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
