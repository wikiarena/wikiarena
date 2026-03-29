export interface WikipediaSearchResult {
  title: string;
  description: string;
}

export interface WikipediaTitleResolution {
  requestedTitle: string;
  canonicalTitle: string | null;
  isValid: boolean;
  isRedirect: boolean;
}

interface CachedSearchResult {
  results: WikipediaSearchResult[];
  timestampMs: number;
}

interface CachedTitleResolution {
  resolution: WikipediaTitleResolution;
  timestampMs: number;
}

export class WikipediaSearchService {
  private readonly cache = new Map<string, CachedSearchResult>();
  private readonly resolutionCache = new Map<string, CachedTitleResolution>();
  private readonly cacheDurationMs = 5 * 60 * 1000;
  private readonly maxResults = 6;
  private abortController: AbortController | null = null;

  async search(query: string): Promise<WikipediaSearchResult[]> {
    const normalizedQuery = query.trim();
    if (normalizedQuery.length < 2) {
      return [];
    }

    const cached = this.getCached(normalizedQuery);
    if (cached !== null) {
      return cached;
    }

    if (this.abortController !== null) {
      this.abortController.abort();
    }

    this.abortController = new AbortController();

    try {
      const response = await fetch(
        `https://en.wikipedia.org/w/api.php?action=opensearch&search=${encodeURIComponent(normalizedQuery)}&limit=${this.maxResults}&format=json&origin=*`,
        {
          signal: this.abortController.signal,
          headers: {
            Accept: "application/json",
          },
        },
      );

      if (!response.ok) {
        throw new Error(`Wikipedia search failed with status ${response.status}`);
      }

      const payload = (await response.json()) as [string, string[], string[], string[]];
      const [, titles, descriptions] = payload;
      const results = titles
        .map((title, index) => ({
          title,
          description: descriptions[index] ?? "",
        }))
        .filter((result) => result.title.trim().length > 0);

      this.cache.set(normalizedQuery.toLowerCase(), {
        results,
        timestampMs: Date.now(),
      });
      return results;
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        return [];
      }
      return [];
    }
  }

  cancel(): void {
    this.abortController?.abort();
    this.abortController = null;
  }

  async validatePage(title: string): Promise<boolean> {
    const resolution = await this.resolveTitle(title);
    return resolution.isValid;
  }

  async resolveTitle(title: string): Promise<WikipediaTitleResolution> {
    const normalizedTitle = title.trim();
    if (!normalizedTitle) {
      return {
        requestedTitle: normalizedTitle,
        canonicalTitle: null,
        isValid: true,
        isRedirect: false,
      };
    }

    const cachedResolution = this.resolutionCache.get(normalizedTitle.toLowerCase());
    if (
      cachedResolution !== undefined &&
      Date.now() - cachedResolution.timestampMs <= this.cacheDurationMs
    ) {
      return cachedResolution.resolution;
    }

    try {
      const response = await fetch(
        `https://en.wikipedia.org/w/api.php?action=query&titles=${encodeURIComponent(normalizedTitle)}&redirects=1&format=json&formatversion=2&origin=*`,
        {
          headers: {
            Accept: "application/json",
          },
        },
      );

      if (!response.ok) {
        throw new Error(`Wikipedia validation failed with status ${response.status}`);
      }

      const payload = (await response.json()) as {
        query?: {
          redirects?: Array<{
            from?: string;
            to?: string;
          }>;
          pages?: Array<{
            title?: string;
            missing?: boolean;
          }>;
        };
      };

      const firstPage = (payload.query?.pages ?? []).find((page) => page.missing !== true);
      const canonicalTitle = firstPage?.title?.trim() || null;
      const resolution = {
        requestedTitle: normalizedTitle,
        canonicalTitle,
        isValid: canonicalTitle !== null,
        isRedirect: (payload.query?.redirects?.length ?? 0) > 0,
      };

      this.resolutionCache.set(normalizedTitle.toLowerCase(), {
        resolution,
        timestampMs: Date.now(),
      });
      return resolution;
    } catch {
      return {
        requestedTitle: normalizedTitle,
        canonicalTitle: null,
        isValid: false,
        isRedirect: false,
      };
    }
  }

  private getCached(query: string): WikipediaSearchResult[] | null {
    const cachedEntry = this.cache.get(query.toLowerCase());
    if (cachedEntry === undefined) {
      return null;
    }

    if (Date.now() - cachedEntry.timestampMs > this.cacheDurationMs) {
      this.cache.delete(query.toLowerCase());
      return null;
    }

    return cachedEntry.results;
  }
}
