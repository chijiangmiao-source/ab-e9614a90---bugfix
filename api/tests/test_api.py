"""API 端到端测试（TestClient）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_solve_ok():
    payload = {
        "points": ["r", "a", "b", "c", "d"],
        "root": "r",
        "channels": [
            {"id": "e1", "from": "r", "to": "a", "cost": 5},
            {"id": "e2", "from": "a", "to": "b", "cost": 1},
            {"id": "e3", "from": "b", "to": "a", "cost": 1},
            {"id": "e4", "from": "b", "to": "c", "cost": 1},
            {"id": "e5", "from": "c", "to": "a", "cost": 1},
            {"id": "e6", "from": "c", "to": "d", "cost": 1},
        ],
    }
    r = client.post("/api/solve", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["total_cost"] == 8
    assert body["canonical_ids"] == ["e1", "e2", "e4", "e6"]
    assert len(body["tree"]) == 4
    assert body["record"]["contractions"] == 2
    assert len(body["record"]["expansions"]) == 2


def test_solve_glacier_nested_cycles():
    """五点双层环：局部低价入口需经嵌套环统一裁决（次优 18，最优 14）。"""
    payload = {
        "points": ["v0", "v1", "v2", "v3", "v4"],
        "root": "v0",
        "channels": [
            {"id": "e00", "from": "v0", "to": "v4", "cost": 8},
            {"id": "e01", "from": "v0", "to": "v1", "cost": 8},
            {"id": "e02", "from": "v3", "to": "v1", "cost": 3},
            {"id": "e03", "from": "v0", "to": "v4", "cost": 8},
            {"id": "e04", "from": "v2", "to": "v4", "cost": 11},
            {"id": "e05", "from": "v1", "to": "v3", "cost": 1},
            {"id": "e06", "from": "v0", "to": "v3", "cost": 7},
            {"id": "e07", "from": "v3", "to": "v4", "cost": 6},
            {"id": "e08", "from": "v1", "to": "v4", "cost": 5},
            {"id": "e09", "from": "v4", "to": "v3", "cost": 2},
            {"id": "e10", "from": "v0", "to": "v2", "cost": 3},
            {"id": "e11", "from": "v1", "to": "v2", "cost": 1},
        ],
    }
    r = client.post("/api/solve", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["total_cost"] == 14
    assert body["canonical_ids"] == ["e00", "e02", "e09", "e11"]
    assert sum(c["cost"] for c in body["tree"]) == 14
    record = body["record"]
    assert record["contractions"] == 2
    assert len(record["expansions"]) == 2
    # 内层环先收缩、外层环后收缩
    assert set(record["levels"][0]["cycle"]["nodes"]) == {"v1", "v3"}
    assert "v4" in record["levels"][1]["cycle"]["nodes"]
    # 展开顺序：外层先展开（e00 进入 v4，替换 e08），内层后展开
    assert record["expansions"][0]["entering_channel"] == "e00"
    assert record["expansions"][0]["removed_cycle_channel"] == "e08"
    assert record["expansions"][1]["entering_channel"] == "e09"
    assert record["expansions"][1]["removed_cycle_channel"] == "e05"


def test_solve_glacier_order_invariant():
    """打乱点 / 通道提交顺序不改变结果。"""
    import random

    payload = {
        "points": ["v0", "v1", "v2", "v3", "v4"],
        "root": "v0",
        "channels": [
            {"id": "e00", "from": "v0", "to": "v4", "cost": 8},
            {"id": "e01", "from": "v0", "to": "v1", "cost": 8},
            {"id": "e02", "from": "v3", "to": "v1", "cost": 3},
            {"id": "e03", "from": "v0", "to": "v4", "cost": 8},
            {"id": "e04", "from": "v2", "to": "v4", "cost": 11},
            {"id": "e05", "from": "v1", "to": "v3", "cost": 1},
            {"id": "e06", "from": "v0", "to": "v3", "cost": 7},
            {"id": "e07", "from": "v3", "to": "v4", "cost": 6},
            {"id": "e08", "from": "v1", "to": "v4", "cost": 5},
            {"id": "e09", "from": "v4", "to": "v3", "cost": 2},
            {"id": "e10", "from": "v0", "to": "v2", "cost": 3},
            {"id": "e11", "from": "v1", "to": "v2", "cost": 1},
        ],
    }
    base = client.post("/api/solve", json=payload).json()
    for seed in range(10):
        rng = random.Random(seed)
        p = dict(payload)
        p["points"] = sorted(payload["points"], key=lambda _: rng.random())
        p["channels"] = sorted(payload["channels"], key=lambda _: rng.random())
        body = client.post("/api/solve", json=p).json()
        assert body["total_cost"] == 14
        assert body["canonical_ids"] == ["e00", "e02", "e09", "e11"]
        assert body["record"]["contractions"] == 2
        assert body["tree"] == base["tree"]


def test_solve_unsolvable():
    payload = {
        "points": ["r", "a", "z"],
        "root": "r",
        "channels": [{"id": "u1", "from": "r", "to": "a", "cost": 1}],
    }
    r = client.post("/api/solve", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "unsolvable"
    assert body["unreachable"] == ["z"]
    assert body["reason"]


def test_invalid_self_loop():
    payload = {
        "points": ["r", "a"],
        "root": "r",
        "channels": [{"id": "c1", "from": "a", "to": "a", "cost": 1}],
    }
    r = client.post("/api/solve", json=payload)
    assert r.status_code == 422
    body = r.json()
    assert body["status"] == "invalid"
    assert any("自环" in e for e in body["errors"])


def test_invalid_schema():
    r = client.post("/api/solve", json={"points": ["r"], "root": "r"})
    assert r.status_code == 422
    assert r.json()["status"] == "invalid"


def test_negative_cost_rejected():
    payload = {
        "points": ["r", "a"],
        "root": "r",
        "channels": [{"id": "c1", "from": "r", "to": "a", "cost": -2}],
    }
    r = client.post("/api/solve", json=payload)
    assert r.status_code == 422
    assert r.json()["status"] == "invalid"
