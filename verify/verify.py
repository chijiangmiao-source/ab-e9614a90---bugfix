"""verify 一次性服务：对真实 API 与经 Web 反代的同一请求做样例核对 + HTTP 冒烟。

样例覆盖：嵌套环收缩、平行通道、同优规范树字典序、不可达点；
另含输入错误（自环 / 结构非法）核对。全部断言通过则进程以 0 退出，
任一失败立即以非零码退出。
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

# 复用后端的记录复算逻辑，从“独立消费者”视角核对可复算记录
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/srv/api")
sys.path.insert(0, os.path.join(_HERE, "..", "api"))
from app.arborescence import Channel, replay_record  # noqa: E402

API = os.environ.get("API_BASE", "http://api:8000")
WEB = os.environ.get("WEB_BASE", "http://web")

FAILURES: list[str] = []


def http(method: str, url: str, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def wait_for(url: str, label: str, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if resp.status == 200:
                    return True
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1)
    FAILURES.append(f"{label} 在 {timeout}s 内未就绪: {last}")
    return False


def check(cond: bool, msg: str) -> None:
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {msg}")
    if not cond:
        FAILURES.append(msg)


def channels_of(payload: dict) -> list[Channel]:
    return [
        Channel(id=c["id"], u=c["from"], v=c["to"], cost=c["cost"])
        for c in payload["channels"]
    ]


SCENARIOS = {
    "nested": {
        "payload": {
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
        },
        "expect_ids": ["e1", "e2", "e4", "e6"],
        "expect_cost": 8,
        "expect_contractions": 2,
    },
    "parallel": {
        "payload": {
            "points": ["r", "x", "y"],
            "root": "r",
            "channels": [
                {"id": "p1", "from": "r", "to": "x", "cost": 3},
                {"id": "p2", "from": "r", "to": "x", "cost": 1},
                {"id": "p3", "from": "x", "to": "y", "cost": 2},
                {"id": "p4", "from": "r", "to": "y", "cost": 9},
                {"id": "p5", "from": "y", "to": "x", "cost": 4},
            ],
        },
        "expect_ids": ["p2", "p3"],
        "expect_cost": 3,
        "expect_contractions": 0,
    },
    "canonical": {
        "payload": {
            "points": ["r", "b", "c", "d"],
            "root": "r",
            "channels": [
                {"id": "k1", "from": "r", "to": "b", "cost": 1},
                {"id": "k2", "from": "b", "to": "c", "cost": 1},
                {"id": "k3", "from": "r", "to": "c", "cost": 1},
                {"id": "k4", "from": "c", "to": "d", "cost": 1},
                {"id": "k5", "from": "r", "to": "d", "cost": 1},
            ],
        },
        "expect_ids": ["k1", "k2", "k4"],
        "expect_cost": 3,
        "expect_contractions": 0,
    },
    "unreachable": {
        "payload": {
            "points": ["r", "a", "b", "z"],
            "root": "r",
            "channels": [
                {"id": "u1", "from": "r", "to": "a", "cost": 1},
                {"id": "u2", "from": "a", "to": "b", "cost": 1},
                {"id": "u3", "from": "z", "to": "a", "cost": 1},
            ],
        },
        "expect_unreachable": ["z"],
    },
    "glacier": {
        # 五点双层环：内层 {v1,v3} 回流，v4 与其闭合成外层环，v2 为叶子；
        # 根对 v4 有 e00/e03 两条同代价入口。局部贪心得次优 18，
        # 嵌套环统一裁决后最优为 14、规范序列 [e00,e02,e09,e11]。
        "payload": {
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
        },
        "expect_ids": ["e00", "e02", "e09", "e11"],
        "expect_cost": 14,
        "expect_contractions": 2,
        "expect_inner_cycle_nodes": ["v1", "v3"],
        "expect_expansions": [
            {"entering_channel": "e00", "enters_node": "v4",
             "removed_cycle_channel": "e08", "kept_cycle_channels": ["e09"]},
            {"entering_channel": "e09", "enters_node": "v3",
             "removed_cycle_channel": "e05", "kept_cycle_channels": ["e02"]},
        ],
    },
}


def verify_ok_scenario(name: str, sc: dict) -> None:
    print(f"- 样例 {name}")
    st_api, body_api = http("POST", f"{API}/api/solve", sc["payload"])
    st_web, body_web = http("POST", f"{WEB}/api/solve", sc["payload"])
    check(st_api == 200 and body_api.get("status") == "ok", "API 直连返回 200/ok")
    check(st_web == 200 and body_web.get("status") == "ok", "经页面同源反代返回 200/ok")
    check(body_api == body_web, "页面反代结果与 API 直连完全一致")
    if body_api.get("status") != "ok":
        return
    check(body_api["total_cost"] == sc["expect_cost"],
          f"总代价 == {sc['expect_cost']}（实际 {body_api['total_cost']}）")
    check(body_api["canonical_ids"] == sc["expect_ids"],
          f"规范树标识序列 == {sc['expect_ids']}（实际 {body_api['canonical_ids']}）")
    check(body_api["record"]["contractions"] == sc["expect_contractions"],
          f"环收缩次数 == {sc['expect_contractions']}")

    # 展开替换明细（进入通道 / 进入点 / 被替换环边 / 保留环边）
    expect_exps = sc.get("expect_expansions")
    if expect_exps is not None:
        exps = body_api["record"]["expansions"]
        check(len(exps) == len(expect_exps),
              f"展开次数 == {len(expect_exps)}（实际 {len(exps)}）")
        for i, want in enumerate(expect_exps):
            if i >= len(exps):
                break
            got = exps[i]
            check(
                all(got.get(k) == v for k, v in want.items()),
                f"第 {i + 1} 次展开明细 == {want}（实际 {got}）",
            )
    # 收缩环次序（内 → 外）
    inner_nodes = sc.get("expect_inner_cycle_nodes")
    if inner_nodes is not None:
        cyc0 = body_api["record"]["levels"][0]["cycle"]
        check(cyc0 is not None and set(cyc0["nodes"]) == set(inner_nodes),
              f"最先收缩内层环 {inner_nodes}（实际 {cyc0 and cyc0['nodes']}）")

    replayed = replay_record(
        sc["payload"]["points"], sc["payload"]["root"],
        channels_of(sc["payload"]), body_api["record"],
    )
    check(replayed == body_api["canonical_ids"], "收缩/展开记录独立复算得到同一规范树")
    cost_sum = sum(
        c["cost"] for c in body_api["tree"] if c["id"] in set(body_api["canonical_ids"])
    )
    check(cost_sum == body_api["total_cost"], "逐边代价之和等于总代价")


def verify_order_invariance(name: str, sc: dict, rounds: int = 8) -> None:
    """打乱点与通道的提交顺序，真实 HTTP 结果须保持不变。"""
    import random

    print(f"- 样例 {name} 提交顺序无关性（真实 HTTP）")
    _, baseline = http("POST", f"{API}/api/solve", sc["payload"])
    for seed in range(rounds):
        rng = random.Random(1000 + seed)
        payload = {
            "points": sorted(sc["payload"]["points"], key=lambda _: rng.random()),
            "root": sc["payload"]["root"],
            "channels": sorted(sc["payload"]["channels"], key=lambda _: rng.random()),
        }
        st, body = http("POST", f"{API}/api/solve", payload)
        ok = (
            st == 200
            and body.get("status") == "ok"
            and body.get("total_cost") == sc["expect_cost"]
            and body.get("canonical_ids") == sc["expect_ids"]
            and body.get("record", {}).get("contractions") == sc["expect_contractions"]
        )
        check(ok, f"打乱顺序第 {seed + 1} 轮结果不变")
        if ok:
            check(
                replay_record(
                    payload["points"], payload["root"],
                    channels_of(payload), body["record"],
                )
                == sc["expect_ids"],
                f"打乱顺序第 {seed + 1} 轮记录独立复算一致",
            )



def verify_unreachable_scenario() -> None:
    print("- 样例 unreachable（不可达点）")
    sc = SCENARIOS["unreachable"]
    st_api, body_api = http("POST", f"{API}/api/solve", sc["payload"])
    st_web, body_web = http("POST", f"{WEB}/api/solve", sc["payload"])
    check(st_api == 200 and body_api["status"] == "unsolvable", "API 直连报告无解")
    check(body_web == body_api, "页面反代同样报告无解")
    check(body_api["unreachable"] == sc["expect_unreachable"],
          f"不可达点 == {sc['expect_unreachable']}（实际 {body_api['unreachable']}）")
    check(bool(body_api.get("reason")), "附带明确原因说明")


def verify_invalid_inputs() -> None:
    print("- 输入错误核对")
    # 自环
    self_loop = {
        "points": ["r", "a"], "root": "r",
        "channels": [{"id": "c1", "from": "a", "to": "a", "cost": 1}],
    }
    st, body = http("POST", f"{API}/api/solve", self_loop)
    check(st == 422 and body["status"] == "invalid", "自环返回 422/invalid")
    check(any("自环" in e for e in body.get("errors", [])), "自环原因明确")
    st2, body2 = http("POST", f"{WEB}/api/solve", self_loop)
    check(st2 == 422 and body2["status"] == "invalid", "页面反代同样拒绝自环")
    # 结构非法（根不在点集 + 点不足）
    bad = {"points": ["x"], "root": "nope", "channels": []}
    st, body = http("POST", f"{API}/api/solve", bad)
    check(st == 422 and body["status"] == "invalid", "结构非法返回 422/invalid")
    check(bool(body.get("errors")), "结构非法附带错误列表")
    # 负代价（pydantic 层）
    neg = {
        "points": ["r", "a"], "root": "r",
        "channels": [{"id": "c1", "from": "r", "to": "a", "cost": -3}],
    }
    st, body = http("POST", f"{API}/api/solve", neg)
    check(st == 422 and body["status"] == "invalid", "负代价返回 422/invalid")


def verify_http_smoke() -> None:
    print("- HTTP / 页面冒烟")
    for base, label in ((API, "API"), (WEB, "Web")):
        st, body = http("GET", f"{base}/api/health")
        check(st == 200 and body.get("status") == "ok", f"{label} 的 /api/health 可用")
    with urllib.request.urlopen(f"{WEB}/", timeout=5) as resp:
        html = resp.read().decode()
        check(resp.status == 200, "Web 首页 200")
        check('<div id="root">' in html, "首页包含 React 挂载点")
        check("/assets/" in html and html.count("<script") >= 1, "首页引用构建产物")


def main() -> int:
    print("== 等待服务就绪 ==")
    ok_api = wait_for(f"{API}/api/health", "api")
    ok_web = wait_for(f"{WEB}/", "web")
    if not (ok_api and ok_web):
        print("\nVERIFY FAILED:", "; ".join(FAILURES))
        return 1

    print("== 真实 API 与页面结果核对 ==")
    for name in ("nested", "parallel", "canonical", "glacier"):
        verify_ok_scenario(name, SCENARIOS[name])
    verify_order_invariance("glacier", SCENARIOS["glacier"])
    verify_unreachable_scenario()
    verify_invalid_inputs()
    verify_http_smoke()

    if FAILURES:
        print(f"\nVERIFY FAILED（{len(FAILURES)} 项）:")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("\nVERIFY PASSED：全部样例、记录复算、输入错误与冒烟检查通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
