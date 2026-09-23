"""最小汇流树求解器单元测试。

包含与暴力枚举对拍的随机化测试：枚举所有 n-1 条边的子集，
独立验证最小总代价与字典序最小规范树。
"""

from __future__ import annotations

import itertools
import random

import pytest

from app.arborescence import (
    Channel,
    ProblemError,
    reachable_from,
    replay_record,
    solve,
    validate_problem,
)


def brute_force(points, root, channels):
    """暴力枚举全部 n-1 边子集，返回 (最小代价, 字典序最小标识序列) 或 None。"""
    n = len(points)
    best_cost = None
    best_ids = None
    for combo in itertools.combinations(channels, n - 1):
        indeg = {}
        ok = True
        for c in combo:
            if c.v == root:
                ok = False
                break
            indeg[c.v] = indeg.get(c.v, 0) + 1
            if indeg[c.v] > 1:
                ok = False
                break
        if not ok or any(indeg.get(p, 0) != 1 for p in points if p != root):
            continue
        if reachable_from(root, list(combo)) != set(points):
            continue
        cost = sum(c.cost for c in combo)
        ids = sorted(c.id for c in combo)
        if best_cost is None or cost < best_cost or (cost == best_cost and ids < best_ids):
            best_cost, best_ids = cost, ids
    if best_cost is None:
        return None
    return best_cost, best_ids


def make(points, root, channels):
    return [Channel(id=c[0], u=c[1], v=c[2], cost=c[3]) for c in channels]


NESTED = (
    ["r", "a", "b", "c", "d"],
    "r",
    make(
        ["r", "a", "b", "c", "d"],
        "r",
        [
            ("e1", "r", "a", 5),
            ("e2", "a", "b", 1),
            ("e3", "b", "a", 1),
            ("e4", "b", "c", 1),
            ("e5", "c", "a", 1),
            ("e6", "c", "d", 1),
        ],
    ),
)

PARALLEL = (
    ["r", "x", "y"],
    "r",
    make(
        ["r", "x", "y"],
        "r",
        [
            ("p1", "r", "x", 3),
            ("p2", "r", "x", 1),
            ("p3", "x", "y", 2),
            ("p4", "r", "y", 9),
            ("p5", "y", "x", 4),
        ],
    ),
)

CANONICAL = (
    ["r", "b", "c", "d"],
    "r",
    make(
        ["r", "b", "c", "d"],
        "r",
        [
            ("k1", "r", "b", 1),
            ("k2", "b", "c", 1),
            ("k3", "r", "c", 1),
            ("k4", "c", "d", 1),
            ("k5", "r", "d", 1),
        ],
    ),
)

UNREACHABLE = (
    ["r", "a", "b", "z"],
    "r",
    make(
        ["r", "a", "b", "z"],
        "r",
        [("u1", "r", "a", 1), ("u2", "a", "b", 1), ("u3", "z", "a", 1)],
    ),
)

# 五点双层环：内层环 {v1,v3}（e05/e02），v4 与该回流闭合成外层环
# （e08/e09），v2 为叶子。根对 v4 有两条同代价平行入口 e00/e03。
# 逐点选最低入口会得到 18 的次优树 [e02,e06,e08,e10]；只有嵌套环统一
# 裁决才能得到 14 的规范树 [e00,e02,e09,e11]。
GLACIER = (
    ["v0", "v1", "v2", "v3", "v4"],
    "v0",
    make(
        ["v0", "v1", "v2", "v3", "v4"],
        "v0",
        [
            ("e00", "v0", "v4", 8),
            ("e01", "v0", "v1", 8),
            ("e02", "v3", "v1", 3),
            ("e03", "v0", "v4", 8),
            ("e04", "v2", "v4", 11),
            ("e05", "v1", "v3", 1),
            ("e06", "v0", "v3", 7),
            ("e07", "v3", "v4", 6),
            ("e08", "v1", "v4", 5),
            ("e09", "v4", "v3", 2),
            ("e10", "v0", "v2", 3),
            ("e11", "v1", "v2", 1),
        ],
    ),
)


class TestSamples:
    def test_nested_cycles(self):
        points, root, channels = NESTED
        res = solve(points, root, channels)
        assert res["status"] == "ok"
        assert res["total_cost"] == 8
        assert res["canonical_ids"] == ["e1", "e2", "e4", "e6"]
        levels = res["record"]["levels"]
        # 第一层收缩环 {a, b}
        assert levels[0]["cycle"] is not None
        assert set(levels[0]["cycle"]["nodes"]) == {"a", "b"}
        s1 = levels[0]["cycle"]["supernode"]
        # 第二层出现嵌套环：超点 S1 与 c 互指
        assert levels[1]["cycle"] is not None
        assert set(levels[1]["cycle"]["nodes"]) == {s1, "c"}
        assert res["record"]["contractions"] == 2
        # 展开记录：先内层后外层
        exps = res["record"]["expansions"]
        assert len(exps) == 2
        assert exps[0]["entering_channel"] == "e1"
        assert exps[0]["removed_cycle_channel"] == "e5"
        assert exps[1]["removed_cycle_channel"] == "e3"
        # 记录可复算
        assert replay_record(points, root, channels, res["record"]) == res["canonical_ids"]

    def test_parallel_channels(self):
        points, root, channels = PARALLEL
        res = solve(points, root, channels)
        assert res["status"] == "ok"
        assert res["total_cost"] == 3
        assert res["canonical_ids"] == ["p2", "p3"]
        assert res["record"]["contractions"] == 0
        assert replay_record(points, root, channels, res["record"]) == ["p2", "p3"]

    def test_canonical_tiebreak(self):
        points, root, channels = CANONICAL
        res = solve(points, root, channels)
        assert res["status"] == "ok"
        assert res["total_cost"] == 3
        # 四棵同优树中字典序最小者为 [k1, k2, k4]
        assert res["canonical_ids"] == ["k1", "k2", "k4"]
        assert replay_record(points, root, channels, res["record"]) == ["k1", "k2", "k4"]

    def test_unreachable(self):
        points, root, channels = UNREACHABLE
        res = solve(points, root, channels)
        assert res["status"] == "unsolvable"
        assert res["unreachable"] == ["z"]
        assert res["reason"]


class TestGlacierNested:
    """五点双层环场景：局部低价入口必须经嵌套环统一裁决。"""

    def test_optimal_cost_and_canonical_sequence(self):
        points, root, channels = GLACIER
        res = solve(points, root, channels)
        assert res["status"] == "ok"
        assert res["total_cost"] == 14
        assert res["canonical_ids"] == ["e00", "e02", "e09", "e11"]
        # 逐边合计与总代价一致
        assert sum(c["cost"] for c in res["tree"]) == 14

    def test_matches_brute_force(self):
        points, root, channels = GLACIER
        expect = brute_force(points, root, channels)
        assert expect == (14, ["e00", "e02", "e09", "e11"])

    def test_two_nested_contractions_inner_then_outer(self):
        points, root, channels = GLACIER
        res = solve(points, root, channels)
        levels = res["record"]["levels"]
        assert res["record"]["contractions"] == 2
        # 第 0 层：内层二点环 {v1, v3}
        c0 = levels[0]["cycle"]
        assert c0 is not None
        assert set(c0["nodes"]) == {"v1", "v3"}
        assert set(c0["channels"]) == {"e02", "e05"}
        s1 = c0["supernode"]
        # 第 1 层：内层超点与 v4 闭合成外层环
        c1 = levels[1]["cycle"]
        assert c1 is not None
        assert set(c1["nodes"]) == {s1, "v4"}
        assert set(c1["channels"]) == {"e08", "e09"}
        s2 = c1["supernode"]
        # 最深层无环
        assert levels[2]["cycle"] is None
        # 环内非环边 e07 被丢弃
        assert "e07" in c1["dropped_internal"]
        # 两次收缩产生两个不同超点
        assert s1 != s2

    def test_two_expansions_outer_then_inner(self):
        points, root, channels = GLACIER
        res = solve(points, root, channels)
        exps = res["record"]["expansions"]
        assert len(exps) == 2
        levels = res["record"]["levels"]
        s_outer = levels[1]["cycle"]["supernode"]
        s_inner = levels[0]["cycle"]["supernode"]
        # 最深层先展开：外层环先展开
        assert exps[0]["supernode"] == s_outer
        assert exps[0]["entering_channel"] == "e00"
        assert exps[0]["enters_node"] == "v4"
        assert exps[0]["removed_cycle_channel"] == "e08"
        assert exps[0]["kept_cycle_channels"] == ["e09"]
        # 再展开内层环：e09 进入 v3，替换 e05、保留 e02
        assert exps[1]["supernode"] == s_inner
        assert exps[1]["entering_channel"] == "e09"
        assert exps[1]["enters_node"] == "v3"
        assert exps[1]["removed_cycle_channel"] == "e05"
        assert exps[1]["kept_cycle_channels"] == ["e02"]

    def test_record_replays_to_canonical_tree(self):
        points, root, channels = GLACIER
        res = solve(points, root, channels)
        assert replay_record(points, root, channels, res["record"]) == [
            "e00", "e02", "e09", "e11"
        ]

    def test_invariant_under_submission_order(self):
        import random

        points, root, channels = GLACIER
        import json

        baseline = json.dumps(solve(points, root, channels), sort_keys=True)
        for seed in range(25):
            rng = random.Random(seed)
            ps = points[:]
            cs = channels[:]
            rng.shuffle(ps)
            rng.shuffle(cs)
            res = solve(ps, root, cs)
            assert res["total_cost"] == 14
            assert res["canonical_ids"] == ["e00", "e02", "e09", "e11"]
            assert res["record"]["contractions"] == 2
            assert replay_record(ps, root, cs, res["record"]) == [
                "e00", "e02", "e09", "e11"
            ]
            assert json.dumps(res, sort_keys=True) == baseline


class TestValidation:
    def ok(self, points, root, channels):
        validate_problem(points, root, make(points, root, channels))

    def test_too_few_points(self):
        with pytest.raises(ProblemError):
            self.ok(["r"], "r", [])

    def test_too_many_points(self):
        with pytest.raises(ProblemError):
            self.ok([f"p{i}" for i in range(41)], "p0", [])

    def test_duplicate_point(self):
        with pytest.raises(ProblemError) as ei:
            self.ok(["r", "a", "a"], "r", [])
        assert any("重复" in e for e in ei.value.errors)

    def test_root_not_in_points(self):
        with pytest.raises(ProblemError):
            self.ok(["r", "a"], "x", [("c1", "r", "a", 1)])

    def test_self_loop(self):
        with pytest.raises(ProblemError) as ei:
            self.ok(["r", "a"], "r", [("c1", "a", "a", 1)])
        assert any("自环" in e for e in ei.value.errors)

    def test_duplicate_channel_id(self):
        with pytest.raises(ProblemError):
            self.ok(["r", "a"], "r", [("c1", "r", "a", 1), ("c1", "r", "a", 2)])

    def test_negative_cost(self):
        with pytest.raises(ProblemError):
            self.ok(["r", "a"], "r", [("c1", "r", "a", -1)])

    def test_too_many_channels(self):
        chans = [(f"c{i}", "r", "a", 1) for i in range(161)]
        with pytest.raises(ProblemError):
            self.ok(["r", "a"], "r", chans)

    def test_parallel_allowed(self):
        self.ok(["r", "a"], "r", [("c1", "r", "a", 1), ("c2", "r", "a", 5)])

    def test_non_ascii_id_rejected(self):
        with pytest.raises(ProblemError):
            self.ok(["r", "点"], "r", [])


class TestStructure:
    def test_supernode_name_collision_avoided(self):
        # 用户点占用了 S1，超点须另取名字
        points = ["r", "S1", "b"]
        channels = make(
            points,
            "r",
            [("c1", "r", "S1", 5), ("c2", "S1", "b", 1), ("c3", "b", "S1", 1)],
        )
        res = solve(points, "r", channels)
        assert res["status"] == "ok"
        assert res["canonical_ids"] == ["c1", "c2"]
        sname = res["record"]["levels"][0]["cycle"]["supernode"]
        assert sname != "S1"

    def test_edge_into_root_never_selected(self):
        points = ["r", "a"]
        channels = make(points, "r", [("c1", "r", "a", 1), ("c2", "a", "r", 0)])
        res = solve(points, "r", channels)
        assert res["canonical_ids"] == ["c1"]

    def test_zero_cost_cycle(self):
        points = ["r", "a", "b"]
        channels = make(
            points,
            "r",
            [("c1", "r", "a", 0), ("c2", "a", "b", 0), ("c3", "b", "a", 0)],
        )
        res = solve(points, "r", channels)
        assert res["status"] == "ok"
        assert res["total_cost"] == 0

    def test_chain_of_40(self):
        points = [f"n{i:02d}" for i in range(40)]
        channels = make(
            points, "n00", [(f"c{i:02d}", f"n{i:02d}", f"n{i+1:02d}", i) for i in range(39)]
        )
        res = solve(points, "n00", channels)
        assert res["status"] == "ok"
        assert res["total_cost"] == sum(range(39))
        assert len(res["canonical_ids"]) == 39


class TestBruteForce:
    @pytest.mark.parametrize("seed", range(300))
    def test_random_small(self, seed):
        rng = random.Random(seed)
        n = rng.randint(2, 6)
        points = [f"v{i}" for i in range(n)]
        root = points[0]
        m = rng.randint(0, min(12, n * (n - 1)))
        pairs = [(u, v) for u in points for v in points if u != v]
        rng.shuffle(pairs)
        channels = [
            Channel(id=f"e{i}", u=u, v=v, cost=rng.randint(0, 5))
            for i, (u, v) in enumerate(pairs[:m])
        ]
        res = solve(points, root, channels)
        expect = brute_force(points, root, channels)
        if expect is None:
            assert res["status"] == "unsolvable"
            assert res["unreachable"]
        else:
            assert res["status"] == "ok"
            assert res["total_cost"] == expect[0]
            assert res["canonical_ids"] == expect[1]
            assert replay_record(points, root, channels, res["record"]) == expect[1]

    def test_random_with_parallel_edges(self):
        rng = random.Random(20260922)
        for _ in range(200):
            n = rng.randint(2, 5)
            points = [f"v{i}" for i in range(n)]
            root = points[0]
            m = rng.randint(0, 14)
            channels = []
            for i in range(m):
                u = rng.choice(points)
                v = rng.choice([p for p in points if p != u])
                channels.append(Channel(id=f"e{i}", u=u, v=v, cost=rng.randint(0, 4)))
            res = solve(points, root, channels)
            expect = brute_force(points, root, channels)
            if expect is None:
                assert res["status"] == "unsolvable"
            else:
                assert res["status"] == "ok"
                assert res["total_cost"] == expect[0]
                assert res["canonical_ids"] == expect[1]
                assert replay_record(points, root, channels, res["record"]) == expect[1]
