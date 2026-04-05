import { describe, expect, it } from "bun:test";
import { readFileSync } from "node:fs";

const stylesheet = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

function readFillValueForRule(selector) {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const ruleMatch = stylesheet.match(new RegExp(`${escapedSelector}\\s*\\{([\\s\\S]*?)\\}`, "m"));
  if (ruleMatch === null) {
    throw new Error(`Could not find style rule for ${selector}`);
  }

  const fillDeclarationMatch = ruleMatch[1].match(/fill:\s*([^;]+);/);
  if (fillDeclarationMatch === null) {
    throw new Error(`Could not find fill declaration for ${selector}`);
  }

  return fillDeclarationMatch[1].trim();
}

describe("path graph hover styles", () => {
  it("keeps highlighted node centers opaque so edges do not bleed through", () => {
    for (const selector of [
      ".path-graph-node.is-active .path-graph-node-circle",
      ".path-graph-node.is-neighbor .path-graph-node-circle",
    ]) {
      const fillValue = readFillValueForRule(selector);

      expect(fillValue).not.toMatch(/^rgba\(/);
      expect(fillValue).not.toBe("transparent");
    }
  });
});
