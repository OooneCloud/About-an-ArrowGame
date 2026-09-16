# -*- coding: utf-8 -*-
"""
tools/generate_level.py —— 随机生成可通关关卡

用“逆向构造法”生成高密度、随机分布的关卡：

  1. 随机选择 N 个格子并随机打乱成一个“消除顺序”；
  2. 按逆序依次放置箭头：放置第 i 个箭头时，保证它的前进方向上
     不包含任何“更晚才消除”的箭头（即逆序中已放置的箭头）；
  3. 这样按原消除顺序点击时，每个箭头前方必然无阻挡，关卡必然可通关；
  4. 再通过质量过滤：包含四种方向、有足够多的初始阻挡箭头、
     同行/同列不出现连续同向长排、具备一定的依赖深度。

用法：
    python tools/generate_level.py            # 随机生成一关（演示）
    python tools/generate_level.py --rows 8 --cols 8 --arrows 28 --seed 5
"""

import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game import solve_order, _blocked, DIRECTIONS, EMPTY


def path_has_arrow(board, r, c, d):
    """(r,c) 处沿方向 d 到棋盘边界是否已有箭头。"""
    dr, dc = DIRECTIONS[d]
    rr, cc = r + dr, c + dc
    while 0 <= rr < len(board) and 0 <= cc < len(board[0]):
        if board[rr][cc] in DIRECTIONS:
            return True
        rr += dr
        cc += dc
    return False


def arrow_stats(board):
    n = sum(1 for row in board for ch in row if ch in DIRECTIONS)
    dirs = {ch for row in board for ch in row if ch in DIRECTIONS}
    blocked = sum(1 for r in range(len(board)) for c in range(len(board[0]))
                  if board[r][c] in DIRECTIONS and _blocked(board, r, c))
    return n, dirs, blocked


def max_same_run(board):
    """同行/同列中连续同方向箭头的最大长度（衡量“一整排同向”的程度）。"""
    rows, cols = len(board), len(board[0])
    best = 1
    for r in range(rows):
        run = 1
        for c in range(1, cols):
            a, b = board[r][c - 1], board[r][c]
            run = run + 1 if (a in DIRECTIONS and a == b) else 1
            best = max(best, run)
    for c in range(cols):
        run = 1
        for r in range(1, rows):
            a, b = board[r - 1][c], board[r][c]
            run = run + 1 if (a in DIRECTIONS and a == b) else 1
            best = max(best, run)
    return best


def greedy_rounds(board):
    """贪心模拟消除所需轮数（依赖深度）。"""
    g = [list(row) for row in board]
    rounds = 0
    while True:
        free = [(r, c) for r in range(len(g)) for c in range(len(g[0]))
                if g[r][c] in DIRECTIONS and not _blocked(g, r, c)]
        if not free:
            remain = sum(1 for row in g for ch in row if ch in DIRECTIONS)
            return rounds, remain
        rounds += 1
        for r, c in free:
            g[r][c] = EMPTY


def generate_level(rows, cols, n_arrows, max_run=2, min_blocked_ratio=0.3,
                   min_rounds=3, seed=None, tries=4000):
    """生成一个满足质量条件的随机关卡；失败返回 None。"""
    rng = random.Random(seed)
    cells_all = [(r, c) for r in range(rows) for c in range(cols)]
    for _ in range(tries):
        cells = rng.sample(cells_all, n_arrows)
        order = cells[:]
        rng.shuffle(order)
        board = [[EMPTY] * cols for _ in range(rows)]
        ok = True
        for idx in range(n_arrows - 1, -1, -1):      # 逆序放置
            r, c = order[idx]
            cands = [d for d in DIRECTIONS if not path_has_arrow(board, r, c, d)]
            if not cands:                             # 四个方向都被已放箭头挡住
                ok = False
                break
            board[r][c] = rng.choice(cands)
        if not ok:
            continue
        if solve_order(board) is None:                # 双保险：求解器校验
            continue
        n, dirs, blocked = arrow_stats(board)
        if dirs != set("^v<>"):
            continue
        if blocked < min_blocked_ratio * n:           # 保证有碰撞玩法
            continue
        if max_same_run(board) > max_run:             # 避免一整排同向
            continue
        rounds, remain = greedy_rounds(board)
        if rounds < min_rounds or remain != 0:        # 保证一定依赖深度
            continue
        return board, rounds, blocked
    return None


def board_to_text(board):
    return [" ".join(row) for row in board]


def main():
    ap = argparse.ArgumentParser(description="随机生成可通关关卡")
    ap.add_argument("--rows", type=int, default=6)
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--arrows", type=int, default=16)
    ap.add_argument("--min-rounds", type=int, default=3)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--show", action="store_true", help="额外打印统计信息")
    args = ap.parse_args()

    res = generate_level(args.rows, args.cols, args.arrows,
                         min_rounds=args.min_rounds, seed=args.seed)
    if res is None:
        print("生成失败：请降低箭头数量或放宽条件")
        sys.exit(1)
    board, rounds, blocked = res
    n, dirs, _ = arrow_stats(board)
    for line in board_to_text(board):
        print(line)
    if args.show:
        print(f"# 箭头={n}, 初始被阻挡={blocked}({blocked/n:.0%}), "
              f"依赖深度={rounds}轮, 最大同向连排={max_same_run(board)}")


if __name__ == "__main__":
    main()
