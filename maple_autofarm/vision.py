"""纯图像分析：血条/蓝条比例、小地图上自己和其他玩家的位置。

只依赖 numpy，输入是 RGB 的 numpy 数组 (H, W, 3)，坐标都相对游戏窗口客户区。
这样可以脱离游戏、直接拿截图做测试。
"""
from __future__ import annotations

import numpy as np


def _is_red(px: np.ndarray) -> np.ndarray:
    r, g, b = px[..., 0].astype(int), px[..., 1].astype(int), px[..., 2].astype(int)
    return (r > 150) & (g < 100) & (b < 100)


def _is_blue(px: np.ndarray) -> np.ndarray:
    r, g, b = px[..., 0].astype(int), px[..., 1].astype(int), px[..., 2].astype(int)
    return (b > 150) & (r < 100)


def bar_ratio(img: np.ndarray, region: dict, kind: str) -> float:
    """返回 0~1 的填充比例。取 y 行上下各 1 像素，按列投票，抗噪点。"""
    y, x1, x2 = region["y"], region["x1"], region["x2"]
    strip = img[max(y - 1, 0): y + 2, x1: x2 + 1]
    if strip.size == 0:
        return 1.0
    mask = _is_red(strip) if kind == "hp" else _is_blue(strip)
    filled_cols = mask.sum(axis=0) >= 2
    if not filled_cols.any():
        return 0.0
    # 条是从左往右填充的，取最右侧一个“已填充”列的位置作为比例
    last = int(np.nonzero(filled_cols)[0].max())
    return (last + 1) / filled_cols.size


def _blobs(mask: np.ndarray, min_size: int = 3, max_size: int = 60) -> list[tuple[float, float, int]]:
    """极简连通域（4 邻接），返回 [(cx, cy, size)]。小地图很小，不需要 OpenCV。"""
    seen = np.zeros_like(mask, dtype=bool)
    h, w = mask.shape
    out = []
    for sy, sx in zip(*np.nonzero(mask)):
        if seen[sy, sx]:
            continue
        stack, pts = [(sy, sx)], []
        seen[sy, sx] = True
        while stack:
            y, x = stack.pop()
            pts.append((y, x))
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        if min_size <= len(pts) <= max_size:
            ys, xs = zip(*pts)
            out.append((float(np.mean(xs)), float(np.mean(ys)), len(pts)))
    return out


def _crop_minimap(img: np.ndarray, mm: dict) -> np.ndarray:
    return img[mm["y1"]: mm["y2"], mm["x1"]: mm["x2"]]


def find_self(img: np.ndarray, mm: dict) -> tuple[float, float] | None:
    """小地图上自己是一个黄点。返回相对小地图左上角的 (x, y)，找不到返回 None。"""
    crop = _crop_minimap(img, mm).astype(int)
    r, g, b = crop[..., 0], crop[..., 1], crop[..., 2]
    mask = (r > 220) & (g > 200) & (b < 100)
    blobs = _blobs(mask, min_size=4, max_size=40)
    if not blobs:
        return None
    # 地图装饰里也可能有零星黄色像素，取最大的那块
    cx, cy, _ = max(blobs, key=lambda t: t[2])
    return cx, cy


def count_other_players(img: np.ndarray, mm: dict) -> int:
    """小地图上其他玩家是红点。"""
    crop = _crop_minimap(img, mm).astype(int)
    r, g, b = crop[..., 0], crop[..., 1], crop[..., 2]
    mask = (r > 220) & (g < 60) & (b < 60)
    return len(_blobs(mask, min_size=4, max_size=40))
