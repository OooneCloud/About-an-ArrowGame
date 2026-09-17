# -*- coding: utf-8 -*-
"""
game.py —— “一箭又一箭”核心游戏逻辑

本模块只包含与界面无关的规则与状态：
  - 棋盘（二维网格）与箭头方向
  - 四方向路径检测（是否被其他箭头阻挡）
  - 点击处理（飞出 / 被阻挡 / 空白格）
  - 多关卡流程（通关、失败、重新开始、进入下一关）
  - 每关限时倒计时（超时失败）与星级评分（按用时、生命消耗与撤销次数评定 1~5 星；使用 AI 求解直接 1 星）
  - 关卡可解性校验（用于设计关卡时保证一定能通关）

不依赖 pygame，因此可以独立进行单元测试。
"""

from copy import deepcopy

# 方向字符 -> (行方向偏移, 列方向偏移)
# 行坐标向下增加，列坐标向右增加
DIRECTIONS = {
    "^": (-1, 0),   # 上
    "v": (1, 0),    # 下
    "<": (0, -1),   # 左
    ">": (0, 1),    # 右
}

EMPTY = "."   # 空格子


def _blocked(grid, r, c):
    """
    判断 (r, c) 位置上的箭头，沿其前进方向到棋盘边界之间是否存在其他箭头。

    实现思路：
      1. 从箭头所在的格子出发，沿方向 (dr, dc) 一格一格向前走；
      2. 每走一步先检查是否越界，越界说明前方直达边界，返回 False；
      3. 若途中遇到任意箭头，说明被阻挡，返回 True。

    边界条件用“先判断是否越界、再访问格子”的顺序保证不会发生数组越界，
    因此位于边缘且朝向棋盘外的箭头（如左上角朝上的箭头）也能安全判断。
    """
    rows = len(grid)
    cols = len(grid[0])
    ch = grid[r][c]
    dr, dc = DIRECTIONS[ch]
    rr, cc = r + dr, c + dc
    while 0 <= rr < rows and 0 <= cc < cols:
        if grid[rr][cc] in DIRECTIONS:
            return True
        rr += dr
        cc += dc
    return False


def solve_order(grid):
    """
    校验一个关卡是否可通关，若可通关则返回一个可行的点击顺序（列表，元素为 (r, c)）。

    原理：
      消除一个箭头只会移除障碍，永远不会给其他箭头新增障碍，
      因此“每次任意点击一个当前未被阻挡的箭头”的贪心策略是正确的：
      只要按某种顺序能全部消除，贪心过程就一定能全部消除；
      若贪心过程中某一步没有任何箭头可消除，则说明该关卡必然无法通关。
    """
    g = [list(row) for row in grid]
    order = []
    while True:
        # 找出所有当前未被阻挡的箭头
        candidates = []
        for r in range(len(g)):
            for c in range(len(g[0])):
                if g[r][c] in DIRECTIONS and not _blocked(g, r, c):
                    candidates.append((r, c))
        if not candidates:
            # 若棋盘上已无箭头，说明全部消除成功；否则为死局
            remain = [g[r][c] for row in g for c in range(len(g[0])) if g[r][c] in DIRECTIONS]
            if not remain:
                return order
            return None
        r, c = candidates[0]
        g[r][c] = EMPTY
        order.append((r, c))


class Level:
    """单个关卡：保存棋盘初始状态、生命值（失误次数）与限时，并处理一次点击。"""

    def __init__(self, grid, max_mistakes=3, time_limit=60, max_undo=3, max_hint=3):
        self._initial_grid = [list(row) for row in grid]
        self.max_mistakes = max_mistakes
        self.max_undo = max_undo              # 每关最多可撤销次数
        self.max_hint = max_hint              # 每关最多可提示次数
        self.time_limit = float(time_limit)   # 限时时长（秒）
        self.reset()

    # ---------- 状态查询 ----------

    def reset(self):
        """恢复本关初始状态：棋盘、生命值、剩余时间与操作历史全部还原。"""
        self.grid = deepcopy(self._initial_grid)
        self.mistakes = self.max_mistakes
        self.remaining = self.time_limit      # 剩余时间（秒）
        self.history = []                     # 操作历史：[(r, c, "fly" | "blocked")]
        self.undo_left = self.max_undo        # 本关剩余可撤销次数
        self.hint_left = self.max_hint        # 本关剩余可提示次数
        self.used_ai_solve = False            # 本关是否使用过 AI 求解（评分直接 1 星）

    @property
    def undo_count(self):
        """本关已使用的撤销次数。"""
        return self.max_undo - self.undo_left

    @property
    def hint_count(self):
        """本关已使用的提示次数。"""
        return self.max_hint - self.hint_left

    @property
    def elapsed(self):
        """本关已用时间（秒） = 限时 - 剩余时间。"""
        return self.time_limit - self.remaining

    @property
    def rows(self):
        return len(self.grid)

    @property
    def cols(self):
        return len(self.grid[0])

    def in_bounds(self, r, c):
        return 0 <= r < self.rows and 0 <= c < self.cols

    def initial_dir(self, r, c):
        """读取初始棋盘上 (r, c) 处的箭头方向（用于飞出动画等界面逻辑）。"""
        if self.in_bounds(r, c):
            return self._initial_grid[r][c]
        return EMPTY

    def remaining_arrows(self):
        """当前棋盘上剩余箭头数量。"""
        return sum(1 for row in self.grid for ch in row if ch in DIRECTIONS)

    def cleared(self):
        """本关是否已清空全部箭头。"""
        return self.remaining_arrows() == 0

    def is_blocked(self, r, c):
        """供外部使用的路径检测接口，委托给模块级函数。"""
        return _blocked(self.grid, r, c)

    def hint(self):
        """
        提示：返回一个当前“前方无阻挡、可直接消除”的箭头位置 (r, c)。
        按行优先返回第一个可消除的箭头；棋盘已清空或死局时返回 None。
        （本方法只做查询，不消耗提示次数；次数由 use_hint() 单独管理。）
        """
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c] in DIRECTIONS and not self.is_blocked(r, c):
                    return (r, c)
        return None

    def use_hint(self):
        """
        消耗一次提示机会。返回剩余次数；次数已用尽时返回 -1（不改变状态）。
        """
        if self.hint_left <= 0:
            return -1
        self.hint_left -= 1
        return self.hint_left

    def undo(self):
        """
        撤销最近一步操作（每关最多 max_undo 次）：
          - 上一步是 fly    -> 把该箭头恢复到原位；
          - 上一步是 blocked -> 生命值 +1。
        返回 (结果, (r, c))；无可撤销操作或撤销次数用尽时返回 (None, None)。
        """
        if self.undo_left <= 0 or not self.history:
            return (None, None)
        r, c, result = self.history.pop()
        self.undo_left -= 1
        if result == "fly":
            self.grid[r][c] = self._initial_grid[r][c]
        elif result == "blocked":
            self.mistakes = min(self.max_mistakes, self.mistakes + 1)
        return (result, (r, c))

    def tick(self, dt):
        """限时倒计时：剩余时间减去 dt 秒（不小于 0）。"""
        self.remaining = max(0.0, self.remaining - dt)

    def stars(self):
        """
        通关评分：返回 1~5 颗星；未通关返回 0。

        规则（综合用时、生命消耗、撤销次数与提示次数，5 星制）：
          时间分：已用时间 / 限时 <= 50% -> 0；<= 75% -> 1；否则 -> 2
          生命分：消耗生命 0 点 -> 0；1 点 -> 1；>= 2 点 -> 2
          撤销分：撤销 0 次 -> 0；1 次 -> 1；>= 2 次 -> 2
          提示分：提示 0 次 -> 0；>= 1 次 -> 1
          星级   = max(1, 5 - (时间分 + 生命分 + 撤销分 + 提示分))
        即：快速、零消耗、不用撤销和提示 -> 5 星；用过撤销或提示会扣分。
        特殊：本关使用过 AI 求解 -> 直接判定为 1 星。
        """
        if not self.cleared():
            return 0
        if self.used_ai_solve:
            return 1
        ratio = self.elapsed / self.time_limit
        time_penalty = 0 if ratio <= 0.5 else (1 if ratio <= 0.75 else 2)
        used_mistakes = self.max_mistakes - self.mistakes   # mistakes 存的是“剩余”次数
        mistake_penalty = 0 if used_mistakes == 0 else (1 if used_mistakes == 1 else 2)
        undo_penalty = 0 if self.undo_count == 0 else (1 if self.undo_count == 1 else 2)
        hint_penalty = 1 if self.hint_count > 0 else 0
        return max(1, 5 - (time_penalty + mistake_penalty + undo_penalty + hint_penalty))

    # ---------- 点击处理 ----------

    def click(self, r, c):
        """
        玩家点击 (r, c) 格子。

        返回 (结果, 附加信息)：
          ("empty",   None)          点击了空白格或越界，无任何效果
          ("fly",     None)          箭头前方无阻挡，箭头飞出并消失
          ("blocked", 剩余失误次数)   箭头被阻挡，不能消失，失误次数减 1
        """
        if not self.in_bounds(r, c):
            return ("empty", None)
        if self.grid[r][c] not in DIRECTIONS:
            return ("empty", None)
        if self.is_blocked(r, c):
            self.mistakes -= 1
            self.history.append((r, c, "blocked"))
            return ("blocked", self.mistakes)
        self.grid[r][c] = EMPTY
        self.history.append((r, c, "fly"))
        return ("fly", None)


class Game:
    """多关卡游戏流程：当前关卡、通关/失败状态、关卡切换。"""

    # 游戏状态
    PLAYING = "PLAYING"        # 游戏中
    LEVEL_CLEAR = "LEVEL_CLEAR"  # 本关通关，可进入下一关
    ALL_CLEAR = "ALL_CLEAR"    # 全部关卡通关
    FAILED = "FAILED"          # 本关失败（失误次数耗尽）

    def __init__(self, levels):
        self.levels = levels
        self.level_index = 0
        self.current = levels[0]
        self.state = self.PLAYING
        self.fail_reason = None      # 失败原因：None / "mistakes"（失误耗尽）/ "timeout"（超时）

    # ---------- 状态查询 ----------

    @property
    def level_no(self):
        return self.level_index + 1

    @property
    def total_levels(self):
        return len(self.levels)

    def is_last_level(self):
        return self.level_index == len(self.levels) - 1

    def total_stars(self):
        """全部关卡的总星数（未通关的关卡计 0，满分 = 关卡数 × 3）。"""
        return sum(level.stars() for level in self.levels)

    # ---------- 流程控制 ----------

    def tick(self, dt):
        """每帧推进时间：仅游戏中状态倒计时；限时耗尽 -> 超时失败。"""
        if self.state != self.PLAYING:
            return
        self.current.tick(dt)
        if self.current.remaining <= 0:
            self.state = self.FAILED
            self.fail_reason = "timeout"

    def click(self, r, c):
        """
        处理一次点击，并根据结果自动更新游戏状态。
        返回与 Level.click 相同的结果，供界面层做动画。
        """
        result, remaining = self.current.click(r, c)
        if result == "fly" and self.current.cleared():
            # 清空本关全部箭头 -> 先显示本关通关界面；
            # 最后一关点击“下一关”后才进入全部通关（总星数）界面
            self.state = self.LEVEL_CLEAR
        elif result == "blocked" and remaining == 0:
            # 生命值耗尽 -> 本关失败
            self.state = self.FAILED
            self.fail_reason = "mistakes"
        return result, remaining

    def undo(self):
        """
        撤销上一步（仅游戏中；因生命耗尽而失败时也允许撤销一步来恢复）。
        通关 / 全部通关 / 超时失败状态不可撤销。
        """
        if self.state == self.FAILED and self.fail_reason == "mistakes":
            # 失败由“被阻挡”触发，栈顶必为 blocked：撤销后恢复生命并回到游戏中
            result, pos = self.current.undo()
            if result == "blocked":
                self.state = self.PLAYING
                self.fail_reason = None
            return (result, pos)
        if self.state != self.PLAYING:
            return (None, None)
        return self.current.undo()

    def hint(self):
        """委托当前关卡返回一个可消除的箭头位置。"""
        return self.current.hint()

    def use_ai_solve(self):
        """标记本关使用了 AI 求解：评分将直接判定为 1 星。"""
        self.current.used_ai_solve = True

    def next_level(self):
        """从通关界面进入下一关；最后一关通关后点击则进入全部通关（总星数）界面。"""
        if self.is_last_level():
            self.state = self.ALL_CLEAR
            return
        self.level_index += 1
        self.current = self.levels[self.level_index]
        self.state = self.PLAYING
        self.fail_reason = None

    def restart_level(self):
        """重新开始当前关卡，恢复到初始棋盘、失误次数与剩余时间。"""
        self.current.reset()
        self.state = self.PLAYING
        self.fail_reason = None
