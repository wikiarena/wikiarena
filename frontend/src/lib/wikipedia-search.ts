export interface WikipediaSearchResult {
  title: string;
  description: string;
}

interface CachedSearchResult {
  results: WikipediaSearchResult[];
  timestampMs: number;
}

export class WikipediaSearchService {
  private readonly cache = new Map<string, CachedSearchResult>();
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
