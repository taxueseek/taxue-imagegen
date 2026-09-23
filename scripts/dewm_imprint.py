#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""平台署名水印去除（右下角「AI生成 / WORKBUDDY」式固定署名）。

适用边界的判据（2026-09-23 实测，9 张 1536x1024 横版）：
  · dewm 全族解的是「与图像同分布混合的半透明平铺水印」——靠 k̂ 与 R² 反解。
    平台署名是**生成后另贴的固定图案**（位置/形状/透明度恒定），k̂≈0 是必然，
    dewm_v10 会直接报「conf 低 / k̂≈0 → 这张图我解不了」；此时**不要** --no-guard 硬解。
  · rmwm_light 在纸纹底上掩膜退化为 100%（坑 35 同类）→ 会整块抹平，不可用。
  · 故另开本脚本。三条路按「同系列张数」自动选择：

  1) 跨图共识掩膜（N≥2）：署名在 N 张里位置形状一致、图像内容各异
     → 逐像素 min_i(gray_i - median_blur(gray_i)) 把署名从图形边缘里分离出来。
     单图阈值做不到这点：阈值必须放宽才盖得住笔画，于是误纳图形边缘，
     inpaint 后会把飘带/网点抹平一块（比水印本身更显眼）。
  2) αM 反解：I_out = I_bg·(1-αM) + 255·αM，A = median_i(α_i)，I_bg = (I_out-255A)/(1-A)
     保住笔画下的纸纹与网点，但密集笔画处 median 背景失准 → 留一层淡暗鬼影。
  3) 混合路由（默认）：逐图判断底层类型（中值背景已滤掉细笔画，剩余即底层）
     亮(lum>185)且低饱和(sat<45) → 纸底 → inpaint（最干净）
     底层亮度 < --dark（默认 110） → 深色场 → 也走 inpaint
        （实测教训：黑场若走反解，αM 被多数纸底图主导，署名会**整块残留**）
     其余（中间调彩色图形） → 反解（保纹理）

  注意判据不能用「跨图离散度 σ」：σ 大只说明 9 张内容不同，不代表某张此处是图形——
  民国那张署名正压在全纸底上，而它在 9 张间的 σ 同样很大。

单图（N=1）时降级为「单图高亮掩膜 + inpaint」，效果不如 N≥2 的共识版。

用法：
  python3 dewm_imprint.py img/*.png --out _clean          # 同系列多张（推荐）
  python3 dewm_imprint.py one.png --out _clean            # 单图降级
  [--roi x0,y0,x1,y1] [--thresh 0.05] [--dark 110] [--dry-run]
输出一律落 --out，绝不在原图上改写。
"""
import _log
import os, sys, glob, argparse

try:
    import numpy as np
    from PIL import Image
    import cv2
except ImportError as _e:          # 缺依赖时说人话，别甩 traceback（见 scripts/_env.py）
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import _env
    _env.die(_e, ['cv2', 'numpy', 'PIL'])

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dewm_io import safe_target  # noqa: E402


def _median_bg(sub, k=31):
    """逐通道中值背景：细笔画署名被滤掉，剩下的即底层。"""
    return np.stack([cv2.medianBlur(sub[:, :, c], k) for c in range(3)],
                    axis=2).astype(np.float32)


def est_alpha(sub, k=31, floor=12.0):
    """逐像素估计该图的 αM（RGB 三通道分别估）。"""
    x = sub.astype(np.float32)
    bg = _median_bg(sub, k)
    return (x - bg) / np.maximum(255.0 - bg, floor)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--roi", default=None, help="默认右下角 15%% x 12%%（百分号须转义，否则 --help 崩溃）")
    ap.add_argument("--thresh", type=float, default=0.05, help="αM 判定阈值")
    ap.add_argument("--cap", type=float, default=0.92, help="αM 上封顶")
    ap.add_argument("--dark", type=float, default=110.0,
                    help="底层亮度低于此值走 inpaint（深色场反解会残留）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    files = []
    for pat in args.images:
        files.extend(sorted(glob.glob(pat)) or [pat])
    files = [f for f in files if "_textband" not in f]
    if not files:
        sys.exit("no input")

    ims = []
    for f in files:
        im = Image.open(f)
        # >8 位输入必须拒绝，不能「转一下继续」（2026-09-23 实测）：
        # PIL 把 I / I;16 / F 转 RGB 时是按 255 截断的，实测一张 16 位灰图
        # （值域 40000–60000）产出 **100% 纯白的图**，而脚本照旧打印 `[ok]`——
        # 静默产出坏图并报成功，比直接报错坏得多。要 8 位输入就明说。
        if im.mode in ("I", "I;16", "I;16B", "I;16L", "I;16N", "F"):
            sys.exit(f"[abort] {os.path.basename(f)} 是 {im.mode}（超过 8 位）。"
                     f"本脚本只处理 8 位图：直接 convert('RGB') 会把它按 255 截断、整张变纯白，"
                     f"而输出仍会被当成成功。请先降到 8 位（或换 8 位原图）再跑。")
        ims.append(im.convert("RGB"))
    sizes = {im.size for im in ims}
    if len(sizes) != 1:
        sys.exit(f"尺寸不一致，无法跨图统计：{sizes}（请按系列分批）")
    w, h = sizes.pop()
    x0, y0, x1, y1 = (tuple(int(v) for v in args.roi.split(",")) if args.roi
                      else (int(w * 0.85), int(h * 0.88), w, h))

    arrs = [np.asarray(im) for im in ims]
    subs = [a[y0:y1, x0:x1] for a in arrs]
    n = len(files)

    # ---- 掩膜：N≥2 用共识，N=1 用单图高亮 ----
    if n >= 2:
        d = []
        for s in subs:
            g = cv2.cvtColor(s, cv2.COLOR_RGB2GRAY).astype(np.float32)
            d.append(g - cv2.medianBlur(g.astype(np.uint8), 31).astype(np.float32))
        D = np.min(np.stack(d), axis=0)
    else:
        g = cv2.cvtColor(subs[0], cv2.COLOR_RGB2GRAY).astype(np.float32)
        D = g - cv2.medianBlur(g.astype(np.uint8), 31).astype(np.float32)
    m = cv2.dilate((D > 6).astype(np.uint8) * 255, np.ones((5, 5), np.uint8))

    # ---- αM 场 ----
    A = np.median(np.stack([est_alpha(s) for s in subs]), axis=0) if n >= 2 \
        else est_alpha(subs[0])
    A = cv2.blur(np.clip(A, 0.0, args.cap), (3, 3))
    n_g = A.max(axis=2) > args.thresh

    cov = n_g.mean() * 100
    print(f"[imprint] n={n} ROI=({x0},{y0})-({x1},{y1}) 待修={cov:.2f}% "
          f"掩膜覆盖={(m>0).mean()*100:.2f}%")
    if cov > 60:
        print("  [abort] 判定覆盖率 >60%，判据退化（坑 35 同类）—— 拒绝写出")
        # 退出码 2：与「跑完了但没写出」区分开。原先 return 即 rc=0，调用方（含 Agent）
        # 只看退出码会以为成功产出，等于把「没做」报成「做好了」。
        sys.exit(2)
    if args.dry_run:
        print("  [dry] 仅统计，不写出")
        return

    full = np.zeros((h, w), np.uint8)
    full[y0:y1, x0:x1] = m
    for f, a, s in zip(files, arrs, subs):
        sub_bg = _median_bg(s)
        lum = sub_bg.mean(2)
        sat = sub_bg.max(2) - sub_bg.min(2)
        go_inpaint = ((lum > 185) & (sat < 45)) | (lum < args.dark)

        bgr = cv2.cvtColor(a, cv2.COLOR_RGB2BGR)
        filled = cv2.cvtColor(cv2.inpaint(bgr, full, 4, cv2.INPAINT_TELEA),
                              cv2.COLOR_BGR2RGB)
        restored = np.clip((s.astype(np.float32) - 255.0 * A) / np.maximum(1.0 - A, 0.08),
                           0, 255)
        pick = (n_g & ~go_inpaint)[:, :, None]
        base = (n_g & go_inpaint)[:, :, None]
        out_sub = np.where(pick, restored,
                           np.where(base, filled[y0:y1, x0:x1].astype(np.float32),
                                    s.astype(np.float32)))
        out = a.astype(np.float32).copy()
        out[y0:y1, x0:x1] = out_sub
        # 输出守卫：--out 传源目录时 join(basename) 会静默覆盖原图（同族 2026-09-08 踩过）。
        dst = safe_target(f, args.out)
        img_out = Image.fromarray(np.clip(out, 0, 255).round().astype(np.uint8))
        if os.path.splitext(dst)[1].lower() in (".jpg", ".jpeg"):
            # JPEG 是有损的：PIL 默认 quality=75，会把**水印区之外**的像素也重编码
            # （实测 ROI 外最大改动 17 灰阶），A/B 对比能力当场作废。默认提到 95 并关色度下采样。
            img_out.save(dst, quality=95, subsampling=0)
        else:
            img_out.save(dst)
        print(f"  [ok] {os.path.basename(f)}  反解区={pick.mean()*100:.1f}%  "
              f"inpaint区={base.mean()*100:.1f}%")


if __name__ == "__main__":
    _log.run("dewm_imprint", main)
