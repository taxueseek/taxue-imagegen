#!/usr/bin/env bash
# One-way sync: the skill's source of truth -> the public repo checkout.
#
# Direction matters, and so does the scope. Two failure modes this script exists to prevent:
#
#   1. Syncing the wrong way. Development happens in the skill directory (`~/.workbuddy/
#      skills/taxue-imagegen`); the release tree is the git checkout of the public repo.
#      A plain `rsync -a --delete` from the release tree back into the skill would delete
#      every local-only asset (`_research/`, `scripts/logs/`) and could silently revert
#      newer skill-side work. So SRC is pinned to this script's own skill directory —
#      never the other way round — and only DEST is passed in.
#
#   2. Deleting release-only files. Unlike a tree that mirrors the skill 1:1, the release
#      repo carries files the skill directory does not have (README.md / README.en.md /
#      LICENSE / ASSET-LICENSE.md / examples/ / assets/ / .github/). A top-level
#      `--delete` would wipe them. So the sync is scoped to the skill payload only, and
#      the release-only files are asserted to still exist afterwards.
#
# Usage:  scripts/sync_release.sh <DEST>          # DEST = the public repo checkout
#         scripts/sync_release.sh <DEST> --dry-run
set -euo pipefail

DRY=""
ITEMIZE=""
if [ "${2:-}" = "--dry-run" ]; then DRY="--dry-run"; ITEMIZE="-i"; fi

if [ $# -lt 1 ]; then
  echo "usage: scripts/sync_release.sh <DEST> [--dry-run]" >&2
  echo "       DEST = checkout of the public repo (must contain README.md)" >&2
  exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$(dirname "$HERE")"
DEST="$1"

for d in "$SRC" "$DEST"; do
  [ -d "$d" ] || { echo "not found: $d" >&2; exit 1; }
done
[ -f "$DEST/README.md" ] || {
  echo "refusing: $DEST does not look like the release checkout (no README.md)" >&2
  exit 1
}
[ "$SRC" != "$DEST" ] || { echo "refusing: SRC == DEST" >&2; exit 1; }

# 注意：排除项不带尾斜杠——rsync 与 diff 都要认这几条，带斜杠只有 rsync 认
EXCLUDES=(--exclude='.git' --exclude='.DS_Store' --exclude='__pycache__'
          --exclude='logs' --exclude='_prompts' --exclude='_prompts_ink'
          --exclude='.trash' --exclude='_research' --exclude='*.pyc')

echo "SRC  = $SRC"
echo "DEST = $DEST $DRY"
echo

# 只同步技能载荷：顶层两个文件 + 三个目录。release-only 文件不在这份清单里，不动它们。
rsync -a $DRY $ITEMIZE "${EXCLUDES[@]}" "$SRC/SKILL.md" "$SRC/CHANGELOG.md" "$DEST/"
for sub in references scripts sub-skills; do
  [ -d "$SRC/$sub" ] || continue
  rsync -a --delete $DRY $ITEMIZE "${EXCLUDES[@]}" "$SRC/$sub/" "$DEST/$sub/"
done

if [ -n "$DRY" ]; then
  echo
  echo "dry-run：上面是将会发生的改动，未写入"
  exit 0
fi

# ① 同步到位：本轮同步的内容必须逐字节一致
rc=0
for f in SKILL.md CHANGELOG.md; do
  cmp -s "$SRC/$f" "$DEST/$f" || { echo "drift: $f" >&2; rc=1; }
done
diff -rq "${EXCLUDES[@]}" "$SRC/references" "$DEST/references" >/dev/null || { echo "drift: references/" >&2; rc=1; }
for sub in scripts sub-skills; do
  diff -rq "${EXCLUDES[@]}" "$SRC/$sub" "$DEST/$sub" >/dev/null || { echo "drift: $sub/" >&2; rc=1; }
done
[ "$rc" -eq 0 ] && echo "✓ 技能载荷逐字节一致"

# ② 发布仓独有的资产必须还在（防「同步顺手把 README 删了」）
missing=0
for f in README.md README.en.md LICENSE ASSET-LICENSE.md .github/workflows/validate.yml; do
  [ -e "$DEST/$f" ] || { echo "release-only asset missing after sync: $f" >&2; missing=1; }
done
[ "$missing" -eq 0 ] && echo "✓ 发布仓独有资产完好（README / LICENSE / CI）"
[ "$rc" -eq 0 ] && [ "$missing" -eq 0 ] || exit 1
echo
echo "下一步（在 DEST 里）：bash scripts/run_tests.sh  →  git commit  →  push"
