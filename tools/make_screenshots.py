# -*- coding: utf-8 -*-
"""
tools/make_screenshots.py —— 无窗口生成游戏截图（供 README 与博客使用）

使用 SDL dummy 视频驱动，不弹出窗口，直接调用 main.App 的渲染逻辑
把各界面状态渲染成 PNG 保存到 screenshots/ 目录。
无阻挡/被阻挡箭头均从关卡数据中自动推导，关卡调整后无需修改。

运行方式（在项目根目录）：
    python tools/make_screenshots.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame

from game import Game, Level, solve_order, DIRECTIONS, EMPTY
from levels import LEVELS, MAX_MISTAKES
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
    """在当前关卡中找无阻挡/被阻挡箭头所在的格子中心坐标（多个）。"""
    level = app.game.current
    cells = []
    rows, cols, cell, ox, oy = app.board_geometry()
    for r in range(level.rows):
        for c in range(level.cols):
            if level.grid[r][c] not in DIRECTIONS:
                continue
            blocked = level.is_blocked(r, c)
            if (want_free and not blocked) or (not want_free and blocked):
                cells.append((r, c, ox + c * cell + cell // 2, oy + r * cell + cell // 2))
    return cells


def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    app = app_module.App()

    now = pygame.time.get_ticks()

    # 1) 开始界面
    app.render(screen, now)
    save(screen, "start.png")

    # 2) 进入游戏，显示第 1 关
    app.start_game()
    app.render(screen, now)
    save(screen, "game_level1.png")

    # 3) 碰撞反馈：点击第 1 关中“被阻挡”的箭头 -> 晃动 + 提示 + 失误 -1
    blocked = find_cells(app, want_free=False)
    assert blocked, "第 1 关没有被阻挡的箭头"
    _, _, bx, by = blocked[0]
    app.handle_click((bx, by))
    if app.shake_anims:
        app.shake_anims[0]["t0"] -= 160   # 让晃动动画处于中间帧
    if app.popups:
        app.popups[0]["t0"] -= 160
    app.render(screen, pygame.time.get_ticks())
    save(screen, "collision.png")

    # 4) 飞出动画：点击“无阻挡”的箭头，让箭头处于飞行中间帧
    free = find_cells(app, want_free=True)
    assert free, "第 1 关没有无阻挡的箭头"
    # 选择飞行距离最长的箭头，让截图直观展示“飞到棋盘边缘”
    best = max(free, key=lambda f: app._fly_distance(
        f[0], f[1], app.game.current.initial_dir(f[0], f[1])))
    _, _, fx, fy = best
    app.handle_click((fx, fy))
    if app.fly_anims:
        app.fly_anims[0]["t0"] -= int(0.35 * app.fly_anims[0]["dur"])   # 飞行约 35% 处
    app.render(screen, pygame.time.get_ticks())
    save(screen, "fly_animation.png")

    # 5) 通关界面：用求解器顺序清空第 1 关（未消耗时间，显示 3 星）
    app.game.restart_level()
    app.popups.clear()
    app.shake_anims.clear()
    app.fly_anims.clear()
    order = solve_order(LEVELS[0])
    for r, c in order:
        app.game.click(r, c)
    app.render(screen, pygame.time.get_ticks())
    save(screen, "level_clear.png")

    # 6) 失败界面：构造失误耗尽的第 2 关
    app.start_game()
    app.game.level_index = 1
    app.game.current = app.game.levels[1]
    app.game.current.mistakes = 0
    app.game.state = Game.FAILED
    app.game.fail_reason = "mistakes"
    app.render(screen, pygame.time.get_ticks())
    save(screen, "failed.png")

    # 6b) 超时失败界面：时间耗尽
    app.start_game()
    app.game.current.remaining = 0.2
    app.game.tick(1.0)                     # 时间耗尽 -> FAILED(timeout)
    assert app.game.state == Game.FAILED and app.game.fail_reason == "timeout"
    app.render(screen, pygame.time.get_ticks())
    save(screen, "timeout.png")

    # 7) 全部通关界面：构造全部关卡已清空，显示总星数
    app.start_game()
    for lv in app.game.levels:
        lv.grid = [["." for _ in range(lv.cols)] for _ in range(lv.rows)]  # 已清空
        lv.remaining = lv.time_limit * 0.5              # 用时 50%，全部 3 星 -> 15/15
    app.game.level_index = app.game.total_levels - 1
    app.game.current = app.game.levels[app.game.level_index]
    app.game.state = Game.ALL_CLEAR
    app.render(screen, pygame.time.get_ticks())
    save(screen, "all_clear.png")

    # 8) 第 5 关游戏界面（8x8 高密度棋盘）
    app.start_game()
    app.game.level_index = app.game.total_levels - 1
    app.game.current = app.game.levels[app.game.level_index]
    app.game.state = Game.PLAYING
    app.render(screen, pygame.time.get_ticks())
    save(screen, "game_level5.png")

    # 9) 第 2~4 关游戏界面（随机布局检查）
    for idx in (1, 2, 3):
        app.start_game()                      # 重新生成关卡，确保失误次数为初始值
        app.game.level_index = idx
        app.game.current = app.game.levels[idx]
        app.game.state = Game.PLAYING
        app.render(screen, pygame.time.get_ticks())
        save(screen, "game_level%d.png" % (idx + 1))

    pygame.quit()
    print("ALL_SCREENSHOTS_OK")


if __name__ == "__main__":
    main()
