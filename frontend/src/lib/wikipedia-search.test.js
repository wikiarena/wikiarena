import { afterEach, describe, expect, it, mock } from "bun:test";

import { WikipediaSearchService } from "./wikipedia-search.ts";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("WikipediaSearchService", () => {
  it("resolves redirect titles to canonical article titles", async () => {
    globalThis.fetch = mock(async () => {
      return {
        ok: true,
        json: async () => ({
          query: {
            redirects: [
              {
                from: "USA",
                to: "United States",
              },
            ],
            pages: [
              {
                title: "United States",
              },
            ],
          },
        }),
      };
    });

    const service = new WikipediaSearchService();
    const resolution = await service.resolveTitle("USA");

    expect(resolution).toEqual({
      requestedTitle: "USA",
      canonicalTitle: "United States",
      isValid: true,
      isRedirect: true,
    });
  });

  it("marks missing titles as invalid", async () => {
    globalThis.fetch = mock(async () => {
      return {
        ok: true,
        json: async () => ({
          query: {
            pages: [
              {
                title: "Made Up Article",
                missing: true,
              },
            ],
          },
        }),
      };
    });

    const service = new WikipediaSearchService();
    const resolution = await service.resolveTitle("Made Up Article");

    expect(resolution).toEqual({
      requestedTitle: "Made Up Article",
      canonicalTitle: null,
      isValid: false,
      isRedirect: false,
    });
  });
});
