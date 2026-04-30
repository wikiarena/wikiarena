import { describe, expect, it } from "bun:test";

import {
  buildSolverLinkUrl,
  normalizeSolverLinkPathMode,
  readSolverLinkParams,
} from "./solver-link.ts";

describe("solver link params", () => {
  it("reads start, target, and path mode from the URL query", () => {
    const params = readSolverLinkParams(
      "?start=Yu%20ssi%20samdaerok&target=2009%20California%20League%20season&mode=all",
    );

    expect(params).toEqual({
      startTitle: "Yu ssi samdaerok",
      targetTitle: "2009 California League season",
      pathMode: "all_shortest",
    });
  });

  it("supports shorter aliases for shared links", () => {
    expect(readSolverLinkParams("?from=Start&to=Target&path_mode=1")).toEqual({
      startTitle: "Start",
      targetTitle: "Target",
      pathMode: "single",
    });
    expect(normalizeSolverLinkPathMode("all_shortest")).toBe("all_shortest");
  });

  it("ignores incomplete pairs", () => {
    expect(readSolverLinkParams("?start=Only%20one%20title")).toBeNull();
    expect(readSolverLinkParams("?target=Only%20one%20title")).toBeNull();
  });

  it("serializes the current solved pair as a canonical share URL", () => {
    expect(
      buildSolverLinkUrl(
        "https://wikiarena.org/solver?old=1#results",
        {
          startTitle: "Yu ssi samdaerok",
          targetTitle: "2009 California League season",
        },
        "all_shortest",
      ),
    ).toBe(
      "https://wikiarena.org/solver?start=Yu+ssi+samdaerok&target=2009+California+League+season&mode=all_shortest#results",
    );
  });
});
