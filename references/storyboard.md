# 类型 D · 叙事分镜(漫剧切片)· v1.0

> 实测日期：2026-09-08。案例 1：赛博朋克·雨夜侦探 9 帧(1024x1792，9/9 一次通过 + 9/9 CLEAN)。
> 案例 2(2026-09-08)：水墨武侠·孤剑客 9 帧(`build_storyboard_ink.py`，串行 9 连发 0 撞名，8/9 v10 一次 CLEAN，08_eyes 纹理纸底 v10 残留 amp6.3 → pick_wm v7 胜出 CLEAN)。
> 案例 2 结论：①水墨留白风与双 LOCK 兼容良好(红缨单色锚跨帧稳定复现)；②浅纸底去水印 v10 基本直解，纹理区残留走 pick_wm；③泛黄检测对宣纸底/R-B 阈值系统性误报(纸色偏暖)，按材质性豁免处理。

---

## 一、定位：与类型 A/B 的本质区别

| | A 概念海报 | B 手绘群像 | **D 叙事分镜** |
|---|---|---|---|
| 核心约束 | 孤置主体+文字带+留白 | 角色可数+差异化 | **跨帧一致性 + 镜头叙事** |
| 图与图关系 | 相互独立(九风格对比) | 单张内群像 | **连续叙事切片**(同角色/同风格/不同场景) |
| 文字 | 三级文字带是主角 | 无 | **无字纯净**(NEGATIVE 排除) |
| 硬底线 | 纯白背景/比例/留白 | 人数约束 | **LOCK 段逐字复用** |

## 二、核心机制：双 LOCK 一致性锚

ImageGen 各张独立生成(文生图，无 reference 图传递)，跨帧一致性的**唯一可行手段**：
把同一段「风格锚 + 角色档案」**逐字符复用**进每一帧的 prompt。

```
帧 prompt = 开场句 + STYLE_LOCK + CHARACTER_LOCK + SCENE(该帧独有) + NEGATIVE
```

- **STYLE_LOCK**：媒介/色调/光效/构图方向/氛围。色板必须**点名具体色**(如 deep teal + hot magenta + cyan on near-black)，不许只写"赛博朋克风"。
- **CHARACTER_LOCK**：发型(含碎发细节)/瞳色/表情基调/服装(含发光件位置)/义体/随身标志物。锚点选**高辨识、易复现**的特征：发色发型 > 服装轮廓 > 发光件 > 瞳色。仅 3-4 个锚点能稳定复现；更细的(疤痕、首饰)会漂。
- LOCK 段写好后**任何一帧都不许改一个词**——改词=换锚。

## 三、模板全文(可直接抄改)

```text
A single vertical 9:16 movie storyboard frame, one continuous scene, no panel borders.

STYLE LOCK (identical in every frame): <媒介+色板+光效+氛围，一段写死>

CHARACTER LOCK (identical in every frame): <发型+瞳色+表情+服装+义体+标志物，一段写死>

FRAME {n} of 9 — <镜头类型>. <场景/人物动作/光线/构图，本帧唯一可变段>

NEGATIVE: no text, no letters, no numbers, no captions, no speech bubbles, no subtitles, no watermark, no logo, no signature, no border, no panel frame, no split panels, no collage.
```

英文 prompt(size-and-params 实测英文优于中文；镜头术语 wide establishing / tracking shot / two-shot / extreme close-up 模型响应准确)。

## 四、9 帧镜头脚本设计法

叙事弧 + 镜头多样性双轨：
1. **叙事弧**：建立(眺望) → 起(接任务) → 承(深入/问询) → 转(查证/追逐/对峙/揭示) → 合(收尾)。8 帧剧情 + 首尾呼应场景。
2. **镜头轮换**(9 帧全不同)：wide establishing → medium prop shot → full-body tracking → two-shot interior → environmental medium → action diagonal → confrontation side → extreme close-up → wide closing。
3. **光线也推进叙事**：首帧夜雨 → 尾帧黎明，色温弧线本身就是分镜语言。

## 五、实测参数与工程纪律

| 项 | 实测结论 |
|---|---|
| 画幅 | `1024x1792` **精确输出**(实为 4:7 = 0.571，非精确 9:16 = 0.5625；差值 0.9%，肉眼不可辨，2026-09-08 实测漫剧原生比例) |
| 出图方式 | **必须串行**：3 张并行再撞同秒名(08-27-07 两次写入，S3 被覆盖)——坑 17 在分镜场景复现，串行 6 连发 0 事故 |
| 文字控制 | NEGATIVE 对 UI/字幕/水印文字有效(9 帧 0 翻车)；**场景霓虹招牌字保留**(S2 日文ラーメン招牌)——属环境元素，漫剧切片可接受；要全无字需在 SCENE 段写 "signs with abstract glowing shapes instead of letters" |
| 去水印 | pick_wm.py 直接可用(α 模板按宽度锚定，@1024 宽水印位置与 1536 高无关)；9/9 CLEAN，v7 全胜(深色高纹理底 v8 unstable 偏高) |
| 泛黄检测误报 | 尾帧黎明/暖色场景 R-B 会超阈值——**叙事性暖色豁免**，人工确认即可 |

## 六、复用清单(换个题材 = 换两处)

1. 换 `STYLE_LOCK`(例：水墨淡彩+留白 / 吉卜力水彩+暖阳 / 韩系厚涂+低饱和)
2. 换 `CHARACTER_LOCK`(3-5 个高辨识锚点)
3. 按第四节重写 `SCENES` 列表(9 段镜头脚本)
4. 串行出图 → 每张落地即改名锁定 → pick_wm → audit 回扫

构建脚本参考：`scripts/build_storyboard.py`(SCENES 列表驱动，一键生成 9 条 prompt 文件)。
