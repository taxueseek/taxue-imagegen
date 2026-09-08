#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""explore - taxue-imagegen 探索模式 helper (single / scan).

两种模式共用同一文件落地结构：
  _prompts/NN_xxx.txt  fill_meta 生成的提示词（真源）
  manifest.json        期望文件名 + 槽位值 + 批次序号（用于 rename 与回写）

子命令：
  build   从 CSV 规格生成 n 份提示词 + manifest
  settle  列出 image_dir 中已生成的文件，匹配 manifest 顺序，按 mtime 排序改名
          默认 dry-run；--apply 才执行 mv

CSV 表头：num,style,topic,intent,subject,en,cn,ens,manpu
  manpu 留空 = 孤置型；写 1 = 满铺型
  num 两位（01-99）作前缀；name 留空则用 {num}_{style}

纪律：出图每批 ≤ 3 张（防同秒时间戳撞名），立即 ls 核对 + settle 改名锁定。
"""

import argparse
import csv
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FM = os.path.join(HERE, "fill_meta.py")


def fail(msg):
    print(f"explore: {msg}", file=sys.stderr)
    sys.exit(2)


def slugify(s):
    out = []
    for ch in s:
        if ch.isalnum() or ch in "_-":
            out.append(ch)
        elif ch in " \t":
            out.append("_")
    return "".join(out).strip("_") or "x"


def build(csv_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    # utf-8-sig 自动剥离 BOM（部分编辑器/工具写文件时会带 BOM）
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
    if not rows:
        fail(f"CSV {csv_path} is empty")
    manifest = {"source": os.path.abspath(csv_path), "items": []}
    for r in rows:
        num = r["num"].strip().zfill(2)
        style = r["style"].strip()
        name = r.get("name", "").strip() or slugify(style)
        manpu = r.get("manpu", "").strip() in ("1", "true", "yes", "y")
        out_txt = os.path.join(out_dir, f"{num}_{name}.txt")
        args = [sys.executable, FM, "A",
                "--set", f"视觉风格={style}",
                "--set", f"内容主题={r['topic'].strip()}",
                "--set", f"表达意图={r['intent'].strip()}",
                "--set", f"主体形象={r['subject'].strip()}",
                "--set", f"英文主标题={r['en'].strip()}",
                "--set", f"中文短句={r['cn'].strip()}",
                "--set", f"英文短句={r['ens'].strip()}"]
        if manpu:
            args.append("--manpu")
        args += ["--out", out_txt]
        rc = subprocess.call(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ok = (rc == 0) and os.path.exists(out_txt)
        manifest["items"].append({
            "num": num, "name": name, "style": style,
            "topic": r["topic"].strip(),
            "en": r["en"].strip(),
            "cn": r["cn"].strip(),
            "ens": r["ens"].strip(),
            "manpu": manpu, "prompt": out_txt, "ok": ok,
        })
        flag = "ok  " if ok else "FAIL"
        print(f"{flag} {num} {name}")
    mp = os.path.join(out_dir, "manifest.json")
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"manifest -> {mp}  ({len(rows)} items)")
    return 0


def settle(img_dir, manifest_path, apply=False):
    if not os.path.isdir(img_dir):
        fail(f"img_dir not found: {img_dir}")
    if not os.path.isfile(manifest_path):
        fail(f"manifest not found: {manifest_path}")
    manifest = json.load(open(manifest_path, encoding="utf-8"))
    items = manifest["items"]
    files = []
    for f in os.listdir(img_dir):
        if f.lower().endswith(".png"):
            full = os.path.join(img_dir, f)
            files.append((os.path.getmtime(full), f, full))
    files.sort()
    print(f"found {len(files)} png in {img_dir} (sorted by mtime)")
    if len(files) != len(items):
        print(f"⚠️  expected {len(items)} got {len(files)}  --  "
              f"likely batch collision; identify by reading each file")
    mapping = []
    for i, it in enumerate(items):
        target = f"{it['num']}_{it['name']}.png"
        if i >= len(files):
            mapping.append((None, target, "MISSING"))
            continue
        mapping.append((files[i][1], target, "OK"))
    for src, tgt, status in mapping:
        src_disp = src if src else "---"
        print(f"  {status:7s}  {src_disp:60s}  ->  {tgt}")
    if not apply:
        print("\ndry-run. re-run with --apply to rename.")
        return 0
    n = 0
    for src, tgt, status in mapping:
        if status == "OK":
            os.rename(os.path.join(img_dir, src), os.path.join(img_dir, tgt))
            n += 1
    print(f"renamed {n} files.")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="taxue-imagegen 探索模式 helper (single / scan)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="从 CSV 生成 n 份提示词 + manifest")
    b.add_argument("csv", help="规格 CSV (num,style,topic,intent,subject,en,cn,ens,manpu)")
    b.add_argument("out_dir", help="提示词 + manifest 输出目录")

    s = sub.add_parser("settle", help="核对 img_dir 与 manifest，按 mtime 改名")
    s.add_argument("img_dir", help="出图目录")
    s.add_argument("manifest", help="manifest.json 路径")
    s.add_argument("--apply", action="store_true",
                   help="实际执行 mv（默认 dry-run）")

    a = ap.parse_args()
    if a.cmd == "build":
        sys.exit(build(a.csv, a.out_dir))
    if a.cmd == "settle":
        sys.exit(settle(a.img_dir, a.manifest, a.apply))


if __name__ == "__main__":
    main()
