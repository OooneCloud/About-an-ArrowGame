# -*- coding: utf-8 -*-
"""
tools/make_extra_gifs.py —— 生成两张补充演示 GIF：
  1) 12_solving.gif：AI 求解过程（求解中“撤销/提示/AI求解”按钮全部置灰，箭头自动飞出，最终 1 星通关）
  2) 11_fail.gif  ：失败界面（正常消除后连续点击被阻挡箭头，生命耗尽 -> “生命值耗尽”失败面板）
运行方式（在项目根目录）：
    python tools/make_extra_gifs.py
输出：screenshots/12_solving.gif、screenshots/11_fail.gif
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
from PIL import Image

from game import solve_order, DIRECTIONS
from levels import LEVELS
import main as app_module

SCREEN_W, SCREEN_H = app_module.SCREEN_W, app_module.SCREEN_H
SHOTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "screenshots")

FPS = 60
GIF_EVERY = 4          # 每 4 帧取一帧 -> 15 fps


def cell_center(app, r, c):
    rows, cols, cell, ox, oy = app.board_geometry()
    return (ox + c * cell + cell // 2, oy + r * cell + cell // 2)


def blocked_cells(app):
    """当前关卡中所有“被阻挡”的箭头坐标。"""
    level = app.game.current
    return [(r, c) for r in range(level.rows) for c in range(level.cols)
            if level.grid[r][c] in DIRECTIONS and level.is_blocked(r, c)]


def free_cells(app):
    """当前关卡中所有“无阻挡”的箭头坐标。"""
    level = app.game.current
    return [(r, c) for r in range(level.rows) for c in range(level.cols)
            if level.grid[r][c] in DIRECTIONS and not level.is_blocked(r, c)]


def run_scene(total_frames, actions, out_name):
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    clock = pygame.time.Clock()
    app = app_module.App()

    frames = []
    last = pygame.time.get_ticks()
    for i in range(total_frames):
        now = pygame.time.get_ticks()
        dt = min((now - last) / 1000.0, 0.25)
        last = now

        for event in pygame.event.get():
            pass

        if i in actions:
            kind, arg = actions[i]
            if kind == "start":
                btn = app.buttons.get("start")
                if btn:
                    app.handle_click(btn.rect.center)
            elif kind == "cell":
                app.handle_click(cell_center(app, arg[0], arg[1]))
            elif kind == "solve":
                btn = app.buttons.get("solve")
                if btn:
                    app.handle_click(btn.rect.center)

        app.update(now, dt)
        app.render(screen, now)
        pygame.display.flip()
        clock.tick(FPS)

        if i % GIF_EVERY == 0:
            data = pygame.image.tostring(screen, "RGB")
            img = Image.frombytes("RGB", (SCREEN_W, SCREEN_H), data)
            frames.append(img)

    pygame.quit()

    out = os.path.join(SHOTS, out_name)
    os.makedirs(SHOTS, exist_ok=True)
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=1000 // (FPS // GIF_EVERY), loop=0)
    print("saved:", out, "frames:", len(frames))


def make_solving_gif():
    """AI 求解演示：开始 -> 点“AI求解” -> 按钮置灰、箭头自动飞出 -> 1 星通关面板。"""
    order = solve_order(LEVELS[0])
    assert order
    # 时间表：40 帧后点开始，80 帧后点 AI 求解；求解由 _advance_solve 自动推进
    actions = {40: ("start", None), 80: ("solve", None)}
    # 最后留 40 帧给通关面板展示；求解过程按真实时间约 9 箭头 * 0.35s + 动画
    total = 80 + int(len(order) * 0.35 * FPS) + 200
    run_scene(total, actions, "12_solving.gif")


def make_fail_gif():
    """失败演示：正常消除一个箭头 -> 连续点击被阻挡箭头 3 次 -> 生命耗尽失败面板。"""
    # 被阻挡与无阻挡箭头在场景内动态取（不同关卡/随机生成布局不同）
    actions = {
        40: ("start", None),
        75: ("cell", "__FREE__"),     # 动态替换为第一个无阻挡箭头
        130: ("cell", "__BLOCKED__"),  # 连续 3 次点击被阻挡箭头
        175: ("cell", "__BLOCKED__"),
        220: ("cell", "__BLOCKED__"),
    }
    # 自定义执行：需要动态解析 __FREE__ / __BLOCKED__
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    clock = pygame.time.Clock()
    app = app_module.App()

    total = 300
    frames = []
    last = pygame.time.get_ticks()
    for i in range(total):
        now = pygame.time.get_ticks()
        dt = min((now - last) / 1000.0, 0.25)
        last = now
        for event in pygame.event.get():
            pass

        if i in actions:
            kind, arg = actions[i]
            if kind == "start":
                btn = app.buttons.get("start")
                if btn:
                    app.handle_click(btn.rect.center)
            elif kind == "cell":
                if arg == "__FREE__":
                    cells = free_cells(app)
                    assert cells, "第 1 关没有无阻挡箭头"
                    r, c = cells[0]
                elif arg == "__BLOCKED__":
                    cells = blocked_cells(app)
                    assert cells, "第 1 关没有被阻挡箭头"
                    r, c = cells[0]   # 始终点击同一个被阻挡箭头（3 条命刚好耗尽）
                app.handle_click(cell_center(app, r, c))

        app.update(now, dt)
        app.render(screen, now)
        pygame.display.flip()
        clock.tick(FPS)

        if i % GIF_EVERY == 0:
            data = pygame.image.tostring(screen, "RGB")
            img = Image.frombytes("RGB", (SCREEN_W, SCREEN_H), data)
            frames.append(img)

    pygame.quit()
    out = os.path.join(SHOTS, "11_fail.gif")
    os.makedirs(SHOTS, exist_ok=True)
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=1000 // (FPS // GIF_EVERY), loop=0)
    print("saved:", out, "frames:", len(frames))


def main():
    make_solving_gif()
    make_fail_gif()
    print("EXTRA_GIFS_OK")


if __name__ == "__main__":
    main()
