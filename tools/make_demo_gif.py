# -*- coding: utf-8 -*-
"""
tools/make_demo_gif.py —— 自动演示：按求解器顺序自动点击，录制游戏过程为 GIF

运行方式（在项目根目录）：
    python tools/make_demo_gif.py
输出：screenshots/demo.gif
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame
from PIL import Image

from game import Game, Level, solve_order
from levels import LEVELS, MAX_MISTAKES
import main as app_module

SCREEN_W, SCREEN_H = app_module.SCREEN_W, app_module.SCREEN_H
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "screenshots", "demo.gif")

FPS = 60
GIF_EVERY = 4          # 每 4 帧取一帧 -> 15 fps


def cell_center(app, r, c):
    rows, cols, cell, ox, oy = app.board_geometry()
    return (ox + c * cell + cell // 2, oy + r * cell + cell // 2)


def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    clock = pygame.time.Clock()
    app = app_module.App()

    order1 = solve_order(LEVELS[0])
    order2 = solve_order(LEVELS[1])

    # 动态生成时间表
    actions = {70: ("start", None)}          # 点击“开始游戏”
    frame = 90
    for r, c in order1:                       # 按可行顺序清除第 1 关全部箭头
        actions[frame] = ("cell", (r, c))
        frame += 34
    actions[frame] = ("next", None)           # 点击“下一关”
    frame += 40
    actions[frame] = ("cell", order2[0])      # 第 2 关点击前两个箭头
    frame += 34
    actions[frame] = ("cell", order2[1])
    total_frames = frame + 46

    frames = []
    for i in range(total_frames):
        now = pygame.time.get_ticks()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pass

        if i in actions:
            kind, arg = actions[i]
            if kind == "start":
                btn = app.buttons.get("start")
                if btn:
                    app.handle_click(btn.rect.center)
            elif kind == "cell":
                app.handle_click(cell_center(app, arg[0], arg[1]))
            elif kind == "next":
                btn = app.buttons.get("next")
                if btn:
                    app.handle_click(btn.rect.center)

        app.update(now)
        app.render(screen, now)
        pygame.display.flip()
        clock.tick(FPS)

        if i % GIF_EVERY == 0:
            data = pygame.image.tostring(screen, "RGB")
            img = Image.frombytes("RGB", (SCREEN_W, SCREEN_H), data)
            frames.append(img)

    pygame.quit()

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    frames[0].save(OUT, save_all=True, append_images=frames[1:],
                   duration=1000 // (FPS // GIF_EVERY), loop=0)
    print("saved:", OUT, "frames:", len(frames))


if __name__ == "__main__":
    main()
