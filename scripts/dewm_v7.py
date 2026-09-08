"""dewm_v7 — 暗底子水印安全版（v6 反解公式失败的兜底）。

【背景与原理】
v6 数学反解公式 rec = (sub-255·α)/(1-α) 在白底上稳定，0.2s/张、零残留。
但在深色/金色底子上，α=0.71 把分母压到 0.29，PNG 编码的微小舍入误差（±1）
被放大 3.4 倍，叠加金底子高对比纹理后，落成红蓝彩色噪点。

v7 思路：放弃数学反解，改用「α 模板做 mask + cv2.inpaint」。
让周围纹理自然填回水印区，对任何底色都稳定。

【用法】
  python3 dewm_v7.py a.png                         # 输出到 a.png 所在目录的 _clean/a.png
  python3 dewm_v7.py *.png                         # 批量，全部进 _clean/（原图不动）
  python3 dewm_v7.py a.png --out final.png         # 指定目标文件（不得与源文件同名）
  python3 dewm_v7.py *.png --out clean/            # 指定输出目录（不得是源目录本身）
  python3 dewm_v7.py a.png --inplace               # 原地覆盖（危险，需显式声明）
  python3 dewm_v7.py a.png --radius 5              # 加大 inpaint 半径（复杂纹理）
  python3 dewm_v7.py a.png --crop /tmp/zoom.png    # 4x 放大目检裁片

【永不覆盖原图】
输出路径统一由 dewm_io.safe_target() 解析：默认落 `<源目录>/_clean/<原名>`；
`--out` 若指向源文件或源目录则自动重定向到 _clean/ 并告警；
只有显式 `--inplace` 才允许覆盖。详见 dewm_io.py 头部说明。

【何时用哪个】
- 白底 / 浅底图（多数） →  scripts/dewm.py  v6  数学反解，0.2s/张、零残留
- 深色 / 金色 / 满铺图  →  scripts/dewm_v7.py   inpaint 兜底，保留纹理
- 复杂半调纹理         →  scripts/dewm_v7.py --radius 5

依赖：opencv-python-headless、numpy（零模型，0.3s/张）
"""
import argparse, os, sys
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dewm_io import imread_any, imwrite_any, safe_target, add_common_args, save_crop  # noqa: E402

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "wm_alpha_1024.npz")
BASE_W, BASE_H = 1024, 1536


def load_template(W, H):
    z = np.load(TEMPLATE_PATH)
    tm, tbox = z["alpha"], z["box"]
    s = W / BASE_W
    bw, bh = int(round((tbox[2] - tbox[0]) * s)), int(round((tbox[3] - tbox[1]) * s))
    a = cv2.resize(tm, (bw, bh), interpolation=cv2.INTER_LINEAR)
    return a, (W - bw, H - bh)

def inpaint_watermark(img, inpaint_radius=3):
    H, W = img.shape[:2]
    a, (x0, y0) = load_template(W, H)
    # mask: full image size, mark only template bbox region where alpha is meaningful
    mask = np.zeros((H, W), dtype=np.uint8)
    region = (a > 0.05).astype(np.uint8) * 255
    # dilate alpha region to cover anti-aliasing edges that the template missed
    kernel = np.ones((3, 3), np.uint8)
    region = cv2.dilate(region, kernel, iterations=1)
    mask[y0:y0 + region.shape[0], x0:x0 + region.shape[1]] = region
    out = cv2.inpaint(img, mask, inpaint_radius, cv2.INPAINT_TELEA)
    return out, int((mask > 0).sum())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    add_common_args(ap)
    ap.add_argument("--radius", type=int, default=3, help="inpaint radius (default 3)")
    args = ap.parse_args()
    multi = len(args.paths) > 1
    for path in args.paths:
        img = imread_any(path)
        if img is None:
            print(f"skip  {path}"); continue
        H, W = img.shape[:2]
        out, n = inpaint_watermark(img, args.radius)
        name = os.path.basename(path)
        target = safe_target(path, args.out, inplace=args.inplace)
        imwrite_any(target, out)
        print(f"ok    {name}  inpaint_px={n} → {target}")
        save_crop(out, path, args.crop, multi)

if __name__ == "__main__":
    main()
