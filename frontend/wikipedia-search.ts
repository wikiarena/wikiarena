interface WikipediaSearchResult {
    title: string;
    description: string;
    url: string;
}

interface SearchCache {
    [query: string]: {
        results: WikipediaSearchResult[];
        timestamp: number;
    };
}

class WikipediaSearchService {
    private cache: SearchCache = {};
    private abortController: AbortController | null = null;
    private readonly CACHE_DURATION = 5 * 60 * 1000; // 5 minutes
    private readonly MIN_QUERY_LENGTH = 2;
    private readonly MAX_RESULTS = 8;

    /**
     * Search Wikipedia using the OpenSearch API
     */
    async search(query: string): Promise<WikipediaSearchResult[]> {
        // Validate query
        if (!query || query.trim().length < this.MIN_QUERY_LENGTH) {
            return [];
        }

        const trimmedQuery = query.trim();

        // Check cache first
        const cached = this.getCachedResults(trimmedQuery);
        if (cached) {
            return cached;
        }

        // Cancel previous request
        if (this.abortController) {
            this.abortController.abort();
        }

        // Create new abort controller
        this.abortController = new AbortController();

        try {
            const response = await fetch(
                `https://en.wikipedia.org/w/api.php?action=opensearch&search=${encodeURIComponent(trimmedQuery)}&limit=${this.MAX_RESULTS}&format=json&origin=*`,
                {
                    signal: this.abortController.signal,
                    headers: {
                        'Accept': 'application/json',
                    }
                }
            );

            if (!response.ok) {
                throw new Error(`Wikipedia API error: ${response.status}`);
            }

            const data = await response.json();
            
            // OpenSearch format: [query, [titles], [descriptions], [urls]]
            const [searchTerm, titles, descriptions, urls] = data;
            
            const results: WikipediaSearchResult[] = titles
                .map((title: string, index: number) => ({
                    title,
                    description: descriptions[index] || '',
                    url: urls[index] || `https://en.wikipedia.org/wiki/${encodeURIComponent(title)}`
                }))
                .filter((result: WikipediaSearchResult) => {
                    // Filter out obvious fake/echo results, but be conservative
                    // to avoid removing legitimate pages
                    const normalizedTitle = result.title.toLowerCase().trim();
                    const normalizedQuery = trimmedQuery.toLowerCase().trim();
                    
                    // Only filter out disambiguation pages that are exact matches
                    // and explicitly mention disambiguation
                    if (normalizedTitle === normalizedQuery && 
                        result.description && 
                        (result.description.includes('may refer to') || 
                         result.description.toLowerCase().includes('disambiguation'))) {
                        return false;
                    }
                    
                    // Filter out obviously invalid results (empty titles, malformed URLs)
                    if (!result.title.trim() || 
                        !result.url || 
                        !result.url.includes('wikipedia.org')) {
                        return false;
                    }
                    
                    return true;
                });

            // Cache the results
            this.cacheResults(trimmedQuery, results);

            return results;
        } catch (error) {
            if (error instanceof Error && error.name === 'AbortError') {
                // Request was cancelled, return empty results
                return [];
            }
            
            console.error('Wikipedia search error:', error);
            return [];
        }
    }

    /**
     * Check if we have cached results for this query
     */
    private getCachedResults(query: string): WikipediaSearchResult[] | null {
        const cached = this.cache[query.toLowerCase()];
        
        if (!cached) {
            return null;
        }

        // Check if cache is still valid
        const now = Date.now();
        if (now - cached.timestamp > this.CACHE_DURATION) {
            delete this.cache[query.toLowerCase()];
            return null;
        }

        return cached.results;
    }

    /**
     * Cache search results
     */
    private cacheResults(query: string, results: WikipediaSearchResult[]): void {
        this.cache[query.toLowerCase()] = {
            results,
            timestamp: Date.now()
        };

        // Clean up old cache entries to prevent memory leaks
        this.cleanupCache();
    }

    /**
     * Remove expired cache entries
     */
    private cleanupCache(): void {
        const now = Date.now();
        const entries = Object.entries(this.cache);
        
        // If we have too many entries, clean up
        if (entries.length > 100) {
            for (const [query, cached] of entries) {
                if (now - cached.timestamp > this.CACHE_DURATION) {
                    delete this.cache[query];
                }
            }
        }
    }

    /**
     * Cancel any ongoing search requests
     */
    cancelCurrentSearch(): void {
        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }
    }

    /**
     * Clear the search cache
     */
    clearCache(): void {
        this.cache = {};
    }

    /**
     * Validate if a page title exists on Wikipedia
     */
    async validatePage(title: string): Promise<boolean> {
        try {
            const response = await fetch(
                `https://en.wikipedia.org/w/api.php?action=query&titles=${encodeURIComponent(title)}&format=json&origin=*`
            );
            
            const data = await response.json();
            const pages = data.query?.pages;
            
            if (!pages) return false;
            
            // Check if any page exists (not missing)
            return Object.values(pages).some((page: any) => !page.missing);
        } catch (error) {
            console.error('Page validation error:', error);
            return false;
        }
    }
}

export { WikipediaSearchService, type WikipediaSearchResult }; 