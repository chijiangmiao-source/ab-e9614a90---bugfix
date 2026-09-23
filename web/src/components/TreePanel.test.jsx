import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import TreePanel from "./TreePanel.jsx";

// 与后端 POST /api/solve 对「双层环裁决」样例返回的 tree 逐字一致的夹具
//（真实 API/HTTP 层的一致性由 verify 服务核对）。
const API_TREE = [
  { id: "e00", from: "v0", to: "v4", cost: 8 },
  { id: "e02", from: "v3", to: "v1", cost: 3 },
  { id: "e09", from: "v4", to: "v3", cost: 2 },
  { id: "e11", from: "v1", to: "v2", cost: 1 },
];

describe("<TreePanel /> 双层环裁决样例", () => {
  it("逐边合计与 API 总代价一致（14，而非次优 18）", () => {
    const html = renderToStaticMarkup(
      <TreePanel tree={API_TREE} totalCost={14} evidence={new Map()} />
    );
    expect(html).toContain("总代价 14");
    // 表尾逐边合计：8 + 3 + 2 + 1 = 14
    expect(html).toMatch(/合计[\s\S]*<td[^>]*>14<\/td>/);
    expect(html).not.toContain(">18<");
    for (const e of API_TREE) {
      expect(html).toContain(e.id);
    }
  });
});
