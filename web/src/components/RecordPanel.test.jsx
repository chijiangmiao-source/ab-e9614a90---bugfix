import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import RecordPanel from "./RecordPanel.jsx";

// 「双层环裁决」样例的可复算记录（字段与后端 POST /api/solve 返回一致）。
const RECORD = {
  levels: [
    {
      depth: 0,
      nodes: ["v0", "v1", "v2", "v3", "v4"],
      chosen: [
        { node: "v1", channel: "e02", cost: 3 },
        { node: "v2", channel: "e11", cost: 1 },
        { node: "v3", channel: "e05", cost: 1 },
        { node: "v4", channel: "e08", cost: 5 },
      ],
      cycle: {
        supernode: "S1",
        nodes: ["v1", "v3"],
        channels: ["e05", "e02"],
        rewired_in: [
          { channel: "e09", from: "v4", to: "v3", original_cost: 2, adjusted_cost: 1, enters: "v3" },
        ],
        dropped_internal: [],
      },
    },
    {
      depth: 1,
      nodes: ["S1", "v0", "v2", "v4"],
      chosen: [
        { node: "S1", channel: "e09", cost: 1 },
        { node: "v2", channel: "e11", cost: 1 },
        { node: "v4", channel: "e08", cost: 5 },
      ],
      cycle: {
        supernode: "S2",
        nodes: ["S1", "v4"],
        channels: ["e08", "e09"],
        rewired_in: [
          { channel: "e00", from: "v0", to: "v4", original_cost: 8, adjusted_cost: 3, enters: "v4" },
        ],
        dropped_internal: ["e07"],
      },
    },
    {
      depth: 2,
      nodes: ["S2", "v0", "v2"],
      chosen: [
        { node: "S2", channel: "e00", cost: 3 },
        { node: "v2", channel: "e11", cost: 1 },
      ],
      cycle: null,
    },
  ],
  expansions: [
    {
      supernode: "S2",
      entering_channel: "e00",
      enters_node: "v4",
      removed_cycle_channel: "e08",
      kept_cycle_channels: ["e09"],
    },
    {
      supernode: "S1",
      entering_channel: "e09",
      enters_node: "v3",
      removed_cycle_channel: "e05",
      kept_cycle_channels: ["e02"],
    },
  ],
};

describe("<RecordPanel /> 双层环裁决记录", () => {
  it("依次展示内层、外层两次收缩与两次展开替换", () => {
    const html = renderToStaticMarkup(
      <RecordPanel record={RECORD} selectedItem={null} onSelect={() => {}} />
    );
    // 两次环收缩：先内层 S1（v1→v3），再外层 S2（S1↔v4）
    expect(html).toContain("环收缩 → S1");
    expect(html).toContain("环收缩 → S2");
    expect(html.indexOf("环收缩 → S1")).toBeLessThan(html.indexOf("环收缩 → S2"));
    // 丢弃的环内非环边
    expect(html).toContain("e07");
    // 两次展开：外层先（e00 替换 e08，保留 e09），内层后（e09 替换 e05，保留 e02）
    expect(html).toContain("展开 S2");
    expect(html).toContain("展开 S1");
    expect(html).toContain("e00");
    expect(html).toContain("e08");
    expect(html).toContain("e09");
    expect(html).toContain("e05");
    expect(html).toContain("e02");
  });
});
