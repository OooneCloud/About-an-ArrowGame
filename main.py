# -*- coding: utf-8 -*-
"""
main.py —— “一箭又一箭”小游戏（pygame 图形界面）

运行方式：
    python main.py

命令行参数：
    --smoke [帧数]   无窗口冒烟测试：渲染若干帧后自动退出（用于验证程序可运行）
    --fps            显示帧率（调试用）

界面结构：
    开始界面 -> 游戏界面 -> 通关 / 失败界面
    游戏界面顶部 HUD 显示：当前关卡、剩余箭头数量、剩余失误次数、剩余时间、重新开始按钮
    通关后按“用时 + 失误次数”评定 1~3 颗星
"""

import os
import sys
import math
import argparse

import pygame

from game import Game, Level, DIRECTIONS, EMPTY
from levels import LEVELS, MAX_MISTAKES, TIME_LIMITS

# ---------------------------------------------------------------- 常量
SCREEN_W, SCREEN_H = 780, 700
FPS = 60
HUD_H = 64                      # 顶部信息栏高度

FLY_MS_PER_CELL = 250       # 箭头飞出动画：每格耗时（毫秒），速度恒定
SHAKE_MS = 480              # 碰撞晃动动画时长（毫秒）
POPUP_MS = 900              # 提示文字停留时长（毫秒）

# 配色
COLOR_BG      = (243, 246, 250)   # 背景
COLOR_HUD     = (255, 255, 255)   # 信息栏
COLOR_BOARD   = (232, 238, 245)   # 棋盘格子底色
COLOR_BOARD_BD = (205, 216, 228)
COLOR_TEXT    = (52, 60, 72)
COLOR_SUB     = (120, 132, 148)
COLOR_PRIMARY = (66, 133, 244)    # 主题蓝
COLOR_PRIMARY_DK = (52, 108, 206)
COLOR_DANGER  = (231, 76, 60)
COLOR_GREEN   = (46, 204, 113)
COLOR_OVERLAY = (20, 26, 40)      # 遮罩

# 四种方向的箭头颜色：上红、下蓝、左绿、右橙
DIR_COLORS = {
    "^": (231, 76, 60),
    "v": (52, 152, 219),
    "<": (46, 204, 113),
    ">": (243, 156, 18),
}


# ---------------------------------------------------------------- 工具函数
def make_font(size, bold=False):
    """创建支持中文的字体（依次尝试微软雅黑 / 黑体 / 宋体）。"""
    return pygame.font.SysFont(
        ["microsoftyahei", "simhei", "simsun", "arial"], size, bold=bold)


def draw_text(surface, text, font, color, center):
    """在 (center) 处绘制居中的文字，返回绘制后的矩形。"""
    img = font.render(text, True, color)
    rect = img.get_rect(center=center)
    surface.blit(img, rect)
    return rect


def rounded_rect(surface, rect, color, radius=12, border=0, border_color=None):
    """绘制圆角矩形；border>0 时绘制描边。"""
    if border > 0:
        pygame.draw.rect(surface, border_color, rect, border_radius=radius)
        inner = rect.inflate(-border * 2, -border * 2)
        pygame.draw.rect(surface, color, inner, border_radius=max(radius - border, 0))
    else:
        pygame.draw.rect(surface, color, rect, border_radius=radius)


def draw_star(surface, center, radius, color):
    """绘制一个五角星（尖角朝上），radius 为外接圆半径。"""
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = radius if i % 2 == 0 else radius * 0.45
        pts.append((center[0] + rad * math.cos(ang), center[1] + rad * math.sin(ang)))
    pygame.draw.polygon(surface, color, pts)


class Button:
    """简单的文字按钮：记录矩形与文字，由 App 统一绘制并做点击判定。"""

    def __init__(self, name, rect, text, font, base_color=COLOR_PRIMARY,
                 hover_color=COLOR_PRIMARY_DK, text_color=(255, 255, 255)):
        self.name = name
        self.rect = pygame.Rect(rect)
        self.text = text
        self.font = font
        self.base_color = base_color
        self.hover_color = hover_color
        self.text_color = text_color

    def draw(self, surface, mouse_pos):
        hover = self.rect.collidepoint(mouse_pos)
        color = self.hover_color if hover else self.base_color
        rounded_rect(surface, self.rect, color, radius=self.rect.height // 2)
        draw_text(surface, self.text, self.font, self.text_color, self.rect.center)


# ---------------------------------------------------------------- 箭头绘制
def draw_arrow(surface, center, size, direction, color, offset=(0, 0)):
    """
    在中心点 (center) 绘制一个箭头。
    size 为格子边长的一半左右，方向由 direction 指定，offset 为额外位移（动画用）。
    箭头由“箭杆(粗线段) + 箭头(三角形)”组成，全部用 pygame 基本图形绘制。
    """
    cx, cy = center[0] + offset[0], center[1] + offset[1]
    s = size * 0.38
    w = max(int(s * 0.42), 4)  # 箭杆粗细

    if direction == ">":
        head = [(cx + s, cy), (cx - s * 0.2, cy - s * 0.62), (cx - s * 0.2, cy + s * 0.62)]
        pygame.draw.line(surface, color, (cx - s, cy), (cx + s * 0.2, cy), w)
        pygame.draw.polygon(surface, color, head)
    elif direction == "<":
        head = [(cx - s, cy), (cx + s * 0.2, cy - s * 0.62), (cx + s * 0.2, cy + s * 0.62)]
        pygame.draw.line(surface, color, (cx + s, cy), (cx - s * 0.2, cy), w)
        pygame.draw.polygon(surface, color, head)
    elif direction == "^":
        head = [(cx, cy - s), (cx - s * 0.62, cy + s * 0.2), (cx + s * 0.62, cy + s * 0.2)]
        pygame.draw.line(surface, color, (cx, cy + s), (cx, cy - s * 0.2), w)
        pygame.draw.polygon(surface, color, head)
    elif direction == "v":
        head = [(cx, cy + s), (cx - s * 0.62, cy - s * 0.2), (cx + s * 0.62, cy - s * 0.2)]
        pygame.draw.line(surface, color, (cx, cy - s), (cx, cy + s * 0.2), w)
        pygame.draw.polygon(surface, color, head)


# ---------------------------------------------------------------- 应用主体
class App:
    def __init__(self):
        self.mode = "start"               # start / game
        self.game = None
        self.fly_anims = []               # 飞出动画：[{r, c, d, t0}]
        self.shake_anims = []             # 碰撞晃动：[{r, c, t0}]
        self.popups = []                  # 浮动提示：[{text, x, y, t0, color}]
        self.buttons = {}                 # name -> Button
        self.fonts = {}
        self.mouse_pos = (0, 0)

    # ---------------- 字体缓存 ----------------
    def font(self, size, bold=False):
        key = (size, bold)
        if key not in self.fonts:
            self.fonts[key] = make_font(size, bold)
        return self.fonts[key]

    # ---------------- 游戏流程 ----------------
    def start_game(self):
        """从开始界面进入游戏（回到第 1 关）。"""
        self.game = Game(
            [Level(g, m, t) for g, m, t in zip(LEVELS, MAX_MISTAKES, TIME_LIMITS)]
        )
        self.fly_anims.clear()
        self.shake_anims.clear()
        self.popups.clear()
        self.mode = "game"

    def board_geometry(self):
        """根据当前关卡的棋盘尺寸计算格子大小与棋盘左上角坐标。"""
        rows, cols = self.game.current.rows, self.game.current.cols
        margin = 30
        cell = min(86, (SCREEN_W - 2 * margin) // cols, (SCREEN_H - HUD_H - 2 * margin) // rows)
        board_w, board_h = cols * cell, rows * cell
        ox = (SCREEN_W - board_w) // 2
        oy = HUD_H + (SCREEN_H - HUD_H - board_h) // 2
        return rows, cols, cell, ox, oy

    # ---------------- 动画更新（按帧推进） ----------------
    def update(self, now, dt=0.0):
        if self.mode == "game" and self.game is not None:
            self.game.tick(dt)          # 限时倒计时（仅游戏中状态生效）
        self.fly_anims = [a for a in self.fly_anims if now - a["t0"] < a["dur"]]
        self.shake_anims = [a for a in self.shake_anims if now - a["t0"] < SHAKE_MS]
        self.popups = [p for p in self.popups if now - p["t0"] < POPUP_MS]

    # ---------------- 点击处理 ----------------
    def handle_click(self, pos):
        now = pygame.time.get_ticks()
        if self.mode == "start":
            if self.buttons.get("start") and self.buttons["start"].rect.collidepoint(pos):
                self.start_game()
            return

        # 游戏界面
        if self.game.state == Game.PLAYING:
            # 重新开始按钮
            if self.buttons.get("restart") and self.buttons["restart"].rect.collidepoint(pos):
                self.game.restart_level()
                self.fly_anims.clear()
                self.shake_anims.clear()
                self.popups.clear()
                return
            # 棋盘点击
            rows, cols, cell, ox, oy = self.board_geometry()
            if ox <= pos[0] < ox + cols * cell and oy <= pos[1] < oy + rows * cell:
                c = (pos[0] - ox) // cell
                r = (pos[1] - oy) // cell
                self._on_board_click(r, c, now)
        elif self.game.state == Game.LEVEL_CLEAR:
            if self.buttons.get("next") and self.buttons["next"].rect.collidepoint(pos):
                self.game.next_level()
                self.fly_anims.clear()
                self.shake_anims.clear()
                self.popups.clear()
        elif self.game.state == Game.FAILED:
            if self.buttons.get("retry") and self.buttons["retry"].rect.collidepoint(pos):
                self.game.restart_level()
                self.fly_anims.clear()
                self.shake_anims.clear()
                self.popups.clear()
        elif self.game.state == Game.ALL_CLEAR:
            if self.buttons.get("home") and self.buttons["home"].rect.collidepoint(pos):
                self.mode = "start"

    def _on_board_click(self, r, c, now):
        result, remaining = self.game.click(r, c)
        if result == "fly":
            # 逻辑层已把该格清空，这里从初始棋盘读取方向并计算飞出距离
            d = self.game.current.initial_dir(r, c)
            dist = self._fly_distance(r, c, d)
            self.fly_anims.append({
                "r": r, "c": c, "d": d, "t0": now,
                "dist": dist, "dur": max(int(dist * FLY_MS_PER_CELL), 120),
            })
        elif result == "blocked":
            self.shake_anims.append({"r": r, "c": c, "t0": now})
            rows, cols, cell, ox, oy = self.board_geometry()
            cx = ox + c * cell + cell // 2
            cy = oy + r * cell + cell // 2
            self.popups.append({
                "text": "被挡住了！失误 -1",
                "x": cx, "y": cy - cell // 2,
                "t0": now, "color": COLOR_DANGER,
            })

    def _fly_distance(self, r, c, d):
        """
        计算箭头从格子中心到对应方向棋盘边缘的距离（单位：格），
        并额外加上 0.6 格余量，保证箭头完全飞出棋盘后才消失。
        """
        rows, cols, _, _, _ = self.board_geometry()
        EXIT = 0.6
        if d == ">":
            return (cols - c) - 0.5 + EXIT
        if d == "<":
            return c + 0.5 + EXIT
        if d == "v":
            return (rows - r) - 0.5 + EXIT
        return r + 0.5 + EXIT      # "^"

    # ---------------- 渲染 ----------------
    def render(self, surface, now):
        surface.fill(COLOR_BG)
        self.mouse_pos = pygame.mouse.get_pos()

        if self.mode == "start":
            self._render_start(surface)
        else:
            self._render_game(surface, now)

    def _render_start(self, surface):
        center_x = SCREEN_W // 2
        # 标题
        draw_text(surface, "一箭又一箭", self.font(64, True), COLOR_TEXT, (center_x, 170))
        draw_text(surface, "点击箭头，让所有箭头依次飞出棋盘！",
                  self.font(24), COLOR_SUB, (center_x, 235))

        # 规则说明
        rules = [
            "规则：",
            "· 点击箭头，检查它前进方向直到棋盘边界之间是否有其他箭头；",
            "· 前方无阻挡 → 箭头飞出被消除；有阻挡 → 晃动提示并消耗 1 次失误；",
            "· 清空全部箭头通关，失误次数耗尽或超时则本关失败；",
            "· 通关后按用时与失误评定 1~3 颗星。",
        ]
        y = 300
        for line in rules:
            color = COLOR_TEXT if line == "规则：" else COLOR_SUB
            draw_text(surface, line, self.font(21), color, (center_x, y))
            y += 32

        # 开始按钮
        btn = Button("start", pygame.Rect(center_x - 110, 500, 220, 58),
                     "开始游戏", self.font(28, True))
        btn.draw(surface, self.mouse_pos)
        self.buttons["start"] = btn

        draw_text(surface, "共 %d 关 · 失误 %d~%d 次 · 限时 %d~%d 秒" % (
            len(LEVELS), min(MAX_MISTAKES), max(MAX_MISTAKES),
            min(TIME_LIMITS), max(TIME_LIMITS)),
            self.font(18), COLOR_SUB, (center_x, 600))
        draw_text(surface, "软件工程第二次作业 · 使用 pygame 开发",
                  self.font(16), COLOR_SUB, (center_x, 640))

    def _render_game(self, surface, now):
        game = self.game
        rows, cols, cell, ox, oy = self.board_geometry()
        grid = game.current.grid

        # ---- 顶部 HUD ----
        rounded_rect(surface, pygame.Rect(0, 0, SCREEN_W, HUD_H), COLOR_HUD, radius=0)
        pygame.draw.line(surface, COLOR_BOARD_BD, (0, HUD_H), (SCREEN_W, HUD_H), 2)
        draw_text(surface, "第 %d / %d 关" % (game.level_no, game.total_levels),
                  self.font(26, True), COLOR_TEXT, (90, HUD_H // 2))
        draw_text(surface, "剩余箭头：%d" % game.current.remaining_arrows(),
                  self.font(22), COLOR_TEXT, (250, HUD_H // 2))

        # 剩余失误次数（红心显示）
        self._draw_mistakes(surface, 345, HUD_H // 2, game.current)

        # 剩余时间（≤10 秒变红提示）
        remain_sec = math.ceil(max(0.0, game.current.remaining))
        time_color = COLOR_DANGER if remain_sec <= 10 else COLOR_TEXT
        draw_text(surface, "时间：%d 秒" % remain_sec,
                  self.font(22, True), time_color, (565, HUD_H // 2))

        btn = Button("restart", pygame.Rect(SCREEN_W - 150, 14, 130, 36),
                     "重新开始", self.font(18, True))
        btn.draw(surface, self.mouse_pos)
        self.buttons["restart"] = btn

        # ---- 棋盘 ----
        for r in range(rows):
            for c in range(cols):
                rect = pygame.Rect(ox + c * cell, oy + r * cell, cell, cell)
                rounded_rect(surface, rect, COLOR_BOARD, radius=8)
                pygame.draw.rect(surface, COLOR_BOARD_BD, rect, width=1, border_radius=8)

        # 晃动中的箭头（先画，处于棋盘格内）
        shaking = {(a["r"], a["c"]) for a in self.shake_anims}
        flying = {(a["r"], a["c"]) for a in self.fly_anims}
        for a in self.shake_anims:
            p = (now - a["t0"]) / SHAKE_MS
            dx = math.sin((now - a["t0"]) * 0.055) * 9 * (1 - p)
            dy = math.cos((now - a["t0"]) * 0.07) * 5 * (1 - p)
            ch = grid[a["r"]][a["c"]]
            if ch in DIRECTIONS:
                center = (ox + a["c"] * cell + cell // 2, oy + a["r"] * cell + cell // 2)
                draw_arrow(surface, center, cell // 2, ch, DIR_COLORS[ch], (dx, dy))

        # 棋盘上的箭头
        for r in range(rows):
            for c in range(cols):
                ch = grid[r][c]
                if ch in DIRECTIONS and (r, c) not in flying and (r, c) not in shaking:
                    center = (ox + c * cell + cell // 2, oy + r * cell + cell // 2)
                    draw_arrow(surface, center, cell // 2, ch, DIR_COLORS[ch])

        # 飞出动画（沿方向滑出棋盘，飞越整段距离到棋盘边缘后消失）
        for a in self.fly_anims:
            p = min((now - a["t0"]) / a["dur"], 1.0)
            dr, dc = DIRECTIONS[a["d"]]
            off = (dc * cell * a["dist"] * p, dr * cell * a["dist"] * p)
            center = (ox + a["c"] * cell + cell // 2, oy + a["r"] * cell + cell // 2)
            draw_arrow(surface, center, cell // 2, a["d"], DIR_COLORS[a["d"]], off)

        # 浮动提示
        for p in self.popups:
            age = now - p["t0"]
            alpha = max(0, 255 * (1 - age / POPUP_MS))
            img = self.font(20, True).render(p["text"], True, p["color"])
            img.set_alpha(int(alpha))
            rect = img.get_rect(center=(p["x"], p["y"] - age * 0.03))
            surface.blit(img, rect)

        # ---- 通关 / 失败 / 全部通关 遮罩 ----
        if game.state == Game.LEVEL_CLEAR:
            lv = game.current
            used_sec = math.ceil(lv.elapsed)
            used_mist = lv.max_mistakes - lv.mistakes
            self._render_overlay(surface, "第 %d 关通关！" % game.level_no,
                                 "用时 %d 秒 · 失误 %d 次" % (used_sec, used_mist),
                                 [("next", "下一关")], stars=lv.stars())
        elif game.state == Game.FAILED:
            if game.fail_reason == "timeout":
                title, subtitle = "时间到！", "限时耗尽，本关失败，再试一次吧"
            else:
                title, subtitle = "失误次数耗尽", "本关失败，再试一次吧"
            self._render_overlay(surface, title, subtitle,
                                 [("retry", "重新开始")])
        elif game.state == Game.ALL_CLEAR:
            self._render_overlay(surface, "恭喜通关全部关卡！",
                                 "共获得 %d / %d 颗星" % (
                                     game.total_stars(), game.total_levels * 3),
                                 [("home", "返回首页")])

    def _draw_mistakes(self, surface, x, cy, level):
        """绘制剩余失误次数：红色实心表示剩余，灰色空心表示已消耗。"""
        draw_text(surface, "失误：", self.font(22), COLOR_TEXT, (x, cy))
        step = 26
        start = x + 52
        for i in range(level.max_mistakes):
            cx = start + i * step
            remaining = i < level.mistakes
            color = COLOR_DANGER if remaining else (200, 208, 218)
            pygame.draw.circle(surface, color, (cx, cy), 9)
            pygame.draw.circle(surface, (255, 255, 255), (cx - 3, cy - 3), 3)
        draw_text(surface, str(level.mistakes), self.font(20, True), COLOR_TEXT,
                  (start + level.max_mistakes * step + 12, cy))

    def _render_overlay(self, surface, title, subtitle, buttons, stars=None):
        """绘制半透明遮罩 + 结果面板 +（可选）星级 + 按钮。"""
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((*COLOR_OVERLAY, 150))
        surface.blit(overlay, (0, 0))

        panel_h = 340 if stars is not None else 250
        panel = pygame.Rect(0, 0, 460, panel_h)
        panel.center = (SCREEN_W // 2, SCREEN_H // 2)
        rounded_rect(surface, panel, (255, 255, 255), radius=18)
        pygame.draw.rect(surface, COLOR_BOARD_BD, panel, width=2, border_radius=18)

        ty = panel.centery - 85
        draw_text(surface, title, self.font(36, True), COLOR_TEXT, (SCREEN_W // 2, ty))

        if stars is not None:
            # 星级：金色实心 = 已获得，灰色 = 未获得，并配文字说明
            gold, gray = (243, 156, 18), (205, 216, 228)
            start_x = SCREEN_W // 2 - 2 * 44
            for i in range(3):
                draw_star(surface, (start_x + i * 44, ty + 56), 24,
                          gold if i < stars else gray)
            draw_text(surface, "%d / 3 星" % stars, self.font(18, True), COLOR_SUB,
                      (SCREEN_W // 2, ty + 104))
            sy = ty + 148
        else:
            sy = ty + 70

        draw_text(surface, subtitle, self.font(20), COLOR_SUB, (SCREEN_W // 2, sy))

        bw, bh = 180, 50
        bx = panel.centerx - bw // 2
        by = panel.centery + (120 if stars is not None else 42)
        for name, text in buttons:
            btn = Button(name, pygame.Rect(bx, by, bw, bh), text, self.font(22, True))
            btn.draw(surface, self.mouse_pos)
            self.buttons[name] = btn
            by += bh + 14


# ---------------------------------------------------------------- 主循环
def main():
    parser = argparse.ArgumentParser(description="一箭又一箭小游戏")
    parser.add_argument("--smoke", nargs="?", const=120, type=int, default=0,
                        help="无窗口冒烟测试：渲染指定帧数后自动退出")
    args = parser.parse_args()

    if args.smoke > 0:
        os.environ["SDL_VIDEODRIVER"] = "dummy"

    pygame.init()
    pygame.display.set_caption("一箭又一箭 - 软件工程第二次作业")
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    clock = pygame.time.Clock()

    app = App()
    frame = 0
    running = True
    last = pygame.time.get_ticks()

    while running:
        now = pygame.time.get_ticks()
        dt = min((now - last) / 1000.0, 0.25)   # 每帧真实耗时（秒），限制最大步长
        last = now
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                app.handle_click(event.pos)

        app.update(now, dt)
        app.render(screen, now)
        pygame.display.flip()
        clock.tick(FPS)

        frame += 1
        if args.smoke > 0 and frame >= args.smoke:
            print("SMOKE_OK: rendered %d frames" % frame)
            running = False

    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
