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
    游戏界面顶部 HUD 显示：当前关卡、剩余生命（红点）、剩余时间，右上角“重新开始”按钮
    棋盘下方：撤销 / 提示 / AI求解 功能按钮（各限 3 次，按钮显示剩余次数）
    通关后按“用时 + 生命消耗 + 撤销次数 + 提示次数”评定 1~5 颗星；使用 AI 求解直接 1 星
    通关界面延迟到最后一个箭头完全飞出棋盘后再显示
辅助功能：撤销上一步（3 次）、提示可消除箭头（3 次）、AI 自动求解通关（评分 1 星）
箭头飞出时有程序生成的“嗖”声效（不依赖外部素材）
"""

import os
import sys
import math
import argparse

import pygame

from game import Game, Level, DIRECTIONS, EMPTY, solve_order
from levels import LEVELS, MAX_MISTAKES, TIME_LIMITS

# ---------------------------------------------------------------- 常量
SCREEN_W, SCREEN_H = 780, 700
FPS = 60
HUD_H = 64                      # 顶部信息栏高度

FLY_MS_PER_CELL = 250       # 箭头飞出动画：每格耗时（毫秒），速度恒定
SHAKE_MS = 480              # 碰撞晃动动画时长（毫秒）
POPUP_MS = 900              # 提示文字停留时长（毫秒）
SOLVE_STEP = 0.35           # AI 求解：每步间隔（秒）

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
COLOR_GOLD    = (243, 156, 18)   # 提示高亮 / 星级金色
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


_VIS_CENTER_CACHE = {}   # (text, 字号, 粗体) -> 视觉中心偏移量（像素）


def draw_text(surface, text, font, color, center, visual_center=False):
    """
    在 (center) 处绘制居中的文字，返回绘制后的矩形。
    visual_center=True 时按字形实际像素范围做“视觉居中”修正：
    中文字体的全角标点（如“！”）在边界框内有不对称留白，按边界框居中会整体偏左，
    修正后文字视觉重心与 (center) 对齐。
    """
    img = font.render(text, True, color)
    rect = img.get_rect(center=center)
    if visual_center:
        key = (text, font.get_height(), font.get_bold())
        off = _VIS_CENTER_CACHE.get(key)
        if off is None:
            w, h = img.get_size()
            raw = pygame.image.tostring(img, "RGBA")
            left, right = w, -1
            for yy in range(h):
                row = yy * w
                for xx in range(w):
                    if raw[(row + xx) * 4 + 3] > 8:   # alpha 可见像素
                        if xx < left:
                            left = xx
                        if xx > right:
                            right = xx
            off = ((left + right) / 2 - w / 2) if right >= left else 0.0
            _VIS_CENTER_CACHE[key] = off
        rect.centerx = round(center[0] - off)
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


def _make_swish_sound():
    """
    程序生成一个短促的“嗖”声（频率上扫 + 指数衰减），用于箭头飞出。
    不依赖任何外部音频素材；mixer 不可用（如无音频设备、冒烟测试）时返回 None。
    """
    try:
        if not pygame.mixer.get_init():
            return None
        import array
        rate = 44100
        dur = 0.16
        n = int(rate * dur)
        samples = array.array("h")
        for i in range(n):
            t = i / rate
            f = 500 + 1500 * (t / dur)              # 500Hz -> 2000Hz 上扫
            env = (1 - t / dur) ** 1.8               # 衰减包络
            v = int(12000 * env * math.sin(2 * math.pi * f * t))
            samples.append(max(-32767, min(32767, v)))
        return pygame.mixer.Sound(buffer=samples.tobytes())
    except Exception:
        return None


class Button:
    """简单的文字按钮：记录矩形与文字，由 App 统一绘制并做点击判定。"""

    def __init__(self, name, rect, text, font, base_color=COLOR_PRIMARY,
                 hover_color=COLOR_PRIMARY_DK, text_color=(255, 255, 255),
                 enabled=True):
        self.name = name
        self.rect = pygame.Rect(rect)
        self.text = text
        self.font = font
        self.base_color = base_color
        self.hover_color = hover_color
        self.text_color = text_color
        self.enabled = enabled

    def draw(self, surface, mouse_pos):
        if not self.enabled:
            # 禁用态：灰色底 + 浅色文字，不响应 hover
            rounded_rect(surface, self.rect, (185, 192, 202), radius=self.rect.height // 2)
            draw_text(surface, self.text, self.font, (235, 239, 244), self.rect.center)
            return
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
        self.hint_cell = None             # 提示高亮的箭头 (r, c)
        self.solving = False              # AI 求解进行中
        self.solve_seq = None             # 求解点击顺序
        self.solve_idx = 0
        self.solve_timer = 0.0
        self.snd_fly = _make_swish_sound()   # 箭头飞出音效（程序生成）

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
        self.hint_cell = None
        self._stop_solve()
        self.mode = "game"

    def _stop_solve(self):
        """停止 AI 求解并清空相关状态。"""
        self.solving = False
        self.solve_seq = None
        self.solve_idx = 0
        self.solve_timer = 0.0

    def _start_solve(self):
        """用贪心求解器算出当前关卡的通关顺序，并开始自动执行。"""
        seq = solve_order(self.game.current.grid)
        if not seq:
            self.popups.append({
                "text": "当前局面无解，无法自动求解", "x": SCREEN_W // 2,
                "y": 150, "t0": pygame.time.get_ticks(), "color": COLOR_DANGER,
            })
            return
        self.hint_cell = None
        self.game.use_ai_solve()      # 标记本关使用了 AI 求解：评分直接 1 星
        self.solving = True
        self.solve_seq = seq
        self.solve_idx = 0
        self.solve_timer = 0.0

    def board_geometry(self):
        """根据当前关卡的棋盘尺寸计算格子大小与棋盘左上角坐标（底部预留功能按钮区）。"""
        rows, cols = self.game.current.rows, self.game.current.cols
        margin = 30
        btn_area = 64                       # 底部“撤销/提示/AI求解”按钮区高度
        cell = min(86, (SCREEN_W - 2 * margin) // cols,
                   (SCREEN_H - HUD_H - 2 * margin - btn_area) // rows)
        board_w, board_h = cols * cell, rows * cell
        ox = (SCREEN_W - board_w) // 2
        oy = HUD_H + (SCREEN_H - HUD_H - btn_area - board_h) // 2
        return rows, cols, cell, ox, oy

    # ---------------- 动画更新（按帧推进） ----------------
    def update(self, now, dt=0.0):
        if self.mode == "game" and self.game is not None:
            if self.solving:
                self._advance_solve(dt, now)     # AI 求解期间暂停倒计时
            else:
                self.game.tick(dt)               # 限时倒计时（仅游戏中状态生效）
        self.fly_anims = [a for a in self.fly_anims if now - a["t0"] < a["dur"]]
        self.shake_anims = [a for a in self.shake_anims if now - a["t0"] < SHAKE_MS]
        self.popups = [p for p in self.popups if now - p["t0"] < POPUP_MS]

    def _advance_solve(self, dt, now):
        """AI 求解：按求解器顺序每隔 SOLVE_STEP 秒点击一个箭头，直到通关。"""
        if self.game.state != Game.PLAYING or self.solve_seq is None:
            self._stop_solve()
            return
        self.solve_timer += dt
        while self.solve_timer >= SOLVE_STEP and self.game.state == Game.PLAYING:
            self.solve_timer -= SOLVE_STEP
            if self.solve_idx >= len(self.solve_seq):
                self._stop_solve()
                return
            r, c = self.solve_seq[self.solve_idx]
            self.solve_idx += 1
            if self.game.current.grid[r][c] in DIRECTIONS:
                self._on_board_click(r, c, now)   # 带动画点击
        if self.solve_idx >= len(self.solve_seq) or self.game.state != Game.PLAYING:
            self._stop_solve()

    # ---------------- 点击处理 ----------------
    def handle_click(self, pos):
        now = pygame.time.get_ticks()
        if self.mode == "start":
            if self.buttons.get("start") and self.buttons["start"].rect.collidepoint(pos):
                self.start_game()
            return

        # 游戏界面
        if self.game.state == Game.PLAYING:
            # 重新开始按钮（AI 求解进行中也可用，用于随时中断）
            if self.buttons.get("restart") and self.buttons["restart"].rect.collidepoint(pos):
                self.game.restart_level()
                self.fly_anims.clear()
                self.shake_anims.clear()
                self.popups.clear()
                self.hint_cell = None
                self._stop_solve()
                return
            # AI 求解进行中：撤销 / 提示 / AI求解 与棋盘全部禁用（按钮显示置灰）
            if self.solving:
                return
            if self.buttons.get("undo") and self.buttons["undo"].rect.collidepoint(pos) \
                    and self.game.current.undo_left > 0:
                self._do_undo()
                return
            if self.buttons.get("hint") and self.buttons["hint"].rect.collidepoint(pos) \
                    and self.game.current.hint_left > 0:
                self._do_hint()
                return
            if self.buttons.get("solve") and self.buttons["solve"].rect.collidepoint(pos):
                self._start_solve()
                return
            # 棋盘点击
            rows, cols, cell, ox, oy = self.board_geometry()
            if ox <= pos[0] < ox + cols * cell and oy <= pos[1] < oy + rows * cell:
                c = (pos[0] - ox) // cell
                r = (pos[1] - oy) // cell
                self.hint_cell = None      # 玩家开始手动操作，清除提示
                self._on_board_click(r, c, now)
        elif self.game.state == Game.LEVEL_CLEAR:
            if self.buttons.get("next") and self.buttons["next"].rect.collidepoint(pos):
                self.game.next_level()
                self.fly_anims.clear()
                self.shake_anims.clear()
                self.popups.clear()
                self.hint_cell = None
                self._stop_solve()
        elif self.game.state == Game.FAILED:
            if self.buttons.get("retry") and self.buttons["retry"].rect.collidepoint(pos):
                self.game.restart_level()
                self.fly_anims.clear()
                self.shake_anims.clear()
                self.popups.clear()
                self.hint_cell = None
                self._stop_solve()
        elif self.game.state == Game.ALL_CLEAR:
            if self.buttons.get("home") and self.buttons["home"].rect.collidepoint(pos):
                self.mode = "start"

    def _do_undo(self):
        """撤销上一步，并给出浮动反馈。"""
        result, pos = self.game.undo()
        if result is None:
            return
        self.hint_cell = None
        self._stop_solve()
        self.popups.append({
            "text": "已撤销上一步", "x": SCREEN_W // 2, "y": 150,
            "t0": pygame.time.get_ticks(), "color": COLOR_GREEN,
        })

    def _do_hint(self):
        """消耗一次提示机会，并高亮一个当前可直接消除的箭头。"""
        if self.game.current.use_hint() < 0:
            return
        cell = self.game.hint()
        if cell is None:
            self.popups.append({
                "text": "当前没有可消除的箭头", "x": SCREEN_W // 2, "y": 150,
                "t0": pygame.time.get_ticks(), "color": COLOR_DANGER,
            })
            return
        self.hint_cell = cell

    def _on_board_click(self, r, c, now):
        result, remaining = self.game.click(r, c)
        if result == "fly":
            # 逻辑层已把该格清空，这里从初始棋盘读取方向并计算飞出距离
            if self.snd_fly is not None:
                self.snd_fly.play()       # 箭头飞出音效
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
                "text": "被挡住了！生命 -1",
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
            "· 前方无阻挡 → 箭头飞出被消除；有阻挡 → 晃动提示并消耗 1 点生命；",
            "· 清空全部箭头通关，生命值耗尽或超时则本关失败；",
            "· 通关后按用时、生命消耗、撤销与提示次数评定 1~5 颗星。",
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

        draw_text(surface, "共 %d 关 · 生命 %d~%d 点 · 限时 %d~%d 秒" % (
            len(LEVELS), min(MAX_MISTAKES), max(MAX_MISTAKES),
            min(TIME_LIMITS), max(TIME_LIMITS)),
            self.font(18), COLOR_SUB, (center_x, 600))

    def _render_game(self, surface, now):
        game = self.game
        rows, cols, cell, ox, oy = self.board_geometry()
        grid = game.current.grid

        # ---- 顶部 HUD ----
        rounded_rect(surface, pygame.Rect(0, 0, SCREEN_W, HUD_H), COLOR_HUD, radius=0)
        pygame.draw.line(surface, COLOR_BOARD_BD, (0, HUD_H), (SCREEN_W, HUD_H), 2)
        draw_text(surface, "第 %d / %d 关" % (game.level_no, game.total_levels),
                  self.font(26, True), COLOR_TEXT, (90, HUD_H // 2))

        # 剩余生命值（红点显示，不显示数量文字）
        self._draw_lives(surface, 230, HUD_H // 2, game.current)

        # 剩余时间（≤10 秒变红提示；右移避免与生命值红点过近）
        remain_sec = math.ceil(max(0.0, game.current.remaining))
        time_color = COLOR_DANGER if remain_sec <= 10 else COLOR_TEXT
        draw_text(surface, "时间：%d 秒" % remain_sec,
                  self.font(22, True), time_color, (455, HUD_H // 2))

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

        # 提示高亮：金色闪烁边框
        if self.hint_cell is not None:
            hr, hc = self.hint_cell
            if grid[hr][hc] in DIRECTIONS and (hr, hc) not in flying and (hr, hc) not in shaking:
                pulse = 0.5 + 0.5 * math.sin(now * 0.006)
                rect = pygame.Rect(ox + hc * cell, oy + hr * cell, cell, cell)
                pygame.draw.rect(surface, COLOR_GOLD, rect,
                                 width=int(2 + 3 * pulse), border_radius=8)

        # 浮动提示
        for p in self.popups:
            age = now - p["t0"]
            alpha = max(0, 255 * (1 - age / POPUP_MS))
            img = self.font(20, True).render(p["text"], True, p["color"])
            img.set_alpha(int(alpha))
            rect = img.get_rect(center=(p["x"], p["y"] - age * 0.03))
            surface.blit(img, rect)

        # ---- 底部功能按钮：撤销 / 提示 / AI求解 ----
        cx = SCREEN_W // 2
        btn_y = oy + rows * cell + 12
        bw, bh = 110, 40
        solving = self.solving
        undo_left = game.current.undo_left
        btn = Button("undo", pygame.Rect(cx - 177, btn_y, bw, bh),
                     "撤销 %d/%d" % (undo_left, game.current.max_undo),
                     self.font(18, True), enabled=undo_left > 0 and not solving)
        btn.draw(surface, self.mouse_pos)
        self.buttons["undo"] = btn

        hint_left = game.current.hint_left
        btn = Button("hint", pygame.Rect(cx - 55, btn_y, bw, bh),
                     "提示 %d/%d" % (hint_left, game.current.max_hint),
                     self.font(18, True), enabled=hint_left > 0 and not solving)
        btn.draw(surface, self.mouse_pos)
        self.buttons["hint"] = btn

        btn = Button("solve", pygame.Rect(cx + 67, btn_y, bw, bh), "AI求解",
                     self.font(18, True), enabled=not solving)
        btn.draw(surface, self.mouse_pos)
        self.buttons["solve"] = btn

        # ---- 通关 / 失败 / 全部通关 遮罩 ----
        # 通关/全部通关时等最后一个箭头完全飞出棋盘后再弹出结果面板
        if game.state == Game.LEVEL_CLEAR and not self.fly_anims:
            lv = game.current
            used_sec = math.ceil(lv.elapsed)
            used_lives = lv.max_mistakes - lv.mistakes
            # 最后一关先显示本关通关界面，点“查看总星数”再进入全部通关界面
            btn_text = "查看总星数" if game.is_last_level() else "下一关"
            self._render_overlay(surface, "第 %d 关通关！" % game.level_no,
                                 "用时 %d 秒 · 消耗生命 %d 点" % (used_sec, used_lives),
                                 [("next", btn_text)], stars=lv.stars())
        elif game.state == Game.FAILED:
            if game.fail_reason == "timeout":
                title, subtitle = "时间到！", "限时耗尽，本关失败，再试一次吧"
            else:
                title, subtitle = "生命值耗尽", "本关失败，再试一次吧"
            self._render_overlay(surface, title, subtitle,
                                 [("retry", "重新开始")])
        elif game.state == Game.ALL_CLEAR and not self.fly_anims:
            self._render_overlay(surface, "恭喜通关全部关卡！",
                                 "共获得 %d / %d 颗星" % (
                                     game.total_stars(), game.total_levels * 5),
                                 [("home", "返回首页")])

    def _draw_lives(self, surface, x, cy, level):
        """绘制剩余生命值：红色实心表示剩余生命，灰色空心表示已消耗，不显示数量文字。"""
        draw_text(surface, "生命值", self.font(22), COLOR_TEXT, (x, cy))
        step = 26
        start = x + 55
        for i in range(level.max_mistakes):
            cx = start + i * step
            remaining = i < level.mistakes
            color = COLOR_DANGER if remaining else (200, 208, 218)
            pygame.draw.circle(surface, color, (cx, cy), 9)
            pygame.draw.circle(surface, (255, 255, 255), (cx - 3, cy - 3), 3)

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
        # 标题启用“视觉居中”修正：全角感叹号等标点的边界框留白会使标题偏左
        draw_text(surface, title, self.font(36, True), COLOR_TEXT,
                  (SCREEN_W // 2, ty), visual_center=True)

        if stars is not None:
            # 星级：金色实心 = 已获得，灰色 = 未获得（5 星制），并配文字说明
            gold, gray = (243, 156, 18), (205, 216, 228)
            start_x = SCREEN_W // 2 - 2 * 44          # 5 颗星整体居中（中间那颗对准屏幕中心）
            for i in range(5):
                draw_star(surface, (start_x + i * 44, ty + 56), 24,
                          gold if i < stars else gray)
            draw_text(surface, "%d / 5 星" % stars, self.font(18, True), COLOR_SUB,
                      (SCREEN_W // 2, ty + 104))
            sy = ty + 148
        else:
            sy = ty + 70

        draw_text(surface, subtitle, self.font(20), COLOR_SUB, (SCREEN_W // 2, sy))

        bw, bh = 180, 50
        bx = panel.centerx - bw // 2
        by = panel.centery + (85 if stars is not None else 42)   # 按钮留出底部边距，避免贴住面板底边
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
        os.environ["SDL_AUDIODRIVER"] = "dummy"   # 冒烟测试不初始化真实音频

    pygame.mixer.pre_init(44100, -16, 1, 512)     # 单声道 16bit，匹配程序生成的音效
    pygame.init()
    pygame.display.set_caption("一箭又一箭")
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
