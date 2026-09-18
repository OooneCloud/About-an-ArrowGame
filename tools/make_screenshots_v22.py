# -*- coding: utf-8 -*-
"""
tools/make_screenshots_v22.py —— 生成 v2.2.1 版本的全部界面截图（README 与博客用）

使用 SDL dummy 视频/音频驱动，不弹窗口，直接调用 main.App 渲染逻辑，
把各界面状态保存为 PNG 到 screenshots/ 目录。

运行方式（在项目根目录）：
    python tools/make_screenshots_v22.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame

pygame.mixer.pre_init(44100, -16, 1, 512)
pygame.init()

from game import Game, Level, solve_order, generate_challenge
from levels import LEVELS, MAX_MISTAKES, TIME_LIMITS
import main as app_module

SCREEN_W, SCREEN_H = app_module.SCREEN_W, app_module.SCREEN_H
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "screenshots")


def save(screen, name):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    pygame.image.save(screen, path)
    print("saved:", name)


def find_cells(app, want_free=True):
    """在当前关卡中找无阻挡/被阻挡箭头所在格子的中心坐标（多个）。"""
    level = app.game.current
    cells = []
    rows, cols, cell, ox, oy = app.board_geometry()
    for r in range(level.rows):
        for c in range(level.cols):
            if level.grid[r][c] not in app_module.DIRECTIONS:
                continue
            blocked = level.is_blocked(r, c)
            if (want_free and not blocked) or (not want_free and blocked):
                cells.append((r, c, ox + c * cell + cell // 2, oy + r * cell + cell // 2))
    return cells


def main():
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    app = app_module.App()
    now = pygame.time.get_ticks()

    # 1) 开始界面（关卡选择 / 挑战关卡）
    app.render(screen, now)
    save(screen, "01_start.png")

    # 2) 选关界面：已通关 1~3 关（显示星级并解锁第 4 关）
    app.completed = {0, 1, 2}
    app.stars = {0: 5, 1: 4, 2: 3}
    app.show_select()
    app.render(screen, now)
    save(screen, "13_level_select.png")

    # 3) 各固定关游戏界面
    for idx, name in [(0, "02_game_level1.png"), (1, "03_game_level2.png"),
                      (2, "game_level3.png"), (3, "game_level4.png"),
                      (4, "04_game_level5.png")]:
        app.enter_level(idx)
        app.render(screen, now)
        save(screen, name)

    # 4) 碰撞反馈：点击第 1 关被阻挡箭头 -> 晃动 + 提示 + 生命 -1
    app.enter_level(0)
    blocked = find_cells(app, want_free=False)
    assert blocked, "第 1 关没有被阻挡的箭头"
    _, _, bx, by = blocked[0]
    app.handle_click((bx, by))
    if app.shake_anims:
        app.shake_anims[0]["t0"] -= 160     # 晃动动画中间帧
    if app.popups:
        app.popups[0]["t0"] -= 160
    app.render(screen, pygame.time.get_ticks())
    save(screen, "05_collision.png")

    # 5) 飞出动画：点击飞行距离最长的箭头，展示“飞到棋盘边缘”
    app.enter_level(0)
    free = find_cells(app, want_free=True)
    assert free, "第 1 关没有无阻挡的箭头"
    best = max(free, key=lambda f: app._fly_distance(
        f[0], f[1], app.game.current.initial_dir(f[0], f[1])))
    _, _, fx, fy = best
    app.handle_click((fx, fy))
    assert app.fly_anims, "点击后没有产生飞出动画"
    app.fly_anims[0]["t0"] -= int(0.55 * app.fly_anims[0]["dur"])
    print("fly anim:", app.fly_anims[0]["r"], app.fly_anims[0]["c"],
          app.fly_anims[0]["d"], "dist=", app.fly_anims[0]["dist"])
    app.render(screen, pygame.time.get_ticks())
    save(screen, "fly_animation.png")

    # 6) 通关界面：按求解顺序清空第 1 关（零失误、零消耗 -> 5 星）
    app.enter_level(0)
    order = solve_order(LEVELS[0])
    for r, c in order:
        app.game.click(r, c)
    app.fly_anims.clear()
    app.shake_anims.clear()
    app.popups.clear()
    app.render(screen, pygame.time.get_ticks())
    save(screen, "06_level_clear.png")

    # 7) 失败界面：生命耗尽（第 2 关）
    app.enter_level(1)
    app.game.current.mistakes = 0
    app.game.state = Game.FAILED
    app.game.fail_reason = "mistakes"
    app.render(screen, pygame.time.get_ticks())
    save(screen, "07_failed.png")

    # 8) 超时失败界面
    app.enter_level(0)
    app.game.current.remaining = 0.2
    app.game.tick(1.0)
    assert app.game.state == Game.FAILED and app.game.fail_reason == "timeout"
    app.render(screen, pygame.time.get_ticks())
    save(screen, "08_timeout.png")

    # 9) 全部通关：总星数 40/40（棋盘已清空）
    app.completed = set(range(8))
    app.stars = {i: 5 for i in range(8)}
    app.enter_level(7)
    lv = app.game.current
    lv.grid = [["." for _ in range(lv.cols)] for _ in range(lv.rows)]  # 已清空
    app.game.state = Game.ALL_CLEAR
    app.render(screen, pygame.time.get_ticks())
    save(screen, "09_all_clear.png")

    # 10) 挑战关卡（10×10 高密度随机棋盘）
    board, n_arrows = generate_challenge()
    app._enter_challenge(board)
    app.render(screen, pygame.time.get_ticks())
    save(screen, "14_challenge.png")

    pygame.quit()
    print("ALL_SCREENSHOTS_OK")


if __name__ == "__main__":
    main()
