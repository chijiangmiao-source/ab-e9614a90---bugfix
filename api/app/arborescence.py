"""最小汇流树（最小树形图）求解器 —— Chu–Liu/Edmonds 算法的手工实现。

不依赖任何现成图优化库。给定注入根与带非负整数代价的有向通道，
求一棵以根为源、覆盖全部采样点、总代价最小的汇流树（每个非根点
恰有一条入选通道且自根可达）。同优解中按"升序通道标识序列"取字典序
最小者（规范树）。

除规范树外，本模块还产出可复算的有向环收缩 / 展开记录：
  * 每一层为每个非根点选出的最小入边；
  * 每次有向环收缩（环节点、环边、超点、入边代价 w − w*(v) 修正、
    丢弃的环内非环边）；
  * 每次展开替换（进入通道、进入点、被替换的环边、保留的环边）。

求解流程：
  1. 每个非根点选键 (代价, 规范惩罚, 标识) 最小的入边；
  2. 若选中边含有向环，则把环收缩为超点：环外→环内的入边代价修正为
     w(e) − w*(enters)，环内边全部丢弃，递归求解收缩图；
  3. 递归返回后展开：以进入超点的通道落回环内对应节点，删去该节点的
     原环边、保留其余环边——代价变化与收缩时的修正严格抵消。嵌套环
     由递归自然处理，最深层先展开；
  4. 规范解：先用朴素键求最优代价 C*，再按通道标识升序逐条试探
     "强制入选"（把强制边收缩为链块后递归求解），仅当最优代价仍为 C*
     时接受；最后以 (代价, 是否规范边, 标识) 为键重跑 Edmonds，使产出
     的收缩 / 展开记录恰好对应规范树。
"""

from __future__ import annotations

from dataclasses import dataclass


class ProblemError(Exception):
    """输入不合法时抛出。errors 为逐条原因列表。"""

    def __init__(self, reason: str, errors: list[str] | None = None):
        super().__init__(reason)
        self.reason = reason
        self.errors = errors or [reason]


@dataclass(frozen=True)
class Channel:
    id: str
    u: str  # 上游点（from）
    v: str  # 下游点（to）
    cost: int


@dataclass
class _Edge:
    """某一收缩层级上的边。orig 始终指向原始通道。"""

    orig: Channel
    u: str  # 当前层级的尾点（可能是超点）
    v: str  # 当前层级的头点（可能是超点）
    # 字典序键 (代价分量, 规范惩罚分量, 标识次序)；收缩时整组减去
    # e.v 当前入口的键（分量分别相减）。字典序整数向量本身构成全序
    # 阿贝尔群，Edmonds 的代价修正对它逐分量成立，嵌套任意层均不失真，
    # 也不受用户代价数值范围影响。
    key: tuple[int, int, int]
    enters: str  # 本边最终落回的环内原始节点（展开时定位被替换环边）
    lower: "_Edge | None"  # 收缩前一层对应的边；原始层为 None


# ---------------------------------------------------------------------------
# 输入校验
# ---------------------------------------------------------------------------

_MAX_POINTS = 40
_MIN_POINTS = 2
_MAX_CHANNELS = 160
_MAX_ID_LEN = 32


def _is_ascii_id(value: str) -> bool:
    if not isinstance(value, str) or not (1 <= len(value) <= _MAX_ID_LEN):
        return False
    # 可打印 ASCII（不含空白），便于排序与展示
    return all(0x21 <= ord(ch) <= 0x7E for ch in value)


def validate_problem(
    points: list[str], root: str, channels: list[Channel]
) -> None:
    """收集全部输入错误；有任何错误即抛 ProblemError。"""
    errors: list[str] = []

    if not (_MIN_POINTS <= len(points) <= _MAX_POINTS):
        errors.append(
            f"采样点数量须为 {_MIN_POINTS}..{_MAX_POINTS}，实际为 {len(points)}"
        )
    seen: set[str] = set()
    for p in points:
        if not _is_ascii_id(p):
            errors.append(f"采样点标识非法（须为 1..{_MAX_ID_LEN} 个可打印 ASCII 字符）: {p!r}")
        elif p in seen:
            errors.append(f"采样点标识重复: {p!r}")
        seen.add(p)

    if not _is_ascii_id(root):
        errors.append(f"注入根标识非法: {root!r}")
    elif root not in seen:
        errors.append(f"注入根 {root!r} 不在采样点集合中")

    if len(channels) > _MAX_CHANNELS:
        errors.append(f"通道数量至多为 {_MAX_CHANNELS}，实际为 {len(channels)}")

    chan_ids: set[str] = set()
    for c in channels:
        if not _is_ascii_id(c.id):
            errors.append(f"通道标识非法: {c.id!r}")
        elif c.id in chan_ids:
            errors.append(f"通道标识重复: {c.id!r}")
        chan_ids.add(c.id)
        if c.u not in seen:
            errors.append(f"通道 {c.id!r} 的起点 {c.u!r} 不是已知采样点")
        if c.v not in seen:
            errors.append(f"通道 {c.id!r} 的终点 {c.v!r} 不是已知采样点")
        if c.u == c.v:
            errors.append(f"通道 {c.id!r} 是自环（{c.u!r} -> {c.v!r}），不被允许")
        if not isinstance(c.cost, int) or isinstance(c.cost, bool) or c.cost < 0:
            errors.append(f"通道 {c.id!r} 的代价须为非负整数，实际为 {c.cost!r}")

    if errors:
        raise ProblemError("输入不合法", errors)


# ---------------------------------------------------------------------------
# Edmonds 核心（带收缩 / 展开记录）
# ---------------------------------------------------------------------------


def _fresh_supernode(counter: list[int], nodes: set[str]) -> str:
    """取一个不与本层任何节点（含用户点与既有超点）冲突的超点名。"""
    while True:
        name = f"S{counter[0]}"
        counter[0] += 1
        if name not in nodes:
            return name


def _find_cycle(nodes: list[str], root: str, in_edge: dict[str, _Edge]) -> list[str] | None:
    """在每个非根点恰有一条选中入边的函数图上找一个有向环。

    返回环节点列表（沿选中入边逆向行走的顺序），无环返回 None。
    """
    for start in sorted(nodes):
        if start == root:
            continue
        seen: dict[str, int] = {}
        order: list[str] = []
        cur = start
        while cur != root and cur not in seen:
            seen[cur] = len(order)
            order.append(cur)
            cur = in_edge[cur].u
        if cur != root:
            return order[seen[cur]:]
    return None


def _cycle_forward(cycle: list[str], in_edge: dict[str, _Edge]) -> tuple[list[str], list[str]]:
    """把逆向行走得到的环转换为沿通道方向的展示顺序。

    返回 (节点序列, 通道标识序列)，其中通道 i 从节点 i 指向节点 i+1（末位回绕）。
    """
    # cycle 中 in_edge[cycle[i]].u == cycle[(i+1) % k]
    k = len(cycle)
    nodes_fwd = [cycle[0]] + [cycle[k - 1 - i] for i in range(k - 1)]
    channels_fwd = [in_edge[nodes_fwd[(i + 1) % k]].orig.id for i in range(k)]
    return nodes_fwd, channels_fwd


def _solve_level(
    nodes: list[str],
    root: str,
    edges: list[_Edge],
    depth: int,
    levels: list[dict],
    expansions: list[dict],
    sup_counter: list[int],
) -> list[_Edge] | None:
    """单层 Chu–Liu/Edmonds：选最小入边 → 遇环收缩并递归 → 展开。

    返回以**本层** _Edge 表示的入选边（恰好覆盖每个非根本层节点一条
    入边），本层无可行树形图时返回 None。levels / expansions 收集记录。
    """
    node_set = set(nodes)
    # 进入根的边永远不可能属于以根为源的树形图，直接排除。
    edges = [e for e in edges if e.v != root]

    # 1) 每个非根点选键最小的入边（键末位为唯一标识次序，结果与提交顺序无关）。
    in_edges: dict[str, list[_Edge]] = {}
    for e in edges:
        in_edges.setdefault(e.v, []).append(e)

    in_edge: dict[str, _Edge] = {}
    chosen_detail: list[dict] = []
    for n in sorted(nodes):
        if n == root:
            continue
        cand = in_edges.get(n)
        if not cand:
            return None  # 本层存在无入边的非根节点 → 收缩图无解
        best = min(cand, key=lambda e: e.key)
        in_edge[n] = best
        chosen_detail.append(
            {"node": n, "channel": best.orig.id, "cost": best.key[0]}
        )

    # 2) 选中边中是否含有向环。
    cycle = _find_cycle(sorted(nodes), root, in_edge)
    if cycle is None:
        levels.append(
            {
                "depth": depth,
                "nodes": sorted(nodes),
                "chosen": chosen_detail,
                "cycle": None,
            }
        )
        return [in_edge[n] for n in sorted(nodes) if n != root]

    cycle_set = set(cycle)
    nodes_fwd, channels_fwd = _cycle_forward(cycle, in_edge)
    cycle_edge_ids = {in_edge[n].orig.id for n in cycle}

    # 3) 收缩为超点，构造下一层边；同时整理代价修正 / 丢弃记录。
    sup = _fresh_supernode(sup_counter, node_set)
    contracted = [n for n in sorted(nodes) if n not in cycle_set] + [sup]

    rewired_in: list[dict] = []
    dropped_internal: list[str] = []
    next_edges: list[_Edge] = []
    for e in edges:
        u_in = e.u in cycle_set
        v_in = e.v in cycle_set
        if u_in and v_in:
            # 环内边：环边随环保留，其余环内边在收缩图中无意义，丢弃。
            if e.orig.id not in cycle_edge_ids:
                dropped_internal.append(e.orig.id)
            continue
        if not u_in and not v_in:
            next_edges.append(
                _Edge(e.orig, e.u, e.v, e.key, enters=e.enters, lower=e)
            )
        elif v_in and not u_in:
            # 环外 → 环内：键的每个分量分别减去 e.v 当前入口的对应分量，
            # 即代价修正 w(e) − w*(enters)，惩罚与标识次序一并平移。
            star = in_edge[e.v]
            nkey = (e.key[0] - star.key[0], e.key[1] - star.key[1], e.key[2])
            rewired_in.append(
                {
                    "channel": e.orig.id,
                    "from": e.orig.u,
                    "to": e.orig.v,
                    "original_cost": e.key[0],
                    "adjusted_cost": nkey[0],
                    "enters": e.v,
                }
            )
            next_edges.append(
                _Edge(e.orig, e.u, sup, nkey, enters=e.v, lower=e)
            )
        else:  # u_in and not v_in：环内 → 环外，尾点改挂超点。
            next_edges.append(
                _Edge(e.orig, sup, e.v, e.key, enters=e.enters, lower=e)
            )

    levels.append(
        {
            "depth": depth,
            "nodes": sorted(nodes),
            "chosen": chosen_detail,
            "cycle": {
                "supernode": sup,
                "nodes": nodes_fwd,
                "channels": channels_fwd,
                "rewired_in": sorted(rewired_in, key=lambda r: r["channel"]),
                "dropped_internal": sorted(dropped_internal),
            },
        }
    )

    # 4) 递归求解收缩图。
    sub_picked = _solve_level(
        contracted, root, next_edges, depth + 1, levels, expansions, sup_counter
    )
    if sub_picked is None:
        return None

    # 5) 展开：把下一层入选边一一映射回本层。
    picked: list[_Edge] = []
    entering: _Edge | None = None
    for se in sub_picked:
        pe = se.lower  # 本层对应边（收缩图中的边全部带 lower）
        picked.append(pe)
        if se.v == sup:  # 收缩层中进入超点的那唯一一条边
            assert entering is None, "收缩环在递归解中有多条进入通道，内部不一致"
            entering = pe
    assert entering is not None, "收缩环在递归解中没有进入通道，内部不一致"

    # 进入通道在本层落入环中的节点（可能是更早收缩出的超点）head：
    # 删去 head 的当前环边、保留其余环边；enters 记录其最终落回的原始点。
    head = entering.v
    assert head in cycle_set
    kept = [
        in_edge[n]
        for n in nodes_fwd
        if n != head
    ]
    picked.extend(kept)

    expansions.append(
        {
            "supernode": sup,
            "entering_channel": entering.orig.id,
            "enters_node": entering.enters,
            "removed_cycle_channel": in_edge[head].orig.id,
            "kept_cycle_channels": [e.orig.id for e in kept],
        }
    )
    return picked


def _edmonds(
    nodes: list[str], root: str, edges: list[_Edge]
) -> tuple[list[_Edge], list[dict], list[dict]] | None:
    """完整 Edmonds 运行；返回 (入选边, 层级记录, 展开记录) 或 None。"""
    levels: list[dict] = []
    expansions: list[dict] = []
    picked = _solve_level(
        list(nodes), root, edges, 0, levels, expansions, [1]
    )
    if picked is None:
        return None
    return picked, levels, expansions


def _rank_of(channels: list[Channel]) -> dict[str, int]:
    """通道标识按字典序升序的次序（键的最末位，唯一）。"""
    return {cid: i for i, cid in enumerate(sorted(c.id for c in channels))}


def _make_edge(c: Channel, u: str, v: str, pen: int, rank: dict[str, int]) -> _Edge:
    return _Edge(
        c,
        u,
        v,
        (c.cost, pen, rank[c.id]),
        enters=c.v,
        lower=None,
    )


def _initial_edges(
    channels: list[Channel], forced_ids: set[str] | None = None
) -> list[_Edge]:
    """构造原始层边；forced_ids 中的边在同代价时优先（规范惩罚 0）。"""
    forced_ids = forced_ids or set()
    rank = _rank_of(channels)
    return [
        _make_edge(c, c.u, c.v, 0 if c.id in forced_ids else 1, rank)
        for c in channels
    ]


# ---------------------------------------------------------------------------
# 强制入选约束下的最小代价（用于规范树的字典序贪心）
# ---------------------------------------------------------------------------


class _DSU:
    def __init__(self, items):
        self.parent = {x: x for x in items}

    def find(self, x):
        p = self.parent
        while p[x] != x:
            p[x] = p[p[x]]
            x = p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _min_cost_with_forced(
    points: list[str], root: str, channels: list[Channel], forced: list[Channel]
) -> int | None:
    """在必须包含 forced 中全部通道的前提下求最小总代价；不可行返回 None。"""
    parent: dict[str, str] = {}
    for f in forced:
        if f.v == root or f.v in parent:
            return None  # 根不能有入边；每点至多一条入边
        parent[f.v] = f.u
    # 强制边内部不得成环（函数图：每点至多一个父指针，沿链走访判环）
    for start in parent:
        seen: set[str] = set()
        cur = start
        while cur in parent:
            if cur in seen:
                return None
            seen.add(cur)
            cur = parent[cur]

    dsu = _DSU(points)
    for f in forced:
        dsu.union(f.u, f.v)

    comp = {p: dsu.find(p) for p in points}
    head: dict[str, str] = {}
    for p in points:
        if p not in parent:  # 每个强制链块恰有一个无强制入边的点（头）
            head[comp[p]] = p

    forced_ids = {f.id for f in forced}
    rank = _rank_of(channels)
    red_edges: list[_Edge] = []
    for c in channels:
        if c.id in forced_ids:
            continue
        cu, cv = comp[c.u], comp[c.v]
        if cu == cv:
            continue  # 块内边：成环或与强制链冲突
        if head[cv] != c.v:
            continue  # 终点在块内且不是链头：不能从块外给它入边
        red_edges.append(_make_edge(c, cu, cv, 0, rank))

    nodes = sorted(set(comp.values()))
    root_comp = comp[root]
    sub = _edmonds(nodes, root_comp, red_edges)
    if sub is None:
        return None
    picked = sub[0]
    return sum(f.cost for f in forced) + sum(e.orig.cost for e in picked)


# ---------------------------------------------------------------------------
# 顶层求解
# ---------------------------------------------------------------------------


def reachable_from(root: str, channels: list[Channel]) -> set[str]:
    adj: dict[str, list[str]] = {}
    for c in channels:
        adj.setdefault(c.u, []).append(c.v)
    seen = {root}
    stack = [root]
    while stack:
        u = stack.pop()
        for v in adj.get(u, ()):
            if v not in seen:
                seen.add(v)
                stack.append(v)
    return seen


def solve(points: list[str], root: str, channels: list[Channel]) -> dict:
    """求解并组装 API 结果。输入须已通过 validate_problem。"""
    reach = reachable_from(root, channels)
    unreachable = sorted(p for p in points if p not in reach)
    if unreachable:
        return {
            "status": "unsolvable",
            "reason": "存在无法自注入根经有向通道到达的采样点，"
            "无法满足“每个非根点恰有一条入选通道并从根可达”。",
            "unreachable": unreachable,
        }

    # 1) 朴素 Edmonds 求最小总代价 C*（同代价按标识升序）。
    run = _edmonds(list(points), root, _initial_edges(channels))
    assert run is not None, "全部可达但 Edmonds 无解，内部不一致"
    best_cost = sum(e.orig.cost for e in run[0])

    # 2) 字典序贪心：按标识升序试探强制入选，仅当不抬高最优代价时接受。
    #    嵌套环的统一裁决完全体现在 C* 中：局部最低入口能否保留取决于
    #    层层收缩 / 展开后的全局代价，贪心试探只在全局最优解上进行。
    forced: list[Channel] = []
    for c in sorted(channels, key=lambda c: c.id):
        cand = _min_cost_with_forced(points, root, channels, forced + [c])
        if cand == best_cost:
            forced.append(c)
    forced_ids = {c.id for c in forced}

    # 3) 以规范惩罚重跑，使收缩 / 展开记录恰好对应规范树。
    run = _edmonds(list(points), root, _initial_edges(channels, forced_ids))
    assert run is not None, "规范解重跑无解，内部不一致"
    picked, levels, expansions = run
    assert sum(e.orig.cost for e in picked) == best_cost, "规范解代价与最优代价不一致"
    final_ids = sorted(e.orig.id for e in picked)
    assert set(final_ids) == forced_ids, "规范解与字典序强制集不一致"

    by_id = {c.id: c for c in channels}
    tree = [
        {"id": cid, "from": by_id[cid].u, "to": by_id[cid].v, "cost": by_id[cid].cost}
        for cid in final_ids
    ]
    return {
        "status": "ok",
        "total_cost": best_cost,
        "tree": tree,
        "canonical_ids": final_ids,
        "record": {
            "levels": levels,
            "expansions": expansions,
            "contractions": sum(1 for lv in levels if lv["cycle"]),
        },
    }


# ---------------------------------------------------------------------------
# 记录复算（供测试与 verify 服务核对证据链）
# ---------------------------------------------------------------------------


def replay_record(
    points: list[str], root: str, channels: list[Channel], record: dict
) -> list[str]:
    """根据收缩 / 展开记录复算最终入选通道标识（升序）。

    复算规则：叶子层（无环层）的入选通道 ∪ 每次展开保留的环边。
    同时校验记录内部一致性：每次展开的进入通道须已在当前选中集内、
    被替换 / 保留的环边须恰好分割对应环、最终每非根点恰有一条入边且
    自根可达。
    """
    levels: list[dict] = record["levels"]
    expansions: list[dict] = record["expansions"]
    if not levels:
        raise AssertionError("记录缺少层级信息")
    leaf = levels[-1]
    if leaf["cycle"] is not None:
        raise AssertionError("最深层仍含环，记录不完整")
    selected: set[str] = {c["channel"] for c in leaf["chosen"]}

    cycles_by_super: dict[str, dict] = {}
    for lv in levels:
        if lv["cycle"]:
            cyc = lv["cycle"]
            cycles_by_super[cyc["supernode"]] = cyc

    if len(expansions) != len(cycles_by_super):
        raise AssertionError(
            f"展开次数 {len(expansions)} 与收缩次数 {len(cycles_by_super)} 不一致"
        )

    removed_all: list[str] = []
    for exp in expansions:
        if exp["supernode"] not in cycles_by_super:
            raise AssertionError(f"展开记录引用了未知超点 {exp['supernode']}")
        cyc = cycles_by_super[exp["supernode"]]
        if exp["entering_channel"] not in selected:
            raise AssertionError(
                f"展开 {exp['supernode']} 的进入通道 {exp['entering_channel']} 不在当前选中集"
            )
        cycle_channels = set(cyc["channels"])
        removed = exp["removed_cycle_channel"]
        kept = exp["kept_cycle_channels"]
        if removed not in cycle_channels:
            raise AssertionError(
                f"展开 {exp['supernode']} 移除的 {removed} 不属于该环"
            )
        if any(k not in cycle_channels for k in kept):
            raise AssertionError(
                f"展开 {exp['supernode']} 保留的边中存在不属于该环的通道"
            )
        if len(set(kept)) != len(kept) or removed in kept:
            raise AssertionError(
                f"展开 {exp['supernode']} 的保留环边存在重复或包含被替换边"
            )
        if set(kept) | {removed} != cycle_channels:
            raise AssertionError(
                f"展开 {exp['supernode']} 的替换 / 保留边未恰好分割该环"
            )
        selected.update(kept)
        removed_all.append(removed)

    by_id = {c.id: c for c in channels}
    for cid in selected:
        if cid not in by_id:
            raise AssertionError(f"选中通道 {cid} 不在输入中")
    for cid in removed_all:
        if cid in selected:
            raise AssertionError(f"被展开替换掉的环边 {cid} 仍出现在最终树中")
    # 结构校验：每非根点恰一条入边、无环、自根可达
    indeg: dict[str, int] = {}
    for cid in selected:
        indeg[by_id[cid].v] = indeg.get(by_id[cid].v, 0) + 1
    for p in points:
        want = 0 if p == root else 1
        if indeg.get(p, 0) != want:
            raise AssertionError(f"点 {p} 的入选入边数为 {indeg.get(p, 0)}，应为 {want}")
    sub_channels = [by_id[cid] for cid in selected]
    if reachable_from(root, sub_channels) != set(points):
        raise AssertionError("复算结果不能自根到达全部点")
    return sorted(selected)
