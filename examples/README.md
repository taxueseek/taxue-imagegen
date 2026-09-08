# examples/

> 仓库示例图均来自本技能（taxue-imagegen）的实际出图产出，AI 合规水印已
> 通过 `scripts/dewm_v10.py` 或 `scripts/rmwm.py` 修复剥离。版权与使用条款
> 见 [../ASSET-LICENSE.md](../ASSET-LICENSE.md)；代码、SKILL 指令、脚本
> 与参考文献走 MIT License。

## 九张样张

| 文件 | 赛道 | 主题 | 关键参数 | 出图日期 |
|---|---|---|---|---|
| `example-A-crane-ink.png` | A · 竖版概念海报 | 「踏雪」水墨鹤 | 2:3 · 1024×1536 · 高质量 | 2026-09-07 |
| `example-A-sheer-silk.png` | A · 竖版概念海报（穿插型变体） | 「SHEER」薄纱 | 2:3 · 1024×1536 · 高质量 | 2026-09-07 |
| `example-A-char-matrix.png` | A · 竖版概念海报 | 「字符成画」字符点阵 | 2:3 · 1024×1536 · 高质量 | 2026-09-07 |
| `example-B-dog-lineup.png` | B · 手绘群像 | 犬种图鉴 14 只 | 2:3 · 1024×1536 · 高质量 | 2026-09-06 |
| `example-B-travelers.png` | B · 手绘群像（异形混搭） | 旅团 + 机器人 + 怪物 | 2:3 · 1024×1536 · 高质量 | 2026-09-06 |
| `example-C-01-coffee-pouch.png` | C · 写实包装 Mockup | SLOW/ROAST 咖啡袋 | 3:4 · 1152×1536 · 高质量 | 2026-09-08 |
| `example-C-02-glass-serum.png` | C · 写实包装 Mockup | PURE/ACTIVE 精华瓶 + 纸盒 | 3:4 · 1152×1536 · 高质量 | 2026-09-08 |
| `example-C-03-beverage-can.png` | C · 写实包装 Mockup | BITTER/CITRUS 饮料罐 | 3:4 · 1152×1536 · 高质量 | 2026-09-08 |
| `example-C-04-lidded-box.png` | C · 写实包装 Mockup | SILENT/HOURS 天地盖硬盒 | 3:4 · 1152×1536 · 高质量 | 2026-09-08 |

赛道 C 四张对应 [`../references/packaging-editorial.md` §二](../references/packaging-editorial.md)
槽位表的四种包装形态（v1.9 r3 4/4 文字逐字全对实测）。赛道 C 的归档源图位于
`WorkBuddy` 会话工作区（`packaging-halftone/images_r3/`），已迁移至本目录并经
`scripts/dewm_v10.py` 修复水印。

## `explore_sample.csv`

探索模式样表：9 行主题 × 8 字段（`num, style, topic, intent, subject, en,
cn, ens, manpu`），对应 `references/explore-mode.md` §一 的「九张横向采样」
实验配置。跑法：

```bash
python3 scripts/explore.py build examples/explore_sample.csv _prompts/
# 出图后批量改名（防同秒时间戳撞名）：
python3 scripts/explore.py settle _prompts/ _out/
```

## 归档脚本

本地归档推荐：

```bash
cd ~/Pictures/WorkBuddy
python3 _tools/sync_images.py --apply
```

按日期分目录、同主题合并、SHA-256 去重、幂等可反复跑。