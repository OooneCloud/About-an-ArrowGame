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
import random

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
            remain = [ch for row in g for ch in row if ch in DIRECTIONS]
            if not remain:
                return order
            return None
        r, c = candidates[0]
        g[r][c] = EMPTY
        order.append((r, c))


# ---------------------------------------------------------------- 关卡生成（挑战关卡用）
def _path_has_arrow(board, r, c, d):
    """(r, c) 处沿方向 d 到棋盘边界是否已有箭头。"""
    dr, dc = DIRECTIONS[d]
    rr, cc = r + dr, c + dc
    while 0 <= rr < len(board) and 0 <= cc < len(board[0]):
        if board[rr][cc] in DIRECTIONS:
            return True
        rr += dr
        cc += dc
    return False


def _path_arrow_count(board, r, c, d):
    """(r, c) 处沿方向 d 到棋盘边界路径上的箭头数量。"""
    dr, dc = DIRECTIONS[d]
    rr, cc = r + dr, c + dc
    cnt = 0
    while 0 <= rr < len(board) and 0 <= cc < len(board[0]):
        if board[rr][cc] in DIRECTIONS:
            cnt += 1
        rr += dr
        cc += dc
    return cnt


def _max_same_run(board):
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


def _max_block_same(board, block=2):
    """任意 block×block 子块内同一方向箭头数的最大值（衡量“同向箭头扎堆”的程度）。"""
    rows, cols = len(board), len(board[0])
    best = 0
    for r in range(rows - block + 1):
        for c in range(cols - block + 1):
            counts = {}
            for rr in range(r, r + block):
                for cc in range(c, c + block):
                    ch = board[rr][cc]
                    if ch in DIRECTIONS:
                        counts[ch] = counts.get(ch, 0) + 1
            best = max(best, max(counts.values(), default=0))
    return best


def _direction_range(board):
    """四种方向箭头数量的极差（最多 - 最少），衡量方向分布是否均衡。"""
    counts = {d: 0 for d in DIRECTIONS}
    for row in board:
        for ch in row:
            if ch in DIRECTIONS:
                counts[ch] += 1
    vals = list(counts.values())
    return max(vals) - min(vals)


def _quadrant_kinds_ok(board, min_kinds=3, min_arrows=4, allow_missing=1):
    """
    方向分散性检查：把棋盘按行列中点分为四个象限，
    箭头数不少于 min_arrows 的象限，其方向种类不得少于 min_kinds。
    允许最多 allow_missing 个象限不满足（避免两个大范围象限都只有
    两种箭头的聚集现象，同时不过度苛刻导致高密度关卡无法生成）。
    """
    rows, cols = len(board), len(board[0])
    mid_r, mid_c = rows // 2, cols // 2
    quads = [
        (0, mid_r, 0, mid_c), (0, mid_r, mid_c, cols),
        (mid_r, rows, 0, mid_c), (mid_r, rows, mid_c, cols),
    ]
    missing = 0
    for r0, r1, c0, c1 in quads:
        kinds = set()
        n = 0
        for r in range(r0, r1):
            for c in range(c0, c1):
                ch = board[r][c]
                if ch in DIRECTIONS:
                    kinds.add(ch)
                    n += 1
        if n >= min_arrows and len(kinds) < min_kinds:
            missing += 1
            if missing > allow_missing:
                return False
    return True


def _direction_centroid_ok(board, max_dev=None):
    """
    方向-位置分散检查：箭头不应聚在自己指向的那一侧。

    增量构造法的“前进方向路径必须为空”约束会让箭头偏向自己指向的方向
    （左箭头聚集在左侧、下箭头聚集在下部等）。本函数只惩罚这类方向性偏移：
      - "<" 的平均列不应比棋盘中心列靠左太多；
      - ">" 的平均列不应比棋盘中心列靠右太多；
      - "^" 的平均行不应比棋盘中心行靠上太多；
      - "v" 的平均行不应比棋盘中心行靠下太多。
    反方向（如 "<" 偏右）属于自然随机波动，不惩罚。
    """
    rows, cols = len(board), len(board[0])
    if max_dev is None:
        # 阈值按棋盘规模设定：小棋盘箭头少、质心波动大
        max_dev = max(2.4, 1.6 + 0.1 * min(rows, cols))
    cy_r, cy_c = (rows - 1) / 2.0, (cols - 1) / 2.0
    for d in DIRECTIONS:
        pts = [(r, c) for r in range(rows) for c in range(cols) if board[r][c] == d]
        if not pts:
            continue
        mr = sum(p[0] for p in pts) / len(pts)
        mc = sum(p[1] for p in pts) / len(pts)
        if d == "<":
            dev = cy_c - mc          # 偏左多少
        elif d == ">":
            dev = mc - cy_c          # 偏右多少
        elif d == "^":
            dev = cy_r - mr          # 偏上多少
        else:  # "v"
            dev = mr - cy_r          # 偏下多少
        if dev > max_dev:
            return False
    return True


def _window3x3_ok(board):
    """任意一个 3×3 范围内四种箭头至少出现一次（v3temp 新增约束）。"""
    rows, cols = len(board), len(board[0])
    for r in range(rows - 2):
        for c in range(cols - 2):
            kinds = set()
            for rr in range(r, r + 3):
                for cc in range(c, c + 3):
                    ch = board[rr][cc]
                    if ch in DIRECTIONS:
                        kinds.add(ch)
            if len(kinds) < 4:
                return False
    return True


def _window3x3_gain(board, r, c, d):
    """在 (r, c) 放置方向 d 后，新增“补齐四种方向”的 3×3 窗口数量（v3temp 放置引导）。"""
    rows, cols = len(board), len(board[0])
    gain = 0
    for wr in range(max(0, r - 2), min(rows - 3, r) + 1):
        for wc in range(max(0, c - 2), min(cols - 3, c) + 1):
            kinds = set()
            for rr in range(wr, wr + 3):
                for cc in range(wc, wc + 3):
                    ch = board[rr][cc]
                    if ch in DIRECTIONS:
                        kinds.add(ch)
            if d not in kinds:
                gain += 1
    return gain


def _run_ok_at(grid, r, c, max_run=2):
    """检查 (r, c) 所在行 / 列是否产生超过 max_run 的连续同向箭头（局部检查）。"""
    rows, cols = len(grid), len(grid[0])
    ch = grid[r][c]
    run = 1
    cc = c - 1
    while cc >= 0 and grid[r][cc] == ch:
        run += 1
        cc -= 1
    cc = c + 1
    while cc < cols and grid[r][cc] == ch:
        run += 1
        cc += 1
    if run > max_run:
        return False
    run = 1
    rr = r - 1
    while rr >= 0 and grid[rr][c] == ch:
        run += 1
        rr -= 1
    rr = r + 1
    while rr < rows and grid[rr][c] == ch:
        run += 1
        rr += 1
    return run <= max_run


def _run_ok_place(board, r, c, d, max_run=2):
    """在 (r, c) 放置方向 d 后，该行 / 列连续同向箭头是否仍不超过 max_run。"""
    board[r][c] = d
    ok = _run_ok_at(board, r, c, max_run)
    board[r][c] = EMPTY
    return ok


def _block2_ok_at(grid, r, c, max_same=3):
    """检查包含 (r, c) 的 2×2 子块中同方向箭头数是否不超过 max_same（局部检查）。"""
    rows, cols = len(grid), len(grid[0])
    ch = grid[r][c]
    for dr in (-1, 0):
        for dc in (-1, 0):
            r0, c0 = r + dr, c + dc
            if 0 <= r0 < rows - 1 and 0 <= c0 < cols - 1:
                sub = [grid[r0][c0], grid[r0][c0 + 1], grid[r0 + 1][c0], grid[r0 + 1][c0 + 1]]
                if sum(1 for x in sub if x == ch) > max_same:
                    return False
    return True


def _optimize_spread(board, max_dev=None, max_swaps=400, max_run=2):
    """
    局部搜索优化方向-位置分散：把“聚在自己指向方向”的箭头与反侧的
    其他方向箭头交换位置，改善质心偏差；每次交换都校验可解性、
    且不破坏行/列连续同向与 2×2 同向限制，否则回滚。
    交换不改变各方向箭头数量。

    返回优化后的棋盘（字符串行列表）。若已达标则原样返回。
    """
    rows, cols = len(board), len(board[0])
    grid = [list(row) for row in board]
    if max_dev is None:
        max_dev = max(2.4, 1.6 + 0.1 * min(rows, cols))
    cy_r, cy_c = (rows - 1) / 2.0, (cols - 1) / 2.0

    def dev_of(d):
        """返回 (方向偏差, 该方向箭头位置列表)"""
        pts = [(r, c) for r in range(rows) for c in range(cols) if grid[r][c] == d]
        if not pts:
            return 0.0, pts
        mr = sum(p[0] for p in pts) / len(pts)
        mc = sum(p[1] for p in pts) / len(pts)
        if d == "<":
            dev = cy_c - mc
        elif d == ">":
            dev = mc - cy_c
        elif d == "^":
            dev = cy_r - mr
        else:
            dev = mr - cy_r
        return dev, pts

    for _ in range(max_swaps):
        # 找出偏差最大的方向（需要改善的目标）
        worst_d, worst_dev = None, 0.0
        for d in DIRECTIONS:
            dev, _ = dev_of(d)
            if dev > worst_dev:
                worst_d, worst_dev = d, dev
        if worst_d is None or worst_dev <= max_dev:
            break
        _, pts = dev_of(worst_d)
        if not pts:
            break
        # 选一个“最靠指向侧”的目标箭头
        if worst_d == "<":
            r1, c1 = min(pts, key=lambda p: p[1])
        elif worst_d == ">":
            r1, c1 = max(pts, key=lambda p: p[1])
        elif worst_d == "^":
            r1, c1 = min(pts, key=lambda p: p[0])
        else:
            r1, c1 = max(pts, key=lambda p: p[0])
        # 候选交换对象：其他方向的箭头，越靠“反侧”越优先
        others = [(r, c) for r in range(rows) for c in range(cols)
                  if grid[r][c] in DIRECTIONS and grid[r][c] != worst_d]
        if not others:
            break
        def opp_key(p):
            if worst_d == "<":
                return p[1]
            if worst_d == ">":
                return -p[1]
            if worst_d == "^":
                return p[0]
            return -p[0]
        others.sort(key=opp_key, reverse=True)
        improved = False
        for (r2, c2) in others[:12]:
            d2 = grid[r2][c2]
            grid[r1][c1], grid[r2][c2] = grid[r2][c2], grid[r1][c1]
            ok_swap = (
                solve_order(grid) is not None
                and _run_ok_at(grid, r1, c1, max_run)
                and _run_ok_at(grid, r2, c2, max_run)
                and _block2_ok_at(grid, r1, c1)
                and _block2_ok_at(grid, r2, c2)
            )
            if ok_swap:
                new_dev, _ = dev_of(worst_d)
                if new_dev < worst_dev - 0.05:
                    improved = True
                    break
            # 回滚
            grid[r1][c1], grid[r2][c2] = grid[r2][c2], grid[r1][c1]
        if not improved:
            # 该方向没有可改善的交换，标记为不再尝试（防死循环）
            break
    return [''.join(row) for row in grid]


def _greedy_rounds(board):
    """贪心模拟消除所需轮数（依赖深度）与是否全部消除。"""
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


def _has_mutual_block(board):
    """棋盘上是否存在互挡对（同行 >< 或同列 ^v）。"""
    opp = {"<": ">", ">": "<", "^": "v", "v": "^"}
    for r in range(len(board)):
        for c in range(len(board[0])):
            d = board[r][c]
            if d in DIRECTIONS:
                dr, dc = DIRECTIONS[d]
                rr, cc = r + dr, c + dc
                while 0 <= rr < len(board) and 0 <= cc < len(board[0]):
                    if board[rr][cc] == opp[d]:
                        return True
                    rr += dr
                    cc += dc
    return False


def _dead_arrows(board):
    """贪心消除后仍无法消除的箭头（死锁剩余）。"""
    g = [list(row) for row in board]
    while True:
        cands = [(r, c) for r in range(len(g)) for c in range(len(g[0]))
                 if g[r][c] in DIRECTIONS and not _blocked(g, r, c)]
        if not cands:
            break
        r, c = cands[0]
        g[r][c] = EMPTY
    return [(r, c) for r in range(len(g)) for c in range(len(g[0]))
            if g[r][c] in DIRECTIONS]


def _move_keeps_window(board, r, c, r2, c2):
    """把 (r,c) 处的箭头移到 (r2,c2)（方向不变）后，3×3 窗口约束是否仍可能保持。
    换出格子的所有窗口内必须仍存在另一个同方向箭头。"""
    rows, cols = len(board), len(board[0])
    d = board[r][c]
    if board[r2][c2] in DIRECTIONS:
        return False
    for wr in range(max(0, r - 2), min(rows - 3, r) + 1):
        for wc in range(max(0, c - 2), min(cols - 3, c) + 1):
            cnt = 0
            for rr in range(wr, wr + 3):
                for cc in range(wc, wc + 3):
                    if (rr, cc) != (r, c) and board[rr][cc] == d:
                        cnt += 1
            if cnt == 0:
                return False
    return True


def _move_fix_deadlock(board, max_moves=80):
    """v3temp：通过“移动死锁箭头（方向不变）”打破阻挡环，返回可解布局或 None。

    3×3 窗口四方向齐全时，方向混合会产生双向阻挡环（如 > 与 < 同行互挡、
    ^ 与 v 同列互挡），且环内箭头往往是窗口内该方向的“唯一供应”，换方向
    会破坏窗口约束；因此只做同方向移动到空位（保持窗口约束），再迭代消除。
    """
    g = [list(row) for row in board]
    rows, cols = len(g), len(g[0])
    rng = random.Random()
    for _ in range(max_moves):
        if solve_order(g) is not None:
            return g
        dead = _dead_arrows(g)
        if not dead:
            return g
        moved = False
        rng.shuffle(dead)
        for (r, c) in dead:
            d = g[r][c]
            empties = [(r2, c2) for r2 in range(rows) for c2 in range(cols)
                       if g[r2][c2] == EMPTY]
            rng.shuffle(empties)
            for (r2, c2) in empties:
                if not _move_keeps_window(g, r, c, r2, c2):
                    continue
                g[r2][c2] = d
                g[r][c] = EMPTY
                moved = True
                break
            if moved:
                break
        if not moved:
            return None
    return g if solve_order(g) is not None else None


def _forms_mutual_block(board, r, c, d):
    """在 (r, c) 放置方向 d 后，是否会与已有箭头形成互挡对（同行 >< 或同列 ^v）。

    互挡对（如 > 与 < 在同一行，> 在左 < 在右）构成双向阻挡环：> 的飞行路径
    经过 <，< 的飞行路径经过 >，两者互相锁定，任何情况下都无法解锁，是布局
    不可解的根因。中间隔有其他箭头不影响互挡成立（阻挡判定只看路径上有箭头），
    因此检测必须扫描整条路径。放置（含骨架）阶段一律禁止互挡对。
    """
    opp = {"<": ">", ">": "<", "^": "v", "v": "^"}[d]
    dr, dc = DIRECTIONS[d]
    rr, cc = r + dr, c + dc
    while 0 <= rr < len(board) and 0 <= cc < len(board[0]):
        if board[rr][cc] == opp:
            return True
        rr += dr
        cc += dc
    return False


def _would_form_cycle(board, r, c, d):
    """放置 d 于 (r, c) 后，是否会让阻挡关系形成环（死锁）。

    阻挡环（互挡对或 3+ 方向循环，如 ^→<→v→>→^）中的箭头互相锁定，
    是布局不可解的根因。放置时在“模拟放置后的棋盘”上做被挡链 DFS：
    从挡住新箭头的箭头出发，沿“被谁挡”的边搜索，若能到达被新箭头挡住的
    箭头，则新箭头闭合了一个环，禁止放置。
    """
    g = [list(row) for row in board]
    g[r][c] = d
    rows, cols = len(g), len(g[0])
    dr, dc = DIRECTIONS[d]
    # 挡住新箭头的箭头（路径上任意箭头都挡它）
    x_blockers = []
    rr, cc = r + dr, c + dc
    while 0 <= rr < rows and 0 <= cc < cols:
        if g[rr][cc] in DIRECTIONS:
            x_blockers.append((rr, cc))
        rr += dr
        cc += dc
    if not x_blockers:
        return False                      # 新箭头不被挡 → 不会闭合环
    # 被新箭头挡住的箭头：其飞行路径经过 (r, c) 的箭头。
    # 这类箭头在 (r, c) 的四侧都可能存在（例如 (r,c) 右侧同行的 "<" 路径向左经过它），
    # 因此向四个方向分别扫描：某方向侧上的箭头，若指向 (r, c) 即被新箭头挡住。
    x_targets = set()
    for (sdr, sdc) in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        rr, cc = r + sdr, c + sdc
        while 0 <= rr < rows and 0 <= cc < cols:
            ch = g[rr][cc]
            if ch in DIRECTIONS:
                # 箭头在 (r,c) 的 sdr/sdc 侧，其方向指向 (r,c) 的充要条件：
                # 方向向量正好相反（如右侧同行的 "<" → 方向 (0,-1)）。
                # 该侧任意一个指向 (r,c) 的箭头都被新箭头挡住，继续扫描。
                if DIRECTIONS[ch] == (-sdr, -sdc):
                    x_targets.add((rr, cc))
            rr += sdr
            cc += sdc
    if not x_targets:
        return False                      # 新箭头不挡任何人 → 不会闭合环
    # 从挡住新箭头的箭头出发 DFS，沿“被谁挡”的边搜索，看能否到达被新箭头挡住的箭头
    seen = set()
    stack = list(x_blockers)
    while stack:
        (br, bc) = stack.pop()
        if (br, bc) in seen:
            continue
        seen.add((br, bc))
        if (br, bc) in x_targets:
            return True                   # 成环
        bd = g[br][bc]
        bdr, bdc = DIRECTIONS[bd]
        rr, cc = br + bdr, bc + bdc
        while 0 <= rr < rows and 0 <= cc < cols:
            if g[rr][cc] in DIRECTIONS:
                stack.append((rr, cc))
            rr += bdr
            cc += bdc
    return False


def _build_skeleton(rows, cols, rng):
    """v3temp：为所有 3×3 窗口贪心分配“四方向骨架箭头”。

    返回 (board, 骨架箭头数)；任一需求无法满足时返回 (None, 0)。
    骨架一旦建成，后续填充只会增加窗口内的方向种类，3×3 约束永久满足。
    放置同时禁止互挡对，保证最终布局必然可解。
    """
    windows = [(wr, wc) for wr in range(rows - 2) for wc in range(cols - 2)]
    needs = {(wr, wc, d) for wr, wc in windows for d in DIRECTIONS}
    board = [[EMPTY] * cols for _ in range(rows)]
    counts = {d: 0 for d in DIRECTIONS}
    while needs:
        best_by_dir = {}
        for r in range(rows):
            for c in range(cols):
                if board[r][c] in DIRECTIONS:
                    continue
                for d in DIRECTIONS:
                    if _would_form_cycle(board, r, c, d):
                        continue
                    cnt = 0
                    for wr in range(max(0, r - 2), min(rows - 3, r) + 1):
                        for wc in range(max(0, c - 2), min(cols - 3, c) + 1):
                            if (wr, wc, d) in needs:
                                cnt += 1
                    if cnt > 0:
                        key = best_by_dir.get(d, (0, None))
                        if cnt > key[0]:
                            best_by_dir[d] = (cnt, (r, c))
        if not best_by_dir:
            return None, 0

        def score(d):
            cnt, _pos = best_by_dir[d]
            return (cnt / 9.0) - counts[d] * 0.05   # 满足需求多优先，兼顾骨架方向均衡

        d = max(best_by_dir, key=score)
        _cnt, (r, c) = best_by_dir[d]
        board[r][c] = d
        counts[d] += 1
        for wr in range(max(0, r - 2), min(rows - 3, r) + 1):
            for wc in range(max(0, c - 2), min(cols - 3, c) + 1):
                needs.discard((wr, wc, d))
    return board, sum(1 for row in board for ch in row if ch in DIRECTIONS)


def generate_level(rows, cols, n_arrows, max_run=2, max_block=3,
                   min_blocked_ratio=0.3, min_rounds=3, max_range=5,
                   seed=None, tries=2000, step_tries=150, max_dev=None,
                   max_path_arrows=0):
    """
    v3temp：骨架 + 填充 + 移动修复 的关卡生成器。

    核心新约束：任意 3×3 范围四方向齐全（_window3x3_ok）。
    流程：
      1. _build_skeleton 为所有 3×3 窗口贪心放置四方向骨架箭头（窗口约束由骨架保证）；
      2. 增量填充其余箭头到 n_arrows（方向数量均衡 + 前进路径约束 + 乱序引导）；
      3. solve_order 校验可解性；死锁（双向阻挡环）时用 _move_fix_deadlock
         移动死锁箭头（方向不变）打破环；
      4. 质量过滤：四方向齐全 / 方向数量均衡（极差 ≤ max_range）/
         乱序（run ≤ max_run、2×2 不同向）/ blocked 比例 / 依赖深度轮数。

    注意：v3temp 布局串行可解但并发消除可能剩箭头（remain≠0 属正常），
    因此 rounds 只保留依赖深度下限检查，不做 remain 校验。
    """
    rng = random.Random(seed)
    dirs = list(DIRECTIONS)
    cy_r, cy_c = (rows - 1) / 2.0, (cols - 1) / 2.0
    if max_dev is None:
        max_dev = max(2.4, 1.6 + 0.1 * min(rows, cols))
    for _ in range(tries):
        board, skel = _build_skeleton(rows, cols, rng)
        if board is None:
            continue
        counts = {d: sum(1 for row in board for ch in row if ch == d) for d in DIRECTIONS}
        quad_cnt = {d: [0, 0, 0, 0] for d in DIRECTIONS}
        for r in range(rows):
            for c in range(cols):
                ch = board[r][c]
                if ch in DIRECTIONS:
                    q = (2 if r >= rows // 2 else 0) + (1 if c >= cols // 2 else 0)
                    quad_cnt[ch][q] += 1
        placed = skel
        ok = True
        for _step in range(n_arrows - skel):
            # 方向选择：数量最少的方向优先（保持四方向数量均衡）
            dir_order = sorted(dirs, key=lambda d: (counts[d], rng.random()))
            added = False
            for d in dir_order:
                cand_pos = [(r, c) for r in range(rows) for c in range(cols)
                            if board[r][c] == EMPTY
                            and _path_arrow_count(board, r, c, d) <= max_path_arrows]
                if not cand_pos:
                    continue
                if max_run >= 1:
                    cand_pos = [p for p in cand_pos
                                if _run_ok_place(board, p[0], p[1], d, max_run)]
                if not cand_pos:
                    continue
                # 阻挡环（死锁根因）检测：放置后不允许闭合任何环
                cand_pos = [p for p in cand_pos
                            if not _would_form_cycle(board, p[0], p[1], d)]
                if not cand_pos:
                    continue
                if counts[d] == 0:
                    r, c = rng.choice(cand_pos)
                else:
                    scores = []
                    for (rr, cc) in cand_pos:
                        q = (2 if rr >= rows // 2 else 0) + (1 if cc >= cols // 2 else 0)
                        # 象限均衡引导 + 小随机扰动
                        scores.append(1.0 / (quad_cnt[d][q] + 1) + rng.random() * 0.08)
                    r, c = rng.choices(cand_pos, weights=scores, k=1)[0]
                board[r][c] = d
                counts[d] += 1
                q = (2 if r >= rows // 2 else 0) + (1 if c >= cols // 2 else 0)
                quad_cnt[d][q] += 1
                placed += 1
                added = True
                break
            if not added:
                ok = False
                break
        if not ok or placed < n_arrows:
            continue
        # 放置全程禁止成环 → 无阻挡环 → 必然可解（防御性再校验）
        if solve_order(board) is None:
            continue
        dirs_set = {ch for row in board for ch in row if ch in DIRECTIONS}
        if dirs_set != set("^v<>"):
            continue
        if not _window3x3_ok(board):                     # 骨架保证，防御性复查
            continue
        if _direction_range(board) > max_range:          # 方向数量均衡
            continue
        blocked = sum(1 for r in range(rows) for c in range(cols)
                      if board[r][c] in DIRECTIONS and _blocked(board, r, c))
        if blocked < min_blocked_ratio * n_arrows:       # 保证有碰撞玩法
            continue
        if _max_same_run(board) > max_run:               # 避免一整排同向
            continue
        if _max_block_same(board, 2) > max_block:        # 避免同向箭头扎堆（禁止 2×2 全同向）
            continue
        rounds, _remain = _greedy_rounds(board)
        if rounds < min_rounds:                          # 保证一定依赖深度
            continue
        return board, rounds, blocked
    return None


def generate_challenge(seed=None):
    """
    生成“挑战关卡”棋盘：10×10、高密度。

    在线生成要求快，因此采用预算式策略，按“乱序性要求”从严到宽依次尝试：
      1. 60 个箭头 + 行/列连续同向 ≤ 2（严格乱序）；
      2. 60 个箭头 + 行/列连续同向 ≤ 3；
      3. 密度逐级下调（58 → 40），行/列连续同向 ≤ 3。
    返回 (board, n_arrows)；全部失败返回 None。
    """
    rng = random.Random(seed)
    attempts = [(60, 2, 250), (60, 3, 150), (60, 3, 150)]
    for n, max_run, tries in attempts:
        res = generate_level(10, 10, n, max_run=max_run, max_block=3,
                             min_blocked_ratio=0.25, min_rounds=2,
                             tries=tries, step_tries=120,
                             max_path_arrows=1,
                             seed=rng.randrange(10 ** 9))
        if res is not None:
            return res[0], n
    for n in range(58, 39, -1):
        res = generate_level(10, 10, n, max_run=3, max_block=3,
                             min_blocked_ratio=0.2, min_rounds=2,
                             tries=80, step_tries=120,
                             max_path_arrows=1,
                             seed=rng.randrange(10 ** 9))
        if res is not None:
            return res[0], n
    return None


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
