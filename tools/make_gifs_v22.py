# -*- coding: utf-8 -*-
"""
tools/make_gifs_v22.py —— 生成 v2.2.1 版本的 3 个演示 GIF（README 与博客用）

输出：
  screenshots/10_demo.gif    普通关通关演示（开始→选关→第1关通关→第2关）
  screenshots/11_fail.gif    生命耗尽失败演示
  screenshots/12_solving.gif AI 求解演示（按钮变灰 + 自动通关）

运行方式（在项目根目录）：
    python tools/make_gifs_v22.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
from PIL import Image

from game import Game, Level, solve_order
from levels import LEVELS, MAX_MISTAKES, TIME_LIMITS
import main as app_module

SCREEN_W, SCREEN_H = app_module.SCREEN_W, app_module.SCREEN_H
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "screenshots")

FPS = 60
GIF_EVERY = 4          # 每 4 帧取一帧 -> 15 fps


def cell_center(app, r, c):
    rows, cols, cell, ox, oy = app.board_geometry()
    return (ox + c * cell + cell // 2, oy + r * cell + cell // 2)


def find_blocked(app):
    """当前关卡所有被阻挡箭头格子的中心坐标。"""
    level = app.game.current
    out = []
    rows, cols, cell, ox, oy = app.board_geometry()
    for r in range(level.rows):
        for c in range(level.cols):
            if level.grid[r][c] in app_module.DIRECTIONS and level.is_blocked(r, c):
                out.append((r, c, ox + c * cell + cell // 2, oy + r * cell + cell // 2))
    return out


def run(app, screen, total_frames, actions):
    """按时间表驱动点击并录制 GIF。actions: {frame: ("btn", name)|("cell", (r,c))}"""
    clock = pygame.time.Clock()
    frames = []
    last = pygame.time.get_ticks()
    for i in range(total_frames):
        now = pygame.time.get_ticks()
        dt = min((now - last) / 1000.0, 0.25)
        last = now
        if i in actions:
            kind, arg = actions[i]
            if kind == "btn":
                btn = app.buttons.get(arg)
                if btn:
                    app.handle_click(btn.rect.center)
            elif kind == "cell":
                app.handle_click(cell_center(app, arg[0], arg[1]))
        app.update(now, dt)
        app.render(screen, now)
        pygame.display.flip()
        clock.tick(FPS)
        if i % GIF_EVERY == 0:
            data = pygame.image.tostring(screen, "RGB")
            frames.append(Image.frombytes("RGB", (SCREEN_W, SCREEN_H), data))
    return frames


def save_gif(frames, name):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=1000 // (FPS // GIF_EVERY), loop=0)
    print("saved:", name, "frames:", len(frames))


def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))

    # ---------- 10_demo.gif：普通关通关演示 ----------
    app = app_module.App()
    order1 = solve_order(LEVELS[0])
    order2 = solve_order(LEVELS[1])
    actions = {40: ("btn", "select"), 70: ("btn", "lv0")}
    frame = 105
    for r, c in order1:
        actions[frame] = ("cell", (r, c))
        frame += 34
    actions[frame + 22] = ("btn", "next")       # 通关界面出现后点“下一关”
    frame2 = frame + 22 + 40
    for r, c in order2[:2]:
        actions[frame2] = ("cell", (r, c))
        frame2 += 34
    frames = run(app, screen, frame2 + 46, actions)
    save_gif(frames, "10_demo.gif")

    # ---------- 11_fail.gif：生命耗尽失败演示 ----------
    app = app_module.App()
    actions = {40: ("btn", "select"), 70: ("btn", "lv0")}
    # 第 1 关取一个被阻挡箭头，连续点击 3 次耗尽生命
    blocked = None
    # 进入第 1 关后取被阻挡箭头（先手动进入一次获取坐标）
    app2 = app_module.App()
    app2.enter_level(0)
    bl = find_blocked(app2)
    assert bl, "第 1 关没有被阻挡的箭头"
    blocked = bl[0]
    frame = 105
    for i in range(3):
        actions[frame] = ("cell", (blocked[0], blocked[1]))
        frame += 52
    frames = run(app, screen, frame + 40, actions)
    save_gif(frames, "11_fail.gif")

    # ---------- 12_solving.gif：AI 求解演示（按钮变灰） ----------
    app = app_module.App()
    actions = {40: ("btn", "select"), 70: ("btn", "lv0"), 100: ("btn", "solve")}
    total = 100 + 9 * 22 + 70     # 求解约 0.35s/步，多录一段直到通关
    frames = run(app, screen, total, actions)
    save_gif(frames, "12_solving.gif")

    pygame.quit()
    print("ALL_GIFS_OK")


if __name__ == "__main__":
    main()
