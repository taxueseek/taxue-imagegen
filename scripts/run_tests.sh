#!/usr/bin/env bash
# Full test suite for taxue-imagegen. Exits non-zero on any failure.
# Usage: bash scripts/run_tests.sh
set -euo pipefail

cd "$(dirname "$0")/.."
echo "== taxue-imagegen test suite =="

pass=0
fail=0

echo ""
echo "[1/6] import-check all scripts"
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
echo "[2/6] SKILL.md front-matter"
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
echo "[3/6] preflight smoke test on Track A template"
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
echo "[4/6] critical files exist"
missing=""
for f in README.md README.en.md CHANGELOG.md LICENSE ASSET-LICENSE.md \
         scripts/run_tests.sh scripts/fill_meta.py scripts/postcheck.py scripts/preflight.py \
         references/poster-v5.md references/crowd-illustration.md \
         references/packaging-editorial.md references/pitfalls.md references/size-and-params.md; do
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
echo "[5/6] hero asset present"
if [ -f assets/readme/hero.png ] && [ -f assets/readme/hero.svg ]; then
    echo "  OK"
    pass=$((pass+1))
else
    echo "  FAIL: assets/readme/hero.{png,svg} missing"
    fail=$((fail+1))
fi

echo ""
echo "[6/6] privacy: no machine-local absolute paths"
leaks=$(grep -rnE '/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/' \
    --include='*.py' --include='*.sh' --include='*.md' --include='*.yml' --include='*.yaml' \
    --exclude-dir=.git --exclude-dir=__pycache__ . 2>/dev/null \
    | grep -vE '/(Users|home)/(runner|example|user|yourname)/' || true)
if [ -z "$leaks" ]; then
    echo "  OK"
    pass=$((pass+1))
else
    echo "  FAIL: machine-local absolute paths found:"
    echo "$leaks" | sed 's/^/    /' | head -20
    fail=$((fail+1))
fi

echo ""
echo "== summary =="
echo "  pass: $pass"
echo "  fail: $fail"

if [ "$fail" -gt 0 ]; then
    exit 1
fi
echo "all checks passed"