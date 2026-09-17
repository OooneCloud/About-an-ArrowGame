# -*- coding: utf-8 -*-
"""
tests/test_game.py —— “一箭又一箭”自动化测试

覆盖作业要求的测试项：
  T01 点击前方无阻挡的箭头         -> 箭头飞出棋盘并消失
  T02 点击前方有阻挡的箭头         -> 箭头不消失，失误次数减 1
  T03 点击位于边缘且朝向棋盘外的箭头 -> 箭头正常消失，不发生越界错误
  T04 消除本关全部箭头             -> 显示通关并进入下一关
  T05 失误次数耗尽                -> 显示失败并允许重新开始
  T06 游戏进行中重新开始           -> 箭头布局和失误次数恢复

评分机制测试项（后续追加，5 星制）：
  T07 限时耗尽                   -> 超时失败
  T08 快速（用时 ≤50%）无消耗不用撤销/提示 -> 5 星
  T09 用时 ≤75% 或生命消耗 1 点   -> 4 星
  T10 用时超 75% 或生命消耗 ≥2 点 -> 3 星
  T11 重新开始                   -> 剩余时间恢复
  T12 通关后                     -> 时间停止倒计时

撤销 / 提示 / AI 求解测试项（后续追加）：
  T13 撤销消除步骤               -> 箭头恢复到原位
  T14 撤销失误步骤               -> 生命值 +1
  T15 无历史时撤销               -> 返回 (None, None)
  T16 连续撤销                   -> 棋盘恢复初始布局
  T17 通关后撤销                 -> 无效
  T18 生命耗尽失败后撤销         -> 恢复游戏中状态
  T19 提示                       -> 返回一个前方无阻挡的箭头
  T20 空棋盘提示                 -> 返回 None
  T21 撤销次数用尽               -> 不再允许撤销，次数不恢复
  T22 使用 AI 求解               -> 通关评分直接 1 星
  T23 使用撤销 1 次              -> 星级最高 4 星
  T24 提示次数用尽               -> 不再允许提示，重新开始后恢复
  T25 使用提示 1 次              -> 星级最高 4 星
  T26 使用撤销 ≥2 次             -> 星级最高 3 星

另外补充：四方向路径检测的单元测试、关卡可解性校验、关卡方向齐全性校验。
测试中“无阻挡/有阻挡箭头”均从关卡数据中自动推导，关卡调整后无需修改测试。

运行方式（在项目根目录）：
    python -m unittest discover -s tests -v
或：
    python -m pytest tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game import Level, Game, solve_order, _blocked, DIRECTIONS, EMPTY, \
    generate_level, generate_challenge, _max_same_run, _max_block_same, \
    _direction_range, _quadrant_kinds_ok
from levels import LEVELS, MAX_MISTAKES


# ---------------------------------------------------------------- 工具函数
def grid_of(*rows):
    """把若干行字符串（用空格分隔格子）转换成字符网格。"""
    return [row.split() for row in rows]


def arrow_count(grid):
    return sum(1 for row in grid for ch in row if ch in DIRECTIONS)


def find_free_arrow(grid):
    """在关卡中找一个“前方无阻挡”的箭头，返回 (r, c)。"""
    level = Level(grid)
    for r in range(level.rows):
        for c in range(level.cols):
            if level.grid[r][c] in DIRECTIONS and not level.is_blocked(r, c):
                return r, c
    raise AssertionError("关卡中找不到无阻挡的箭头")


def find_blocked_arrow(grid):
    """在关卡中找一个“前方有阻挡”的箭头，返回 (r, c)。"""
    level = Level(grid)
    for r in range(level.rows):
        for c in range(level.cols):
            if level.grid[r][c] in DIRECTIONS and level.is_blocked(r, c):
                return r, c
    raise AssertionError("关卡中找不到被阻挡的箭头")


# ---------------------------------------------------------------- 路径检测
class TestPathDetection(unittest.TestCase):
    """四方向路径检测：无阻挡、有阻挡、边界三种情况。"""

    def test_right_no_block(self):
        level = Level(grid_of("> . .", ". . .", ". . ."))
        self.assertFalse(level.is_blocked(0, 0))

    def test_right_blocked_by_any_arrow(self):
        level = Level(grid_of("> < .", ". . .", ". . ."))
        self.assertTrue(level.is_blocked(0, 0))
        level = Level(grid_of("> . <", ". . .", ". . ."))
        self.assertTrue(level.is_blocked(0, 0))

    def test_left_no_block_and_block(self):
        level = Level(grid_of(". . <", ". . .", ". . ."))
        self.assertFalse(level.is_blocked(0, 2))
        level = Level(grid_of("> . <", ". . .", ". . ."))
        self.assertTrue(level.is_blocked(0, 2))

    def test_up_no_block_and_block(self):
        level = Level(grid_of(". . .", "^ . .", ". . ."))
        self.assertFalse(level.is_blocked(1, 0))      # 上方是空格
        level = Level(grid_of("^ . .", "^ . .", ". . ."))
        self.assertTrue(level.is_blocked(1, 0))       # 上方有箭头

    def test_down_no_block_and_block(self):
        level = Level(grid_of(". . .", "v . .", ". . ."))
        self.assertFalse(level.is_blocked(1, 0))
        level = Level(grid_of("v . .", "v . .", ". . ."))
        self.assertTrue(level.is_blocked(0, 0))

    def test_edge_arrow_no_out_of_bounds(self):
        """位于边缘且朝向棋盘外的箭头：判断时不能越界，且视为无阻挡。"""
        # 左上角朝上、右下角朝下、左上角朝左、右上角朝右
        cases = [
            (grid_of("^ . .", ". . .", ". . ."), (0, 0)),
            (grid_of(". . .", ". . .", ". . v"), (2, 2)),
            (grid_of("< . .", ". . .", ". . ."), (0, 0)),
            (grid_of(". . >", ". . .", ". . ."), (0, 2)),
        ]
        for grid, (r, c) in cases:
            level = Level(grid)
            self.assertFalse(level.is_blocked(r, c))
            result, _ = level.click(r, c)
            self.assertEqual(result, "fly")


# ---------------------------------------------------------------- 作业测试项
class TestHomeworkCases(unittest.TestCase):
    """对应作业 T01 - T06。"""

    def test_t01_click_unblocked_arrow_fly(self):
        """T01：点击前方无阻挡的箭头 -> 箭头飞出棋盘并消失。"""
        level = Level(LEVELS[0])
        r, c = find_free_arrow(LEVELS[0])
        before = level.remaining_arrows()
        result, _ = level.click(r, c)
        self.assertEqual(result, "fly")
        self.assertEqual(level.grid[r][c], EMPTY)
        self.assertEqual(level.remaining_arrows(), before - 1)

    def test_t02_click_blocked_arrow(self):
        """T02：点击前方有阻挡的箭头 -> 箭头不消失，失误次数减 1。"""
        level = Level(LEVELS[0])
        r, c = find_blocked_arrow(LEVELS[0])
        before = level.remaining_arrows()
        self.assertTrue(level.is_blocked(r, c))
        result, remaining = level.click(r, c)
        self.assertEqual(result, "blocked")
        self.assertEqual(remaining, level.max_mistakes - 1)
        self.assertIn(level.grid[r][c], DIRECTIONS)   # 箭头仍在
        self.assertEqual(level.remaining_arrows(), before)

    def test_t03_edge_arrow_facing_outside(self):
        """T03：点击位于边缘且朝向棋盘外的箭头 -> 正常消失，不发生越界错误。"""
        level = Level(grid_of("^ . .", ". . .", ". . v"))
        result1, _ = level.click(0, 0)                # 左上角朝上
        result2, _ = level.click(2, 2)                # 右下角朝下
        self.assertEqual(result1, "fly")
        self.assertEqual(result2, "fly")
        self.assertEqual(level.remaining_arrows(), 0)

    def test_t04_clear_all_arrows_show_clear_and_next(self):
        """T04：消除本关全部箭头 -> 显示通关并进入下一关。"""
        game = Game([Level(LEVELS[0]), Level(LEVELS[1])])
        order = solve_order(LEVELS[0])                # 按求解器给出的可行顺序点击
        self.assertIsNotNone(order)
        for r, c in order:
            result, _ = game.click(r, c)
            self.assertEqual(result, "fly")
        self.assertEqual(game.state, Game.LEVEL_CLEAR)   # 显示通关
        game.next_level()                                 # 进入下一关
        self.assertEqual(game.level_no, 2)
        self.assertEqual(game.state, Game.PLAYING)
        self.assertEqual(game.current.remaining_arrows(), arrow_count(LEVELS[1]))

    def test_t04_last_level_all_clear(self):
        """最后一关清空 -> 先显示本关通关界面，点“下一关”后显示全部通关。"""
        game = Game([Level(LEVELS[-1])])
        order = solve_order(LEVELS[-1])
        self.assertIsNotNone(order)
        for r, c in order:
            game.click(r, c)
        self.assertEqual(game.state, Game.LEVEL_CLEAR)   # 先显示本关通关界面
        game.next_level()                                # 再进入全部通关
        self.assertEqual(game.state, Game.ALL_CLEAR)

    def test_t05_mistakes_exhausted_fail_and_retry(self):
        """T05：失误次数耗尽 -> 显示失败并允许重新开始。"""
        game = Game([Level(LEVELS[0])])
        r, c = find_blocked_arrow(LEVELS[0])
        max_m = game.current.max_mistakes
        for i in range(max_m):                        # 连续点击被阻挡的箭头
            result, remaining = game.click(r, c)
            self.assertEqual(result, "blocked")
        self.assertEqual(remaining, 0)
        self.assertEqual(game.state, Game.FAILED)      # 显示失败
        game.restart_level()                           # 重新开始
        self.assertEqual(game.state, Game.PLAYING)
        self.assertEqual(game.current.mistakes, game.current.max_mistakes)
        self.assertEqual(game.current.remaining_arrows(), arrow_count(LEVELS[0]))

    def test_t06_restart_restores_layout_and_mistakes(self):
        """T06：游戏进行中重新开始 -> 箭头布局和失误次数恢复。"""
        game = Game([Level(LEVELS[0])])
        fr, fc = find_free_arrow(LEVELS[0])
        result, _ = game.click(fr, fc)    # 消除一个无阻挡箭头
        self.assertEqual(result, "fly")

        # 消除后，在“当前状态”中找一个仍被阻挡的箭头再点击（失误一次）
        cur = game.current
        blocked = [(r, c) for r in range(cur.rows) for c in range(cur.cols)
                   if cur.grid[r][c] in DIRECTIONS and cur.is_blocked(r, c)]
        self.assertTrue(blocked, "消除一个箭头后关卡中没有仍被阻挡的箭头")
        br, bc = blocked[0]
        result, _ = game.click(br, bc)
        self.assertEqual(result, "blocked")

        self.assertEqual(game.current.remaining_arrows(), arrow_count(LEVELS[0]) - 1)
        self.assertEqual(game.current.mistakes, game.current.max_mistakes - 1)

        game.restart_level()
        self.assertEqual(game.current.grid, [list(r) for r in LEVELS[0]])  # 布局恢复
        self.assertEqual(game.current.mistakes, game.current.max_mistakes)  # 失误恢复
        self.assertEqual(game.state, Game.PLAYING)


# ---------------------------------------------------------------- 限时与星级
class TestScoring(unittest.TestCase):
    """限时倒计时与星级评分（T07 - T12）。"""

    def test_t07_timeout_fails(self):
        """T07：限时耗尽 -> 本关失败（超时）。"""
        game = Game([Level(LEVELS[0], time_limit=5)])
        self.assertEqual(game.state, Game.PLAYING)
        game.tick(6.0)
        self.assertEqual(game.state, Game.FAILED)
        self.assertEqual(game.fail_reason, "timeout")

    def test_t07_no_fail_before_timeout(self):
        """限时未耗尽时不会失败，剩余时间不会减到负数。"""
        game = Game([Level(LEVELS[0], time_limit=10)])
        game.tick(3.0)
        self.assertEqual(game.state, Game.PLAYING)
        self.assertAlmostEqual(game.current.remaining, 7.0)

    def test_t08_five_stars_fast_no_cost(self):
        """T08：用时 ≤ 50%、无生命消耗、不用撤销和提示 -> 5 星。"""
        level = Level(LEVELS[0], time_limit=100)
        level.remaining = 50.0                      # 已用 50 秒 = 50%
        for r, c in solve_order(LEVELS[0]):
            result, _ = level.click(r, c)
            self.assertEqual(result, "fly")
        self.assertEqual(level.stars(), 5)

    def test_t09_four_stars(self):
        """T09：用时 70%（≤75%）或生命消耗 1 点 -> 4 星。"""
        # 用时 70%（无消耗、不用撤销和提示）
        level = Level(LEVELS[0], time_limit=100)
        level.remaining = 30.0
        for r, c in solve_order(LEVELS[0]):
            level.click(r, c)
        self.assertEqual(level.stars(), 4)
        # 快通但有 1 次生命消耗
        level2 = Level(LEVELS[0], time_limit=100)
        level2.remaining = 50.0
        level2.mistakes = level2.max_mistakes - 1
        for r, c in solve_order(LEVELS[0]):
            level2.click(r, c)
        self.assertEqual(level2.stars(), 4)

    def test_t10_three_stars(self):
        """T10：用时超过 75% 或生命消耗 ≥2 点 -> 3 星。"""
        # 用时 90%（无消耗）
        level = Level(LEVELS[0], time_limit=100)
        level.remaining = 10.0
        for r, c in solve_order(LEVELS[0]):
            level.click(r, c)
        self.assertEqual(level.stars(), 3)
        # 生命消耗 2 点（快通）
        level2 = Level(LEVELS[0], time_limit=100)
        level2.remaining = 50.0
        level2.mistakes = 0
        for r, c in solve_order(LEVELS[0]):
            level2.click(r, c)
        self.assertEqual(level2.stars(), 3)

    def test_t10_not_cleared_zero_star(self):
        """未通关时星级为 0（不计入总分）。"""
        level = Level(LEVELS[0])
        self.assertEqual(level.stars(), 0)

    def test_t11_restart_resets_timer(self):
        """T11：重新开始 -> 剩余时间恢复为限时。"""
        game = Game([Level(LEVELS[0])])
        game.tick(15.0)
        self.assertLess(game.current.remaining, game.current.time_limit)
        game.restart_level()
        self.assertAlmostEqual(game.current.remaining, game.current.time_limit)

    def test_t12_time_pauses_after_clear(self):
        """T12：通关后时间不再倒计时（评分按通关瞬间冻结）。"""
        game = Game([Level(LEVELS[0]), Level(LEVELS[1])])
        for r, c in solve_order(LEVELS[0]):
            game.click(r, c)
        self.assertEqual(game.state, Game.LEVEL_CLEAR)
        before = game.current.remaining
        game.tick(30.0)
        self.assertEqual(game.current.remaining, before)
        self.assertGreaterEqual(game.current.stars(), 1)


# ---------------------------------------------------------------- 撤销 / 提示
class TestUndoHint(unittest.TestCase):
    """撤销上一步与提示功能（T13 - T20）。"""

    def test_t13_undo_fly_restores_arrow(self):
        """T13：撤销消除步骤 -> 箭头恢复到原位。"""
        level = Level(LEVELS[0])
        r, c = find_free_arrow(LEVELS[0])
        level.click(r, c)
        self.assertEqual(level.grid[r][c], EMPTY)
        result, pos = level.undo()
        self.assertEqual(result, "fly")
        self.assertEqual(pos, (r, c))
        self.assertEqual(level.grid[r][c], LEVELS[0][r][c])
        self.assertEqual(level.remaining_arrows(), arrow_count(LEVELS[0]))

    def test_t14_undo_blocked_restores_life(self):
        """T14：撤销失误步骤 -> 生命值 +1。"""
        level = Level(LEVELS[0])
        r, c = find_blocked_arrow(LEVELS[0])
        level.click(r, c)
        self.assertEqual(level.mistakes, level.max_mistakes - 1)
        result, _ = level.undo()
        self.assertEqual(result, "blocked")
        self.assertEqual(level.mistakes, level.max_mistakes)

    def test_t15_undo_empty_history(self):
        """T15：没有历史操作时撤销 -> (None, None)。"""
        level = Level(LEVELS[0])
        self.assertEqual(level.undo(), (None, None))

    def test_t16_undo_restores_initial_board(self):
        """T16：连续撤销 -> 棋盘恢复初始布局。"""
        level = Level(LEVELS[0])
        for r, c in solve_order(LEVELS[0])[:3]:
            level.click(r, c)
        self.assertEqual(level.remaining_arrows(), arrow_count(LEVELS[0]) - 3)
        for _ in range(3):
            level.undo()
        self.assertEqual(level.grid, [list(row) for row in LEVELS[0]])
        self.assertEqual(level.remaining_arrows(), arrow_count(LEVELS[0]))

    def test_t17_undo_disabled_after_clear(self):
        """T17：通关后撤销无效。"""
        game = Game([Level(LEVELS[0]), Level(LEVELS[1])])
        for r, c in solve_order(LEVELS[0]):
            game.click(r, c)
        self.assertEqual(game.state, Game.LEVEL_CLEAR)
        self.assertEqual(game.undo(), (None, None))

    def test_t18_undo_revives_from_failure(self):
        """T18：生命耗尽失败后撤销 -> 恢复生命并回到游戏中。"""
        game = Game([Level(LEVELS[0])])
        r, c = find_blocked_arrow(LEVELS[0])
        for _ in range(game.current.max_mistakes):
            game.click(r, c)
        self.assertEqual(game.state, Game.FAILED)
        result, _ = game.undo()
        self.assertEqual(result, "blocked")
        self.assertEqual(game.state, Game.PLAYING)
        self.assertEqual(game.fail_reason, None)
        self.assertEqual(game.current.mistakes, 1)

    def test_t18_undo_disabled_after_timeout(self):
        """超时失败不可撤销（时间不可逆）。"""
        game = Game([Level(LEVELS[0], time_limit=5)])
        game.tick(6.0)
        self.assertEqual(game.state, Game.FAILED)
        self.assertEqual(game.fail_reason, "timeout")
        self.assertEqual(game.undo(), (None, None))

    def test_t19_hint_returns_unblocked_arrow(self):
        """T19：提示返回一个前方无阻挡的箭头。"""
        level = Level(LEVELS[0])
        r, c = level.hint()
        self.assertIsNotNone((r, c))
        self.assertIn(level.grid[r][c], DIRECTIONS)
        self.assertFalse(level.is_blocked(r, c))

    def test_t20_hint_none_on_empty_board(self):
        """T20：棋盘为空时提示返回 None。"""
        level = Level([["."]])
        self.assertIsNone(level.hint())

    def test_t21_undo_limit_exhausted(self):
        """T21：撤销次数用尽后不再允许撤销。"""
        level = Level(LEVELS[0])                       # 默认最多撤销 3 次
        order = solve_order(LEVELS[0])[:level.max_undo]
        self.assertEqual(len(order), level.max_undo)
        for r, c in order:
            level.click(r, c)
        # 撤销到次数用尽
        for _ in range(level.max_undo):
            result, _ = level.undo()
            self.assertIsNotNone(result)
        self.assertEqual(level.undo_left, 0)
        self.assertEqual(level.undo(), (None, None))   # 次数用尽，撤销无效
        self.assertEqual(level.remaining_arrows(), arrow_count(LEVELS[0]))  # 已全部还原

    def test_t21_undo_left_resets(self):
        """重新开始时撤销次数恢复为上限。"""
        game = Game([Level(LEVELS[0])])
        r, c = find_free_arrow(LEVELS[0])
        game.click(r, c)
        game.undo()
        self.assertEqual(game.current.undo_left, game.current.max_undo - 1)
        game.restart_level()
        self.assertEqual(game.current.undo_left, game.current.max_undo)

    def test_t22_ai_solve_one_star(self):
        """T22：使用 AI 求解 -> 通关评分直接 1 星。"""
        game = Game([Level(LEVELS[0]), Level(LEVELS[1])])
        game.use_ai_solve()
        for r, c in solve_order(LEVELS[0]):
            game.click(r, c)
        self.assertEqual(game.state, Game.LEVEL_CLEAR)
        self.assertEqual(game.current.stars(), 1)

    def test_t23_undo_lowers_stars(self):
        """T23：使用撤销后星级最高 4 星。"""
        level = Level(LEVELS[0], time_limit=100)
        level.remaining = 50.0                       # 用时 50%，时间分 0
        r, c = find_free_arrow(LEVELS[0])
        level.click(r, c)
        level.undo()                                 # 撤销 1 次
        for rr, cc in solve_order(LEVELS[0]):
            if level.grid[rr][cc] in DIRECTIONS:
                level.click(rr, cc)
        self.assertEqual(level.stars(), 4)           # 5 - 撤销分 1

    def test_t24_hint_limit(self):
        """T24：提示次数用尽后不再允许提示，重新开始后恢复。"""
        game = Game([Level(LEVELS[0])])
        for _ in range(game.current.max_hint):
            self.assertGreaterEqual(game.current.use_hint(), 0)
        self.assertEqual(game.current.hint_left, 0)
        self.assertEqual(game.current.use_hint(), -1)   # 用尽
        game.restart_level()
        self.assertEqual(game.current.hint_left, game.current.max_hint)

    def test_t25_hint_lowers_stars(self):
        """T25：使用提示扣 1 分 -> 快通 + 零消耗 + 提示 1 次 = 4 星。"""
        level = Level(LEVELS[0], time_limit=100)
        level.remaining = 50.0
        level.use_hint()
        for r, c in solve_order(LEVELS[0]):
            level.click(r, c)
        self.assertEqual(level.stars(), 4)

    def test_t26_undo_twice_three_stars(self):
        """T26：撤销 2 次 -> 撤销分 2，快通 + 零消耗 = 3 星。"""
        level = Level(LEVELS[0], time_limit=100)
        level.remaining = 50.0
        for r, c in solve_order(LEVELS[0])[:2]:
            level.click(r, c)
        level.undo()
        level.undo()
        for rr, cc in solve_order(LEVELS[0]):
            if level.grid[rr][cc] in DIRECTIONS:
                level.click(rr, cc)
        self.assertEqual(level.stars(), 3)


# ---------------------------------------------------------------- 关卡质量
class TestLevels(unittest.TestCase):
    """关卡数据质量：尺寸一致、可通关、包含四种方向、难度递增。"""

    def test_all_levels_solvable(self):
        """每个关卡都必须存在合理的通关顺序。"""
        for i, grid in enumerate(LEVELS):
            self.assertIsNotNone(
                solve_order(grid),
                msg="关卡 %d 无法通关！" % (i + 1),
            )

    def test_all_levels_rectangular(self):
        for i, grid in enumerate(LEVELS):
            widths = {len(row) for row in grid}
            self.assertEqual(len(widths), 1, msg="关卡 %d 不是矩形棋盘" % (i + 1))

    def test_all_levels_have_four_directions(self):
        """每个关卡都应包含上、下、左、右四种方向的箭头。"""
        for i, grid in enumerate(LEVELS):
            dirs = {ch for row in grid for ch in row if ch in DIRECTIONS}
            self.assertEqual(dirs, set("^v<>"), msg="关卡 %d 缺少某些方向的箭头" % (i + 1))

    def test_mistakes_config_matches_levels(self):
        self.assertEqual(len(MAX_MISTAKES), len(LEVELS))

    def test_every_level_has_free_arrow(self):
        """每个关卡开局都至少有一个可直接飞出的箭头（否则不可能通关）。"""
        for i, grid in enumerate(LEVELS):
            self.assertIsNotNone(find_free_arrow(grid), msg="关卡 %d 开局无路可走" % (i + 1))

    def test_every_level_has_blocked_arrow(self):
        """除入门关外，大部分关卡都应存在被阻挡的箭头（保证有碰撞玩法）。"""
        for i, grid in enumerate(LEVELS[1:], start=2):
            self.assertIsNotNone(find_blocked_arrow(grid),
                                 msg="关卡 %d 没有任何被阻挡的箭头" % i)

    def test_solver_finds_valid_order(self):
        """求解器给出的点击顺序必须每一步都合法（即每一步箭头前方均无阻挡）。"""
        for grid in LEVELS:
            order = solve_order(grid)
            self.assertIsNotNone(order)
            g = [list(row) for row in grid]
            for r, c in order:
                self.assertIn(g[r][c], DIRECTIONS)
                self.assertFalse(
                    _blocked(g, r, c),
                    msg="求解顺序中 (%d,%d) 的箭头在步骤中仍有阻挡" % (r, c),
                )
                g[r][c] = EMPTY
            self.assertTrue(all(ch not in DIRECTIONS for row in g for ch in row))


# ---------------------------------------------------------------- 挑战关卡与乱序性
class TestChallenge(unittest.TestCase):
    """挑战关卡生成器与全部关卡的方向乱序性（T27 - T31）。"""

    def test_t27_challenge_generated_solvable(self):
        """T27：挑战关卡生成器返回可通关的高密度棋盘。"""
        board, n = generate_challenge()
        self.assertIsNotNone(board)
        self.assertGreaterEqual(n, 50)               # 高密度（10×10 至少 50 个箭头）
        self.assertEqual(len(board), 10)
        self.assertEqual(len(board[0]), 10)
        self.assertIsNotNone(solve_order(board))

    def test_t28_challenge_differs_across_seeds(self):
        """T28：不同随机种子生成的挑战关卡布局不同（真随机）。"""
        board1, _ = generate_challenge(seed=1)
        board2, _ = generate_challenge(seed=2)
        self.assertNotEqual(board1, board2)

    def test_t29_levels_no_long_same_run(self):
        """T29：所有固定关卡同行/同列连续同向箭头不超过 2 个（方向打散）。"""
        for i, grid in enumerate(LEVELS):
            self.assertLessEqual(_max_same_run(grid), 2,
                                 msg="关卡 %d 出现连续 3 个以上同向箭头" % (i + 1))

    def test_t30_levels_no_full_same_block(self):
        """T30：所有固定关卡任意 2×2 区域内同方向箭头不超过 3 个（不扎堆）。"""
        for i, grid in enumerate(LEVELS):
            self.assertLessEqual(_max_block_same(grid, 2), 3,
                                 msg="关卡 %d 出现 2×2 全同向箭头" % (i + 1))

    def test_t31_challenge_limits_config(self):
        """T31：挑战关卡限 1 次撤销、1 次提示、3 点生命（main 层使用，这里验证 Level 参数生效）。"""
        from levels import CHALLENGE_MISTAKES, CHALLENGE_UNDO, CHALLENGE_HINT, CHALLENGE_TIME
        board, _ = generate_challenge(seed=7)
        level = Level(board, max_mistakes=CHALLENGE_MISTAKES, time_limit=CHALLENGE_TIME,
                      max_undo=CHALLENGE_UNDO, max_hint=CHALLENGE_HINT)
        self.assertEqual(level.max_mistakes, 3)
        self.assertEqual(level.max_undo, 1)
        self.assertEqual(level.max_hint, 1)
        self.assertEqual(level.time_limit, 180)

    def test_t32_levels_direction_range_within_5(self):
        """T32：所有固定关卡四种方向箭头数量极差不超过 5（方向分布均衡）。"""
        for i, grid in enumerate(LEVELS):
            self.assertLessEqual(_direction_range(grid), 5,
                                 msg="关卡 %d 各方向箭头数量相差过大" % (i + 1))

    def test_t32_challenge_direction_range_within_5(self):
        """T32b：随机关卡（挑战）方向数量极差同样不超过 5。"""
        board, _ = generate_challenge(seed=11)
        self.assertLessEqual(_direction_range(board), 5)

    def test_t33_levels_quadrant_kinds_ok(self):
        """T33：所有固定关卡不存在“大范围区域只有两种箭头”的聚集（象限方向种类达标）。"""
        for i, grid in enumerate(LEVELS):
            self.assertTrue(_quadrant_kinds_ok(grid),
                            msg="关卡 %d 某象限方向种类过少（聚集）" % (i + 1))

    def test_t33_challenge_quadrant_kinds_ok(self):
        """T33b：随机关卡同样满足象限分散性。"""
        board, _ = generate_challenge(seed=13)
        self.assertTrue(_quadrant_kinds_ok(board))


if __name__ == "__main__":
    unittest.main(verbosity=2)
