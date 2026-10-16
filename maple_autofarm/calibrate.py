"""校准工具：自动找出血条/蓝条坐标，并显示你在小地图上的位置。

请在【满血满蓝】时运行（以管理员身份）:
    python calibrate.py                 # 截取游戏窗口
    python calibrate.py shot.png        # 或者分析一张截图（截图需只包含游戏客户区）

运行后会更新 config.json 里的 hp_bar / mp_bar，并保存 calibrate_debug.png 供检查。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import vision

CFG = Path(__file__).with_name("config.json")


def longest_run(mask_row: np.ndarray) -> tuple[int, int]:
    best, start, cur = (0, -1), None, 0
    for x, v in enumerate(list(mask_row) + [False]):
        if v and start is None:
            start = x
        elif not v and start is not None:
            if x - start > best[0]:
                best = (x - start, start)
            start = None
    return best[1], best[1] + best[0] - 1


def find_bar(img: np.ndarray, kind: str, x_min: int = 0) -> dict | None:
    h = img.shape[0]
    pred = vision._is_red if kind == "hp" else vision._is_blue
    best = None
    for y in range(h - 80, h):
        x1, x2 = longest_run(pred(img[y, x_min:]))
        if x1 >= 0 and (best is None or x2 - x1 > best[2] - best[1]):
            best = (y, x1 + x_min, x2 + x_min)
    if best is None or best[2] - best[1] < 50:
        return None
    # 取条形区域的中间行
    y, x1, x2 = best
    rows = [yy for yy in range(h - 80, h) if pred(img[yy, x1:x2 + 1]).mean() > 0.9]
    return {"x1": x1, "x2": x2, "y": int(np.median(rows)) if rows else y}


def grab_game(title: str) -> np.ndarray:
    from bot import GameWindow
    return GameWindow(title).grab()


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    img = (np.array(Image.open(sys.argv[1]).convert("RGB")) if len(sys.argv) > 1
           else grab_game(cfg["window_title"]))
    print("客户区尺寸:", img.shape[1], "x", img.shape[0])

    hp = find_bar(img, "hp")
    mp = find_bar(img, "mp", x_min=hp["x2"] + 1) if hp else None
    if hp and mp:
        # 蓝条宽度与血条相同（蓝不满时识别到的会偏短）
        mp["x2"] = mp["x1"] + (hp["x2"] - hp["x1"])
        cfg["regions"]["hp_bar"], cfg["regions"]["mp_bar"] = hp, mp
        CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        print("血条:", hp, "\n蓝条:", mp, "\n已写入 config.json")
    else:
        print("没识别到血条/蓝条，请确认满血满蓝、窗口没被遮挡，或手动填写 config.json")

    r = cfg["regions"]
    print(f"当前 HP {vision.bar_ratio(img, r['hp_bar'], 'hp'):.0%}  MP {vision.bar_ratio(img, r['mp_bar'], 'mp'):.0%}")
    mm = r["minimap"]
    pos = vision.find_self(img, mm)
    print("小地图上自己的位置:", "未找到（检查 minimap 区域）" if pos is None else f"x={pos[0]:.0f}, y={pos[1]:.0f}")
    print("其他玩家数:", vision.count_other_players(img, mm))
    print("提示: 走到你想巡逻的左端/右端各运行一次，把 x 填进 patrol.left_x / right_x")

    dbg = Image.fromarray(img)
    d = ImageDraw.Draw(dbg)
    for key, color in (("hp_bar", "yellow"), ("mp_bar", "cyan")):
        b = r[key]
        d.rectangle([b["x1"], b["y"] - 3, b["x2"], b["y"] + 3], outline=color)
    d.rectangle([mm["x1"], mm["y1"], mm["x2"], mm["y2"]], outline="magenta")
    if pos:
        px, py = mm["x1"] + pos[0], mm["y1"] + pos[1]
        d.ellipse([px - 5, py - 5, px + 5, py + 5], outline="red", width=2)
    out = Path(__file__).with_name("calibrate_debug.png")
    dbg.save(out)
    print("已保存", out)


if __name__ == "__main__":
    main()
