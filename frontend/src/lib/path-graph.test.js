import { describe, expect, it } from "bun:test";
import { readFileSync } from "node:fs";

const stylesheet = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

function readRuleDeclarations(selector) {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const ruleMatch = stylesheet.match(new RegExp(`${escapedSelector}\\s*\\{([\\s\\S]*?)\\}`, "m"));
  if (ruleMatch === null) {
    throw new Error(`Could not find style rule for ${selector}`);
  }

  return ruleMatch[1];
}

function readDeclarationValueForRule(selector, propertyName) {
  const declarations = readRuleDeclarations(selector);
  const escapedPropertyName = propertyName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const declarationMatch = declarations.match(new RegExp(`${escapedPropertyName}:\\s*([^;]+);`));
  if (declarationMatch === null) {
    throw new Error(`Could not find ${propertyName} declaration for ${selector}`);
  }

  return declarationMatch[1].trim();
}

function readFillValueForRule(selector) {
  const fillDeclarationMatch = readRuleDeclarations(selector).match(/fill:\s*([^;]+);/);
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

describe("path graph clipping styles", () => {
  it("lets solved results grow past very long shortest paths", () => {
    expect(readDeclarationValueForRule(".results-panel.is-visible", "max-height")).toBe("none");
    expect(readDeclarationValueForRule(".results-panel.is-visible", "overflow")).toBe("visible");
  });

  it("does not crop tall graph content inside the horizontal scroll shell", () => {
    expect(readDeclarationValueForRule(".path-graph-shell", "overflow-y")).toBe("visible");
  });
});
