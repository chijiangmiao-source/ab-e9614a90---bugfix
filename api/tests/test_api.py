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


def test_solve_nested_adjudication():
    """局部低价入口需经嵌套环统一裁决的场景：总代价 14、规范序列、
    两次收缩与两次展开，且提交顺序不影响结果。"""
    payload = {
        "points": ["v0", "v1", "v2", "v3", "v4"],
        "root": "v0",
        "channels": [
            {"id": "e00", "from": "v0", "to": "v1", "cost": 7},
            {"id": "e01", "from": "v0", "to": "v3", "cost": 7},
            {"id": "e02", "from": "v0", "to": "v2", "cost": 5},
            {"id": "e03", "from": "v0", "to": "v1", "cost": 9},
            {"id": "e04", "from": "v0", "to": "v3", "cost": 9},
            {"id": "e05", "from": "v3", "to": "v4", "cost": 5},
            {"id": "e06", "from": "v0", "to": "v4", "cost": 6},
            {"id": "e07", "from": "v4", "to": "v1", "cost": 9},
            {"id": "e08", "from": "v3", "to": "v1", "cost": 1},
            {"id": "e09", "from": "v1", "to": "v3", "cost": 1},
            {"id": "e10", "from": "v4", "to": "v3", "cost": 6},
            {"id": "e11", "from": "v1", "to": "v4", "cost": 1},
        ],
    }
    r = client.post("/api/solve", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["total_cost"] == 14
    assert body["canonical_ids"] == ["e00", "e02", "e09", "e11"]
    assert sum(e["cost"] for e in body["tree"]) == 14
    assert body["record"]["contractions"] == 2
    exps = body["record"]["expansions"]
    assert len(exps) == 2
    assert [e["entering_channel"] for e in exps] == ["e00", "e00"]
    assert [e["removed_cycle_channel"] for e in exps] == ["e10", "e08"]
    assert [e["kept_cycle_channels"] for e in exps] == [["e11"], ["e09"]]
    # 改变点与通道的提交顺序，响应完全一致
    shuffled = {
        "points": payload["points"][::-1],
        "root": "v0",
        "channels": payload["channels"][::-1],
    }
    r2 = client.post("/api/solve", json=shuffled)
    assert r2.status_code == 200
    assert r2.json() == body


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
