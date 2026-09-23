/** 内置样例：嵌套环、平行通道、同优规范树、嵌套环裁决、不可达点。 */

export const SAMPLES = {
  nested: {
    name: "嵌套环收缩",
    points: "r a b c d",
    root: "r",
    channels: `# 嵌套有向环：{a,b} 收缩后再与 c 成环
e1, r, a, 5
e2, a, b, 1
e3, b, a, 1
e4, b, c, 1
e5, c, a, 1
e6, c, d, 1`,
  },
  adjudicate: {
    name: "嵌套环裁决（局部低价陷阱）",
    points: "v0 v1 v2 v3 v4",
    root: "v0",
    channels: `# v1 与 v3 的最低入口互指成内层环，v4 再与其闭合成外层环；
# 根部同代价入口 e00/e01（7）与局部低价 e06（6）竞争：
# 逐点贪心得 18，全局最小为 14（e00 e02 e09 e11）
e00, v0, v1, 7
e01, v0, v3, 7
e02, v0, v2, 5
e03, v0, v1, 9
e04, v0, v3, 9
e05, v3, v4, 5
e06, v0, v4, 6
e07, v4, v1, 9
e08, v3, v1, 1
e09, v1, v3, 1
e10, v4, v3, 6
e11, v1, v4, 1`,
  },
  parallel: {
    name: "平行通道",
    points: "r x y",
    root: "r",
    channels: `# r->x 两条平行通道，选代价更小者
p1, r, x, 3
p2, r, x, 1
p3, x, y, 2
p4, r, y, 9
p5, y, x, 4`,
  },
  canonical: {
    name: "同优规范树",
    points: "r b c d",
    root: "r",
    channels: `# 四棵同优树（代价均为 3），规范解取升序标识序列字典序最小: k1 k2 k4
k1, r, b, 1
k2, b, c, 1
k3, r, c, 1
k4, c, d, 1
k5, r, d, 1`,
  },
  unreachable: {
    name: "不可达点（无解）",
    points: "r a b z",
    root: "r",
    channels: `# z 无法自根到达，求解将失败并指出不可达点
u1, r, a, 1
u2, a, b, 1
u3, z, a, 1`,
  },
};
