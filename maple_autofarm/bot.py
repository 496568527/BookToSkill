"""冒险岛怀旧服 自动挂机（Windows）。

用法（以管理员身份运行命令行，否则按键可能发不进游戏）:
    python bot.py               # 读取 config.json
    python bot.py my.json       # 指定配置

热键:  F9 开始/暂停   F12 退出
"""
from __future__ import annotations

import ctypes
import json
import random
import sys
import time
from pathlib import Path

import keyboard
import mss
import numpy as np
import pydirectinput
import win32gui

import vision

pydirectinput.PAUSE = 0.0  # 不要库自带的每次按键后 0.1s 延迟

# 高 DPI 屏幕下保证截图坐标和窗口坐标一致
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


# ---------------------------------------------------------------- 窗口 / 截图
class GameWindow:
    def __init__(self, title: str):
        self.title = title
        self.hwnd = self._find()
        self.sct = mss.mss()

    def _find(self) -> int:
        found = []

        def cb(h, _):
            if win32gui.IsWindowVisible(h) and self.title in win32gui.GetWindowText(h):
                found.append(h)

        win32gui.EnumWindows(cb, None)
        if not found:
            sys.exit(f"找不到标题包含「{self.title}」的窗口，请先打开游戏。")
        return found[0]

    def client_rect(self) -> tuple[int, int, int, int]:
        l, t, r, b = win32gui.GetClientRect(self.hwnd)
        x, y = win32gui.ClientToScreen(self.hwnd, (0, 0))
        return x, y, r - l, b - t

    def is_foreground(self) -> bool:
        return win32gui.GetForegroundWindow() == self.hwnd

    def activate(self):
        try:
            win32gui.SetForegroundWindow(self.hwnd)
        except Exception:
            pass

    def grab(self) -> np.ndarray:
        x, y, w, h = self.client_rect()
        shot = self.sct.grab({"left": x, "top": y, "width": w, "height": h})
        return np.asarray(shot)[..., [2, 1, 0]]  # BGRA -> RGB


# ---------------------------------------------------------------- 按键
class Keys:
    def __init__(self):
        self.held: set[str] = set()

    def tap(self, key: str, hold: float = 0.05):
        pydirectinput.keyDown(key)
        time.sleep(hold + random.uniform(0, 0.03))
        pydirectinput.keyUp(key)

    def down(self, key: str):
        if key not in self.held:
            pydirectinput.keyDown(key)
            self.held.add(key)

    def up(self, key: str):
        if key in self.held:
            pydirectinput.keyUp(key)
            self.held.discard(key)

    def release_all(self):
        for k in list(self.held):
            self.up(k)


# ---------------------------------------------------------------- 主逻辑
class Bot:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.k = cfg["keys"]
        self.win = GameWindow(cfg["window_title"])
        self.keys = Keys()

        self.running = False
        self.quit = False
        self.direction = "right"
        self.last_turn = time.time()
        self.last_potion = {"hp": 0.0, "mp": 0.0}
        self.buff_next = {b["key"]: 0.0 for b in cfg["buffs"]}  # 0 = 开始时立刻放一次
        self.step = 0
        self.start_time = time.time()
        self.player_seen_since: float | None = None
        self.last_pos: tuple[float, float] | None = None
        self.last_move_time = time.time()

        keyboard.add_hotkey("f9", self.toggle)
        keyboard.add_hotkey("f12", self.stop)

    # --- 热键
    def toggle(self):
        self.running = not self.running
        if self.running:
            self.win.activate()
            self.last_move_time = time.time()
        else:
            self.keys.release_all()
        log("▶ 开始挂机" if self.running else "⏸ 已暂停")

    def stop(self):
        self.quit = True
        self.running = False
        log("退出中...")

    # --- 各子任务
    def check_potions(self, img) -> bool:
        """返回 False 表示角色可能已经死亡。"""
        p = self.cfg["potion"]
        r = self.cfg["regions"]
        hp = vision.bar_ratio(img, r["hp_bar"], "hp")
        mp = vision.bar_ratio(img, r["mp_bar"], "mp")
        if self.cfg.get("debug"):
            log(f"HP {hp:.0%}  MP {mp:.0%}")
        if hp <= p["dead_threshold"]:
            return False
        now = time.time()
        if hp < p["hp_threshold"] and now - self.last_potion["hp"] > p["cooldown"]:
            self.keys.tap(self.k["hp_potion"])
            self.last_potion["hp"] = now
            log(f"HP {hp:.0%} → 喝红药")
        if mp < p["mp_threshold"] and now - self.last_potion["mp"] > p["cooldown"]:
            self.keys.tap(self.k["mp_potion"])
            self.last_potion["mp"] = now
            log(f"MP {mp:.0%} → 喝蓝药")
        return True

    def check_buffs(self):
        now = time.time()
        for b in self.cfg["buffs"]:
            if now >= self.buff_next[b["key"]]:
                self.keys.release_all()
                self.keys.tap(b["key"])
                time.sleep(b.get("cast_time", 1.0))
                self.buff_next[b["key"]] = now + b["interval"] + random.uniform(0, 5)
                log(f"释放 BUFF [{b['key']}]")

    def check_safety(self, img) -> bool:
        s = self.cfg["safety"]
        if s["max_runtime_minutes"] and time.time() - self.start_time > s["max_runtime_minutes"] * 60:
            log("达到最长挂机时间，自动停止")
            self.stop()
            return False
        if s["pause_when_player_nearby"]:
            n = vision.count_other_players(img, self.cfg["regions"]["minimap"])
            if n:
                self.player_seen_since = self.player_seen_since or time.time()
                if time.time() - self.player_seen_since > s["player_nearby_seconds"]:
                    log(f"小地图上出现 {n} 名其他玩家，自动暂停（F9 继续）")
                    self.player_seen_since = None
                    self.running = False
                    self.keys.release_all()
                    _beep()
                    return False
            else:
                self.player_seen_since = None
        return True

    def decide_direction(self, img):
        pt = self.cfg["patrol"]
        pos = vision.find_self(img, self.cfg["regions"]["minimap"]) if pt["use_minimap"] else None

        if pos is None:  # 没小地图定位：按时间来回走
            if time.time() - self.last_turn > pt["turn_seconds"]:
                self.turn()
            return

        x = pos[0]
        if self.cfg.get("debug"):
            log(f"小地图位置 x={x:.0f}")
        if x <= pt["left_x"] and self.direction == "left":
            self.turn()
        elif x >= pt["right_x"] and self.direction == "right":
            self.turn()

        # 卡住检测：长时间小地图位置不变，跳一下并掉头
        if self.last_pos is None or abs(x - self.last_pos[0]) > 1.5:
            self.last_pos = pos
            self.last_move_time = time.time()
        elif time.time() - self.last_move_time > self.cfg["safety"]["stuck_seconds"]:
            log("疑似卡住，跳跃并掉头")
            self.keys.tap(self.k["jump"])
            self.turn()
            self.last_move_time = time.time()

    def turn(self):
        self.direction = "left" if self.direction == "right" else "right"
        self.last_turn = time.time()

    def fight_step(self):
        pt = self.cfg["patrol"]
        k = self.k
        # 1) 朝当前方向走一小段
        self.keys.down(k[self.direction])
        if pt["jump_attack"]:
            self.keys.tap(k["jump"])
        time.sleep(pt["walk_seconds"])
        self.keys.up(k[self.direction])
        # 2) 原地连续攻击（先轻点方向键转身）
        self.keys.tap(k[self.direction], hold=0.02)
        for _ in range(pt["attacks_per_step"]):
            self.keys.tap(k["attack"])
            time.sleep(pt["attack_interval"] + random.uniform(0, 0.1))
        # 3) 捡东西
        self.step += 1
        if self.step % max(pt["pickup_every"], 1) == 0:
            for _ in range(3):
                self.keys.tap(k["pickup"], hold=0.03)

    # --- 主循环
    def run(self):
        log("已找到游戏窗口。按 F9 开始/暂停，F12 退出。")
        try:
            while not self.quit:
                if not self.running:
                    time.sleep(0.1)
                    continue
                if not self.win.is_foreground():
                    self.keys.release_all()
                    time.sleep(0.3)
                    continue

                img = self.win.grab()
                if not self.check_safety(img):
                    continue
                if not self.check_potions(img):
                    log("HP 归零，角色可能已死亡，停止挂机")
                    self.keys.release_all()
                    self.running = False
                    _beep()
                    continue
                self.check_buffs()
                self.decide_direction(img)
                self.fight_step()
        finally:
            self.keys.release_all()


def _beep():
    try:
        import winsound
        winsound.Beep(1000, 600)
    except Exception:
        pass


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("config.json"))
    cfg = json.loads(path.read_text(encoding="utf-8"))
    Bot(cfg).run()


if __name__ == "__main__":
    main()
