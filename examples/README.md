# examples/

> 仓库示例图均来自本技能（taxue-imagegen）的实际出图产出，AI 合规水印已
> 通过 `scripts/dewm_v10.py` 或 `scripts/rmwm.py` 修复剥离。版权与使用条款
> 见 [../ASSET-LICENSE.md](../ASSET-LICENSE.md)；代码、SKILL 指令、脚本
> 与参考文献走 MIT License。

## 五张样张

| 文件 | 赛道 | 主题 | 关键参数 | 出图日期 |
|---|---|---|---|---|
| `example-A-crane-ink.png` | A · 竖版概念海报 | 「踏雪」水墨鹤 | 2:3 · 1024×1536 · 高质量 | 2026-09-07 |
| `example-A-sheer-silk.png` | A · 竖版概念海报（穿插型变体） | 「SHEER」薄纱 | 2:3 · 1024×1536 · 高质量 | 2026-09-07 |
| `example-A-char-matrix.png` | A · 竖版概念海报 | 「字符成画」字符点阵 | 2:3 · 1024×1536 · 高质量 | 2026-09-07 |
| `example-B-dog-lineup.png` | B · 手绘群像 | 犬种图鉴 14 只 | 2:3 · 1024×1536 · 高质量 | 2026-09-06 |
| `example-B-travelers.png` | B · 手绘群像（异形混搭） | 旅团 + 机器人 + 怪物 | 2:3 · 1024×1536 · 高质量 | 2026-09-06 |

赛道 C（写实包装 Mockup）的样张待补——赛道 C 是 v1.9 新增，仓库归档时暂无
现成作品；模板与槽位表见
[`../references/packaging-editorial.md`](../references/packaging-editorial.md)。

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