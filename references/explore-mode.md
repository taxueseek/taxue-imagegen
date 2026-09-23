# 探索模式(taxue-imagegen v1.7 新增，2026-09-07)

> 把"生产模式只出 1 张"的纪律松绑，但用**机器化纪律补偿**：分批出图 + settle 核对 + 结论回写。
> 探索 ≠ 自由。v5 模板和 fill_meta 仍然是单一真源；只是允许 N 张同主题/多主题的横向采样。

---

## 一、两种模式

| 模式 | 何时用 | 出图数量 | 目的 |
|---|---|---|---|
| **single 单风格打磨** | 同一风格 + 多个变体(不同主题/主体/文案) | 2–5 张 | 找出该风格最佳变体；迭代硬底线/文案/构图 |
| **scan 多风格扫描** | 一次测 N 种风格，验证模板泛化 | 5–9 张 | 横向对比、补 #六 已验证填空、发现新风格冲突 |

---

## 二、四条纪律(必须)

1. **每批 ≤ 3 张**(防同秒时间戳撞名，实测 6/9/3 三次撞名均发生)。
2. **每批完成立即 `ls -1` 核对**实际文件数 = 期望；缺失的单独补出。
3. **立即 settle 改名**：用 `explore.py settle` 按 manifest 顺序 + mtime 改名为 `NN_xxx.png`。
4. **结论当场回写**：
   - `single` 保留 1 张最佳(或一次定向修 1 项)，其余弃；
   - `scan` 把通过验收的填进 `poster-v5.md #六·乙`；未通过的写进 `pitfalls.md`。

---

## 三、工作流(标准动作)

```bash
# 0. 准备规格（CSV 在 _spec/explore.csv，1 行 = 1 张）
#    表头：num,style,topic,intent,subject,en,cn,ens,manpu
#    manpu 留空 = 孤置型；写 1 = 满铺型；num 两位（01-99）作前缀

# 1. 出稿（不消耗积分）
python3 explore.py build _spec/explore.csv _prompts/
# → _prompts/NN_xxx.txt + manifest.json

# 2. 出图：每批 3 张，相同 image_dir；出完立即 ls
#    batch 1: 01-03, batch 2: 04-06, batch 3: 07-09
#    工具：ImageGen × 3（并行）

# 3. settle：核对 + 改名
python3 explore.py settle <img_dir> manifest.json     # dry-run
python3 explore.py settle <img_dir> manifest.json --apply

# 4. 验收
python3 postcheck.py *.png --top --dewm --text ok
python3 measure.py --grid /tmp/grid.png *.png
```

---

## 四、积分预算

| 模式 | 默认配额 | 失败补救 | 总计 |
|---|---|---|---|
| `single` | 3 张 × 5–10 = 15–30 | blocker 1 张定向 | 20–40 |
| `scan 9` | 9 × 5–10 = 45–90 | 撞名重出 ≤ 3 张 | 60–120 |

批量 ≥ 5 张先确认(沿用 SKILL #0)。

---

## 五、踩坑速查(已沉淀到 pitfalls.md)

- 坑 17：并行 ImageGen 同秒时间戳撞名 → **分批 + settle**
- 坑 18：`output_dir` 参数被忽略 → 不依赖子目录，自己 mv 锁名
- 坑 19：母题侵入顶部留白(有张力风格)→ 母题下移 + 改写动势向下
- 坑 20：垂直主标题穿越顶部留白(极简主义)→ 列入 known soft，不重出

---

## 六、产出物清单

- `_prompts/NN_xxx.txt` — n 份真源提示词(来自 `fill_meta.py`，与生产模式同链路)
- `manifest.json` — 期望文件名 + 槽位值 + 批次序号(用于 rename 与回写)
- `img/NN_xxx.png` — 落盘图(去水印后)
- `/tmp/grid.png` — 对比图
- `scan` 模式：`poster-v5.md #六·乙` 追加通过项；`pitfalls.md` 追加新发现
