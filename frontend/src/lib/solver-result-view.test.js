import { describe, expect, it } from "bun:test";

import {
  getSolverResultTitle,
  getSolverResultView,
} from "./solver-result-view.ts";

describe("solver result view", () => {
  it("uses the timeline only for single-path mode", () => {
    expect(getSolverResultView("single")).toBe("timeline");
    expect(getSolverResultTitle("single")).toBe("Shortest Path");
  });

  it("uses the graph for all-paths mode even when only one path is returned", () => {
    expect(getSolverResultView("all_shortest")).toBe("graph");
    expect(getSolverResultTitle("all_shortest")).toBe("Shortest Paths");
  });
});
